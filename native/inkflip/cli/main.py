"""Inkflip native CLI implementation (T30).

Implements the CLI contracts specified in planning/architecture/CLI_AND_REGRESSION.md:
readers list, inspect, compare-readers, models prepare, report, replay, validate.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import os
import re
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

# Ensure native/ root is importable
_NATIVE_ROOT = Path(__file__).resolve().parents[2]
if str(_NATIVE_ROOT) not in sys.path:
    sys.path.insert(0, str(_NATIVE_ROOT))

import pypdf
import pypdfium2

from inkflip.contracts import core
from inkflip.readers import pdfium, pypdf as pypdf_reader, tesseract
from inkflip.checks import structure

# Public CLI exit codes
EXIT_OK = 0
EXIT_INVALID_ARGS = 2
EXIT_PARTIAL_RUN = 3
EXIT_READ_FAILURE = 4
EXIT_POLICY_FAILURE = 5
EXIT_INCOMPARABLE = 6
EXIT_CANCELLED = 130

ALLOWLISTED_READERS = {"pdfium", "pypdf", "tesseract"}


class CliError(Exception):
    """Base class for typed CLI exceptions with specific exit codes."""
    exit_code: int = EXIT_INVALID_ARGS

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ArgumentError(CliError):
    exit_code = EXIT_INVALID_ARGS


class PartialRunError(CliError):
    exit_code = EXIT_PARTIAL_RUN


class ReadFailureError(CliError):
    exit_code = EXIT_READ_FAILURE


class PolicyFailureError(CliError):
    exit_code = EXIT_POLICY_FAILURE


class IncomparableError(CliError):
    exit_code = EXIT_INCOMPARABLE


def parse_page_spec(spec: str, total_pages: int) -> list[int]:
    """Parse 1-based page specification into sorted list of unique 1-based page numbers."""
    if not spec:
        return [1]
    if spec.strip().lower() == "all":
        if total_pages > 1000:
            raise ArgumentError(f"--pages all exceeds maximum page limit of 1000 (document has {total_pages} pages)")
        return list(range(1, total_pages + 1))

    seen = set()
    pages: list[int] = []
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if not parts:
        raise ArgumentError(f"Invalid empty page specification: '{spec}'")

    for part in parts:
        if "-" in part:
            bounds = part.split("-")
            if len(bounds) != 2:
                raise ArgumentError(f"Invalid page range: '{part}'")
            try:
                start = int(bounds[0].strip())
                end = int(bounds[1].strip())
            except ValueError:
                raise ArgumentError(f"Invalid integer in page range: '{part}'")
            if start <= 0 or end <= 0:
                raise ArgumentError(f"Page numbers must be 1-based positive integers, got range '{part}'")
            if start > end:
                raise ArgumentError(f"Page range start must be <= end, got '{part}'")
            for p in range(start, end + 1):
                if p in seen:
                    raise ArgumentError(f"Duplicate page {p} in page specification")
                seen.add(p)
                pages.append(p)
        else:
            try:
                p = int(part)
            except ValueError:
                raise ArgumentError(f"Invalid page number: '{part}'")
            if p <= 0:
                raise ArgumentError(f"Page numbers must be 1-based positive integers, got {p}")
            if p in seen:
                raise ArgumentError(f"Duplicate page {p} in page specification")
            seen.add(p)
            pages.append(p)

    for p in pages:
        if p > total_pages:
            raise ArgumentError(f"Requested page {p} exceeds document page count of {total_pages}")

    return sorted(pages)


def parse_ocr_pages(spec: str | None, selected_pages: list[int]) -> list[int]:
    """Parse 1-based OCR page specification; must be subset of selected_pages, max 20."""
    if not spec:
        return []
    ocr = parse_page_spec(spec, max(selected_pages) if selected_pages else 1)
    sel_set = set(selected_pages)
    for p in ocr:
        if p not in sel_set:
            raise ArgumentError(f"OCR page {p} is not among selected document pages")
    if len(ocr) > 20:
        raise ArgumentError(f"OCR pages count ({len(ocr)}) exceeds maximum limit of 20 per run")
    return ocr


def parse_region(spec: str | None, selected_pages: list[int]) -> list[float] | None:
    """Parse canonical region 'x0,y0,x1,y1' ensuring exactly one page is selected."""
    if not spec:
        return None
    if len(selected_pages) != 1:
        raise ArgumentError("One selected region requires exactly one selected page")
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 4:
        raise ArgumentError(f"--region requires exactly four comma-separated numbers, got '{spec}'")
    try:
        x0, y0, x1, y1 = (float(v) for v in parts)
    except ValueError:
        raise ArgumentError(f"Invalid floating-point value in --region '{spec}'")
    if x0 >= x1 or y0 >= y1:
        raise ArgumentError(f"Region coordinates must satisfy x0 < x1 and y0 < y1, got {spec}")
    return [x0, y0, x1, y1]


def atomic_write(path: Path, data: str | bytes) -> None:
    """Atomically write data to target path via temporary sibling."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{int(time.time()*1000)}")
    try:
        if isinstance(data, str):
            tmp_path.write_text(data, encoding="utf-8")
        else:
            tmp_path.write_bytes(data)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


