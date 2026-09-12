"""Native rendered-region Tesseract reader adapter (T27).

OCR over a chosen page or region of a bounded, named-renderer raster, per
``planning/architecture/READER_ADAPTER_CONTRACT.md`` ("Tesseract is invoked
with fixed argv and ``shell=False`` ..."), ``planning/architecture/COORDINATES.md``
(ocr space and inverse crop/resize chains) and ``planning/architecture/CAPABILITIES.md``
("Missing model / timeout distinct from unreadable pixels").

Discipline implemented here:

* Fixed argv, ``shell=False``: ``[tesseract, <private>/input.png, stdout,
  --psm <n>, tsv]``. The caller never names files: the crop is written under a
  neutral name inside a private temporary directory, and ``language`` is
  validated against ``^[a-z0-9_-]{1,32}$`` so no option injection is possible.
* No URL or runtime model fetch: the traineddata file is located on disk next
  to the binary (or via ``TESSDATA_PREFIX``) and hashed. A missing model is a
  distinct typed failure from a missing binary, an undecodable raster
  (``unreadable_pixels``) or a wall-time timeout.
* Context padding is 8 raster pixels or 10 % of the region height (larger),
  clipped to the raster. Original region and padded crop are kept separately;
  the crop/resize transform ``O`` is recorded with its explicit inverse so TSV
  word boxes map back to raster and canonical coordinates.
* Word TSV rows become occurrences with verbatim raw text (punctuation and
  case preserved), confidence as a diagnostic ``engine_score`` (never quality
  truth), and ``estimated`` canonical geometry when the caller recorded the
  named-render metadata (raster scale); without it, geometry is ``unknown``
  with a null polygon and the raw text is retained.
* Empty successful OCR is a completed check with zero occurrences. Wall-time
  overrun terminates the child and yields a distinct ``timeout`` terminal.
  Single-threaded, no threads around the subprocess.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable

from PIL import Image

READER_ID = "tesseract-native"
ADAPTER_VERSION = "1.0.0"
DEFAULT_LANGUAGE = "eng"
# Measured on the T05 fixtures: PSM 6 (uniform block) drops the isolated
# '$100' amount line on the F01 render; the native full-page default is
# tesseract's own automatic segmentation (PSM 3). A deliberately single-line
# user region uses PSM 7; the choice is recorded on the emitted occurrences.
DEFAULT_PSM = 3
SINGLE_LINE_PSM = 7
CONTEXT_PADDING_MIN_PX = 8
CONTEXT_PADDING_RATIO = 0.10
MAX_RASTER_PIXELS = 40_000_000
MAX_WORD_OCCURRENCES = 5000
LANGUAGE_PATTERN = re.compile(r"^[a-z0-9_-]{1,32}$")
VALID_PSM = {3, 4, 6, 7, 8, 11, 12, 13}


class AdapterError(Exception):
    """Typed failure carrying a public reason code."""

    def __init__(self, reason: str, detail: str):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


@dataclass
class RasterHandle:
    """Bounded raster handle over immutable PNG bytes plus named-render metadata."""

    data: bytes
    digest: str
    generation: int
    width: int
    height: int
    render_meta: dict | None
    closed: bool = False

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@dataclass(frozen=True)
class CropPlan:
    """Original region, padded crop rect and the recorded inverse transforms."""

    region: tuple[int, int, int, int]  # x0, y0, x1, y1 in raster px (original)
    padded: tuple[int, int, int, int]  # x0, y0, x1, y1 clipped to raster
    psm: int
    resize: tuple[float, float]  # kx, ky applied to the padded crop
    raster_scale: float | None  # recorded px per physical point, if known

    @property
    def padding(self) -> tuple[int, int]:
        return (self.padded[0] - self.region[0], self.padded[1] - self.region[1])

    def crop_to_raster(self, x: float, y: float) -> tuple[float, float]:
        """Inverse O step 1: padded-crop pixel -> raster pixel (resize undone)."""
        kx, ky = self.resize
        return (x / kx + self.padded[0], y / ky + self.padded[1])

    def raster_to_canonical(self, x: float, y: float) -> tuple[float, float] | None:
        """Inverse chain step 2: raster pixel -> canonical physical points."""
        if self.raster_scale is None or self.raster_scale <= 0:
            return None
        return (x / self.raster_scale, y / self.raster_scale)


def _binary_path(explicit: str | os.PathLike | None) -> Path:
    if explicit is not None:
        path = Path(explicit)
        if not path.is_file():
            raise AdapterError("unsupported", "tesseract executable not found")
        return path
    found = shutil.which("tesseract")
    if found is None:
        raise AdapterError("unsupported", "tesseract executable not found")
    return Path(found)


def _tessdata_dir(binary: Path) -> Path | None:
    env = os.environ.get("TESSDATA_PREFIX")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            binary.parent.parent / "share" / "tessdata",
            binary.parent / "tessdata",
        ]
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def model_digest(binary: Path | None = None, language: str = DEFAULT_LANGUAGE) -> tuple[str | None, Path | None]:
    """Exact local traineddata hash; located on disk, never fetched."""
    if not LANGUAGE_PATTERN.match(language):
        raise AdapterError("unsupported", "invalid language identifier")
    tessdata = _tessdata_dir(_binary_path(binary))
    if tessdata is None:
        return None, None
    trained = tessdata / f"{language}.traineddata"
    if not trained.is_file():
        return None, tessdata
    return hashlib.sha256(trained.read_bytes()).hexdigest(), trained


def _version(binary: Path) -> str:
    try:
        out = subprocess.run(
            [str(binary), "--version"], capture_output=True, text=True, timeout=30, shell=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AdapterError("unsupported", "tesseract executable not runnable") from error
    first = (out.stdout or out.stderr or "").splitlines()
    return first[0].strip() if first else "tesseract (version unavailable)"


def describe(binary: Path | None = None, language: str = DEFAULT_LANGUAGE) -> dict:
    """Complete reader manifest (schema $defs/Reader + ReaderManifest)."""
    binary = _binary_path(binary)
    digest, _ = model_digest(binary, language)
    version_line = _version(binary)
    version = version_line.split()[-1] if version_line else ""
    return {
        "kind": "reader_manifest",
        "schema_version": "1.0.0",
        "reader": {
            "id": READER_ID,
            "name": "Tesseract",
            "version": version,
            "build": version_line,
            "adapter_version": ADAPTER_VERSION,
            "method": "ocr",
            "environment": "native",
            "settings": {
                "normalization": "scalar-whitespace-v1",
                "language": language,
                "psm": DEFAULT_PSM,
                "render_reader_id": "pdfium-native",
                "raster_dpi": None,
                "annotation_mode": "not_applicable",
            },
            "capabilities": [
                {
                    "name": "ocr",
                    "support": "supported" if digest else "unavailable",
                    "limits": [
                        "printed English only; other scripts are preserved by "
                        "native text readers, not claimed from this OCR path",
                        "word confidence is an engine diagnostic, not a quality verdict",
                        "crop padding is 8 raster px or 10% of region height (larger), "
                        "clipped to the raster; original region and padded crop are "
                        "kept separately",
                    ],
                }
            ],
            "model_hashes": [digest] if digest else [],
            "limitations": [
                "single-threaded in-process adapter; wall-time supervision is "
                "enforced per invocation and owned by the native parent task",
                "rasters must come from a recorded named render; the adapter never "
                "fetches models, data or URLs at runtime",
            ],
        },
        "distribution_digest": None,
        "asset_hashes": [digest] if digest else [],
        "execution_policy": "installed_allowlist_no_report_commands",
    }


def open_raster(
    data: bytes,
    digest: str | None,
    generation: int,
    render_meta: dict | None = None,
) -> RasterHandle:
    """Decode and bound the raster; undecodable pixels fail typed."""
    if not isinstance(data, bytes) or not data:
        raise AdapterError("unreadable_pixels", "raster bytes missing or empty")
    computed = hashlib.sha256(data).hexdigest()
    if digest is not None and digest != computed:
        raise AdapterError("parser_error", "raster digest mismatch")
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            width, height = image.size
    except Exception as error:
        raise AdapterError("unreadable_pixels", "raster is not a decodable image") from error
    if width * height > MAX_RASTER_PIXELS:
        raise AdapterError("resource_limit", "raster exceeds pixel budget")
    if render_meta is not None:
        scale = render_meta.get("raster_scale_px_per_pt")
        if scale is not None and (not isinstance(scale, (int, float)) or scale <= 0):
            raise AdapterError("geometry_unavailable", "invalid recorded raster scale")
    return RasterHandle(
        data=data,
        digest=computed,
        generation=generation,
        width=width,
        height=height,
        render_meta=render_meta,
    )


def plan_crop(
    handle: RasterHandle,
    region: tuple[int, int, int, int] | None,
    psm: int = DEFAULT_PSM,
    resize: tuple[float, float] = (1.0, 1.0),
) -> CropPlan:
    """Original region plus clipped padded context; recorded inverse transforms."""
    if psm not in VALID_PSM:
        raise AdapterError("unsupported", "PSM not in the declared set")
    if region is None:
        region = (0, 0, handle.width, handle.height)
    x0, y0, x1, y1 = region
    for value in (x0, y0, x1, y1):
        if not isinstance(value, int) or value != value:
            raise AdapterError("geometry_unavailable", "region coordinates must be integers")
    if not (0 <= x0 < x1 <= handle.width and 0 <= y0 < y1 <= handle.height):
        raise AdapterError("geometry_unavailable", "region outside the recorded raster")
    kx, ky = resize
    if not (isinstance(kx, (int, float)) and kx > 0 and isinstance(ky, (int, float)) and ky > 0):
        raise AdapterError("geometry_unavailable", "resize factors must be positive")
    pad_x = max(CONTEXT_PADDING_MIN_PX, math.ceil(CONTEXT_PADDING_RATIO * (y1 - y0)))
    pad_y = pad_x
    padded = (
        max(0, x0 - pad_x),
        max(0, y0 - pad_y),
        min(handle.width, x1 + pad_x),
        min(handle.height, y1 + pad_y),
    )
    scale = None
    if handle.render_meta is not None:
        scale = handle.render_meta.get("raster_scale_px_per_pt")
    return CropPlan(
        region=region,
        padded=padded,
        psm=psm,
        resize=(float(kx), float(ky)),
        raster_scale=float(scale) if scale else None,
    )


def _occurrence_id(digest: str, ordinal: int) -> str:
    base = f"{READER_ID}-{digest[:12]}-ocr-{ordinal}"
    return re.sub(r"[^a-z0-9_-]", "-", base.lower())[:96]


def _parse_tsv(tsv: str):
    lines = tsv.splitlines()
    if not lines:
        return
    header = lines[0].split("\t")
    try:
        col = {name: header.index(name) for name in ("level", "conf", "text", "left", "top", "width", "height")}
    except ValueError as error:
        raise AdapterError("parser_error", "unexpected TSV layout") from error
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < len(header):
            continue
        try:
            level = int(parts[col["level"]])
            conf = float(parts[col["conf"]])
            left = int(parts[col["left"]])
            top = int(parts[col["top"]])
            width = int(parts[col["width"]])
            height = int(parts[col["height"]])
        except ValueError:
            continue
        text = parts[col["text"]]
        if level == 5 and text.strip():
            yield text, conf, left, top, width, height


def extract(
    handle: RasterHandle,
    plan: dict,
    emit_chunk: Callable[[list[dict]], None],
    cancellation: Callable[[], bool] | None = None,
    binary: Path | None = None,
    timeout_s: float = 120.0,
    crop: CropPlan | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> dict:
    """Terminal OCR extraction over the planned crop; typed terminals only."""
    capability = plan.get("capability", "ocr")

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
    if capability != "ocr":
        return result("unsupported", f"unsupported capability for {READER_ID}: {capability}", 0, [])
    if cancellation is not None and cancellation():
        return result("cancelled", "cancelled by request", 0, [])
    try:
        binary = _binary_path(binary)
    except AdapterError as error:
        return result("unsupported", error.detail, 0, [])

    if crop is None:
        region = plan.get("region")
        region_tuple = tuple(region) if isinstance(region, list) else region
        try:
            crop = plan_crop(handle, region_tuple, psm=DEFAULT_PSM)
        except AdapterError as error:
            return result("failed", f"{error.reason}: {error.detail}", 0, [])
    psm = crop.psm
    try:
        digest_or_none, _ = model_digest(binary, language)
    except AdapterError as error:
        # Includes option-injection attempts via the language identifier.
        return result("unsupported", error.detail, 0, [])
    if digest_or_none is None:
        return result(
            "failed",
            f"missing_model: {language}.traineddata not found next to the binary",
            0,
            [],
        )
    try:
        with Image.open(BytesIO(handle.data)) as image:
            image.load()
            cropped = image.crop(crop.padded)
            kx, ky = crop.resize
            if (kx, ky) != (1.0, 1.0):
                cropped = cropped.resize(
                    (max(1, round(cropped.width * kx)), max(1, round(cropped.height * ky)))
                )
    except Exception as error:
        return result("failed", "unreadable_pixels: raster could not be cropped", 0, [])

    workdir = Path(tempfile.mkdtemp(prefix="inkflip-ocr-"))
    try:
        # Neutral, adapter-generated filename: caller data cannot become an option.
        input_png = workdir / "input.png"
        cropped.save(input_png, format="PNG")
        argv = [
            str(binary),
            str(input_png),
            "stdout",
            "--psm",
            str(psm),
            "tsv",
        ]
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return result("timeout", f"timeout: exceeded {timeout_s}s budget", 0, [])
        except OSError as error:
            return result("unsupported", "tesseract executable not runnable", 0, [])
        stderr = (completed.stderr or "").lower()
        if completed.returncode != 0:
            if "error opening data file" in stderr or f"{language}.traineddata" in stderr:
                return result("failed", f"missing_model: {language} traineddata unreadable", 0, [])
            return result("failed", "parser_error: tesseract exited nonzero", 0, [])

        retained: list[str] = []
        produced = 0
        chunk: list[dict] = []
        ordinal = 0
        for text, conf, left, top, width, height in _parse_tsv(completed.stdout or ""):
            if cancellation is not None and cancellation():
                return result("cancelled", "cancelled by request", produced, retained)
            raster_tl = crop.crop_to_raster(left, top)
            raster_br = crop.crop_to_raster(left + width, top + height)
            canonical_tl = crop.raster_to_canonical(*raster_tl)
            canonical_br = crop.raster_to_canonical(*raster_br)
            if canonical_tl and canonical_br:
                polygon = [
                    [round(canonical_tl[0], 6) + 0.0, round(canonical_tl[1], 6) + 0.0],
                    [round(canonical_br[0], 6) + 0.0, round(canonical_tl[1], 6) + 0.0],
                    [round(canonical_br[0], 6) + 0.0, round(canonical_br[1], 6) + 0.0],
                    [round(canonical_tl[0], 6) + 0.0, round(canonical_br[1], 6) + 0.0],
                ]
                precision = "estimated"
                transform_ids = ["ocr-crop-inverse", "raster-scale-inverse"]
                basis = (
                    f"tesseract word TSV box; inverse crop/resize O then raster "
                    f"scale {crop.raster_scale}; OCR box is an estimated pixel "
                    "interpretation"
                )
            else:
                polygon = None
                precision = "unknown"
                transform_ids = []
                basis = "no recorded raster scale; raw text retained without geometry"
            occurrence = {
                "id": _occurrence_id(handle.digest, ordinal),
                "reader_id": READER_ID,
                "page_index": int(plan.get("page_index", 0)),
                "ordinal": ordinal,
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
                    "precision": precision,
                    "space": "canonical_page",
                    "polygon": polygon,
                    "transform_ids": transform_ids,
                    "basis": basis,
                },
                "engine_score": {
                    "value": max(0.0, min(1.0, conf / 100.0)),
                    "scale_min": 0.0,
                    "scale_max": 1.0,
                    "meaning": "tesseract word confidence (engine diagnostic)",
                },
                "source_asset_id": None,
                "raw_source_locator": f"tesseract:tsv:word[{ordinal}]:psm{psm}",
                "limitations": [],
            }
            ordinal += 1
            chunk.append(occurrence)
            if len(chunk) >= 256:
                emit_chunk(chunk)
                retained.extend(o["id"] for o in chunk)
                produced += len(chunk)
                chunk = []
            if ordinal > MAX_WORD_OCCURRENCES:
                if chunk:
                    emit_chunk(chunk)
                    retained.extend(o["id"] for o in chunk)
                    produced += len(chunk)
                    chunk = []
                return result("failed", "resource_limit: word budget exceeded", produced, retained)
        if chunk:
            emit_chunk(chunk)
            retained.extend(o["id"] for o in chunk)
            produced += len(chunk)
        return result("completed", None, produced, retained)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
