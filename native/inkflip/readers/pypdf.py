"""Native pypdf text reader adapter (T26).

Implements the independent page-level text path over the frozen
``pypdf==6.18.0``, per ``planning/architecture/READER_ADAPTER_CONTRACT.md``:

* pypdf extraction is page-only. This adapter emits one occurrence per page
  with the page's raw extraction output and ``page_only`` geometry (null
  polygon). It never claims per-word locations and never combines its text
  with PDFium boxes by string matching.
* Visitor matrices are not used; no precise geometry is derived here.
* Encrypted and malformed documents become typed failures; a missing password
  is a distinct reason string, and no partial text escapes a failed page.

Immutable input bytes are read from memory only. All calls are single-threaded
in the calling process; handles close deterministically and idempotently.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import io
import re
from pathlib import Path
from typing import Callable

import pypdf

READER_ID = "pypdf-native"
ADAPTER_VERSION = "1.0.0"
MAX_CHARS_PER_PAGE = 200_000
MAX_OCCURRENCES_PER_CHUNK = 256


class AdapterError(Exception):
    """Typed open-time failure carrying a public reason code."""

    def __init__(self, reason: str, detail: str):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


class PypdfHandle:
    """Bounded document handle over immutable bytes."""

    def __init__(self, data: bytes, digest: str, generation: int):
        self.data = data
        self.digest = digest
        self.generation = generation
        self._reader = pypdf.PdfReader(io.BytesIO(data))
        self.closed = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._reader = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _version() -> str:
    return importlib.metadata.version("pypdf")


def _distribution_digest() -> str | None:
    """SHA-256 of the installed pypdf wheel metadata, when locatable."""
    try:
        dist = importlib.metadata.distribution("pypdf")
    except importlib.metadata.PackageNotFoundError:
        return None
    metadata_path = getattr(dist, "_path", None)
    if metadata_path is None:
        return None
    metadata_file = Path(metadata_path) / "METADATA"
    if metadata_file.is_file():
        return hashlib.sha256(metadata_file.read_bytes()).hexdigest()
    return None


def describe() -> dict:
    """Complete reader manifest (schema $defs/Reader + ReaderManifest)."""
    distribution_digest = _distribution_digest()
    return {
        "kind": "reader_manifest",
        "schema_version": "1.0.0",
        "reader": {
            "id": READER_ID,
            "name": "pypdf",
            "version": _version(),
            "build": f"pypdf {_version()} (pure Python)",
            "adapter_version": ADAPTER_VERSION,
            "method": "native_text",
            "environment": "native",
            "settings": {
                "normalization": "scalar-whitespace-v1",
                "language": None,
                "psm": None,
                "render_reader_id": None,
                "raster_dpi": None,
                "annotation_mode": "not_applicable",
            },
            "capabilities": [
                {
                    "name": "native_text",
                    "support": "supported",
                    "limits": [
                        "page-level text only; no per-word geometry is claimed or "
                        "derived from visitor matrices",
                        "text from this reader is never combined with PDFium boxes "
                        "by string matching",
                    ],
                },
                {
                    "name": "crop_metadata",
                    "support": "approximate",
                    "limits": [
                        "declared page dictionaries (media/crop box, /UserUnit, "
                        "/Rotate) are parsed for other adapters' compensation; "
                        "metadata is separate from extraction"
                    ],
                },
            ],
            "model_hashes": [],
            "limitations": [
                "in-process adapter; child-process supervision belongs to the "
                "native parent task",
            ],
        },
        "distribution_digest": distribution_digest,
        "asset_hashes": [],
        "execution_policy": "installed_allowlist_no_report_commands",
    }


def open_document(data: bytes, digest: str | None, generation: int) -> PypdfHandle:
    """Open immutable bytes into a bounded handle; typed failures only."""
    if not isinstance(data, bytes) or not data:
        raise AdapterError("parser_error", "document bytes missing or empty")
    computed = hashlib.sha256(data).hexdigest()
    if digest is not None and digest != computed:
        raise AdapterError("parser_error", "document digest mismatch")
    try:
        return PypdfHandle(data, computed, generation)
    except pypdf.errors.PdfReadError as error:
        detail = str(error)
        if "password" in detail.lower() or "encrypt" in detail.lower():
            raise AdapterError("parser_error", "encrypted document requires a password") from error
        raise AdapterError("parser_error", "document failed to parse") from error
    except Exception as error:
        raise AdapterError("parser_error", "document failed to parse") from error


def pages(handle: PypdfHandle) -> list[dict]:
    """Declared page dictionaries: count, boxes, UserUnit and rotation."""
    if handle.closed:
        raise AdapterError("parser_error", "handle is closed")
    out = []
    for index, page in enumerate(handle._reader.pages):
        crop = page.cropbox
        user_unit = float(page.get("/UserUnit", 1) or 1)
        out.append(
            {
                "index": index,
                "rotation": int(page.get("/Rotate", 0) or 0) % 360,
                "user_unit": user_unit,
                "effective_view": [
                    float(crop.left),
                    float(crop.bottom),
                    float(crop.right),
                    float(crop.top),
                ],
                "basis": "pypdf declared page dictionaries",
            }
        )
    return out


def _occurrence_id(digest: str, page_index: int) -> str:
    base = f"{READER_ID}-{digest[:12]}-p{page_index}-0"
    return re.sub(r"[^a-z0-9_-]", "-", base.lower())[:96]


def extract(
    handle: PypdfHandle,
    plan: dict,
    emit_chunk: Callable[[list[dict]], None],
    cancellation: Callable[[], bool] | None = None,
) -> dict:
    """Terminal page-only extraction: one occurrence per requested page."""
    page_index = plan.get("page_index", 0)
    capability = plan.get("capability", "native_text")

    def result(status: str, reason: str | None, count: int, ids: list[str]) -> dict:
        return {
            "id": plan["id"],
            "status": status,
            "reason": reason,
            "produced_occurrence_count": count,
            "retained_occurrence_ids": ids,
        }

    if handle.closed:
        return result("failed", "parser_error: handle is closed", 0, [])
    if handle._reader.is_encrypted:
        return result("failed", "parser_error: encrypted document requires a password", 0, [])
    if capability != "native_text":
        return result(
            "unsupported",
            f"unsupported capability for {READER_ID}: {capability}",
            0,
            [],
        )
    if plan.get("region_id") is not None:
        return result(
            "unsupported",
            "region-scoped text requires a rendered-region reader path",
            0,
            [],
        )
    try:
        page_count = len(handle._reader.pages)
    except pypdf.errors.PdfReadError as error:
        return result("failed", f"parser_error: {error}", 0, [])
    if not isinstance(page_index, int) or page_index < 0 or page_index >= page_count:
        return result("unsupported", "page_out_of_range", 0, [])

    try:
        if cancellation is not None and cancellation():
            return result("cancelled", "cancelled by request", 0, [])
        text = handle._reader.pages[page_index].extract_text() or ""
    except pypdf.errors.PdfReadError as error:
        return result("failed", f"parser_error: {error}", 0, [])
    except Exception:
        return result("failed", "parser_error: unexpected engine failure", 0, [])
    if cancellation is not None and cancellation():
        return result("cancelled", "cancelled by request", 0, [])
    if len(text) > MAX_CHARS_PER_PAGE:
        return result("failed", "resource_limit: page exceeds character budget", 0, [])

    occurrence = {
        "id": _occurrence_id(handle.digest, page_index),
        "reader_id": READER_ID,
        "page_index": page_index,
        "ordinal": 0,
        "raw_text": text,
        "normalized_text": text,
        "normalization_map": [
            {
                "raw_start": 0,
                "raw_end": len(text),
                "normalized_start": 0,
                "normalized_end": len(text),
                "operation": "identity",
            }
        ],
        "geometry": {
            "precision": "page_only",
            "space": "canonical_page",
            "polygon": None,
            "transform_ids": [],
            "basis": "pypdf extract_text page-level output; no per-word geometry claimed",
        },
        "engine_score": None,
        "source_asset_id": None,
        "raw_source_locator": f"pypdf:page[{page_index}]:extract_text",
        "limitations": ["page-only extraction; anchors unavailable by design"],
    }
    chunk = [occurrence]
    emit_chunk(chunk)
    return result("completed", None, 1, [occurrence["id"]])
