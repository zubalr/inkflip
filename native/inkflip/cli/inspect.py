"""Inspect/replay report construction against native readers and named profiles."""
from __future__ import annotations

import base64
import hashlib
import io
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pypdf

from inkflip.cli.pages import (
    PageSpecError,
    parse_ocr_pages,
    parse_page_spec,
    parse_region,
    polygon_intersects_region,
    region_to_polygon,
)
from inkflip.contracts import core
from inkflip.profiles import (
    BUILTIN_PROFILE_NAMES,
    ProfileAdapter,
    ProfileBlockedError,
    ProfileError,
    ProfileNotFoundError,
    UntrustedProfileError,
    default_profiles_dir,
    load_profile,
)
from inkflip.readers import pdfium, pypdf as pypdf_reader, tesseract
from inkflip.runtime.artifacts import atomic_write_bytes

ALLOWLISTED_READERS = {"pdfium", "pypdf", "tesseract"}
# planning/config/settings.json native.max_file_bytes — fail closed before allocating.
NATIVE_MAX_FILE_BYTES = 104_857_600
NATIVE_MAX_OUTPUT_BYTES = 67_108_864
READER_MODULES = {
    "pdfium": pdfium,
    "pypdf": pypdf_reader,
    "tesseract": tesseract,
}
ALGORITHM_ID = "inkflip-inspect-v1"
PDFIUM_TRANSFORM_PLACEHOLDER = "pdfium-user-to-canonical-c"


class InspectError(Exception):
    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _page_transform_id(index: int) -> str:
    return f"t_raw_to_canonical_p{index}"


def _check_id(reader_key: str, page_index: int, capability: str) -> str:
    suffix = "ocr" if capability == "ocr" else "text"
    return f"chk_{reader_key}_{suffix}_p{page_index}"


def _rewrite_transform_ids(occurrence: dict, page_index: int) -> None:
    geometry = occurrence.get("geometry") or {}
    ids = list(geometry.get("transform_ids") or [])
    rewritten = []
    for ident in ids:
        if ident == PDFIUM_TRANSFORM_PLACEHOLDER:
            rewritten.append(_page_transform_id(page_index))
        else:
            rewritten.append(ident)
    geometry["transform_ids"] = rewritten
    occurrence["geometry"] = geometry


def _normalize_occurrence(occurrence: dict) -> None:
    raw = occurrence.get("raw_text") or ""
    normalized, mapping = core.normalize(raw)
    occurrence["normalized_text"] = normalized
    occurrence["normalization_map"] = mapping


def _canonical_page(meta: dict, transform_id: str) -> dict:
    view = [float(v) for v in meta["effective_view"]]
    user_unit = float(meta.get("user_unit") or 1.0)
    if user_unit <= 0:
        user_unit = 1.0
    width = round((view[2] - view[0]) * user_unit, 6)
    height = round((view[3] - view[1]) * user_unit, 6)
    rotation = int(meta.get("rotation") or 0) % 360
    if rotation not in (0, 90, 180, 270):
        rotation = 0
    return {
        "index": meta["index"],
        "media_box": list(view),
        "crop_box": list(view),
        "effective_view_box": list(view),
        "box_source": meta.get("basis") or "page dictionary",
        "user_unit": user_unit,
        "rotation": rotation,
        "canonical_size_pt": [width, height],
        "raw_to_canonical_transform_id": transform_id,
        "limitations": [],
    }


def _canonical_transform(page: dict) -> dict:
    user_unit = page["user_unit"]
    view = page["effective_view_box"]
    matrix = [user_unit, 0.0, 0.0, -user_unit, -user_unit * view[0], user_unit * view[3]]
    return {
        "id": page["raw_to_canonical_transform_id"],
        "page_index": page["index"],
        "from_space": f"pdf_user:p{page['index']}",
        "to_space": f"canonical:p{page['index']}",
        "matrix": matrix,
        "inverse": core.inverse(matrix),
        "operation": "page_box_to_canonical",
        "precision": "exact",
        "source": "Derived from page crop box and /UserUnit",
    }