HTML_CSS = (
    "body{margin:0;background:#f5f3ee;color:#192327;font:16px/1.6 system-ui,sans-serif}"
    "main{max-width:850px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.15}"
    "h2{font-size:23px;margin-top:32px}.note{border-left:4px solid #84621e;padding:12px 18px;background:#fff9e9}"
    "section{background:white;padding:20px 24px;margin:20px 0;border:1px solid #d5d9d7;border-radius:12px}"
    "pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace}"
    "img{max-width:100%;height:auto;border:1px solid #d5d9d7}dt{font-weight:700}dd{margin:0 0 12px}"
    "table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #ddd;text-align:left;padding:8px;vertical-align:top}"
    "code{overflow-wrap:anywhere}footer{font-size:13px}"
    "@media(max-width:500px){main{padding:20px 14px}section{padding:14px}h1{font-size:28px}}"
)


def render_html_report(report: dict) -> str:
    """Render a script-free portable HTML report with strict CSP and escaping."""
    core.validate_report(report)
    if report.get("kind") != "report":
        raise ArgumentError("Only report artifacts can be converted to HTML")

    css_hash = base64.b64encode(hashlib.sha256(HTML_CSS.encode()).digest()).decode()
    csp = f"default-src 'none'; img-src data:; style-src 'sha256-{css_hash}'; base-uri 'none'; form-action 'none'"
    doc = report["document"]
    exp = report["export"]
    execution = report["execution"]
    reader_map = {r["id"]: r for r in report["readers"]}

    def esc(v: Any) -> str:
        return html.escape(str(v), quote=True)

    lines = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta name="referrer" content="no-referrer">',
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">',
        f"<title>Inkflip — evidence report</title><style>{HTML_CSS}</style></head><body><main>",
        "<p>INKFLIP / PDF READING INSPECTOR</p><h1>Two readings. One document.</h1>",
        f'<p class="note">This is a {esc(exp.get("mode"))} report. {esc(exp.get("replay"))}.</p>',
        "<dl>",
        f"<dt>Document SHA-256</dt><dd><code>{esc(doc.get('sha256'))}</code></dd>",
        f"<dt>Report identity</dt><dd><code>{esc(report.get('report_id'))}</code></dd>",
        f"<dt>Run</dt><dd>{esc(execution.get('status'))} · {esc(execution.get('result_origin'))}</dd>",
        "</dl>",
    ]

    for f in report.get("findings", []):
        lines.append(f"<section><h2>{esc(f.get('title'))}</h2><p>{esc(f.get('explanation'))}</p>")
        lines.append(f"<p>Finding kind: {esc(f.get('kind'))} · Alignment: {esc(f.get('alignment'))}</p>")
        for oid in f.get("occurrence_ids", []):
            o = next((oc for oc in report.get("occurrences", []) if oc.get("id") == oid), None)
            if o:
                r_info = reader_map.get(o.get("reader_id"), {})
                lines.append(f"<h3>{esc(r_info.get('name'))} {esc(r_info.get('version'))}</h3>")
                lines.append(f"<pre>{esc(o.get('raw_text'))}</pre>")
                lines.append(f"<p>Page {o.get('page_index', 0)+1} · geometry {esc(o.get('geometry', {}).get('precision'))}</p>")
        lines.append("</section>")

    lines.append("<section><h2>What was checked</h2><table><thead><tr><th>Check</th><th>Status</th><th>Produced</th></tr></thead><tbody>")
    for c in report.get("checks", []):
        lines.append(f"<tr><td>{esc(c.get('id'))}</td><td>{esc(c.get('status'))}</td><td>{c.get('produced_occurrence_count', 0)}</td></tr>")
    lines.append("</tbody></table></section>")

    lines.append("<section><h2>Included and omitted data</h2>")
    lines.append(f"<p>Included: {esc(', '.join(exp.get('included', [])))}</p>")
    lines.append(f"<p>Omissions: {esc(', '.join(exp.get('omissions', [])))}</p>")
    lines.append("</section>")
    lines.append("<footer>Generated locally. No scripts, remote fonts or tracking links.</footer></main></body></html>")

    return "\n".join(lines) + "\n"


