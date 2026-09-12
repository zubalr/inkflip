"""Native rendered-region Tesseract reader adapter (T27).

OCR over a chosen page or region of a bounded, named-renderer raster, per
``planning/architecture/READER_ADAPTER_CONTRACT.md`` ("Tesseract is invoked
with fixed argv and ``shell=False`` ..."), ``planning/architecture/COORDINATES.md``
(ocr space and inverse crop/resize chains) and ``planning/architecture/CAPABILITIES.md``
("Missing model / timeout distinct from unreadable pixels").

Discipline implemented here:

* Fixed argv, ``shell=False``: ``[tesseract, <private>/input.png, stdout,
  --psm <n>, -l <language>, --tessdata-dir <resolved>, tsv]``. The caller never
  names files: the crop is written under a neutral name inside a private
  temporary directory, and ``language`` is validated against
  ``^[a-z0-9_-]{1,32}$`` so no option injection is possible. The language and
  tessdata directory are selected explicitly in argv, so the recorded manifest
  identity is exactly what the invoked engine loads.
* No URL or runtime model fetch: the traineddata file is located on disk and
  hashed. An explicit ``TESSDATA_PREFIX`` is authoritative (the engine reads
  the same variable) and is never silently overridden or supplemented;
  without it, candidate directories next to the (symlink-resolved) binary are
  probed per language, so a directory is only used when it actually holds
  ``<language>.traineddata``. A missing model is a distinct typed failure from
  a missing binary, an undecodable raster (``unreadable_pixels``) or a
  wall-time timeout.
* Context padding is 8 raster pixels or 10 % of the region height (larger),
  clipped to the raster. Original region and padded crop are kept separately;
  the crop/resize transform ``O`` is recorded with its explicit inverse so TSV
  word boxes map back to raster and canonical coordinates.
* Word TSV rows become occurrences with verbatim raw text (punctuation and
  case preserved), confidence as a diagnostic ``engine_score`` (never quality
  truth), and ``estimated`` canonical geometry when the recorded named render
  carries a ``canonical_to_raster`` affine (``Scale(s)*R``, validated and
  inverted once at open; all four OCR box corners are mapped individually).
  Without it, geometry is ``unknown`` with a null polygon and the raw text is
  retained — the legacy ``raster_scale_px_per_pt`` scalar alone never
  authorizes geometry.
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
import sys
import tempfile
from dataclasses import dataclass, replace as dataclasses_replace
from io import BytesIO
from pathlib import Path
from typing import Callable

from PIL import Image

from inkflip.contracts import apply as _contract_apply
from inkflip.contracts import inverse as _contract_inverse

READER_ID = "tesseract-native"
# Pinned by the shared contract schema ($defs/Reader.adapter_version const);
# behavior changes are documented in the task evidence instead.
ADAPTER_VERSION = "1.0.0"
DEFAULT_LANGUAGE = "eng"
# Measured on the T05 fixtures (macOS implementation run): PSM 6 (uniform
# block) dropped the isolated '$100' amount line there; the native full-page
# default is tesseract's own automatic segmentation (PSM 3). The Linux amd64
# spot-check of 2026-09-12 (artifacts/tasks/T27/psm6-spotcheck.log) read the
# line under PSM 6 as well, so the default is kept pending the coordinator's
# contract decision. A deliberately single-line user region uses PSM 7; the
# choice is recorded on the emitted occurrences.
DEFAULT_PSM = 3
SINGLE_LINE_PSM = 7
CONTEXT_PADDING_MIN_PX = 8
CONTEXT_PADDING_RATIO = 0.10
MAX_RASTER_PIXELS = 40_000_000
MAX_WORD_OCCURRENCES = 5000
LANGUAGE_PATTERN = re.compile(r"^[a-z0-9_-]{1,32}$")
VALID_PSM = {3, 4, 6, 7, 8, 11, 12, 13}
# Geometry authorization (owned API decision, docs/proposals/T27.md): precise
# OCR geometry requires a recorded canonical_to_raster render transform
# (Scale(s)*R, six-component affine per COORDINATES.md). The legacy
# raster_scale_px_per_pt scalar stays a diagnostic and never authorizes
# geometry on its own.
ROUNDTRIP_TOLERANCE_PT = 1e-5
CANONICAL_COORD_LIMIT = 1e9
TSV_COORD_LIMIT = 2**31 - 1


class AdapterError(Exception):
    """Typed failure carrying a public reason code."""

    def __init__(self, reason: str, detail: str):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


@dataclass
class RasterHandle:
    """Bounded raster handle over immutable PNG bytes plus named-render metadata.

    ``canonical_to_raster`` is the validated six-component affine recorded by
    the named render (``Scale(s)*R`` per COORDINATES.md); ``canonical_from_raster``
    is its inverse, derived once at open. Both are ``None`` when unrecorded —
    geometry is then ``unknown`` regardless of any legacy scalar.
    """

    data: bytes
    digest: str
    generation: int
    width: int
    height: int
    render_meta: dict | None
    closed: bool = False
    canonical_to_raster: tuple[float, ...] | None = None
    canonical_from_raster: tuple[float, ...] | None = None

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
    resize: tuple[float, float]  # requested kx, ky applied to the padded crop
    raster_scale: float | None  # legacy diagnostic px per physical point
    # Appended optional fields preserve positional construction. Effective
    # factors come from the ACTUAL integer destination dimensions; the raster
    # inverse is snapshotted from the handle, never caller-invented.
    effective_resize: tuple[float, float] | None = None
    canonical_from_raster: tuple[float, ...] | None = None

    @property
    def padding(self) -> tuple[int, int]:
        return (self.padded[0] - self.region[0], self.padded[1] - self.region[1])

    def crop_to_raster(self, x: float, y: float) -> tuple[float, float]:
        """Inverse O step 1: padded-crop pixel -> raster pixel (resize undone).

        Uses the effective factors recorded from the actual Pillow output
        dimensions so the recorded inverse matches the resize performed."""
        kx, ky = self.effective_resize or self.resize
        return (x / kx + self.padded[0], y / ky + self.padded[1])

    def raster_to_canonical(self, x: float, y: float) -> tuple[float, float] | None:
        """Legacy diagnostic: raster pixel -> canonical points by scale alone.

        Never used to authorize geometry; the matrix path in ``extract`` is
        the authoritative inverse."""
        if self.raster_scale is None or self.raster_scale <= 0:
            return None
        return (x / self.raster_scale, y / self.raster_scale)


def _finite_number(value: object) -> bool:
    """Finite real number within float range. Bounded comparison only:
    math.isfinite on an arbitrary Python bigint raises OverflowError, so
    10**309 and friends are rejected before any float conversion."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return -sys.float_info.max <= value <= sys.float_info.max


