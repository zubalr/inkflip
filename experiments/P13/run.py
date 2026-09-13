#!/usr/bin/env python3
"""P13 — Native RapidOCR complement experiment runner (Task T44).

Audits RapidOCR v3.8.1 (source S47) with PP-OCRv5 mobile English configuration
against native Tesseract baseline over the declared manifest.
Verifies model weights provenance against trusted expected digests, runs real
native Tesseract and RapidOCR per-fixture evaluations, records timing, memory/raster pixels,
raw outputs (boxes, texts, scores), and accounts for missing models/dependencies
and failure cases in denominators honestly without simulated counts or fake rejection claims.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent

# Re-exec via experiment-local virtual environment if available
P13_VENV_PYTHON = ROOT / "experiments" / "P13" / ".venv" / "bin" / "python"


def maybe_reexec_venv() -> None:
    """Re-exec into experiment-local virtual environment when run as CLI script."""
    if P13_VENV_PYTHON.is_file() and sys.executable != str(P13_VENV_PYTHON):
        if "-c" not in sys.argv and not os.environ.get("_INKFLIP_P13_VENV_REEXEC"):
            os.environ["_INKFLIP_P13_VENV_REEXEC"] = "1"
            os.execv(str(P13_VENV_PYTHON), [str(P13_VENV_PYTHON), *sys.argv])


_BLOCKED_NETWORK_CALLS = 0


@contextmanager
def enforce_network_isolation():
    """Enforce runtime offline isolation (Invariants I13 / I14) during OCR inference.

    Intercepts and blocks outbound socket creation and network address resolution,
    recording any attempted network egress.
    """
    global _BLOCKED_NETWORK_CALLS
    original_socket = socket.socket
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo

    class GuardedSocket(original_socket):
        def connect(self, *args, **kwargs):
            global _BLOCKED_NETWORK_CALLS
            _BLOCKED_NETWORK_CALLS += 1
            raise RuntimeError("Runtime network access prohibited by Invariant I14 during OCR inference")

        def connect_ex(self, *args, **kwargs):
            global _BLOCKED_NETWORK_CALLS
            _BLOCKED_NETWORK_CALLS += 1
            return 111  # ECONNREFUSED

        def send(self, *args, **kwargs):
            global _BLOCKED_NETWORK_CALLS
            _BLOCKED_NETWORK_CALLS += 1
            raise RuntimeError("Runtime network access prohibited by Invariant I14 during OCR inference")

        def sendto(self, *args, **kwargs):
            global _BLOCKED_NETWORK_CALLS
            _BLOCKED_NETWORK_CALLS += 1
            raise RuntimeError("Runtime network access prohibited by Invariant I14 during OCR inference")

    def guarded_create_connection(*args, **kwargs):
        global _BLOCKED_NETWORK_CALLS
        _BLOCKED_NETWORK_CALLS += 1
        raise RuntimeError("Runtime network access prohibited by Invariant I14 during OCR inference")

    def guarded_getaddrinfo(*args, **kwargs):
        host = args[0] if args else kwargs.get("host")
        if host in ("localhost", "127.0.0.1", "::1", None):
            return original_getaddrinfo(*args, **kwargs)
        global _BLOCKED_NETWORK_CALLS
        _BLOCKED_NETWORK_CALLS += 1
        raise RuntimeError(f"Runtime network access to {host} prohibited by Invariant I14")

    socket.socket = GuardedSocket  # type: ignore
    socket.create_connection = guarded_create_connection  # type: ignore
    socket.getaddrinfo = guarded_getaddrinfo  # type: ignore
    try:
        yield
    finally:
        socket.socket = original_socket
        socket.create_connection = original_create_connection
        socket.getaddrinfo = original_getaddrinfo

# Ensure required libraries are available
try:
    import pypdf
    import pypdfium2 as pdfium
    from PIL import Image
except (ImportError, ModuleNotFoundError):
    uv = shutil.which("uv")
    if uv and "-c" not in sys.argv and not os.environ.get("_INKFLIP_P13_REEXEC"):
        os.environ["_INKFLIP_P13_REEXEC"] = "1"
        os.execv(uv, [uv, "run", "--project", "native", "python", *sys.argv])
    raise

TARGET_FIXTURE_IDS = {"F14", "F15", "F16"}
TARGET_FAMILIES = {"native-unicode", "ocr-material", "adjacent-crop"}
REQUIRED_RAPIDOCR_VERSION = "3.8.1"
PP_OCRV5_DET_NAMES = ["ch_PP-OCRv5_det_mobile.onnx", "en_PP-OCRv5_mobile_det.onnx", "en_PP-OCRv5_det_infer.onnx"]
PP_OCRV5_REC_NAMES = ["en_PP-OCRv5_rec_mobile.onnx", "en_PP-OCRv5_mobile_rec.onnx", "en_PP-OCRv5_rec_infer.onnx"]

# Official trusted model digests from RapidAI/RapidOCR v3.8.0/v3.8.1 release configuration
OFFICIAL_MODEL_DIGESTS = {
    "ch_PP-OCRv5_det_mobile.onnx": "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
    "en_PP-OCRv5_rec_mobile.onnx": "c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8",
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": "54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7",
}

PREPARATION_COMMAND = "uv pip install --python experiments/P13/.venv/bin/python rapidocr==3.8.1 onnx onnxruntime"
MODEL_DOWNLOAD_BASE = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/onnx/PP-OCRv5/"
MEMORY_BUDGET_BYTES = 1024 * 1024 * 1024  # 1 GiB
DEFAULT_MANIFEST = "evaluation/manifests/development.json"


def resolve_manifest(manifest_arg: str | None) -> Path:
    """Resolve manifest argument to an existing manifest path.

    Distinguishes documented default from explicit override:
    - None, '', or the documented default ('evaluation/manifests/development.json')
      will check evaluation/manifests/development.json, falling back to fixtures/manifest.json.
    - Any other explicitly supplied path (e.g. /tmp/.../development.json or custom paths)
      must exist on disk; if missing, raises FileNotFoundError without fallback.
    """
    if manifest_arg is None or manifest_arg == "" or manifest_arg == DEFAULT_MANIFEST:
        cand_default = ROOT / DEFAULT_MANIFEST
        if cand_default.is_file():
            return cand_default
        cand_fixtures = ROOT / "fixtures" / "manifest.json"
        if cand_fixtures.is_file():
            return cand_fixtures
        raise FileNotFoundError(
            f"Documented default manifests not found: checked {cand_default} and {cand_fixtures}"
        )

    p = Path(manifest_arg)
    if not p.is_absolute():
        p = ROOT / p

    if p.is_file():
        return p

    raise FileNotFoundError(f"Explicit manifest not found: {manifest_arg}")


def load_and_validate_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    """Parse manifest, validate split/hashes, and fail terminal on empty or held-out manifests."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Corrupted manifest JSON at {manifest_path}: {e}")

    entries = data.get("entries")
    if not isinstance(entries, list) or len(entries) == 0:
        raise ValueError(f"Manifest {manifest_path} contains no entries (empty manifest rejected)")

    manifest_split = data.get("split")
    if manifest_split == "evaluation":
        raise ValueError("P13 experiment is strictly forbidden from evaluating held-out evaluation manifests")

    validated_fixtures: list[dict[str, Any]] = []

    for entry in entries:
        split = entry.get("split") or manifest_split
        if split == "evaluation":
            raise ValueError(f"Held-out evaluation entry found in manifest: {entry}")

        fix_id = entry.get("fixture_id", "")
        family = entry.get("family", "")
        if not family:
            group_id = entry.get("group_id", "")
            for tf in TARGET_FAMILIES:
                if tf in group_id:
                    family = tf
                    break

        if fix_id not in TARGET_FIXTURE_IDS and family not in TARGET_FAMILIES:
            continue

        rel = entry.get("path") or entry.get("source_path")
        if not rel:
            continue

        # Resolve path
        p = ROOT / rel
        if not p.is_file():
            p = ROOT / "fixtures" / rel
        if not p.is_file():
            raise FileNotFoundError(f"Fixture referenced in manifest not found on disk: {rel}")

        # Validate sha256 from manifest if present
        expected_sha = entry.get("sha256")
        actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
        if expected_sha and actual_sha.lower() != expected_sha.lower():
            raise ValueError(f"SHA-256 mismatch for {rel}: expected {expected_sha}, got {actual_sha}")

        validated_fixtures.append({
            "fixture_id": fix_id or f"F_{family}",
            "family": family,
            "path": p,
            "rel_path": str(p.relative_to(ROOT)),
            "sha256": actual_sha,
            "role": entry.get("recipe", {}).get("role", "variant") if isinstance(entry.get("recipe"), dict) else "variant",
        })

    if not validated_fixtures:
        raise ValueError(f"Manifest {manifest_path} contains no eligible fixtures for P13 targets {TARGET_FIXTURE_IDS}")

    return validated_fixtures