def _collect_pages(pdf_bytes: bytes, digest: str, indices: list[int]) -> list[dict]:
    handle = pdfium.open_document(pdf_bytes, digest, 1)
    try:
        metas = pdfium.pages(handle)
    finally:
        handle.close()
    pages = []
    for index in indices:
        if index >= len(metas):
            raise InspectError(f"Page index {index} is outside the document", 2)
        transform_id = _page_transform_id(index)
        pages.append(_canonical_page(metas[index], transform_id))
    return pages


def _extract_builtin(
    module,
    reader_key: str,
    pdf_bytes: bytes,
    digest: str,
    page_indices: list[int],
    capability: str,
    region_id: str | None,
    emit_hook: Callable[[list[dict]], None] | None = None,
) -> tuple[dict, list[dict], list[dict], list[dict]]:
    reader = module.describe()["reader"]
    handle = module.open_document(pdf_bytes, digest, 1)
    occurrences: list[dict] = []
    checks: list[dict] = []
    plans: list[dict] = []
    try:
        for index in page_indices:
            check_id = _check_id(reader_key, index, capability)
            plan = {
                "id": check_id,
                "page_index": index,
                "capability": capability,
                "reader_ids": [reader["id"]],
                "region_id": None,
            }
            plans.append(plan)
            chunks: list[list[dict]] = []
            result = module.extract(
                handle,
                {
                    "id": check_id,
                    "page_index": index,
                    "capability": capability,
                    "reader_ids": [reader["id"]],
                    "region_id": None,
                },
                chunks.append,
            )
            page_occs = [item for chunk in chunks for item in chunk]
            for occ in page_occs:
                _rewrite_transform_ids(occ, index)
                _normalize_occurrence(occ)
            if emit_hook:
                emit_hook(page_occs)
            occurrences.extend(page_occs)
            checks.append(result)
    finally:
        handle.close()
    return reader, plans, checks, occurrences


def _extract_tesseract(
    pdf_bytes: bytes,
    digest: str,
    ocr_indices: list[int],
    region: list[float] | None,
) -> tuple[dict, list[dict], list[dict], list[dict]]:
    desc = tesseract.describe()
    reader = desc["reader"]
    capability_reason: str | None = None
    model_digest = None
    try:
        model_digest, _trained = tesseract.model_digest(language="eng")
    except tesseract.AdapterError as error:
        if "executable not found" in error.detail or error.reason == "unsupported":
            capability_reason = f"missing_binary: {error.detail}"
        else:
            capability_reason = f"{error.reason}: {error.detail}"
    plans: list[dict] = []
    checks: list[dict] = []
    occurrences: list[dict] = []
    import pypdfium2

    pdf_doc = pypdfium2.PdfDocument(pdf_bytes)
    try:
        for index in ocr_indices:
            check_id = _check_id("tesseract", index, "ocr")
            plans.append(
                {
                    "id": check_id,
                    "page_index": index,
                    "capability": "ocr",
                    "reader_ids": [reader["id"]],
                    "region_id": "region_selected" if region else None,
                }
            )
            if capability_reason and "missing_binary" in capability_reason:
                checks.append(
                    {
                        "id": check_id,
                        "status": "unsupported",
                        "reason": capability_reason,
                        "produced_occurrence_count": 0,
                        "retained_occurrence_ids": [],
                    }
                )
                continue
            if model_digest is None:
                checks.append(
                    {
                        "id": check_id,
                        "status": "failed",
                        "reason": capability_reason
                        or "missing_model: eng.traineddata is unavailable",
                        "produced_occurrence_count": 0,
                        "retained_occurrence_ids": [],
                    }
                )
                continue
            page = pdf_doc.get_page(index)
            bitmap = page.render(scale=2.0)
            pil_image = bitmap.to_pil()
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG")
            png_bytes = buf.getvalue()
            page.close()
            raster = tesseract.open_raster(
                png_bytes,
                digest=hashlib.sha256(png_bytes).hexdigest(),
                generation=1,
                render_meta={"raster_scale_px_per_pt": 2.0},
            )
            try:
                chunks: list[list[dict]] = []
                result = tesseract.extract(
                    raster,
                    {
                        "id": check_id,
                        "page_index": index,
                        "capability": "ocr",
                        "reader_ids": [reader["id"]],
                        "region_id": None,
                    },
                    chunks.append,
                )
                page_occs = [item for chunk in chunks for item in chunk]
                for occ in page_occs:
                    _normalize_occurrence(occ)
                occurrences.extend(page_occs)
                checks.append(result)
            finally:
                raster.close()
    finally:
        pdf_doc.close()
    return reader, plans, checks, occurrences