def _validate_matrix(matrix: object) -> tuple[float, ...]:
    """Validate a six-component canonical_to_raster affine; typed refusals only."""
    if isinstance(matrix, (tuple, list)):
        if len(matrix) != 6:
            raise AdapterError(
                "geometry_unavailable", "canonical_to_raster must have exactly 6 components"
            )
        components = tuple(matrix)
    else:
        raise AdapterError(
            "geometry_unavailable", "canonical_to_raster must be a 6-component sequence"
        )
    for component in components:
        if not _finite_number(component):
            raise AdapterError(
                "geometry_unavailable", "canonical_to_raster components must be finite numbers"
            )
    return tuple(float(component) for component in components)


def _matrix_inverse(matrix: tuple[float, ...]) -> tuple[float, ...]:
    """Contract inverse plus owned stability checks (finite, bounded round-trip)."""
    try:
        inverse = _contract_inverse(list(matrix))
    except Exception as error:  # ContractError from the singular-transform require
        raise AdapterError(
            "geometry_unavailable", "canonical_to_raster is singular or invalid"
        ) from error
    if not all(math.isfinite(component) for component in inverse):
        raise AdapterError("geometry_unavailable", "canonical_to_raster inverse is not finite")
    return tuple(float(component) for component in inverse)


def _matrix_roundtrip_ok(
    matrix: tuple[float, ...], inverse: tuple[float, ...], width: int, height: int
) -> bool:
    """Round-trip raster corners through inverse and forward within the
    contract budget, and keep the recovered canonical extent bounded."""
    determinant = matrix[0] * matrix[3] - matrix[1] * matrix[2]
    try:
        scale_estimate = math.sqrt(abs(determinant))
    except (OverflowError, ValueError):
        return False
    if not math.isfinite(scale_estimate) or scale_estimate <= 0:
        return False
    tolerance_px = ROUNDTRIP_TOLERANCE_PT * scale_estimate
    for corner in ((0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height))):
        canonical = _contract_apply(inverse, corner)
        if not math.isfinite(canonical[0]) or not math.isfinite(canonical[1]):
            return False
        if max(abs(canonical[0]), abs(canonical[1])) > CANONICAL_COORD_LIMIT:
            return False
        back = _contract_apply(matrix, canonical)
        error = math.hypot(back[0] - corner[0], back[1] - corner[1])
        if not math.isfinite(error) or error > tolerance_px:
            return False
    return True


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