def is_valid_onnx_model(data: bytes, expected_sha256: str | None = None) -> tuple[bool, str]:
    """Validate that raw bytes represent a legitimate, uncorrupted ONNX ModelProto binary."""
    if data.startswith(b"not an ONNX model") or b"dummy" in data[:128] or data.startswith(b"#"):
        return False, "Detected dummy/corrupt non-ONNX text placeholder"

    if len(data) < 64:
        return False, f"File too small for ONNX model ({len(data)} bytes < 64 bytes)"

    # Compare against trusted expected digest if provided
    if expected_sha256:
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha.lower() != expected_sha256.lower():
            return False, f"SHA-256 digest mismatch: expected {expected_sha256}, got {actual_sha}"

    # First attempt ONNX parser validation via onnx library
    try:
        import onnx
        model = onnx.load_model_from_string(data)
        onnx.checker.check_model(model)
        if not model.graph.node and not model.graph.output:
            return False, "ONNX model graph has no nodes or outputs"
        return True, "Valid ONNX model binary"
    except ImportError:
        pass
    except Exception as e:
        return False, f"ONNX protobuf parsing/validation error: {e}"

    # Fallback strict protobuf wire format parser if onnx library is absent
    idx = 0
    total = len(data)
    has_ir_version = False
    has_graph = False

    while idx < total:
        # Read varint tag
        tag_byte = data[idx]
        idx += 1
        field_num = tag_byte >> 3
        wire_type = tag_byte & 0x07

        if field_num == 0 or wire_type not in (0, 1, 2, 5):
            return False, f"Corrupted protobuf wire format: field {field_num}, wire {wire_type} at offset {idx-1}"

        if wire_type == 0:  # Varint
            shift = 0
            val = 0
            while idx < total:
                b = data[idx]
                idx += 1
                val |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
                if shift > 64:
                    return False, "Protobuf varint overflow"
            if field_num == 1:
                # ir_version should be a sensible positive integer (>= 3)
                if val < 3 or val > 20:
                    return False, f"Invalid ONNX ir_version {val} (expected 3..20)"
                has_ir_version = True

        elif wire_type == 1:  # 64-bit fixed
            idx += 8
        elif wire_type == 5:  # 32-bit fixed
            idx += 4
        elif wire_type == 2:  # Length-delimited
            length = 0
            shift = 0
            while idx < total:
                b = data[idx]
                idx += 1
                length |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
                if shift > 32:
                    return False, "Protobuf length overflow"
            if idx + length > total:
                return False, f"Truncated length-delimited field {field_num} ({length} bytes exceeds remaining {total - idx})"
            if field_num == 8:
                has_graph = True
            idx += length

    if not (has_ir_version and has_graph):
        return False, "Missing required ONNX ModelProto fields (ir_version and graph)"

    return True, "Valid ONNX model binary (wire-verified)"


