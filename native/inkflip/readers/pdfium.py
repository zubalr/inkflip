"""Native PDFium text reader adapter (T26).

Implements the native_text path over the frozen ``pypdfium2==5.8.0`` binding /
PDFium 149.0.7825.0 build, per ``planning/architecture/READER_ADAPTER_CONTRACT.md``
and ``planning/architecture/COORDINATES.md``. Observed build-specific behavior
that this adapter compensates for (measured on the T05 fixtures; see
``planning/architecture/COORDINATES.md`` "PDFium" and
``planning/probes/results/pdfium-characters.json``):

* ``PdfDocument.get_size()`` reports rotated crop dimensions but does NOT
  multiply by ``UserUnit``. Physical page dimensions are derived here from
  pypdf page metadata (crop box, ``/UserUnit``) and the canonical transform
  scales once by ``u`` — never twice.
* The character API expands one glyph into several Unicode scalars when the
  font's ToUnicode CMap maps one code to many (the F01 ``$1,000`` mechanism).
  Expanded scalars report the identical glyph box; consecutive characters that
  share an exactly-equal box are coalesced into one occurrence carrying the
  full multi-scalar text with that box. No width is ever interpolated or
  guessed.
* ``get_charbox`` coordinates are raw PDF user space (origin bottom-left,
  unrotated). They are mapped into canonical page space with the documented
  transform ``C = [u, 0, 0, -u, -u*cx0, u*cy1]`` over the crop-box effective
  view. Document rotation changes display only and is not applied to stored
  coordinates.
* ``\\r``/``\\n`` characters synthesized by PDFium between text blocks carry no
  glyph box; they terminate runs and are never emitted as occurrences.

Geometry under malformed or inverted page boxes is ``unknown`` with a null
polygon, never guessed. All library calls run single-threaded in the calling
process; no threading or queueing exists in this module. Closing handles is
deterministic and idempotent.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pypdf
import pypdfium2
from pypdfium2 import PdfDocument

READER_ID = "pdfium-native"
ADAPTER_VERSION = "1.0.0"
MAX_CHARS_PER_PAGE = 200_000
MAX_OCCURRENCES_PER_CHUNK = 256
CHAR_CHUNK = 1024

# Public reason codes from READER_ADAPTER_CONTRACT.md "Capability negotiation".


class AdapterError(Exception):
    """Typed open-time failure carrying a public reason code."""

    def __init__(self, reason: str, detail: str):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


@dataclass
class PdfiumHandle:
    """Bounded document handle; immutable bytes, one digest, one generation."""

    data: bytes
    digest: str
    generation: int
    _doc: PdfDocument = field(repr=False, default=None)
    _metadata: list[dict] = field(repr=False, default=None)
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._doc = None
        self._metadata = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _pdfium_build() -> str:
    return str(pypdfium2.PDFIUM_INFO)


def _binding_version() -> str:
    return importlib.metadata.version("pypdfium2")


def _engine_binary_digest() -> str | None:
    """SHA-256 of the loaded PDFium native binary (I13 build identity)."""
    spec = importlib.util.find_spec("pypdfium2_raw")
    if spec is None or not spec.loader:
        return None
    origin = getattr(spec.loader, "path", None)  # package __init__ or namespace dir
    if not origin:
        return None
    package_dir = Path(origin).parent if Path(origin).name != "" else Path(origin)
    binaries = sorted(
        p
        for p in package_dir.iterdir()
        if p.is_file()
        and p.name.startswith(("libpdfium", "pdfium", "_pdfium"))
        and p.suffix in (".so", ".dylib", ".dll")
    )
    if not binaries:
        return None
    return hashlib.sha256(binaries[0].read_bytes()).hexdigest()


def _distribution_digest() -> str | None:
    """SHA-256 of the installed pypdfium2 wheel metadata, when locatable."""
    try:
        dist = importlib.metadata.distribution("pypdfium2")
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
    engine_digest = _engine_binary_digest()
    distribution_digest = _distribution_digest()
    return {
        "kind": "reader_manifest",
        "schema_version": "1.0.0",
        "reader": {
            "id": READER_ID,
            "name": "PDFium",
            "version": _binding_version(),
            "build": f"pypdfium2 {_binding_version()} / PDFium {_pdfium_build()}",
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
                        "glyph-box granularity; consecutive characters sharing an "
                        "exactly-equal reported box are coalesced without width guessing",
                        "UserUnit compensation derives physical geometry from pypdf "
                        "page metadata; get_size() is not trusted for physical units",
                    ],
                },
                {
                    "name": "render",
                    "support": "unavailable",
                    "limits": [
                        "render scale compensation is proven under the OCR/render "
                        "tasks; not claimed by this reader manifest yet"
                    ],
                },
            ],
            "model_hashes": [engine_digest] if engine_digest else [],
            "limitations": [
                "single-threaded in-process adapter; supervision belongs to the "
                "native parent task",
                "rotation is display-only and is not applied to stored occurrence "
                "coordinates",
            ],
        },
        "distribution_digest": distribution_digest,
        "asset_hashes": [engine_digest] if engine_digest else [],
        "execution_policy": "installed_allowlist_no_report_commands",
    }


def _page_metadata(handle: PdfHandle) -> list[dict]:
    """Effective view, UserUnit and rotation per page from pypdf metadata."""
    if handle._metadata is None:
        reader = pypdf.PdfReader(io.BytesIO(handle.data))
        pages = []
        for page in reader.pages:
            crop = page.cropbox
            media = page.mediabox
            user_unit = float(page.get("/UserUnit", 1) or 1)
            if user_unit <= 0:
                user_unit = float("nan")
            rotate = int(page.get("/Rotate", 0) or 0) % 360
            pages.append(
                {
                    "cropbox": (float(crop.left), float(crop.bottom), float(crop.right), float(crop.top)),
                    "mediabox": (float(media.left), float(media.bottom), float(media.right), float(media.top)),
                    "user_unit": user_unit,
                    "rotation": rotate,
                }
            )
        handle._metadata = pages
    return handle._metadata


def _canonical_transform(meta: dict) -> list[float] | None:
    """C = [u,0,0,-u,-u*cx0,u*cy1] over the crop-box effective view (COORDINATES)."""
    u = meta["user_unit"]
    cx0, cy0, cx1, cy1 = meta["cropbox"]
    values = [u, 0.0, 0.0, -u, -u * cx0, u * cy1]
    if any(v != v or v in (float("inf"), float("-inf")) for v in values):
        return None
    if cx1 - cx0 <= 0 or cy1 - cy0 <= 0 or u <= 0:
        return None
    return values


def _map_point(transform: list[float], x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = transform
    return (a * x + c * y + e, b * x + d * y + f)


def _round6(value: float) -> float:
    rounded = round(value, 6)
    if rounded == 0:
        return 0.0
    return rounded


def _canonical_polygon(transform: list[float], box) -> list[list[float]]:
    """Loose charbox (l, b, r, t) in user space -> canonical quad TL,TR,BR,BL."""
    left, bottom, right, top = box
    tl = _map_point(transform, left, top)
    tr = _map_point(transform, right, top)
    br = _map_point(transform, right, bottom)
    bl = _map_point(transform, left, bottom)
    return [
        [_round6(tl[0]), _round6(tl[1])],
        [_round6(tr[0]), _round6(tr[1])],
        [_round6(br[0]), _round6(br[1])],
        [_round6(bl[0]), _round6(bl[1])],
    ]


def open_document(data: bytes, digest: str | None, generation: int) -> PdfiumHandle:
    """Open immutable bytes into a bounded handle; typed failures only."""
    if not isinstance(data, bytes) or not data:
        raise AdapterError("parser_error", "document bytes missing or empty")
    computed = hashlib.sha256(data).hexdigest()
    if digest is not None and digest != computed:
        raise AdapterError("parser_error", "document digest mismatch")
    try:
        doc = PdfDocument(data)
    except pypdfium2.PdfiumError as error:
        detail = str(error)
        if "password" in detail.lower():
            raise AdapterError("parser_error", "encrypted document requires a password") from error
        raise AdapterError("parser_error", "document failed to parse") from error
    except Exception as error:  # unknown engine failure stays typed, never partial
        raise AdapterError("parser_error", "document failed to parse") from error
    return PdfiumHandle(data=data, digest=computed, generation=generation, _doc=doc)


def pages(handle: PdfHandle) -> list[dict]:
    """Page count plus geometry metadata; physical sizes carry UserUnit once."""
    if handle.closed:
        raise AdapterError("parser_error", "handle is closed")
    metas = _page_metadata(handle)
    out = []
    for index, meta in enumerate(metas):
        transform = _canonical_transform(meta)
        cx0, cy0, cx1, cy1 = meta["cropbox"]
        u = meta["user_unit"]
        out.append(
            {
                "index": index,
                "rotation": meta["rotation"],
                "user_unit": u,
                "effective_view": list(meta["cropbox"]),
                "physical_width_pt": _round6((cx1 - cx0) * u),
                "physical_height_pt": _round6((cy1 - cy0) * u),
                "geometry_supported": transform is not None,
                "basis": "pypdf crop box and /UserUnit metadata; PDFium get_size() "
                "is rotated and UserUnit-blind on this build",
            }
        )
    return out


def _occurrence_id(digest: str, page_index: int, ordinal: int) -> str:
    base = f"{READER_ID}-{digest[:12]}-p{page_index}-{ordinal}"
    return re.sub(r"[^a-z0-9_-]", "-", base.lower())[:96]


def extract(
    handle: PdfiumHandle,
    plan: dict,
    emit_chunk: Callable[[list[dict]], None],
    cancellation: Callable[[], bool] | None = None,
) -> dict:
    """Terminal native_text extraction: occurrences chunked at 256.

    Returns a terminal CheckResult; the full plan is honored even on failure.
    """
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
            "region-scoped native text requires the rendered-region reader path",
            0,
            [],
        )
    metas = _page_metadata(handle)
    if not isinstance(page_index, int) or page_index < 0 or page_index >= len(metas):
        return result("unsupported", "page_out_of_range", 0, [])

    retained: list[str] = []
    produced = 0
    try:
        page = handle._doc[page_index]
        textpage = page.get_textpage()
        try:
            total = textpage.count_chars()
            if total > MAX_CHARS_PER_PAGE:
                return result("failed", "resource_limit: page exceeds character budget", produced, retained)
            meta = metas[page_index]
            transform = _canonical_transform(meta)
            geometry_supported = transform is not None

            ordinal = 0
            chunk: list[dict] = []
            run_text: list[str] = []
            run_box = None
            run_first = None

            def flush_run() -> None:
                nonlocal ordinal, chunk, run_text, run_box, run_first
                if not run_text:
                    return
                polygon = (
                    _canonical_polygon(transform, run_box) if geometry_supported else None
                )
                occurrence = {
                    "id": _occurrence_id(handle.digest, page_index, ordinal),
                    "reader_id": READER_ID,
                    "page_index": page_index,
                    "ordinal": ordinal,
                    "raw_text": "".join(run_text),
                    "normalized_text": "".join(run_text),
                    "normalization_map": [
                        {
                            "raw_start": 0,
                            "raw_end": len(run_text),
                            "normalized_start": 0,
                            "normalized_end": len(run_text),
                            "operation": "identity",
                        }
                    ],
                    "geometry": {
                        "precision": "exact" if geometry_supported else "unknown",
                        "space": "canonical_page",
                        "polygon": polygon,
                        "transform_ids": ["pdfium-user-to-canonical-c"] if geometry_supported else [],
                        "basis": (
                            f"pdfium get_charbox(loose=True) indices "
                            f"{run_first}-{run_first + len(run_text) - 1}; identical "
                            "reported glyph box coalesced; C over pypdf crop/UserUnit"
                            if geometry_supported
                            else "malformed page boxes; geometry not guessed"
                        ),
                    },
                    "engine_score": None,
                    "source_asset_id": None,
                    "raw_source_locator": f"pdfium:char[{run_first}:{run_first + len(run_text)}]:loose",
                    "limitations": [],
                }
                ordinal += 1
                chunk.append(occurrence)
                if len(chunk) >= MAX_OCCURRENCES_PER_CHUNK:
                    emit_chunk(chunk)
                    retained.extend(o["id"] for o in chunk)
                    produced += len(chunk)
                    chunk = []
                run_text = []
                run_box = None
                run_first = None

            for index in range(total):
                if cancellation is not None and index % CHAR_CHUNK == 0 and cancellation():
                    if chunk:
                        emit_chunk(chunk)
                        retained.extend(o["id"] for o in chunk)
                        produced += len(chunk)
                        chunk = []
                    return result("cancelled", "cancelled by request", produced, retained)
                text = textpage.get_text_range(index, 1)
                if text in ("\r", "\n"):
                    # Synthetic block separators from PDFium text assembly; they
                    # carry no glyph box and are not document content.
                    flush_run()
                    continue
                if text == " ":
                    # Keep raw text flow intact (I03): a space rides at the end
                    # of the current run instead of silently disappearing.
                    if run_text:
                        run_text.append(text)
                    flush_run()
                    continue
                box = textpage.get_charbox(index, loose=True)
                if run_box is not None and tuple(box) != tuple(run_box):
                    flush_run()
                if not run_text:
                    run_first = index
                run_text.append(text)
                run_box = box
            flush_run()
            if chunk:
                emit_chunk(chunk)
                retained.extend(o["id"] for o in chunk)
                produced += len(chunk)
            return result("completed", None, produced, retained)
        finally:
            textpage.close()
            page.close()
    except AdapterError:
        raise
    except pypdfium2.PdfiumError as error:
        return result("failed", f"parser_error: {error}", produced, retained)
    except Exception:  # isolate any engine fault into a terminal record
        return result("failed", "parser_error: unexpected engine failure", produced, retained)