def _tessdata_candidates(binary: Path) -> list[Path]:
    """Ordered tessdata candidates. An explicit ``TESSDATA_PREFIX`` is
    authoritative — tesseract itself reads the same variable — so it is never
    silently overridden or supplemented: a model missing there is a missing
    model, full stop. Without it, directories next to the (symlink-resolved)
    binary are probed, mirroring the engine's relative fallback."""
    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        return [Path(env)]
    resolved = binary.resolve()
    candidates = [
        resolved.parent.parent / "share" / "tessdata",
        resolved.parent / "tessdata",
        binary.parent.parent / "share" / "tessdata",
        binary.parent / "tessdata",
    ]
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _tessdata_dir(binary: Path, language: str) -> Path | None:
    """The directory whose ``<language>.traineddata`` the engine will load:
    candidates are probed per language, not first-existing-directory-wins
    (a directory without the requested model never shadows a later one)."""
    for candidate in _tessdata_candidates(binary):
        if (candidate / f"{language}.traineddata").is_file():
            return candidate
    return None


def model_digest(binary: Path | None = None, language: str = DEFAULT_LANGUAGE) -> tuple[str | None, Path | None]:
    """Exact local traineddata hash; located on disk, never fetched. The
    returned path is the file whose bytes are hashed and the exact file the
    engine is pointed at via ``--tessdata-dir``."""
    if not LANGUAGE_PATTERN.match(language):
        raise AdapterError("unsupported", "invalid language identifier")
    tessdata = _tessdata_dir(_binary_path(binary), language)
    if tessdata is None:
        return None, None
    trained = tessdata / f"{language}.traineddata"
    try:
        data = trained.read_bytes()
    except OSError:
        # Sanitized: no path, no errno text; distinct from a missing model.
        raise AdapterError("model_integrity", "traineddata exists but could not be read")
    return hashlib.sha256(data).hexdigest(), trained


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
    digest, trained = model_digest(binary, language)
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
                        "precise OCR geometry requires the recorded "
                        "canonical_to_raster render transform; scale-only "
                        "metadata is a legacy diagnostic and yields unknown "
                        "geometry",
                        "crop padding is 8 raster px or 10% of region height (larger), "
                        "clipped to the raster; original region and padded crop are "
                        "kept separately",
                    ]
                    + (
                        [
                            "model identity: engine is invoked with -l "
                            f"{language} --tessdata-dir {trained.parent}; the hashed "
                            "model file is the exact file the engine loads"
                        ]
                        if trained
                        else []
                    ),
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
            # Budget check on the declared size BEFORE decode: a hostile or
            # accidental oversized header must not allocate first (F6).
            width, height = image.size
            if width * height > MAX_RASTER_PIXELS:
                raise AdapterError("resource_limit", "raster exceeds pixel budget")
            image.load()
    except AdapterError:
        raise
    except Exception as error:
        raise AdapterError("unreadable_pixels", "raster is not a decodable image") from error
    if render_meta is not None:
        scale = render_meta.get("raster_scale_px_per_pt")
        if scale is not None and (not _finite_number(scale) or scale <= 0):
            raise AdapterError("geometry_unavailable", "invalid recorded raster scale")
    canonical_to_raster = None
    canonical_from_raster = None
    if render_meta is not None and render_meta.get("canonical_to_raster") is not None:
        # An explicitly recorded matrix is validated and snapshotted; an
        # invalid one fails typed instead of degrading to the scalar path.
        canonical_to_raster = _validate_matrix(render_meta["canonical_to_raster"])
        canonical_from_raster = _matrix_inverse(canonical_to_raster)
        if not _matrix_roundtrip_ok(canonical_to_raster, canonical_from_raster, width, height):
            raise AdapterError(
                "geometry_unavailable",
                "canonical_to_raster inverse is unstable or out of bounds for this raster",
            )
    return RasterHandle(
        data=data,
        digest=computed,
        generation=generation,
        width=width,
        height=height,
        render_meta=render_meta,
        canonical_to_raster=canonical_to_raster,
        canonical_from_raster=canonical_from_raster,
    )