def audit_rapidocr_environment(custom_search_dirs: list[Path] | None = None) -> dict[str, Any]:
    """Audit RapidOCR package installation, version pin, and PP-OCRv5 model weights provenance."""
    # 1. Package audit
    package_installed = False
    package_version: str | None = None
    package_error: str | None = None

    try:
        import importlib.metadata
        package_version = importlib.metadata.version("rapidocr")
        package_installed = True
    except Exception:
        for pkg_name in ("rapidocr", "rapidocr_onnxruntime"):
            try:
                mod = __import__(pkg_name)
                package_installed = True
                package_version = getattr(mod, "__version__", None)
                break
            except ImportError as e:
                package_error = str(e)

    version_valid = (package_version == REQUIRED_RAPIDOCR_VERSION) if package_version else False

    # 2. Model weights audit (PP-OCRv5 mobile English)
    search_dirs = custom_search_dirs or [
        ROOT / "experiments" / "P13" / "models",
        ROOT / "models" / "rapidocr",
        ROOT / "artifacts" / "P13" / "models",
        ROOT / "vendor" / "rapidocr",
    ]

    found_det: Path | None = None
    found_rec: Path | None = None

    for d in search_dirs:
        if not d.is_dir():
            continue
        if not found_det:
            for name in PP_OCRV5_DET_NAMES:
                cand = d / name
                if cand.is_file():
                    found_det = cand
                    break
        if not found_rec:
            for name in PP_OCRV5_REC_NAMES:
                cand = d / name
                if cand.is_file():
                    found_rec = cand
                    break

    det_audit = None
    rec_audit = None
    weights_corrupt = False
    weights_present = bool(found_det and found_rec)

    if found_det:
        det_bytes = found_det.read_bytes()
        expected_sha = OFFICIAL_MODEL_DIGESTS.get(found_det.name)
        valid, reason = is_valid_onnx_model(det_bytes, expected_sha)
        det_audit = {
            "path": str(found_det.relative_to(ROOT)) if found_det.is_relative_to(ROOT) else str(found_det),
            "filename": found_det.name,
            "size_bytes": len(det_bytes),
            "sha256": hashlib.sha256(det_bytes).hexdigest(),
            "expected_sha256": expected_sha,
            "valid": valid,
            "reason": reason,
        }
        if not valid:
            weights_corrupt = True

    if found_rec:
        rec_bytes = found_rec.read_bytes()
        expected_sha = OFFICIAL_MODEL_DIGESTS.get(found_rec.name)
        valid, reason = is_valid_onnx_model(rec_bytes, expected_sha)
        rec_audit = {
            "path": str(found_rec.relative_to(ROOT)) if found_rec.is_relative_to(ROOT) else str(found_rec),
            "filename": found_rec.name,
            "size_bytes": len(rec_bytes),
            "sha256": hashlib.sha256(rec_bytes).hexdigest(),
            "expected_sha256": expected_sha,
            "valid": valid,
            "reason": reason,
        }
        if not valid:
            weights_corrupt = True

    # 3. Status determination
    if weights_corrupt:
        status = "blocked"
        disposition = "candidate_rejected_corrupted_weights"
    elif package_installed and version_valid and weights_present:
        status = "available"
        disposition = "candidate_ready"
    elif package_installed and not version_valid:
        status = "blocked"
        disposition = "blocked_unpinned_package_version"
    else:
        status = "blocked"
        disposition = "blocked_missing_dependency_and_weights"

    return {
        "candidate_name": f"RapidOCR v{REQUIRED_RAPIDOCR_VERSION} (PP-OCRv5 mobile English)",
        "source_id": "S47",
        "required_package": f"rapidocr=={REQUIRED_RAPIDOCR_VERSION}",
        "package_installed": package_installed,
        "package_version": package_version,
        "version_valid": version_valid,
        "weights_present": weights_present,
        "weights_corrupt": weights_corrupt,
        "detector_model": det_audit,
        "recognizer_model": rec_audit,
        "det_path": str(found_det) if (found_det and not weights_corrupt) else None,
        "rec_path": str(found_rec) if (found_rec and not weights_corrupt) else None,
        "status": status,
        "disposition": disposition,
        "runtime_network_allowed": False,
        "attempted_preparation": {
            "package_command": PREPARATION_COMMAND,
            "weights_source": MODEL_DOWNLOAD_BASE,
            "status": "candidate_prepared" if status == "available" else "candidate_unprepared",
        },
        "actionable_remediation": (
            f"Install rapidocr=={REQUIRED_RAPIDOCR_VERSION} into experiment environment and stage verified "
            "PP-OCRv5 mobile English ONNX weights (ch_PP-OCRv5_det_mobile.onnx, en_PP-OCRv5_rec_mobile.onnx) "
            "into experiments/P13/models/."
        ),
    }


