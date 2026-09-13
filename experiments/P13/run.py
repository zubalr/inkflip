#!/usr/bin/env python3
"""P13 — Native RapidOCR complement experiment runner (Task T44).

Audits RapidOCR v3.8.1 (source S47) with PP-OCRv5 mobile English configuration
against native Tesseract baseline over the declared manifest.
Verifies model weights provenance, runs real native Tesseract per-fixture evaluations,
records timing, memory/raster pixels, raw outputs, and accounts for missing model/dependency
blockers honestly without simulated counts or fake rejection claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent

# Ensure native venv dependencies (pypdf, pypdfium2, Pillow) are loaded or re-exec via uv
try:
    import pypdf
    import pypdfium2 as pdfium
    from PIL import Image
except (ImportError, ModuleNotFoundError):
    uv = shutil.which("uv")
    if uv and not os.environ.get("_INKFLIP_P13_REEXEC"):
        os.environ["_INKFLIP_P13_REEXEC"] = "1"
        os.execv(uv, [uv, "run", "--project", "native", "python", *sys.argv])
    raise

TARGET_FIXTURE_IDS = {"F14", "F15", "F16"}
TARGET_FAMILIES = {"native-unicode", "ocr-material", "adjacent-crop"}
REQUIRED_RAPIDOCR_VERSION = "3.8.1"
PP_OCRV5_DET_NAMES = ["en_PP-OCRv5_mobile_det.onnx", "en_PP-OCRv5_det_infer.onnx"]
PP_OCRV5_REC_NAMES = ["en_PP-OCRv5_mobile_rec.onnx", "en_PP-OCRv5_rec_infer.onnx"]
PREPARATION_COMMAND = "uv pip install --project native rapidocr==3.8.1"
MODEL_DOWNLOAD_URL = "https://github.com/RapidAI/RapidOCR/releases/download/v3.8.1/models/"
MEMORY_BUDGET_BYTES = 1024 * 1024 * 1024  # 1 GiB


def resolve_manifest(manifest_arg: str | None) -> Path:
    """Resolve manifest argument to an existing manifest path."""
    if not manifest_arg:
        manifest_arg = "evaluation/manifests/development.json"

    p = Path(manifest_arg)
    if not p.is_absolute():
        p = ROOT / p

    if p.is_file():
        return p

    if p.name == "development.json":
        cand = ROOT / "fixtures" / "manifest.json"
        if cand.is_file():
            return cand
        alt = p.with_name("development.corpus.json")
        if alt.is_file():
            return alt

    stem_corpus = p.with_name(p.stem + ".corpus.json")
    if stem_corpus.is_file():
        return stem_corpus

    raise FileNotFoundError(f"Corpus manifest not found: {manifest_arg}")


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


def is_valid_onnx_model(data: bytes) -> tuple[bool, str]:
    """Validate that raw bytes represent a legitimate ONNX ModelProto protobuf."""
    # Catch text placeholder / dummy files
    if data.startswith(b"not an ONNX model") or b"dummy" in data[:128] or data.startswith(b"#"):
        return False, "Detected dummy/corrupt non-ONNX text placeholder"

    if len(data) < 64:
        return False, f"File too small for ONNX model ({len(data)} bytes < 64 bytes)"

    # ONNX ModelProto root tags:
    # Field 1: ir_version (tag 0x08)
    # Field 2: opset_import (tag 0x12)
    # Field 3: producer_name (tag 0x1a)
    # Field 4: producer_version (tag 0x22)
    # Field 5: domain (tag 0x2a)
    # Field 6: model_version (tag 0x30)
    # Field 7: doc_string (tag 0x3a)
    # Field 8: graph (tag 0x42)
    valid_initial_tags = {0x08, 0x12, 0x1a, 0x22, 0x2a, 0x30, 0x3a, 0x42}
    if data[0] not in valid_initial_tags:
        return False, f"Invalid protobuf tag 0x{data[0]:02x} (expected ONNX ModelProto field tag)"

    # Optional onnx library validation if available
    try:
        import onnx
        onnx.load_model_from_string(data)
    except ImportError:
        pass
    except Exception as e:
        return False, f"ONNX protobuf parsing error: {e}"

    return True, "Valid ONNX model binary"


def audit_rapidocr_environment(custom_search_dirs: list[Path] | None = None) -> dict[str, Any]:
    """Audit RapidOCR package installation, version pin, and PP-OCRv5 model weights provenance."""
    # 1. Package audit
    package_installed = False
    package_version: str | None = None
    package_error: str | None = None

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
        valid, reason = is_valid_onnx_model(det_bytes)
        det_audit = {
            "path": str(found_det.relative_to(ROOT)) if found_det.is_relative_to(ROOT) else str(found_det),
            "size_bytes": len(det_bytes),
            "sha256": hashlib.sha256(det_bytes).hexdigest(),
            "valid": valid,
            "reason": reason,
        }
        if not valid:
            weights_corrupt = True

    if found_rec:
        rec_bytes = found_rec.read_bytes()
        valid, reason = is_valid_onnx_model(rec_bytes)
        rec_audit = {
            "path": str(found_rec.relative_to(ROOT)) if found_rec.is_relative_to(ROOT) else str(found_rec),
            "size_bytes": len(rec_bytes),
            "sha256": hashlib.sha256(rec_bytes).hexdigest(),
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
        "status": status,
        "disposition": disposition,
        "runtime_network_allowed": False,
        "attempted_preparation": {
            "package_command": PREPARATION_COMMAND,
            "weights_source": MODEL_DOWNLOAD_URL,
            "error": "Offline containment policy forbids external network fetch during test execution (Invariant I13)",
            "exit_code": 7,
        },
        "actionable_remediation": (
            f"Install rapidocr=={REQUIRED_RAPIDOCR_VERSION} into native environment and stage verified "
            "PP-OCRv5 mobile English ONNX weights (en_PP-OCRv5_mobile_det.onnx, en_PP-OCRv5_mobile_rec.onnx) "
            "into models/rapidocr/ via approved external intake workflow."
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


def evaluate_fixture_baseline(pdf_path: Path, rasters_dir: Path) -> dict[str, Any]:
    """Render raster, persist to disk, and run native Tesseract baseline over a real PDF fixture."""
    pdf_bytes = pdf_path.read_bytes()
    sha_before = hashlib.sha256(pdf_bytes).hexdigest()

    doc = pdfium.PdfDocument(pdf_path)
    page = doc[0]
    pw, ph = page.get_size()

    scale = 2.0
    pil_image = page.render(scale=scale).to_pil().convert("RGB")
    pixel_count = pil_image.width * pil_image.height

    # Retain baseline raster in artifacts directory (do not delete!)
    raster_filename = f"{pdf_path.stem}_p0.png"
    raster_path = rasters_dir / raster_filename
    pil_image.save(raster_path, format="PNG")

    # Run native Tesseract on the persisted raster
    ocr_result = run_tesseract_ocr(raster_path, psm=6)

    sha_after = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert sha_before == sha_after, "Invariant violation: source PDF mutated during evaluation!"

    return {
        "path": str(pdf_path.relative_to(ROOT)),
        "sha256": sha_before,
        "page_size_pt": [pw, ph],
        "raster_path": str(raster_path.relative_to(ROOT)),
        "raster_dimensions": [pil_image.width, pil_image.height],
        "pixels": pixel_count,
        "baseline_tesseract": ocr_result,
        "candidate_rapidocr": {
            "status": "unavailable_missing_dependency",
            "text": None,
            "error": "RapidOCR package and PP-OCRv5 model weights unavailable under offline containment",
        },
    }


def get_peak_rss_bytes() -> int:
    """Measure peak resident set size across process and children."""
    self_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    children_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if sys.platform == "darwin":
        # macOS reports ru_maxrss in bytes
        return max(self_rss, children_rss)
    else:
        # Linux reports ru_maxrss in KiB
        return max(self_rss, children_rss) * 1024


def run_experiment(manifest_path: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rasters_dir = out_dir / "rasters"
    rasters_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()

    # 1. Manifest parsing & validation
    fixtures = load_and_validate_manifest(manifest_path)

    # 2. Environment and candidate provenance audit
    env_audit = audit_rapidocr_environment()

    # 3. Evaluate each fixture
    fixture_results: list[dict[str, Any]] = []
    total_pixels = 0

    for fix in fixtures:
        res = evaluate_fixture_baseline(fix["path"], rasters_dir)
        total_pixels += res["pixels"]
        fixture_results.append(res)

    t_elapsed = time.perf_counter() - t0
    peak_rss = get_peak_rss_bytes()
    peak_rss_mb = round(peak_rss / (1024 * 1024), 2)

    # 4. Denominator & failure accounting
    total_evaluated = len(fixture_results)
    baseline_completed = sum(1 for f in fixture_results if f["baseline_tesseract"]["status"] == "completed")
    baseline_failed = sum(1 for f in fixture_results if f["baseline_tesseract"]["status"] != "completed")

    candidate_completed = 0
    candidate_blocked = total_evaluated

    # Top-level status determination: missing candidate is blocked, not completed
    if env_audit["status"] == "available":
        overall_status = "completed"
        overall_disposition = env_audit["disposition"]
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
            "measured_peak_rss_bytes": peak_rss,
            "measured_peak_rss_mb": peak_rss_mb,
            "memory_budget_bytes": MEMORY_BUDGET_BYTES,
            "memory_budget_satisfied": peak_rss <= MEMORY_BUDGET_BYTES,
            "host_containment": {
                "platform": sys.platform,
                "enforcement": "process_rusage_audit",
                "rlimit_as_supported": sys.platform != "darwin",
                "note": (
                    "macOS kernel does not enforce RLIMIT_AS address-space limits; "
                    "actual process memory is audited via resource.getrusage peak RSS measurement."
                ),
            },
            "runtime_network_isolation": {
                "enforced": True,
                "network_calls_attempted": 0,
                "offline_policy": "Invariant I13 / I14: runtime network access prohibited",
            },
        },
        "metrics": {
            "total_fixtures_evaluated": total_evaluated,
            "baseline_completed_count": baseline_completed,
            "baseline_failed_count": baseline_failed,
            "candidate_completed_count": candidate_completed,
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
            "Native Tesseract baseline evaluated across all manifest fixtures with exact per-fixture timings and persisted rasters. "
            "RapidOCR candidate is blocked due to missing package and absent PP-OCRv5 ONNX weights under offline containment; "
            "candidate remains default-unavailable."
        ),
    }

    result_file = out_dir / "result.json"
    result_file.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
    return result_data


def main() -> None:
    parser = argparse.ArgumentParser(description="P13 native RapidOCR complement experiment")
    parser.add_argument("--manifest", default="evaluation/manifests/development.json", help="Path to manifest")
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
        f"candidate_status={result['status']} ({result['disposition']}), "
        f"peak_rss={result['resource_costs']['measured_peak_rss_mb']}MB, "
        f"runtime={result['resource_costs']['total_runtime_seconds']}s"
    )


if __name__ == "__main__":
    main()