def _validate_psm(psm: object) -> int:
    """Type-check before set membership: an unhashable psm must not raise raw."""
    if isinstance(psm, bool) or not isinstance(psm, int) or psm not in VALID_PSM:
        raise AdapterError("unsupported", "PSM not in the declared set")
    return psm


def _validate_resize_factors(resize: object) -> tuple[float, float]:
    """Exact 2-sequence of finite positive numbers; typed before unpacking."""
    if not isinstance(resize, (tuple, list)) or len(resize) != 2:
        raise AdapterError("geometry_unavailable", "resize must be a (kx, ky) pair")
    kx, ky = resize
    for factor in (kx, ky):
        if not _finite_number(factor) or factor <= 0:
            raise AdapterError("geometry_unavailable", "resize factors must be positive finite numbers")
    return (float(kx), float(ky))


def _validate_rect(rect: object, handle: RasterHandle, label: str) -> tuple[int, int, int, int]:
    """A crop rectangle is a 4-sequence of integers inside the raster; every
    violation is a typed geometry_unavailable, never a raw unpack error."""
    if isinstance(rect, tuple) or isinstance(rect, list):
        if len(rect) != 4:
            raise AdapterError("geometry_unavailable", f"{label} must have exactly 4 values")
        values = tuple(rect)
    else:
        raise AdapterError("geometry_unavailable", f"{label} must be a (x0, y0, x1, y1) sequence")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise AdapterError("geometry_unavailable", f"{label} coordinates must be integers")
    x0, y0, x1, y1 = values
    if not (0 <= x0 < x1 <= handle.width and 0 <= y0 < y1 <= handle.height):
        raise AdapterError("geometry_unavailable", f"{label} outside the recorded raster")
    return (x0, y0, x1, y1)


def _validate_crop_plan(crop: CropPlan, handle: RasterHandle) -> None:
    """Caller-built CropPlans get the same discipline as plan_crop output."""
    _validate_psm(crop.psm)
    _validate_rect(crop.region, handle, "region")
    _validate_rect(crop.padded, handle, "padded crop")
    _validate_resize_factors(crop.resize)
    if crop.effective_resize is not None:
        _validate_resize_factors(crop.effective_resize)
    if crop.raster_scale is not None:
        scale = crop.raster_scale
        if not _finite_number(scale) or scale <= 0:
            raise AdapterError("geometry_unavailable", "recorded raster scale must be positive")
    if crop.canonical_from_raster is not None:
        # Validate shape and values BEFORE any conversion; a caller-built
        # inverse never wins: it must match the handle's validated snapshot
        # exactly, or the plan is refused.
        inverse = crop.canonical_from_raster
        if not isinstance(inverse, (tuple, list)) or len(inverse) != 6:
            raise AdapterError(
                "geometry_unavailable", "crop transform must be a 6-component sequence"
            )
        if not all(_finite_number(component) for component in inverse):
            raise AdapterError(
                "geometry_unavailable", "crop transform components must be finite numbers"
            )
        if (
            handle.canonical_from_raster is None
            or tuple(float(component) for component in inverse) != handle.canonical_from_raster
        ):
            raise AdapterError(
                "geometry_unavailable",
                "crop transform does not match the recorded raster provenance",
            )