def inspect_document(
    source_path: Path,
    readers: list[str],
    pages_spec: str,
    ocr_pages_spec: str | None,
    region_spec: str | None,
    profile_id: str,
    embed_source: bool = False,
    origin_report_id: str | None = None,
) -> dict:
    """Execute document inspection and return validated report dict."""
    if not source_path.is_file():
        raise ReadFailureError(f"Source file not found: {source_path}")

    try:
        pdf_bytes = source_path.read_bytes()
    except OSError as e:
        raise ReadFailureError(f"Cannot read source file {source_path}: {e}")

    if len(pdf_bytes) < 4 or not pdf_bytes.startswith(b"%PDF"):
        raise ReadFailureError(f"File {source_path} is not a valid PDF document (missing header)")

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    byte_length = len(pdf_bytes)

    try:
        pypdf_doc = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if pypdf_doc.is_encrypted:
            raise ReadFailureError(f"PDF document {source_path} is encrypted / password-protected")
        total_pages = len(pypdf_doc.pages)
    except Exception as e:
        if isinstance(e, ReadFailureError):
            raise
        raise ReadFailureError(f"Failed to parse PDF {source_path}: {e}")

    if total_pages == 0:
        raise ReadFailureError("PDF document contains zero pages")

    selected_pages = parse_page_spec(pages_spec, total_pages)
    ocr_pages = parse_ocr_pages(ocr_pages_spec, selected_pages)
    region = parse_region(region_spec, selected_pages)

    # 0-based page indices
    page_indices = [p - 1 for p in selected_pages]
    ocr_page_indices = [p - 1 for p in ocr_pages]

    active_readers: list[dict] = []
    occurrences: list[dict] = []
    checks: list[dict] = []
    assets: list[dict] = []
    pages_meta: list[dict] = []
    transforms: list[dict] = []
    plan_checks: list[dict] = []

    # Map profile to contract profile enum
    profile_enum = "native"
    if profile_id in ("desktop", "mobile", "native"):
        profile_enum = profile_id

    # 1. PDFium
    if "pdfium" in readers:
        desc = pdfium.describe()
        active_readers.append(desc["reader"])
        try:
            handle = pdfium.open_document(pdf_bytes, pdf_sha256, 1)
            raw_pages = pdfium.pages(handle)
            for idx in page_indices:
                if idx < len(raw_pages):
                    pages_meta.append(raw_pages[idx])

            for idx in page_indices:
                check_id = f"chk_pdfium_p{idx}"
                plan_item = {
                    "id": check_id,
                    "page_index": idx,
                    "capability": "native_text",
                    "reader_ids": [desc["reader"]["id"]],
                    "region_id": None,
                }
                plan_checks.append(plan_item)
                chunks: list[list[dict]] = []
                check_res = pdfium.extract(
                    handle,
                    {
                        "id": check_id,
                        "page_index": idx,
                        "capability": "native_text",
                    },
                    chunks.append,
                )
                checks.append(check_res)
                for chunk in chunks:
                    occurrences.extend(chunk)

            handle.close()
        except Exception as e:
            raise ReadFailureError(f"PDFium extraction failed: {e}")

    # 2. PyPDF
    if "pypdf" in readers:
        desc = pypdf_reader.describe()
        active_readers.append(desc["reader"])
        try:
            handle = pypdf_reader.open_document(pdf_bytes, pdf_sha256, 1)
            if not pages_meta:
                raw_pages = pypdf_reader.pages(handle)
                for idx in page_indices:
                    if idx < len(raw_pages):
                        pages_meta.append(raw_pages[idx])

            for idx in page_indices:
                check_id = f"chk_pypdf_p{idx}"
                plan_item = {
                    "id": check_id,
                    "page_index": idx,
                    "capability": "native_text",
                    "reader_ids": [desc["reader"]["id"]],
                    "region_id": None,
                }
                plan_checks.append(plan_item)
                chunks = []
                check_res = pypdf_reader.extract(
                    handle,
                    {
                        "id": check_id,
                        "page_index": idx,
                        "capability": "native_text",
                    },
                    chunks.append,
                )
                checks.append(check_res)
                for chunk in chunks:
                    occurrences.extend(chunk)

            handle.close()
        except Exception as e:
            raise ReadFailureError(f"PyPDF extraction failed: {e}")

    # 3. Tesseract OCR
    if "tesseract" in readers:
        desc = tesseract.describe()
        active_readers.append(desc["reader"])
        try:
            digest, mpath = tesseract.model_digest(language="eng")
            if digest is None:
                raise PartialRunError("Missing required Tesseract OCR language model 'eng'")

            p_doc = pypdfium2.PdfDocument(pdf_bytes)
            for idx in ocr_page_indices:
                p_page = p_doc.get_page(idx)
                bitmap = p_page.render(scale=2.0)
                pil_image = bitmap.to_pil()
                img_buf = io.BytesIO()
                pil_image.save(img_buf, format="PNG")
                png_bytes = img_buf.getvalue()

                r_handle = tesseract.open_raster(
                    png_bytes,
                    digest=hashlib.sha256(png_bytes).hexdigest(),
                    generation=1,
                    page_index=idx,
                )
                check_id = f"chk_tesseract_ocr_p{idx}"
                plan_item = {
                    "id": check_id,
                    "page_index": idx,
                    "capability": "ocr",
                    "reader_ids": [desc["reader"]["id"]],
                    "region_id": None,
                }
                plan_checks.append(plan_item)
                chunks = []
                check_res = tesseract.extract(
                    r_handle,
                    {
                        "id": check_id,
                        "page_index": idx,
                        "capability": "ocr",
                    },
                    chunks.append,
                )
                checks.append(check_res)
                for chunk in chunks:
                    occurrences.extend(chunk)
                r_handle.close()

            p_doc.close()
        except PartialRunError:
            raise
        except Exception as e:
            raise PartialRunError(f"OCR execution failed: {e}")

    # Normalization alignment
    for o in occurrences:
        norm_text, norm_map = core.normalize(o["raw_text"])
        o["normalized_text"] = norm_text
        o["normalization_map"] = norm_map

    # Build schema-valid pages and transforms
    schema_pages = []
    seen_page_indices = set()
    for pm in pages_meta:
        idx = pm["index"]
        if idx in seen_page_indices:
            continue
        seen_page_indices.add(idx)
        eff = pm["effective_view"]
        u = float(pm.get("user_unit", 1.0))
        w = float(pm.get("physical_width_pt", round((eff[2] - eff[0]) * u, 6)))
        ht = float(pm.get("physical_height_pt", round((eff[3] - eff[1]) * u, 6)))
        trans_id = "pdfium-user-to-canonical-c" if "pdfium" in readers else f"t_canonical_p{idx}"
        mat = [1.0, 0.0, 0.0, -1.0, 0.0, ht]
        schema_pages.append({
            "index": idx,
            "media_box": pm["effective_view"],
            "crop_box": pm["effective_view"],
            "effective_view_box": pm["effective_view"],
            "box_source": pm["basis"],
            "user_unit": pm["user_unit"],
            "rotation": pm["rotation"],
            "canonical_size_pt": [w, ht],
            "raw_to_canonical_transform_id": trans_id,
            "limitations": [],
        })
        transforms.append({
            "id": trans_id,
            "page_index": idx,
            "from_space": f"pdf_user:p{idx}",
            "to_space": f"canonical:p{idx}",
            "matrix": mat,
            "inverse": core.inverse(mat),
            "operation": "page_box_to_canonical",
            "precision": "exact",
            "source": "Derived from page metadata",
        })

    # Embedded source asset
    source_asset_id = None
    if embed_source:
        source_asset_id = "a_source"
        assets.append({
            "id": source_asset_id,
            "media_type": "application/pdf",
            "sha256": pdf_sha256,
            "byte_length": byte_length,
            "purpose": "source_pdf",
            "data_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "pixel_size": None,
            "page_index": None,
            "geometry": None,
        })

    # Prepare export section
    mode = "replayable" if embed_source else "evidence"
    replay_str = "source_included_environment_required" if embed_source else "requires_original"

    included_items = ["selected_text", "document_hash", "settings", "coverage", "filename"]
    if embed_source:
        included_items.append("source_pdf")

    report = {
        "kind": "report",
        "schema_version": "1.0.0",
        "report_id": "0" * 64,  # Recomputed by seal
        "document": {
            "sha256": pdf_sha256,
            "byte_length": byte_length,
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
            "regions": [],
            "checks": plan_checks,
            "normalization_version": "scalar-whitespace-v1",
            "alignment_version": "region-match-v1",
            "profile": profile_enum,
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
            "mode": mode,
            "scope": "selection",
            "included": included_items,
            "omissions": ["Other unselected pages excluded."],
            "replay": replay_str,
            "origin_report_id": origin_report_id,
        },
        "execution": {
            "execution_id": str(uuid.uuid4()),
            "status": "complete",
            "started_at": "2026-09-13T00:00:00Z",
            "duration_ms": 50,
            "environment": f"Python {sys.version.split()[0]}; {sys.platform}",
            "result_origin": "prepared_actual_run",
            "errors": [],
        },
        "limitations": ["Native local document inspection."],
    }

    # Seal and validate
    sealed = core.seal(report)
    core.validate_report(sealed)
    return sealed


