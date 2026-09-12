"""Bounded native structural observations (T28).

Text-object render mode, boxes and inspectable page properties over the
frozen ``pypdfium2==5.8.0`` binding / PDFium 149.0.7825.0 build, per
``planning/architecture/READER_ADAPTER_CONTRACT.md`` ("Native object checks
use actual ``FPDFTextObj_GetTextRenderMode``, page object traversal and
documented color/geometry getters, with a finite nesting/object budget"),
``planning/architecture/CAPABILITIES.md`` (narrow object observation; no
automatic hidden/safe label; explicit limits instead of a clean certificate)
and ``planning/architecture/COORDINATES.md``.

Discipline implemented here:

* A render-mode observation is a property of the object, never a
  maliciousness or visibility finding. This module emits no hidden/visible
  verdict of any kind; contrast, paint order and overlap are recorded as
  bounded facts with their limits.
* Render mode integers are interpreted with PDF text render mode (``Tr``)
  semantics: 0 fill, 1 stroke, 2 fill_stroke, 3 invisible, 4 fill_clip,
  5 stroke_clip, 6 fill_stroke_clip, 7 clip. The installed build returns the
  raw content-stream ``Tr`` value (empirically verified: ``3 Tr`` reads back
  as 3), although the pypdfium2 enum *names* value 3 ``FILL_STROKE`` and
  reserves 4 for ``INVISIBLE``. Both the raw integer and the interpreted
  name are recorded so a naming divergence can never silently flip the
  meaning; a value outside 0..7 is ``unknown``.
* Absent properties stay absent: a color getter that reports no fill yields
  ``None`` (never a guessed color), an unreadable font name is ``None``,
  malformed page boxes leave geometry ``unknown`` with a null polygon (I04,
  I11).
* Off-crop objects keep their raw/native geometry: canonical coordinates are
  mapped but never clipped to the effective view, the raw user-space box is
  recorded, and the limitation states that page display remains the crop.
* Unsupported compositing is explicitly recorded per occurrence:
  ``FPDFPageObj_HasTransparency`` flags objects participating in
  transparency — alpha fills, soft masks AND non-Normal blend modes
  (empirically verified: /BM /Multiply and /Screen objects are flagged) —
  and such objects carry the unsupported-compositing limitation themselves.
  Stroking alpha below full opacity is flagged symmetrically. The one
  context with no per-object getter on this binding is optional-content
  (``/OC`` BDC) membership; an explicit task-receipt limitation states that
  such objects may emit ordinary records (no false "all checked").
* Finite budgets: top-level page objects, per-object text snippets and
  emitted chunks are bounded; exceeding an object budget is a typed
  ``resource_limit`` terminal that keeps all prior evidence (I17). Every
  planned check reaches a terminal result (I05).

All library calls run single-threaded in the calling process; the document is
reopened from the handle's immutable bytes so reader internals stay
unmodified. Closing the internal document is deterministic.
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pypdfium2
from pypdfium2 import PdfDocument
from pypdfium2 import raw as pdfium_raw
from ctypes import c_float, c_uint, byref, cast, c_ushort

from inkflip.readers import pdfium as pdfium_reader
from inkflip.readers.pdfium import PdfiumHandle

READER_ID = "pdfium-structure"
ADAPTER_VERSION = "1.0.0"
SUPPORTED_CAPABILITIES = ("object_render_mode", "crop_metadata", "paint_overlap")
MAX_PAGE_OBJECTS = 2000
MAX_TEXT_SNIPPET_CHARS = 256
MAX_CHUNK = 256
MAX_FORM_OBSERVATIONS = 64

# PDF text render mode (Tr) semantics from the content-stream operator.
PDF_RENDER_MODE_NAMES = {
    0: "fill",
    1: "stroke",
    2: "fill_stroke",
    3: "invisible",
    4: "fill_clip",
    5: "stroke_clip",
    6: "fill_stroke_clip",
    7: "clip",
}
# Object type constants (FPDF_PAGEOBJ_*).
OBJECT_TYPE_NAMES = {1: "text", 2: "path", 3: "image", 4: "shading", 5: "form"}


class AdapterError(Exception):
    """Typed failure carrying a public reason code."""

    def __init__(self, reason: str, detail: str):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


def _round6(value: float) -> float:
    rounded = round(value, 6)
    if rounded == 0:
        return 0.0
    return rounded


def _canonical_transform(effective_view: list[float], user_unit: float) -> list[float] | None:
    """C = [u,0,0,-u,-u*cx0,u*cy1] over the crop-box effective view."""
    cx0, cy0, cx1, cy1 = effective_view
    values = [user_unit, 0.0, 0.0, -user_unit, -user_unit * cx0, user_unit * cy1]
    if any(v != v or v in (float("inf"), float("-inf")) for v in values):
        return None
    if cx1 - cx0 <= 0 or cy1 - cy0 <= 0 or user_unit <= 0:
        return None
    return values


def _map_point(transform: list[float], x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = transform
    return (a * x + c * y + e, b * x + d * y + f)


def _canonical_polygon(transform: list[float], box) -> list[list[float]] | None:
    """Raw user-space box (l, b, r, t) -> canonical quad TL, TR, BR, BL.

    Never clipped: an object outside the effective view keeps coordinates
    outside the canonical page extent (raw/native geometry preserved)."""
    left, bottom, right, top = box
    corners = [
        _map_point(transform, left, top),
        _map_point(transform, right, top),
        _map_point(transform, right, bottom),
        _map_point(transform, left, bottom),
    ]
    out = []
    for x, y in corners:
        if x != x or y != y or x in (float("inf"), float("-inf")) or y in (float("inf"), float("-inf")):
            return None
        out.append([_round6(x), _round6(y)])
    return out


def _intersects(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def describe() -> dict:
    """Reader manifest (schema $defs/Reader + ReaderManifest) for this check."""
    build = f"{pypdfium2.PDFIUM_INFO}; binding {pdfium_reader._binding_version()}"
    return {
        "kind": "reader_manifest",
        "schema_version": "1.0.0",
        "reader": {
            "id": READER_ID,
            "name": "PDFium structural observation",
            "version": str(pypdfium2.PDFIUM_INFO),
            "build": build,
            "adapter_version": ADAPTER_VERSION,
            "method": "structure",
            "environment": "native",
            "settings": {
                "normalization": "scalar-whitespace-v1",
                "language": None,
                "psm": None,
                "render_reader_id": "pdfium-native",
                "raster_dpi": None,
                "annotation_mode": "not_applicable",
            },
            "capabilities": [
                {
                    "name": "object_render_mode",
                    "support": "supported",
                    "limits": [
                        "narrow object observation: top-level text objects only, "
                        f"finite budget of {MAX_PAGE_OBJECTS} objects per page",
                        "render mode is a document property; no hidden/visible "
                        "verdict is produced",
                    ],
                },
                {
                    "name": "crop_metadata",
                    "support": "supported",
                    "limits": [
                        "page boxes come from the pypdf dictionary adapter and the "
                        "crop-box effective view; off-crop objects keep raw geometry",
                    ],
                },
                {
                    "name": "paint_overlap",
                    "support": "approximate",
                    "limits": [
                        "bounded opaque-rectangle experiment over top-level objects; "
                        "no automatic hidden/safe label",
                    ],
                },
            ],
            "model_hashes": [],
            "limitations": [
                "render-mode integers follow content-stream Tr semantics; the "
                "installed PDFium returns the raw Tr value, so both the raw "
                "integer and the interpreted name are recorded per object",
                "per-occurrence compositing flags cover transparency and "
                "non-Normal blend modes (HasTransparency); comprehensive "
                "clipping, blend, transparency-group, optional-content and "
                "historical-revision inspection is not performed, and /OC BDC "
                "membership has no per-object getter, so such objects may "
                "emit ordinary records",
                "no universal hidden/visible verdict exists in this check",
            ],
        },
        "distribution_digest": pdfium_reader._distribution_digest(),
        "asset_hashes": [h] if (h := pdfium_reader._engine_binary_digest()) else [],
        "execution_policy": "installed_allowlist_no_report_commands",
    }


def _occurrence_id(digest: str, page_index: int, ordinal: int) -> str:
    base = f"{READER_ID}-{digest[:12]}-p{page_index}-obj-{ordinal}"
    return re.sub(r"[^a-z0-9_-]", "-", base.lower())[:96]


def _make_occurrence(
    digest: str,
    page_index: int,
    ordinal: int,
    raw_text: str,
    polygon: list[list[float]] | None,
    geometry_supported: bool,
    transform_ids: list[str],
    basis: str,
    locator: str,
    limitations: list[str],
) -> dict:
    return {
        "id": _occurrence_id(digest, page_index, ordinal),
        "reader_id": READER_ID,
        "page_index": page_index,
        "ordinal": ordinal,
        "raw_text": raw_text,
        "normalized_text": raw_text,
        "normalization_map": [
            {
                "raw_start": 0,
                "raw_end": len(raw_text),
                "normalized_start": 0,
                "normalized_end": len(raw_text),
                "operation": "identity",
            }
        ],
        "geometry": {
            "precision": "exact" if (geometry_supported and polygon is not None) else "unknown",
            "space": "canonical_page",
            "polygon": polygon,
            "transform_ids": transform_ids if (geometry_supported and polygon is not None) else [],
            "basis": basis,
        },
        "engine_score": None,
        "source_asset_id": None,
        "raw_source_locator": locator,
        "limitations": limitations,
    }


def _fill_color(obj) -> tuple[int, int, int, int] | None:
    r, g, b, a = c_uint(), c_uint(), c_uint(), c_uint()
    if pdfium_raw.FPDFPageObj_GetFillColor(obj, byref(r), byref(g), byref(b), byref(a)):
        return (r.value, g.value, b.value, a.value)
    return None


def _stroke_color(obj) -> tuple[int, int, int, int] | None:
    r, g, b, a = c_uint(), c_uint(), c_uint(), c_uint()
    if pdfium_raw.FPDFPageObj_GetStrokeColor(obj, byref(r), byref(g), byref(b), byref(a)):
        return (r.value, g.value, b.value, a.value)
    return None


def _bounds(obj) -> tuple[float, float, float, float] | None:
    left, bottom, right, top = c_float(), c_float(), c_float(), c_float()
    if pdfium_raw.FPDFPageObj_GetBounds(obj, byref(left), byref(bottom), byref(right), byref(top)):
        return (left.value, bottom.value, right.value, top.value)
    return None


def _font_name(obj) -> str | None:
    font = pdfium_raw.FPDFTextObj_GetFont(obj)
    if not font:
        return None
    buf = bytes(128)
    written = pdfium_raw.FPDFFont_GetBaseFontName(font, buf, 128)
    if written <= 0:
        return None
    # This build counts the terminating NUL in the returned length.
    return buf[:written].decode("latin-1", "replace").rstrip("\x00").strip() or None


def _object_text(obj, textpage) -> str | None:
    buf = (c_ushort * (MAX_TEXT_SNIPPET_CHARS + 1))()
    written = pdfium_raw.FPDFTextObj_GetText(obj, textpage, buf, MAX_TEXT_SNIPPET_CHARS)
    if written <= 0:
        return None
    return bytes(buf)[: written * 2].decode("utf-16-le", "replace").split("\x00", 1)[0]


def _render_mode_record(raw_mode: int) -> tuple[str, str]:
    """(raw, interpreted) pair. Interpretation follows content-stream Tr
    semantics; out-of-range values stay 'unknown' with the raw int kept."""
    name = PDF_RENDER_MODE_NAMES.get(raw_mode, "unknown")
    return (str(raw_mode), name)


def extract(
    handle: PdfiumHandle,
    plan: dict,
    emit_chunk: Callable[[list[dict]], None],
    cancellation: Callable[[], bool] | None = None,
) -> dict:
    """Terminal structural observation check; typed terminals only (I05)."""

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
    capability = plan.get("capability")
    if capability not in SUPPORTED_CAPABILITIES:
        return result(
            "unsupported",
            f"unsupported capability for {READER_ID}: {capability}",
            0,
            [],
        )
    if plan.get("region_id") is not None:
        return result(
            "unsupported",
            "structural observation is a whole-page check; region_id is not supported",
            0,
            [],
        )
    page_index = plan.get("page_index", 0)
    pages = pdfium_reader.pages(handle)
    if not isinstance(page_index, int) or page_index < 0 or page_index >= len(pages):
        return result("unsupported", "page_out_of_range", 0, [])
    meta = pages[page_index]

    try:
        doc = PdfDocument(handle.data)
    except pypdfium2.PdfiumError:
        return result("failed", "parser_error: document failed to parse", 0, [])
    try:
        page = doc[page_index]
        textpage = page.get_textpage()
        try:
            return _run_check(handle, plan, capability, page_index, meta, page, textpage, emit_chunk, cancellation)
        finally:
            textpage.close()
            page.close()
    finally:
        doc.close()


def _run_check(handle, plan, capability, page_index, meta, page, textpage, emit_chunk, cancellation) -> dict:
    def result(status, reason, count, ids):
        return {
            "id": plan["id"],
            "status": status,
            "reason": reason,
            "produced_occurrence_count": count,
            "retained_occurrence_ids": ids,
        }

    transform = (
        _canonical_transform(meta["effective_view"], meta["user_unit"])
        if meta["geometry_supported"]
        else None
    )
    geometry_supported = transform is not None
    effective_view = tuple(meta["effective_view"])

    total_objects = pdfium_raw.FPDFPage_CountObjects(page.raw)
    object_limit_exceeded = total_objects > MAX_PAGE_OBJECTS
    scan_count = min(total_objects, MAX_PAGE_OBJECTS)

    retained: list[str] = []
    produced = 0
    chunk: list[dict] = []
    ordinal = 0

    def flush():
        nonlocal chunk, produced, retained
        if chunk:
            emit_chunk(chunk)
            retained.extend(o["id"] for o in chunk)
            produced += len(chunk)
            chunk = []

    def emit(occurrence):
        nonlocal chunk, ordinal
        chunk.append(occurrence)
        ordinal += 1
        if len(chunk) >= MAX_CHUNK:
            flush()

    def cancelled() -> bool:
        return cancellation is not None and cancellation()

    # Classification pass: collect bounded facts without emitting, then emit
    # only the observation kind the requested capability names.
    text_records = []  # classified text-object facts
    opaque_rects = []  # (index, bounds) later-overlap candidates
    form_indices = []  # nested Form XObjects (not traversed)

    for index in range(scan_count):
        if cancelled():
            flush()
            return result("cancelled", "cancelled by request", produced, retained)
        obj = pdfium_raw.FPDFPage_GetObject(page.raw, index)
        obj_type = pdfium_raw.FPDFPageObj_GetType(obj)
        bounds = _bounds(obj)

        if obj_type == pdfium_raw.FPDF_PAGEOBJ_TEXT:
            raw_mode = pdfium_raw.FPDFTextObj_GetTextRenderMode(obj)
            raw_str, mode_name = _render_mode_record(raw_mode)
            fill = _fill_color(obj)
            stroke = _stroke_color(obj) if raw_mode in (1, 2, 5, 6) else None
            text = _object_text(obj, textpage) or ""
            font = _font_name(obj)
            limitations = [
                "render mode recorded as a document property; not a hidden or "
                "visible verdict"
            ]
            if fill is not None and fill[3] < 255:
                limitations.append("alpha compositing not inspected; fill alpha below 255")
            if stroke is not None and stroke[3] < 255:
                limitations.append(
                    "stroke alpha compositing not inspected; stroke alpha below 255"
                )
            if pdfium_raw.FPDFPageObj_HasTransparency(obj):
                limitations.append(
                    "transparency compositing (alpha, soft mask or non-Normal "
                    "blend mode) not inspected; unsupported compositing "
                    "recorded for this object"
                )
            text_records.append(
                {
                    "index": index,
                    "bounds": bounds,
                    "raw_mode": raw_str,
                    "mode_name": mode_name,
                    "fill": fill,
                    "stroke": stroke,
                    "text": text,
                    "font": font,
                    "limitations": limitations,
                }
            )
        elif obj_type == pdfium_raw.FPDF_PAGEOBJ_FORM:
            if len(form_indices) < MAX_FORM_OBSERVATIONS:
                form_indices.append(index)
        elif bounds is not None:
            # Non-text top-level object: candidate for the opaque-rectangle
            # overlap experiment only (bounded, approximate).
            opaque_rects.append((index, bounds))
        obj = None  # objects are owned by the page; no destroy here

    if capability == "object_render_mode":
        for record in text_records:
            if cancelled():
                flush()
                return result("cancelled", "cancelled by request", produced, retained)
            bounds = record["bounds"]
            locator = f"pdfium:pageobj[{record['index']}]:tr{record['raw_mode']}:{record['mode_name']}"
            facts = (
                f"render_mode_raw={record['raw_mode']} render_mode={record['mode_name']}"
                + (
                    f" fill={record['fill'][0]},{record['fill'][1]},{record['fill'][2]},{record['fill'][3]}"
                    if record["fill"] is not None
                    else " fill=unavailable"
                )
                + (
                    f" stroke={record['stroke'][0]},{record['stroke'][1]},{record['stroke'][2]},{record['stroke'][3]}"
                    if record["stroke"] is not None
                    else ""
                )
                + (f" font={record['font']}" if record["font"] is not None else " font=unavailable")
                + f" text={record['text']!r}"
            )
            polygon = (
                _canonical_polygon(transform, bounds)
                if (geometry_supported and bounds is not None)
                else None
            )
            basis = (
                f"FPDFTextObj_GetTextRenderMode and documented getters on page "
                f"object {record['index']}; {facts}; raw user box {bounds!r}"
                if bounds is not None
                else f"FPDFTextObj_GetTextRenderMode on page object {record['index']}; {facts}; no bounds"
            )
            emit(
                _make_occurrence(
                    handle.digest, page_index, ordinal, record["text"], polygon,
                    geometry_supported and bounds is not None,
                    ["pdfium-user-to-canonical-c"], basis, locator,
                    record["limitations"],
                )
            )
        for form_index in form_indices:
            if cancelled():
                flush()
                return result("cancelled", "cancelled by request", produced, retained)
            emit(
                _make_occurrence(
                    handle.digest, page_index, ordinal, "", None, False,
                    [],
                    f"nested Form XObject at page object {form_index}; compositing "
                    "inside the form is not inspected",
                    f"pdfium:pageobj[{form_index}]:form:nested-not-traversed",
                    [
                        "nested Form XObject contents are not traversed; "
                        "compositing unsupported",
                    ],
                )
            )

    if capability == "paint_overlap":
        for record in text_records:
            if cancelled():
                flush()
                return result("cancelled", "cancelled by request", produced, retained)
            text_index = record["index"]
            text_bounds = record["bounds"]
            if text_bounds is None:
                continue
            later = [
                str(idx)
                for idx, rect in opaque_rects
                if idx > text_index and _intersects(text_bounds, rect)
            ]
            limitations = [
                "approximate bounded opaque-rectangle experiment over top-level "
                "objects; paint order and overlap are recorded facts, not a "
                "hidden or visible verdict",
            ]
            locator = (
                f"pdfium:pageobj[{text_index}]:overlap"
                + (":later[" + ",".join(later) + "]" if later else ":none")
            )
            basis = (
                f"top-level object order comparison; text object {text_index} "
                f"bounds {text_bounds!r}; later opaque objects {later if later else 'none'}"
            )
            polygon = _canonical_polygon(transform, text_bounds) if geometry_supported else None
            emit(
                _make_occurrence(
                    handle.digest, page_index, ordinal, "", polygon, geometry_supported,
                    ["pdfium-user-to-canonical-c"], basis, locator, limitations,
                )
            )

    if capability == "crop_metadata":
        cx0, cy0, cx1, cy1 = effective_view
        for record in text_records:
            if cancelled():
                flush()
                return result("cancelled", "cancelled by request", produced, retained)
            bounds = record["bounds"]
            if bounds is None:
                continue
            l, b, r, t = bounds
            outside = l < cx0 or r > cx1 or b < cy0 or t > cy1
            if not outside:
                continue
            polygon = _canonical_polygon(transform, bounds) if geometry_supported else None
            emit(
                _make_occurrence(
                    handle.digest, page_index, ordinal, "", polygon, geometry_supported,
                    ["pdfium-user-to-canonical-c"],
                    f"text object {record['index']} raw user box {bounds!r} lies "
                    "outside the crop-box effective view; geometry is preserved "
                    "unclipped while page display remains the crop",
                    f"pdfium:pageobj[{record['index']}]:off-crop",
                    [
                        "object lies outside the crop-box effective view; raw "
                        "geometry preserved; page display remains the crop",
                    ],
                )
            )
        record_text = (
            f"effective_view={effective_view[0]!r},{effective_view[1]!r},"
            f"{effective_view[2]!r},{effective_view[3]!r}"
            f" user_unit={meta['user_unit']!r} rotation={meta['rotation']}"
            f" physical={meta['physical_width_pt']!r}x{meta['physical_height_pt']!r}pt"
        )
        polygon = _canonical_polygon(transform, effective_view) if geometry_supported else None
        emit(
            _make_occurrence(
                handle.digest, page_index, ordinal, record_text, polygon, geometry_supported,
                ["pdfium-user-to-canonical-c"],
                "pypdf crop-box dictionary adapter and /UserUnit metadata; "
                "PDFium get_size() is rotated and UserUnit-blind on this build",
                "pdfium:page[props]",
                ["original MediaBox may be inherited or absent; only the "
                 "effective view is asserted by the renderer"],
            )
        )

    flush()

    if object_limit_exceeded:
        return result(
            "failed",
            f"resource_limit: page exceeds the {MAX_PAGE_OBJECTS}-object budget",
            produced,
            retained,
        )
    if cancelled():
        flush()
        return result("cancelled", "cancelled by request", produced, retained)
    return result("completed", None, produced, retained)