def _extract_profile(
    profile,
    source_path: Path,
    page_indices: list[int],
) -> tuple[dict, list[dict], list[dict], list[dict], dict]:
    adapter = ProfileAdapter(profile)
    described = adapter.describe()
    reader = described["reader"]
    extracted = adapter.extract(source_path, page_indices)
    identity = {
        "interpreter": extracted.get("interpreter") or described.get("interpreter"),
        "version": extracted.get("pypdf_version")
        or extracted.get("pdfjs_version")
        or reader.get("version"),
        "profile_name": profile.name,
        "profile_sha256": profile.profile_sha256,
        "reader": profile.reader,
    }
    actual_version = identity["version"]
    if actual_version and actual_version != profile.version:
        raise InspectError(
            f"Installed reader version {actual_version} does not match profile {profile.version}",
            2,
        )
    pages = extracted.get("pages") or []
    plans: list[dict] = []
    checks: list[dict] = []
    occurrences: list[dict] = []
    for page_index in page_indices:
        record = next((item for item in pages if item.get("page_index") == page_index), None)
        check_id = _check_id(profile.reader.replace("-", ""), page_index, "native_text")
        plans.append(
            {
                "id": check_id,
                "page_index": page_index,
                "capability": "native_text",
                "reader_ids": [reader["id"]],
                "region_id": None,
            }
        )
        if record is None:
            checks.append(
                {
                    "id": check_id,
                    "status": "failed",
                    "reason": "profile worker omitted the requested page",
                    "produced_occurrence_count": 0,
                    "retained_occurrence_ids": [],
                }
            )
            continue
        status = record.get("status") or "completed"
        reason = record.get("reason")
        raw_text = record.get("raw_text")
        retained: list[str] = []
        if status == "completed" and isinstance(raw_text, str):
            digest12 = hashlib.sha256(source_path.read_bytes()).hexdigest()[:12]
            occ_id = f"{reader['id']}-{digest12}-p{page_index}-0".replace("_", "-")[:96]
            occurrence = {
                "id": occ_id,
                "reader_id": reader["id"],
                "page_index": page_index,
                "ordinal": 0,
                "raw_text": raw_text,
                "normalized_text": raw_text,
                "normalization_map": [],
                "geometry": {
                    "precision": "page_only",
                    "space": "canonical_page",
                    "polygon": None,
                    "transform_ids": [],
                    "basis": f"{profile.reader} isolated worker page-level output",
                },
                "engine_score": None,
                "source_asset_id": None,
                "raw_source_locator": f"{profile.reader}:page[{page_index}]:extract",
                "limitations": ["page-only extraction from isolated profile worker"],
            }
            _normalize_occurrence(occurrence)
            occurrences.append(occurrence)
            retained = [occ_id]
        elif status == "completed" and raw_text is None:
            status = "failed"
            reason = reason or "extraction failed without retained text"
        checks.append(
            {
                "id": check_id,
                "status": status if status in {
                    "completed", "unsupported", "timeout", "cancelled", "failed", "skipped"
                } else "failed",
                "reason": reason,
                "produced_occurrence_count": len(retained),
                "retained_occurrence_ids": retained,
            }
        )
    return reader, plans, checks, occurrences, identity