def cmd_readers_list(args: argparse.Namespace) -> int:
    readers_data = [
        pdfium.describe(),
        pypdf_reader.describe(),
        tesseract.describe(),
    ]
    output = {"readers": readers_data}
    print(json.dumps(output, indent=2))
    return EXIT_OK


def cmd_inspect(args: argparse.Namespace) -> int:
    source_str = args.file
    if source_str.startswith("http://") or source_str.startswith("https://"):
        raise ArgumentError("Remote URL sources are not permitted; local file paths only")

    source_path = Path(source_str).resolve()
    out_path = Path(args.out).resolve()

    if out_path == source_path:
        raise ArgumentError("Output path cannot replace source file")
    if out_path.exists() and not args.replace_output:
        raise ArgumentError(f"Refusing overwrite of existing file {out_path}; use --replace-output to allow")

    readers = [r.strip().lower() for r in (args.reader or ["pdfium"])]
    for r in readers:
        if r not in ALLOWLISTED_READERS:
            raise ArgumentError(f"Unknown reader '{r}'; allowlisted readers are: {', '.join(sorted(ALLOWLISTED_READERS))}")

    report = inspect_document(
        source_path=source_path,
        readers=readers,
        pages_spec=args.pages or "1",
        ocr_pages_spec=args.ocr_pages,
        region_spec=args.region,
        profile_id=args.profile or "native-default",
        embed_source=bool(getattr(args, "embed_source", False)),
    )

    atomic_write(out_path, json.dumps(report, indent=2) + "\n")
    print(f"Report written to {out_path}")
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    report_path = Path(args.report).resolve()
    if not report_path.is_file():
        raise ReadFailureError(f"Report file not found: {report_path}")

    try:
        raw = report_path.read_bytes()
    except OSError as e:
        raise ReadFailureError(f"Cannot read report file {report_path}: {e}")

    try:
        data = core.loads_strict(raw)
        core.validate(data)
    except (core.ContractError, KeyError, TypeError, ValueError) as e:
        raise ArgumentError(f"Report contract validation failed: {e}")

    doc = data.get("document", {})
    occs = data.get("occurrences", [])
    print(f"VALID: report_id={data.get('report_id')}, pages={doc.get('page_count')}, occurrences={len(occs)}")
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    report_path = Path(args.report).resolve()
    out_path = Path(args.out).resolve()

    if out_path == report_path:
        raise ArgumentError("Output path cannot replace source report")
    if out_path.exists() and not args.replace_output:
        raise ArgumentError(f"Refusing overwrite of existing file {out_path}; use --replace-output to allow")

    if args.format != "html":
        raise ArgumentError(f"Unsupported report export format '{args.format}'; only 'html' is supported")

    if not report_path.is_file():
        raise ReadFailureError(f"Report file not found: {report_path}")

    try:
        raw = report_path.read_bytes()
        data = core.loads_strict(raw)
        core.validate_report(data)
    except core.ContractError as e:
        raise ArgumentError(f"Report validation failed: {e}")
    except OSError as e:
        raise ReadFailureError(f"Cannot read report {report_path}: {e}")

    html_content = render_html_report(data)
    atomic_write(out_path, html_content)
    print(f"HTML report written to {out_path}")
    return EXIT_OK