def plan_crop(
    handle: RasterHandle,
    region: tuple[int, int, int, int] | None,
    psm: int = DEFAULT_PSM,
    resize: tuple[float, float] = (1.0, 1.0),
) -> CropPlan:
    """Original region plus clipped padded context; recorded inverse transforms."""
    _validate_psm(psm)
    if region is None:
        region = (0, 0, handle.width, handle.height)
    x0, y0, x1, y1 = _validate_rect(region, handle, "region")
    kx, ky = _validate_resize_factors(resize)
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
        canonical_from_raster=handle.canonical_from_raster,
    )


def _occurrence_id(digest: str, page_index: int, ordinal: int) -> str:
    # Page-scoped like the sibling pdfium adapter: byte-identical rasters from
    # two pages of one document must not collide on occurrence id.
    base = f"{READER_ID}-{digest[:12]}-p{page_index}-ocr-{ordinal}"
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
            # A truncated row would silently lose coverage if skipped: fail
            # the check typed instead of overstating completeness.
            raise AdapterError("parser_error", "truncated TSV row")
        try:
            level = int(parts[col["level"]])
        except ValueError as error:
            raise AdapterError("parser_error", "malformed TSV row level") from error
        if level != 5:
            continue
        # A word row we would emit must be fully valid: silently dropping a
        # malformed engine row would overstate coverage.
        try:
            conf = float(parts[col["conf"]])
            left = int(parts[col["left"]])
            top = int(parts[col["top"]])
            width = int(parts[col["width"]])
            height = int(parts[col["height"]])
        except ValueError as error:
            raise AdapterError("parser_error", "malformed TSV word row") from error
        text = parts[col["text"]]
        if not text.strip():
            continue
        if not math.isfinite(conf):
            raise AdapterError("parser_error", "nonfinite TSV confidence")
        for value in (left, top, width, height):
            if abs(value) > TSV_COORD_LIMIT:
                raise AdapterError("parser_error", "TSV coordinate out of representable range")
        if width <= 0 or height <= 0:
            # A zero or negative extent is a degenerate/reversed box: typed
            # terminal, never estimated invalid geometry or silent success.
            raise AdapterError("parser_error", "nonpositive TSV word extent")
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
        if plan.get("region_id") is not None:
            # A region-scoped plan needs an explicitly resolved crop; silently
            # widening it to full-page OCR would misstate coverage.
            return result(
                "unsupported",
                "region-scoped OCR requires an explicitly resolved crop for this adapter path",
                0,
                [],
            )
        try:
            crop = plan_crop(handle, None, psm=DEFAULT_PSM)
        except AdapterError as error:
            return result("failed", f"{error.reason}: {error.detail}", 0, [])
    else:
        try:
            _validate_crop_plan(crop, handle)
        except AdapterError as error:
            return result(
                "unsupported" if error.reason == "unsupported" else "failed",
                f"{error.reason}: {error.detail}",
                0,
                [],
            )
    psm = crop.psm
    try:
        digest_or_none, trained = model_digest(binary, language)
    except AdapterError as error:
        if error.reason == "model_integrity":
            return result("failed", f"model_integrity: {error.detail}", 0, [])
        # Includes option-injection attempts via the language identifier.
        return result("unsupported", error.detail, 0, [])
    if digest_or_none is None:
        return result(
            "failed",
            f"missing_model: {language}.traineddata not found for the resolved tessdata directory",
            0,
            [],
        )
    tessdata_dir = trained.parent
    try:
        with Image.open(BytesIO(handle.data)) as image:
            image.load()
            cropped = image.crop(crop.padded)
    except Exception as error:
        return result("failed", "unreadable_pixels: raster could not be cropped", 0, [])
    src_w, src_h = cropped.size
    kx, ky = crop.resize
    # Bound the OUTPUT before Pillow allocates it: the input header cap alone
    # does not cover an excessive upscale requested on a small crop.
    if not (math.isfinite(src_w * kx) and math.isfinite(src_h * ky)):
        return result("failed", "resource_limit: resize target exceeds the pixel budget", 0, [])
    dest_w = max(1, round(src_w * kx))
    dest_h = max(1, round(src_h * ky))
    if dest_w * dest_h > MAX_RASTER_PIXELS:
        return result("failed", "resource_limit: resize target exceeds the pixel budget", 0, [])
    if (dest_w, dest_h) != (src_w, src_h):
        try:
            cropped = cropped.resize((dest_w, dest_h))
        except MemoryError as error:
            return result("failed", "resource_limit: resize allocation exceeded the pixel budget", 0, [])
        except OSError as error:
            return result("failed", "unreadable_pixels: resized raster could not be produced", 0, [])
    # The recorded inverse must describe the resize actually performed: the
    # requested factors are rounded to integer destination dimensions.
    crop = dataclasses_replace(
        crop,
        effective_resize=(
            dest_w / src_w if src_w else 1.0,
            dest_h / src_h if src_h else 1.0,
        ),
    )

    try:
        workdir = Path(tempfile.mkdtemp(prefix="inkflip-ocr-"))
    except OSError as error:
        return result("failed", "parser_error: could not create the private OCR workdir", 0, [])
    try:
        # Neutral, adapter-generated filename: caller data cannot become an option.
        input_png = workdir / "input.png"
        try:
            cropped.save(input_png, format="PNG")
        except OSError as error:
            return result("failed", "parser_error: could not write the cropped raster", 0, [])
        argv = [
            str(binary),
            str(input_png),
            "stdout",
            "--psm",
            str(psm),
            "-l",
            language,
            "--tessdata-dir",
            str(tessdata_dir),
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
        try:
            for text, conf, left, top, width, height in _parse_tsv(completed.stdout or ""):
                if cancellation is not None and cancellation():
                    return result("cancelled", "cancelled by request", produced, retained)
                if ordinal >= MAX_WORD_OCCURRENCES:
                    # The budget bounds what is emitted: word 5001 terminates the
                    # check as resource_limit with exactly the capped 5000 kept.
                    if chunk:
                        emit_chunk(chunk)
                        retained.extend(o["id"] for o in chunk)
                        produced += len(chunk)
                        chunk = []
                    return result("failed", "resource_limit: word budget exceeded", produced, retained)
                corners = (
                    (left, top),
                    (left + width, top),
                    (left + width, top + height),
                    (left, top + height),
                )
                if handle.canonical_from_raster is not None:
                    # Map all four actual OCR box corners through the effective
                    # resize inverse, the crop offset and the recorded render
                    # inverse; keep the quad, never rebuild a 2-corner box.
                    polygon = []
                    for corner in corners:
                        raster_point = crop.crop_to_raster(*corner)
                        canonical_point = _contract_apply(handle.canonical_from_raster, raster_point)
                        if not (
                            math.isfinite(canonical_point[0]) and math.isfinite(canonical_point[1])
                        ):
                            raise AdapterError(
                                "parser_error", "nonfinite OCR box mapping"
                            )
                        polygon.append(
                            [
                                round(canonical_point[0], 6) + 0.0,
                                round(canonical_point[1], 6) + 0.0,
                            ]
                        )
                    precision = "estimated"
                    transform_ids = ["ocr-crop-inverse", "canonical-render-inverse"]
                    basis = (
                        "tesseract word TSV box; inverse crop/effective-resize O then "
                        "inverse recorded canonical_to_raster render transform; OCR box "
                        "is an estimated pixel interpretation"
                    )
                else:
                    polygon = None
                    precision = "unknown"
                    transform_ids = []
                    basis = (
                        "no recorded canonical_to_raster render transform; raw text "
                        "retained without geometry"
                    )
                occurrence = {
                    "id": _occurrence_id(handle.digest, int(plan.get("page_index", 0)), ordinal),
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
        except AdapterError as error:
            # A malformed engine row fails the check typed while keeping every
            # already emitted occurrence.
            if chunk:
                emit_chunk(chunk)
                retained.extend(o["id"] for o in chunk)
                produced += len(chunk)
                chunk = []
            return result("failed", f"{error.reason}: {error.detail}", produced, retained)
        if chunk:
            emit_chunk(chunk)
            retained.extend(o["id"] for o in chunk)
            produced += len(chunk)
        return result("completed", None, produced, retained)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