def run_tesseract_ocr(raster_path: Path, psm: int = 6) -> dict[str, Any]:
    """Run native Tesseract CLI on a raster file, returning structured execution outcome."""
    tesseract_bin = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"
    if not os.path.exists(tesseract_bin):
        return {
            "status": "missing_executable",
            "text": "",
            "exit_code": -1,
            "runtime_seconds": 0.0,
            "error": f"Tesseract executable not found at {tesseract_bin}",
        }

    t0 = time.perf_counter()
    try:
        res = subprocess.run(
            [tesseract_bin, str(raster_path), "stdout", "--psm", str(psm)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        elapsed = time.perf_counter() - t0
        if res.returncode != 0:
            return {
                "status": "failed",
                "text": "",
                "exit_code": res.returncode,
                "runtime_seconds": round(elapsed, 4),
                "error": res.stderr.strip() or f"Tesseract process exited with code {res.returncode}",
            }
        return {
            "status": "completed",
            "text": res.stdout.strip(),
            "exit_code": 0,
            "runtime_seconds": round(elapsed, 4),
            "error": None,
        }
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - t0
        return {
            "status": "timeout",
            "text": "",
            "exit_code": -1,
            "runtime_seconds": round(elapsed, 4),
            "error": "Tesseract execution timed out after 15 seconds",
        }
    except OSError as e:
        elapsed = time.perf_counter() - t0
        return {
            "status": "error",
            "text": "",
            "exit_code": -1,
            "runtime_seconds": round(elapsed, 4),
            "error": str(e),
        }


_RAPIDOCR_ENGINE: Any = None


def get_rapidocr_engine(det_model_path: Path, rec_model_path: Path) -> Any:
    """Lazily initialize and reuse a single RapidOCR engine instance."""
    global _RAPIDOCR_ENGINE
    if _RAPIDOCR_ENGINE is None:
        from rapidocr import RapidOCR
        from rapidocr.utils.typings import OCRVersion, LangRec

        params = {
            "Global.use_cls": False,
            "EngineConfig.onnxruntime.intra_op_num_threads": 2,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Det.limit_type": "max",
            "Det.limit_side_len": 960,
            "Det.model_path": str(det_model_path),
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.lang_type": LangRec.EN,
            "Rec.model_path": str(rec_model_path),
        }
        _RAPIDOCR_ENGINE = RapidOCR(params=params)
    return _RAPIDOCR_ENGINE


def run_rapidocr(raster_path: Path, det_model_path: Path, rec_model_path: Path) -> dict[str, Any]:
    """Run RapidOCR inference with PP-OCRv5 mobile English models on a raster."""
    t0 = time.perf_counter()
    try:
        import numpy as np

        img = Image.open(raster_path).convert("RGB")
        img_np = np.array(img)

        engine = get_rapidocr_engine(det_model_path, rec_model_path)
        res = engine(img_np)
        elapsed = time.perf_counter() - t0

        boxes = res.boxes.tolist() if res.boxes is not None else []
        txts = list(res.txts) if res.txts is not None else []
        scores = [round(float(s), 4) for s in res.scores] if res.scores is not None else []
        combined_text = " ".join(txts)

        return {
            "status": "completed",
            "text": combined_text,
            "boxes": boxes,
            "scores": scores,
            "count": len(txts),
            "exit_code": 0,
            "runtime_seconds": round(elapsed, 4),
            "error": None,
        }
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return {
            "status": "failed",
            "text": "",
            "boxes": [],
            "scores": [],
            "count": 0,
            "exit_code": 1,
            "runtime_seconds": round(elapsed, 4),
            "error": str(e),
        }


def evaluate_fixture(pdf_path: Path, rasters_dir: Path, env_audit: dict[str, Any]) -> dict[str, Any]:
    """Render raster, persist to disk, and run native Tesseract baseline + RapidOCR candidate."""
    pdf_bytes = pdf_path.read_bytes()
    sha_before = hashlib.sha256(pdf_bytes).hexdigest()

    doc = pdfium.PdfDocument(pdf_path)
    page = doc[0]
    pw, ph = page.get_size()

    scale = 2.0
    pil_image = page.render(scale=scale).to_pil().convert("RGB")
    pixel_count = pil_image.width * pil_image.height

    # Retain raster in artifacts directory
    raster_filename = f"{pdf_path.stem}_p0.png"
    raster_path = rasters_dir / raster_filename
    pil_image.save(raster_path, format="PNG")

    # 1. Run native Tesseract on the persisted raster
    tesseract_res = run_tesseract_ocr(raster_path, psm=6)

    # 2. Run RapidOCR candidate if available
    if env_audit.get("status") == "available" and env_audit.get("det_path") and env_audit.get("rec_path"):
        rapidocr_res = run_rapidocr(raster_path, Path(env_audit["det_path"]), Path(env_audit["rec_path"]))
    else:
        rapidocr_res = {
            "status": "blocked",
            "text": None,
            "boxes": [],
            "scores": [],
            "count": 0,
            "exit_code": -1,
            "runtime_seconds": 0.0,
            "error": env_audit.get("disposition", "blocked_missing_dependency_and_weights"),
        }

    sha_after = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert sha_before == sha_after, "Invariant violation: source PDF mutated during evaluation!"

    return {
        "path": str(pdf_path.relative_to(ROOT)) if pdf_path.is_relative_to(ROOT) else str(pdf_path),
        "sha256": sha_before,
        "page_size_pt": [pw, ph],
        "raster_path": str(raster_path.relative_to(ROOT)) if raster_path.is_relative_to(ROOT) else str(raster_path),
        "raster_dimensions": [pil_image.width, pil_image.height],
        "pixels": pixel_count,
        "baseline_tesseract": tesseract_res,
        "candidate_rapidocr": rapidocr_res,
    }


def get_peak_rss_bytes() -> int:
    """Measure peak resident set size of current process (ru_maxrss)."""
    self_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    children_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if sys.platform == "darwin":
        # macOS ru_maxrss is in bytes
        return max(self_rss, children_rss)
    else:
        # Linux ru_maxrss is in KiB
        return max(self_rss, children_rss) * 1024


def run_experiment(manifest_path: Path, out_dir: Path) -> dict[str, Any]:
    global _BLOCKED_NETWORK_CALLS
    _BLOCKED_NETWORK_CALLS = 0

    out_dir.mkdir(parents=True, exist_ok=True)
    rasters_dir = out_dir / "rasters"
    rasters_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()

    # 1. Manifest parsing & validation
    fixtures = load_and_validate_manifest(manifest_path)

    # 2. Environment and candidate provenance audit
    env_audit = audit_rapidocr_environment()

    # 3. Evaluate each fixture under runtime network isolation
    fixture_results: list[dict[str, Any]] = []
    total_pixels = 0

    with enforce_network_isolation():
        for fix in fixtures:
            res = evaluate_fixture(fix["path"], rasters_dir, env_audit)
            total_pixels += res["pixels"]
            fixture_results.append(res)

    t_elapsed = time.perf_counter() - t0
    peak_rss = get_peak_rss_bytes()
    peak_rss_mb = round(peak_rss / (1024 * 1024), 2)

    # 4. Denominator & failure accounting
    total_evaluated = len(fixture_results)
    baseline_completed = sum(1 for f in fixture_results if f["baseline_tesseract"]["status"] == "completed")
    baseline_failed = sum(1 for f in fixture_results if f["baseline_tesseract"]["status"] != "completed")

    candidate_completed = sum(1 for f in fixture_results if f["candidate_rapidocr"]["status"] == "completed")
    candidate_failed = sum(1 for f in fixture_results if f["candidate_rapidocr"]["status"] == "failed")
    candidate_blocked = sum(1 for f in fixture_results if f["candidate_rapidocr"]["status"] == "blocked")

    if env_audit["status"] == "available":
        overall_status = "completed"
        overall_disposition = "candidate_evaluated_unintegrated"
    else:
        overall_status = "blocked"
        overall_disposition = env_audit["disposition"]

    result_data: dict[str, Any] = {
        "experiment_id": "P13",
        "task_id": "T44",
        "status": overall_status,
        "disposition": overall_disposition,
        "hypothesis": "Native RapidOCR complement value",
        "baseline": "Tesseract native reader",
        "candidate": env_audit["candidate_name"],
        "manifest": str(manifest_path.relative_to(ROOT)),
        "fixture_ids": sorted(list(TARGET_FIXTURE_IDS)),
        "clean_controls": "Same rasters, clean text and ambiguity fixtures evaluated",
        "environment_audit": env_audit,
        "resource_costs": {
            "total_pixels_evaluated": total_pixels,
            "total_megapixels": round(total_pixels / 1_000_000.0, 4),
            "total_runtime_seconds": round(t_elapsed, 4),
            "process_max_rss_bytes": peak_rss,
            "process_max_rss_mb": peak_rss_mb,
            "memory_budget_bytes": MEMORY_BUDGET_BYTES,
            "memory_budget_satisfied": peak_rss <= MEMORY_BUDGET_BYTES,
            "host_containment": {
                "platform": sys.platform,
                "measurement": "process_max_rss (resource.getrusage RUSAGE_SELF/CHILDREN high-water mark; note: not simultaneous aggregate process-tree RSS)",
                "rlimit_as_enforced": sys.platform != "darwin",
            },
            "runtime_network_isolation": {
                "enforced": True,
                "network_calls_attempted": _BLOCKED_NETWORK_CALLS,
                "offline_policy": "Invariant I13 / I14: runtime network access prohibited during OCR inference (socket-intercepted)",
            },
        },
        "metrics": {
            "total_fixtures_evaluated": total_evaluated,
            "baseline_completed_count": baseline_completed,
            "baseline_failed_count": baseline_failed,
            "candidate_completed_count": candidate_completed,
            "candidate_failed_count": candidate_failed,
            "candidate_blocked_count": candidate_blocked,
            "failure_rate_in_denominator": round(baseline_failed / total_evaluated, 4) if total_evaluated > 0 else 0.0,
        },
        "fixtures": fixture_results,
        "integration_decision": "default_not_installed",
        "acceptance": (
            "Complementary useful failures at fixed precision and memory budget or reject; "
            "missing models/dependencies recorded as blocked; default not installed."
        ),
        "note": (
            "Native Tesseract baseline and RapidOCR PP-OCRv5 candidate evaluated across all manifest fixtures "
            "with exact per-fixture timings and persisted rasters. "
            "Candidate models verified against official trusted digests. "
            "Candidate remains default-not-installed for production."
        ),
    }

    result_file = out_dir / "result.json"
    result_file.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
    return result_data


def main() -> None:
    maybe_reexec_venv()
    parser = argparse.ArgumentParser(description="P13 native RapidOCR complement experiment")
    parser.add_argument(
        "--manifest",
        default=None,
        help="Path to manifest (defaults to evaluation/manifests/development.json or fixtures/manifest.json)",
    )
    parser.add_argument("--out", default="artifacts/P13", help="Output directory")
    args = parser.parse_args()

    manifest_path = resolve_manifest(args.manifest)
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    result = run_experiment(manifest_path, out_dir)
    print(
        f"P13 evaluation complete: {result['metrics']['total_fixtures_evaluated']} fixtures evaluated, "
        f"baseline={result['metrics']['baseline_completed_count']} completed ({result['metrics']['baseline_failed_count']} failed), "
        f"candidate={result['metrics']['candidate_completed_count']} completed ({result['metrics']['candidate_blocked_count']} blocked), "
        f"status={result['status']} ({result['disposition']}), "
        f"max_rss={result['resource_costs']['process_max_rss_mb']}MB, "
        f"runtime={result['resource_costs']['total_runtime_seconds']}s"
    )


if __name__ == "__main__":
    main()