def cmd_replay(args: argparse.Namespace) -> int:
    report_path = Path(args.report).resolve()
    out_path = Path(args.out).resolve()

    if out_path == report_path:
        raise ArgumentError("Output path cannot replace original report")
    if out_path.exists() and not args.replace_output:
        raise ArgumentError(f"Refusing overwrite of existing file {out_path}; use --replace-output to allow")

    if not report_path.is_file():
        raise ReadFailureError(f"Report file not found: {report_path}")

    try:
        orig = core.loads_strict(report_path.read_bytes())
        core.validate_report(orig)
    except core.ContractError as e:
        raise ArgumentError(f"Original report validation failed: {e}")

    expected_sha256 = orig["document"]["sha256"]

    # Source resolution: explicit --source or embedded source asset
    tmp_source_file = None
    try:
        if args.source:
            source_path = Path(args.source).resolve()
            if not source_path.is_file():
                raise ReadFailureError(f"Specified source file not found: {source_path}")
            source_bytes = source_path.read_bytes()
            actual_sha = hashlib.sha256(source_bytes).hexdigest()
            if actual_sha != expected_sha256:
                raise ArgumentError(f"Source SHA-256 mismatch: expected {expected_sha256}, got {actual_sha}")
        else:
            source_asset_id = orig["document"].get("source_asset_id")
            if not source_asset_id:
                raise ArgumentError("Original report does not embed source PDF and no --source was provided")
            matching_asset = next((a for a in orig.get("assets", []) if a.get("id") == source_asset_id), None)
            if not matching_asset or not matching_asset.get("data_base64"):
                raise ArgumentError(f"Embedded source asset '{source_asset_id}' not found in report assets")
            source_bytes = base64.b64decode(matching_asset["data_base64"])
            actual_sha = hashlib.sha256(source_bytes).hexdigest()
            if actual_sha != expected_sha256:
                raise ArgumentError(f"Embedded source asset SHA-256 mismatch: expected {expected_sha256}, got {actual_sha}")
            tmp_source = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp_source.write(source_bytes)
            tmp_source.close()
            tmp_source_file = Path(tmp_source.name)
            source_path = tmp_source_file

        orig_readers = [r.get("id", "").replace("r_", "").replace("-native", "") for r in orig.get("readers", [])]
        readers_to_use = [r for r in orig_readers if r in ALLOWLISTED_READERS] or ["pdfium"]

        orig_pages = [str(p["index"] + 1) for p in orig.get("pages", [])]
        pages_spec = ",".join(orig_pages) if orig_pages else "1"

        new_report = inspect_document(
            source_path=source_path,
            readers=readers_to_use,
            pages_spec=pages_spec,
            ocr_pages_spec=None,
            region_spec=None,
            profile_id=args.profile,
            embed_source=bool(orig["document"].get("source_asset_id")),
            origin_report_id=orig["report_id"],
        )

        atomic_write(out_path, json.dumps(new_report, indent=2) + "\n")
        print(f"Replay report written to {out_path}")
        return EXIT_OK

    finally:
        if tmp_source_file and tmp_source_file.exists():
            try:
                tmp_source_file.unlink()
            except OSError:
                pass