def _apply_region_filter(
    region: list[float] | None,
    region_id: str | None,
    occurrences: list[dict],
    checks: list[dict],
    plans: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    if not region:
        return occurrences, checks, plans
    kept_ids: set[str] = set()
    filtered = []
    for occ in occurrences:
        geometry = occ.get("geometry") or {}
        if polygon_intersects_region(geometry.get("polygon"), region):
            filtered.append(occ)
            kept_ids.add(occ["id"])
    id_map = {check["id"]: check for check in checks}
    for plan in plans:
        if plan.get("capability") == "native_text":
            plan["region_id"] = region_id
        check = id_map.get(plan["id"])
        if check is None:
            continue
        retained = [oid for oid in check.get("retained_occurrence_ids", []) if oid in kept_ids]
        check["retained_occurrence_ids"] = retained
        check["produced_occurrence_count"] = len(retained)
    return filtered, checks, plans


def _execution_status(checks: list[dict]) -> tuple[str, int, list[str]]:
    statuses = [check["status"] for check in checks]
    errors = [check["reason"] for check in checks if check.get("reason")]
    if any(status == "cancelled" for status in statuses):
        return "cancelled", 130, errors
    completed = all(status == "completed" for status in statuses)
    if completed:
        return "complete", 0, errors
    if all(status in {"failed", "timeout"} for status in statuses):
        return "failed", 4, errors
    return "partial", 3, errors


def resolve_named_profile(profile_id: str):
    if profile_id in BUILTIN_PROFILE_NAMES:
        return None
    try:
        return load_profile(profile_id, base_dir=default_profiles_dir())
    except ProfileNotFoundError as exc:
        raise InspectError(str(exc), 2) from exc
    except ProfileBlockedError as exc:
        raise InspectError(str(exc), 3) from exc
    except UntrustedProfileError as exc:
        raise InspectError(str(exc), 2) from exc
    except ProfileError as exc:
        raise InspectError(str(exc), 2) from exc


def inspect_document(
    source_path: Path,
    readers: list[str],
    pages_spec: str,
    ocr_pages_spec: str | None,
    region_spec: str | None,
    profile_id: str,
    embed_source: bool = False,
    origin_report_id: str | None = None,
    expected_sha256: str | None = None,
    required_reader_versions: dict[str, str] | None = None,
) -> tuple[dict, int]:
    if not source_path.is_file():
        raise InspectError(f"Source file not found: {source_path}", 4)
    try:
        source_size = source_path.stat().st_size
    except OSError as exc:
        raise InspectError(f"Cannot stat source file {source_path}: {exc}", 4) from exc
    if source_size > NATIVE_MAX_FILE_BYTES:
        raise InspectError(
            f"Source exceeds native.max_file_bytes {NATIVE_MAX_FILE_BYTES} (got {source_size})",
            5,
        )
    try:
        pdf_bytes = source_path.read_bytes()
    except OSError as exc:
        raise InspectError(f"Cannot read source file {source_path}: {exc}", 4) from exc
    if len(pdf_bytes) < 4 or not pdf_bytes.startswith(b"%PDF"):
        raise InspectError(f"File {source_path} is not a valid PDF document (missing header)", 4)
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    if expected_sha256 and expected_sha256 != pdf_sha256:
        raise InspectError(
            f"Source SHA-256 mismatch: expected {expected_sha256}, got {pdf_sha256}",
            2,
        )
    try:
        pypdf_doc = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if pypdf_doc.is_encrypted:
            raise InspectError(f"PDF document {source_path} is encrypted / password-protected", 4)
        total_pages = len(pypdf_doc.pages)
    except InspectError:
        raise
    except Exception as exc:
        raise InspectError(f"Failed to parse PDF {source_path}: {exc}", 4) from exc
    if total_pages == 0:
        raise InspectError("PDF document contains zero pages", 4)

    try:
        selected_pages = parse_page_spec(pages_spec, total_pages)
        ocr_pages = parse_ocr_pages(ocr_pages_spec, selected_pages)
        region = parse_region(region_spec, selected_pages)
    except PageSpecError as exc:
        raise InspectError(str(exc), 2) from exc

    page_indices = [page - 1 for page in selected_pages]
    ocr_indices = [page - 1 for page in ocr_pages]
    named_profile = resolve_named_profile(profile_id)
    if named_profile is None and profile_id not in BUILTIN_PROFILE_NAMES:
        raise InspectError(f"Unknown profile {profile_id!r}", 2)

    schema_pages = _collect_pages(pdf_bytes, pdf_sha256, page_indices)
    transforms = [_canonical_transform(page) for page in schema_pages]
    plan_profile = profile_id if profile_id in {"desktop", "mobile", "native"} else "native"

    active_readers: list[dict] = []
    occurrences: list[dict] = []
    checks: list[dict] = []
    plan_checks: list[dict] = []
    identity: dict[str, Any] = {
        "profile_name": profile_id,
        "profile_sha256": None,
        "algorithm": ALGORITHM_ID,
    }

    region_id = "region_selected" if region else None
    regions = []
    if region:
        page_index = page_indices[0]
        regions.append(
            {
                "id": region_id,
                "page_index": page_index,
                "geometry": {
                    "precision": "exact",
                    "space": "canonical_page",
                    "polygon": region_to_polygon(region),
                    "transform_ids": [_page_transform_id(page_index)],
                    "basis": "operator-selected canonical unrotated physical region",
                },
                "label": f"selected region {region[0]},{region[1]},{region[2]},{region[3]}",
            }
        )

    if named_profile is not None:
        reader, plans, chk, occs, identity_extra = _extract_profile(
            named_profile, source_path, page_indices
        )
        identity.update(identity_extra)
        active_readers.append(reader)
        plan_checks.extend(plans)
        checks.extend(chk)
        occurrences.extend(occs)
        if required_reader_versions:
            expected = required_reader_versions.get(reader["id"]) or required_reader_versions.get(
                named_profile.reader
            )
            if expected and expected != reader["version"]:
                raise InspectError(
                    f"Replay refused: reader version mismatch for {reader['id']} "
                    f"(recorded {expected}, installed {reader['version']})",
                    2,
                )
    else:
        selected_readers = [name.strip().lower() for name in readers] or ["pdfium"]
        for name in selected_readers:
            if name not in ALLOWLISTED_READERS:
                raise InspectError(
                    f"Unknown reader {name!r}; allowlisted readers are: "
                    f"{', '.join(sorted(ALLOWLISTED_READERS))}",
                    2,
                )
        if "tesseract" in selected_readers and not ocr_indices:
            raise InspectError(
                "--reader tesseract requires explicit --ocr-pages; raster source is PDFium",
                2,
            )
        for name in selected_readers:
            if name == "tesseract":
                reader, plans, chk, occs = _extract_tesseract(
                    pdf_bytes, pdf_sha256, ocr_indices, region
                )
            else:
                reader, plans, chk, occs = _extract_builtin(
                    READER_MODULES[name],
                    name,
                    pdf_bytes,
                    pdf_sha256,
                    page_indices,
                    "native_text",
                    region_id,
                )
            active_readers.append(reader)
            plan_checks.extend(plans)
            checks.extend(chk)
            occurrences.extend(occs)
            if required_reader_versions:
                expected = required_reader_versions.get(reader["id"]) or required_reader_versions.get(name)
                if expected and expected != reader["version"]:
                    raise InspectError(
                        f"Replay refused: reader version mismatch for {reader['id']} "
                        f"(recorded {expected}, installed {reader['version']})",
                        2,
                    )

    occurrences, checks, plan_checks = _apply_region_filter(
        region, region_id, occurrences, checks, plan_checks
    )

    assets: list[dict] = []
    source_asset_id = None
    if embed_source:
        source_asset_id = "a_source"
        assets.append(
            {
                "id": source_asset_id,
                "media_type": "application/pdf",
                "sha256": pdf_sha256,
                "byte_length": len(pdf_bytes),
                "purpose": "source_pdf",
                "data_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                "pixel_size": None,
                "page_index": None,
                "geometry": None,
            }
        )

    included = ["selected_text", "document_hash", "settings", "coverage", "filename"]
    if embed_source:
        included.append("source_pdf")
    env_parts = [
        f"Python {sys.version.split()[0]}",
        sys.platform,
        f"algorithm={ALGORITHM_ID}",
        f"profile_name={identity.get('profile_name')}",
    ]
    if identity.get("profile_sha256"):
        env_parts.append(f"profile_sha256={identity['profile_sha256']}")
    if identity.get("version"):
        env_parts.append(f"reader_version={identity['version']}")
    if identity.get("interpreter"):
        env_parts.append(f"interpreter={identity['interpreter']}")
    environment = "; ".join(env_parts)[:1000]

    report = {
        "kind": "report",
        "schema_version": "1.0.0",
        "report_id": "0" * 64,
        "document": {
            "sha256": pdf_sha256,
            "byte_length": len(pdf_bytes),
            "page_count": total_pages,
            "display_name": source_path.name,
            "source_asset_id": source_asset_id,
        },
        "readers": active_readers,
        "pages": schema_pages,
        "transforms": transforms,
        "occurrences": occurrences,
        "findings": [],
        "annotations": [],
        "plan": {
            "version": "1.0.0",
            "selected_pages": page_indices,
            "regions": regions,
            "checks": plan_checks,
            "normalization_version": "scalar-whitespace-v1",
            "alignment_version": "region-match-v1",
            "profile": plan_profile,
            "budget": {
                "max_raster_pixels": 4000000,
                "max_run_ocr_pixels": 20000000,
                "timeout_ms": 120000,
                "max_retries": 0,
            },
        },
        "checks": checks,
        "assets": assets,
        "export": {
            "mode": "replayable" if embed_source else "evidence",
            "scope": "selection",
            "included": included,
            "omissions": ["Other unselected pages excluded."],
            "replay": "source_included_environment_required" if embed_source else "requires_original",
            "origin_report_id": origin_report_id,
        },
        "execution": {
            "execution_id": str(uuid.uuid4()),
            "run_key": "0" * 64,
            "status": "complete",
            "started_at": _utcnow(),
            "duration_ms": 1,
            "environment": environment,
            "result_origin": "prepared_actual_run",
            "errors": [],
        },
        "limitations": [
            "Native local document inspection.",
            f"algorithm {ALGORITHM_ID}",
        ],
    }

    exec_status, exit_code, errors = _execution_status(checks)
    report["execution"]["status"] = exec_status
    report["execution"]["errors"] = [err for err in errors if err][:100]
    sealed = core.seal(report)
    core.validate(sealed)
    import json as _json

    encoded = (_json.dumps(sealed, indent=2) + "\n").encode("utf-8")
    if len(encoded) > NATIVE_MAX_OUTPUT_BYTES:
        raise InspectError(
            f"Report exceeds native.max_output_bytes_per_file {NATIVE_MAX_OUTPUT_BYTES} "
            f"(got {len(encoded)})",
            5,
        )
    return sealed, exit_code


def write_report(path: Path, report: dict) -> None:
    import json

    payload = (json.dumps(report, indent=2) + "\n").encode("utf-8")
    if len(payload) > NATIVE_MAX_OUTPUT_BYTES:
        raise InspectError(
            f"Report exceeds native.max_output_bytes_per_file {NATIVE_MAX_OUTPUT_BYTES} "
            f"(got {len(payload)})",
            5,
        )
    atomic_write_bytes(path, payload)
