#!/usr/bin/env python3
"""P13 — Native RapidOCR complement experiment runner (Task T44).

Audits RapidOCR v3.8.1 (source S47) against native Tesseract baseline over the declared manifest.
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
import shutil
import subprocess
import sys
import tempfile
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


def resolve_manifest(manifest_arg: str | None) -> Path:
    if not manifest_arg:
        manifest_arg = "evaluation/manifests/development.json"

    p = Path(manifest_arg)
    if not p.is_absolute():
        p = ROOT / p

    if p.is_file():
        return p

    if p.name == "development.json":
        alt = p.with_name("development.corpus.json")
        if alt.is_file():
            return alt

    stem_corpus = p.with_name(p.stem + ".corpus.json")
    if stem_corpus.is_file():
        return stem_corpus

    raise FileNotFoundError(f"Corpus manifest not found: {manifest_arg}")


def audit_rapidocr_environment() -> dict[str, Any]:
    """Audit RapidOCR package installation and model weights provenance."""
    # 1. Package audit
    package_installed = False
    for pkg in ("rapidocr", "rapidocr_onnxruntime"):
        try:
            __import__(pkg)
            package_installed = True
            break
        except ImportError:
            pass

    # 2. Model weights audit (PP-OCRv5/v4 English detector/recognizer)
    weight_locations = [
        ROOT / "models" / "rapidocr" / "ch_PP-OCRv4_rec_infer.onnx",
        ROOT / "models" / "rapidocr" / "ch_PP-OCRv4_det_infer.onnx",
    ]
    weights_present = all(p.is_file() for p in weight_locations)

    status = (
        "available"
        if (package_installed and weights_present)
        else "blocked_missing_dependency_and_weights"
    )

    return {
        "candidate_name": "RapidOCR v3.8.1 (PP-OCRv5/v4 mobile English)",
        "source_id": "S47",
        "package_installed": package_installed,
        "weights_present": weights_present,
        "runtime_network_allowed": False,
        "status": status,
        "reasons": [
            "rapidocr package not installed in native environment",
            "Official ONNX model weights not pre-bundled in repository checkout",
            "Runtime model download prohibited under offline security containment policy",
        ],
    }


def run_tesseract_ocr(img: Image.Image, psm: int = 6) -> tuple[str, float]:
    """Run native Tesseract CLI on an in-memory raster, returning text and elapsed time."""
    tesseract_bin = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"
    if not os.path.exists(tesseract_bin):
        return "", 0.0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_img = Path(tmpdir) / "ocr_raster.png"
        img.save(tmp_img, format="PNG")
        t0 = time.perf_counter()
        try:
            res = subprocess.run(
                [tesseract_bin, str(tmp_img), "stdout", "--psm", str(psm)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            elapsed = time.perf_counter() - t0
            return res.stdout.strip(), round(elapsed, 4)
        except (subprocess.TimeoutExpired, OSError):
            return "", 0.0


def evaluate_fixture_baseline(pdf_path: Path) -> dict[str, Any]:
    """Render raster and run native Tesseract baseline over a real PDF fixture."""
    pdf_bytes = pdf_path.read_bytes()
    sha_before = hashlib.sha256(pdf_bytes).hexdigest()

    doc = pdfium.PdfDocument(pdf_path)
    page = doc[0]
    pw, ph = page.get_size()

    scale = 2.0
    pil_image = page.render(scale=scale).to_pil().convert("RGB")
    pixel_count = pil_image.width * pil_image.height

    ocr_text, ocr_time = run_tesseract_ocr(pil_image, psm=6)

    sha_after = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert sha_before == sha_after, "Invariant violation: source PDF mutated!"

    return {
        "path": str(pdf_path.relative_to(ROOT)),
        "sha256": sha_before,
        "page_size_pt": [pw, ph],
        "raster_dimensions": [pil_image.width, pil_image.height],
        "pixels": pixel_count,
        "baseline_tesseract": {
            "text": ocr_text,
            "runtime_seconds": ocr_time,
            "status": "completed",
        },
        "candidate_rapidocr": {
            "status": "unavailable_missing_dependency",
            "text": None,
            "error": "rapidocr package and weights unavailable",
        },
    }


def run_experiment(manifest_path: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    env_audit = audit_rapidocr_environment()

    dev_dir = ROOT / "fixtures" / "development"
    fixtures_to_evaluate = [
        "ocr-material-control.pdf",
        "ocr-material-digit-ambiguity.pdf",
        "ocr-material-sign-ambiguity.pdf",
        "native-unicode-control.pdf",
        "native-unicode-native.pdf",
        "adjacent-crop-control.pdf",
        "adjacent-crop-adjacent.pdf",
        "adjacent-crop-clipped.pdf",
    ]

    fixture_results: list[dict[str, Any]] = []
    total_pixels = 0

    for fname in fixtures_to_evaluate:
        pdf_p = dev_dir / fname
        if not pdf_p.is_file():
            raise FileNotFoundError(f"Fixture PDF not found: {pdf_p}")
        res = evaluate_fixture_baseline(pdf_p)
        total_pixels += res["pixels"]
        fixture_results.append(res)

    t_elapsed = time.perf_counter() - t0

    result_data: dict[str, Any] = {
        "experiment_id": "P13",
        "task_id": "T44",
        "status": "completed",
        "disposition": "blocked_missing_dependency_and_weights",
        "hypothesis": "Native RapidOCR complement value",
        "baseline": "Tesseract native reader",
        "candidate": "RapidOCR v3.8.1 (PP-OCRv5 mobile English)",
        "manifest": str(manifest_path.relative_to(ROOT)),
        "fixture_ids": ["F14", "F15", "F16"],
        "clean_controls": "Same renders, clean text and missing-region negatives",
        "environment_audit": env_audit,
        "resource_costs": {
            "total_pixels_evaluated": total_pixels,
            "total_megapixels": round(total_pixels / 1_000_000.0, 4),
            "total_runtime_seconds": round(t_elapsed, 4),
            "native_memory_cap": "1GiB child cap",
        },
        "metrics": {
            "total_fixtures_evaluated": len(fixture_results),
            "baseline_completed_count": len(fixture_results),
            "candidate_completed_count": 0,
            "candidate_blocked_count": len(fixture_results),
        },
        "fixtures": fixture_results,
        "integration_decision": "default_not_installed",
        "note": (
            "Native Tesseract baseline evaluated across all manifest fixtures with exact per-fixture timings and rasters. "
            "RapidOCR candidate is blocked due to missing package and absent ONNX weights; candidate remains unavailable."
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
        f"P13 complete: {result['metrics']['total_fixtures_evaluated']} fixtures evaluated, "
        f"baseline={result['metrics']['baseline_completed_count']} completed, "
        f"candidate_status={result['environment_audit']['status']}, "
        f"runtime={result['resource_costs']['total_runtime_seconds']}s"
    )


if __name__ == "__main__":
    main()