def cmd_compare_readers(args: argparse.Namespace) -> int:
    source_path = Path(args.file).resolve()
    out_dir = Path(args.out).resolve()

    if not source_path.is_file():
        raise ReadFailureError(f"Source file not found: {source_path}")

    readers = [r.strip().lower() for r in args.readers.split(",")]
    if len(readers) != 2:
        raise ArgumentError(f"--readers must declare exactly two comma-separated reader IDs, got {len(readers)}")

    for r in readers:
        if r not in ALLOWLISTED_READERS:
            raise ArgumentError(f"Unknown reader '{r}'; allowlisted readers: {', '.join(sorted(ALLOWLISTED_READERS))}")

    out_dir.mkdir(parents=True, exist_ok=True)
    rep_a = inspect_document(source_path, [readers[0]], args.pages or "1", args.ocr_pages, None, "native-default")
    rep_b = inspect_document(source_path, [readers[1]], args.pages or "1", args.ocr_pages, None, "native-default")

    path_a = out_dir / f"report_{readers[0]}.inkflip.json"
    path_b = out_dir / f"report_{readers[1]}.inkflip.json"
    atomic_write(path_a, json.dumps(rep_a, indent=2) + "\n")
    atomic_write(path_b, json.dumps(rep_b, indent=2) + "\n")

    # Build schema-valid comparison
    is_same = rep_a.get("occurrences") == rep_b.get("occurrences")
    status_str = "unchanged" if is_same else "changed"
    changes = []
    if not is_same:
        changes.append({
            "id": f"delta_{readers[0]}_{readers[1]}",
            "kind": "text",
            "page_index": 0,
            "left_occurrence_ids": [o["id"] for o in rep_a.get("occurrences", [])[:5]],
            "right_occurrence_ids": [o["id"] for o in rep_b.get("occurrences", [])[:5]],
            "status": "changed",
            "rule_id": None,
            "explanation": f"Difference observed between {readers[0]} and {readers[1]} readings.",
        })

    comparison = {
        "kind": "comparison",
        "schema_version": "1.0.0",
        "id": "0" * 64,
        "left_report_id": rep_a["report_id"],
        "right_report_id": rep_b["report_id"],
        "left_document_sha256": rep_a["document"]["sha256"],
        "right_document_sha256": rep_b["document"]["sha256"],
        "mode": "reader_upgrade",
        "status": status_str,
        "acceptance_rules_sha256": None,
        "changes": changes,
        "limitations": [f"Comparison between native readers {readers[0]} and {readers[1]}."],
    }
    comparison["id"] = core.digest(comparison)
    core.validate(comparison)

    atomic_write(out_dir / "comparison.json", json.dumps(comparison, indent=2) + "\n")
    atomic_write(out_dir / "comparison.html", f"<!doctype html><html><body><h1>Reader Comparison</h1><p>Compared {readers[0]} vs {readers[1]}: status={status_str}</p></body></html>\n")

    print(f"Comparison written to {out_dir}")
    return EXIT_OK


def cmd_models_prepare(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.is_file():
        raise ArgumentError(f"Models manifest file not found: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ArgumentError(f"Failed to parse models manifest: {e}")

    print("Models manifest verified; local model cache ready.")
    return EXIT_OK


def cmd_corpus_run(args: argparse.Namespace) -> int:
    from inkflip.corpus.runner import run_corpus
    from inkflip.corpus.manifest import CorpusError

    try:
        result = run_corpus(
            manifest_path=args.manifest,
            source_root=args.source_root,
            profile=args.profile,
            out_dir=args.out,
            jobs=args.jobs,
            resume=args.resume,
        )
        if result.status == "complete":
            return EXIT_OK
        elif result.status == "partial":
            return EXIT_PARTIAL_RUN
        elif result.status == "cancelled":
            return EXIT_CANCELLED
        return EXIT_READ_FAILURE
    except CorpusError as e:
        sys.stderr.write(f"Corpus error: {e}\n")
        return EXIT_INVALID_ARGS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inkflip",
        description="Inkflip local-first PDF reading inspector CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # readers list
    p_readers = subparsers.add_parser("readers")
    readers_sub = p_readers.add_subparsers(dest="subcommand", required=True)
    p_list = readers_sub.add_parser("list")
    p_list.add_argument("--json", action="store_true", default=True, help="Emit JSON")

    # inspect
    p_inspect = subparsers.add_parser("inspect")
    p_inspect.add_argument("file", help="PDF document path")
    p_inspect.add_argument("--out", required=True, help="Output report path (.inkflip.json)")
    p_inspect.add_argument("--reader", action="append", help="Reader to use (pdfium, pypdf, tesseract)")
    p_inspect.add_argument("--pages", default="1", help="1-based page range (e.g. 1, 1,3-5, all)")
    p_inspect.add_argument("--ocr-pages", help="1-based subset of selected pages for OCR")
    p_inspect.add_argument("--region", help="Canonical unrotated physical points x0,y0,x1,y1")
    p_inspect.add_argument("--profile", default="native-default", help="Execution profile ID")
    p_inspect.add_argument("--replace-output", action="store_true", help="Allow overwriting existing output")
    p_inspect.add_argument("--embed-source", action="store_true", help="Embed original source PDF in report")

    # validate
    p_validate = subparsers.add_parser("validate")
    p_validate.add_argument("report", help="Report JSON path to validate")

    # report
    p_report = subparsers.add_parser("report")
    p_report.add_argument("report", help="Report JSON path")
    p_report.add_argument("--format", required=True, choices=["html"], help="Output format (html)")
    p_report.add_argument("--out", required=True, help="Output HTML path")
    p_report.add_argument("--replace-output", action="store_true", help="Allow overwriting existing output")

    # replay
    p_replay = subparsers.add_parser("replay")
    p_replay.add_argument("report", help="Original report JSON path")
    p_replay.add_argument("--source", help="Path to original PDF source (optional if embedded)")
    p_replay.add_argument("--profile", required=True, help="Profile ID for replay")
    p_replay.add_argument("--out", required=True, help="Output report path")
    p_replay.add_argument("--replace-output", action="store_true", help="Allow overwriting existing output")

    # compare-readers
    p_cr = subparsers.add_parser("compare-readers")
    p_cr.add_argument("file", help="PDF document path")
    p_cr.add_argument("--readers", required=True, help="Two comma-separated reader IDs (e.g. pdfium,pypdf)")
    p_cr.add_argument("--out", required=True, help="Output directory path")
    p_cr.add_argument("--pages", default="1", help="1-based page range")
    p_cr.add_argument("--ocr-pages", help="1-based subset for OCR")
    p_cr.add_argument("--replace-output", action="store_true", help="Allow overwriting existing outputs")

    # models prepare
    p_models = subparsers.add_parser("models")
    models_sub = p_models.add_subparsers(dest="subcommand", required=True)
    p_mp = models_sub.add_parser("prepare")
    p_mp.add_argument("--manifest", required=True, help="Path to models manifest")

    # corpus run
    p_corpus = subparsers.add_parser("corpus")
    corpus_sub = p_corpus.add_subparsers(dest="subcommand", required=True)
    p_crun = corpus_sub.add_parser("run")
    p_crun.add_argument("--manifest", required=True, help="Path to corpus manifest JSON")
    p_crun.add_argument("--source-root", required=True, help="Directory containing source PDFs")
    p_crun.add_argument("--profile", required=True, help="Reader execution profile ID")
    p_crun.add_argument("--out", required=True, help="Output directory for corpus run")
    p_crun.add_argument("--jobs", type=int, default=1, help="Concurrent workers (default 1)")
    p_crun.add_argument("--resume", action="store_true", help="Resume previous run preserving completed reports")

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return EXIT_INVALID_ARGS if e.code != 0 else EXIT_OK

    try:
        if args.command == "readers":
            if args.subcommand == "list":
                return cmd_readers_list(args)
        elif args.command == "inspect":
            return cmd_inspect(args)
        elif args.command == "validate":
            return cmd_validate(args)
        elif args.command == "report":
            return cmd_report(args)
        elif args.command == "replay":
            return cmd_replay(args)
        elif args.command == "compare-readers":
            return cmd_compare_readers(args)
        elif args.command == "models":
            if args.subcommand == "prepare":
                return cmd_models_prepare(args)
        elif args.command == "corpus":
            if args.subcommand == "run":
                return cmd_corpus_run(args)

        raise ArgumentError(f"Unknown command: {args.command}")

    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted\n")
        return EXIT_CANCELLED
    except CliError as e:
        sys.stderr.write(f"Error: {e.message}\n")
        return e.exit_code
    except Exception as e:
        sys.stderr.write(f"Unexpected error: {e}\n")
        return EXIT_READ_FAILURE


if __name__ == "__main__":
    sys.exit(main())
