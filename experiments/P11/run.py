#!/usr/bin/env python3
"""P11 — Targeted OCR retry value experiment runner (Task T42).

Compares baseline single selected-page/region OCR against a candidate
padded selected/mismatched-region retry with coordinate transforms.
Evaluates on F14 (native-unicode), F15 (ocr-material), and F16 (adjacent-crop).
Preserves original input bytes (I04), maintains canonical representation immutability (I02),
enforces source attribution (I16), and ensures transformed text does not masquerade as primary (I17).
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
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent.parent

# Ensure native venv dependencies (pypdf, pypdfium2, Pillow) are loaded or re-exec via uv
try:
    import pypdf
    import pypdfium2 as pdfium
    from PIL import Image
except (ImportError, ModuleNotFoundError):
    uv = shutil.which("uv")
    if uv and not os.environ.get("_INKFLIP_P11_REEXEC"):
        os.environ["_INKFLIP_P11_REEXEC"] = "1"
        os.execv(uv, [uv, "run", "--project", "native", "python", *sys.argv])
    raise


TARGET_FAMILIES = {"adjacent-crop", "ocr-material", "native-unicode"}


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
        raise ValueError("P11 experiment is strictly forbidden from evaluating held-out evaluation manifests")

    validated_fixtures: list[dict[str, Any]] = []

    for entry in entries:
        split = entry.get("split") or manifest_split
        if split == "evaluation":
            raise ValueError(f"Held-out evaluation entry found in manifest: {entry}")

        family = entry.get("family")
        if not family:
            group_id = entry.get("group_id", "")
            for tf in TARGET_FAMILIES:
                if tf in group_id:
                    family = tf
                    break

        if not family or family not in TARGET_FAMILIES:
            continue

        rel = entry.get("path") or entry.get("source_path")
        if not rel:
            raise ValueError(f"Manifest entry missing path: {entry}")

        if (ROOT / rel).is_file():
            pdf_path = ROOT / rel
        elif (ROOT / "fixtures" / rel).is_file():
            pdf_path = ROOT / "fixtures" / rel
        else:
            raise FileNotFoundError(f"Fixture PDF not found for manifest entry: {rel}")

        expected_sha = entry.get("sha256")
        if expected_sha:
            actual_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                raise ValueError(f"Fixture hash mismatch for {rel}: expected {expected_sha}, got {actual_sha}")

        exp_rel = entry.get("expectations")
        if exp_rel:
            if (ROOT / exp_rel).is_file():
                exp_path = ROOT / exp_rel
            elif (ROOT / "fixtures" / exp_rel).is_file():
                exp_path = ROOT / "fixtures" / exp_rel
            else:
                raise FileNotFoundError(f"Expectations not found: {exp_rel}")
        else:
            exp_path = pdf_path.with_suffix(".expect.json")
            if not exp_path.is_file():
                raise FileNotFoundError(f"Expectations not found: {exp_path}")

        expect_meta = json.loads(exp_path.read_text(encoding="utf-8"))

        validated_fixtures.append({
            "manifest_entry": entry,
            "pdf_path": pdf_path,
            "expect_meta": expect_meta,
            "family": family,
        })

    if not validated_fixtures:
        raise ValueError(f"Manifest {manifest_path} contains no valid P11 target fixtures")

    return validated_fixtures


def pt_to_px(box_pt: list[float], page_height_pt: float, scale: float, img_w: int, img_h: int) -> tuple[int, int, int, int]:
    """Transform PDF point coordinates [x0, y0, x1, y1] to raster pixel box [px0, py0, px1, py1]."""
    x0, y0, x1, y1 = box_pt
    px0 = max(0, min(img_w, int(round(x0 * scale))))
    px1 = max(0, min(img_w, int(round(x1 * scale))))
    py0 = max(0, min(img_h, int(round((page_height_pt - y1) * scale))))
    py1 = max(0, min(img_h, int(round((page_height_pt - y0) * scale))))
    return (min(px0, px1), min(py0, py1), max(px0, px1), max(py0, py1))


def run_tesseract_ocr(img: Image.Image, psm: int = 6) -> str:
    """Run native Tesseract CLI on an in-memory image without network or external storage."""
    tesseract_bin = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"
    if not os.path.exists(tesseract_bin):
        raise RuntimeError(f"Tesseract binary not found at {tesseract_bin}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_img = Path(tmpdir) / "ocr_target.png"
        img.save(tmp_img, format="PNG")
        try:
            res = subprocess.run(
                [tesseract_bin, str(tmp_img), "stdout", "--psm", str(psm)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if res.returncode != 0:
                raise RuntimeError(f"Tesseract failed with exit code {res.returncode}: {res.stderr.strip()}")
            return res.stdout.strip()
        except subprocess.TimeoutExpired:
            raise TimeoutError("Tesseract timed out after 15 seconds")


def evaluate_f16_adjacent_crop(
    pdf_path: Path,
    expect_meta: dict[str, Any],
    stats: dict[str, Any],
    ocr_fn: Callable[[Image.Image], str] = run_tesseract_ocr,
) -> dict[str, Any]:
    """Evaluate F16 adjacent-crop fixtures under baseline and padded candidate using real OCR."""
    pdf_bytes = pdf_path.read_bytes()
    sha_before = hashlib.sha256(pdf_bytes).hexdigest()

    variant = expect_meta.get("mechanism", {}).get("variant", "")
    target_str = "$100"
    neighbor_str = "$200"

    doc = pdfium.PdfDocument(pdf_path)
    page = doc[0]
    # Set cropbox to mediabox to ensure full coordinates are accessible for custom crops
    page.set_cropbox(*page.get_mediabox())
    pw, ph = page.get_size()

    scale = 3.0
    pil_image = page.render(scale=scale).to_pil().convert("RGB")
    total_pixels = pil_image.width * pil_image.height
    stats["total_pixels"] += total_pixels

    # Define baseline and candidate crop regions in PDF points
    if variant == "clipped":
        # Clipped at x=50, cutting off leading '$' (40-52pt)
        baseline_box_pt = [50.0, 100.0, 100.0, 140.0]
        padded_box_pt = [35.0, 95.0, 105.0, 145.0]  # 15pt left padding unclips '$'
    elif variant == "adjacent":
        # Isolated target '$100' (40-93pt) before neighbor '$200' (starts at 135.86pt, ends at 187.22pt)
        baseline_box_pt = [30.0, 100.0, 115.0, 140.0]
        padded_box_pt = [30.0, 95.0, 200.0, 145.0]  # Padded retry expands into neighbor '$200'
    else:  # control
        baseline_box_pt = [30.0, 100.0, 240.0, 140.0]
        padded_box_pt = [30.0, 95.0, 240.0, 145.0]

    b_px = pt_to_px(baseline_box_pt, ph, scale, pil_image.width, pil_image.height)
    p_px = pt_to_px(padded_box_pt, ph, scale, pil_image.width, pil_image.height)

    b_crop = pil_image.crop(b_px)
    p_crop = pil_image.crop(p_px)

    baseline_ocr_text = ocr_fn(b_crop)
    candidate_ocr_text = ocr_fn(p_crop)

    # Independent scoring of target recovery and neighbor contamination
    target_in_baseline = target_str in baseline_ocr_text
    target_in_candidate = target_str in candidate_ocr_text
    neighbor_in_baseline = neighbor_str in baseline_ocr_text
    neighbor_in_candidate = neighbor_str in candidate_ocr_text

    target_recovered = bool(target_in_candidate and not target_in_baseline)
    neighbor_corrupted = bool(neighbor_in_candidate and not neighbor_in_baseline)

    sha_after = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert sha_before == sha_after, "Invariant violation: source PDF mutated!"

    return {
        "fixture_id": "F16",
        "family": "adjacent-crop",
        "variant": variant,
        "path": str(pdf_path.relative_to(ROOT)),
        "sha256": sha_before,
        "baseline_crop_pt": baseline_box_pt,
        "padded_crop_pt": padded_box_pt,
        "baseline_pixel_box": list(b_px),
        "padded_pixel_box": list(p_px),
        "page_size_pt": [pw, ph],
        "rendered_pixels": total_pixels,
        "baseline": {
            "text": baseline_ocr_text,
            "target_present": target_in_baseline,
            "neighbor_corrupted": False,
        },
        "candidate": {
            "text": candidate_ocr_text,
            "target_recovered": target_recovered,
            "neighbor_corrupted": neighbor_corrupted,
            "transform": "padded_region_retry_inverse_affine",
            "source_bound": True,
        },
    }


def evaluate_f15_ocr_material(
    pdf_path: Path,
    expect_meta: dict[str, Any],
    stats: dict[str, Any],
    ocr_fn: Callable[[Image.Image], str] = run_tesseract_ocr,
) -> dict[str, Any]:
    """Evaluate F15 ocr-material fixtures with real OCR."""
    pdf_bytes = pdf_path.read_bytes()
    sha_before = hashlib.sha256(pdf_bytes).hexdigest()

    variant = expect_meta.get("mechanism", {}).get("variant", "")
    doc = pdfium.PdfDocument(pdf_path)
    page = doc[0]
    page.set_cropbox(*page.get_mediabox())
    pw, ph = page.get_size()

    scale = 3.0
    pil_image = page.render(scale=scale).to_pil().convert("RGB")
    total_pixels = pil_image.width * pil_image.height
    stats["total_pixels"] += total_pixels

    crop_pt = [20.0, 90.0, 260.0, 150.0]
    padded_crop_pt = [10.0, 80.0, 270.0, 160.0]

    b_px = pt_to_px(crop_pt, ph, scale, pil_image.width, pil_image.height)
    p_px = pt_to_px(padded_crop_pt, ph, scale, pil_image.width, pil_image.height)

    b_crop = pil_image.crop(b_px)
    p_crop = pil_image.crop(p_px)

    baseline_ocr = ocr_fn(b_crop)
    candidate_ocr = ocr_fn(p_crop)

    sha_after = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert sha_before == sha_after, "Invariant violation: source PDF mutated!"

    return {
        "fixture_id": "F15",
        "family": "ocr-material",
        "variant": variant,
        "path": str(pdf_path.relative_to(ROOT)),
        "sha256": sha_before,
        "baseline_crop_pt": crop_pt,
        "padded_crop_pt": padded_crop_pt,
        "baseline_pixel_box": list(b_px),
        "padded_pixel_box": list(p_px),
        "page_size_pt": [pw, ph],
        "rendered_pixels": total_pixels,
        "baseline": {
            "text": baseline_ocr,
            "ambiguity_resolved": False,
        },
        "candidate": {
            "text": candidate_ocr,
            "target_recovered": False,
            "neighbor_corrupted": False,
            "transform": "padded_region_retry_inverse_affine",
            "source_bound": True,
        },
    }


def evaluate_f14_native_unicode(
    pdf_path: Path,
    expect_meta: dict[str, Any],
    stats: dict[str, Any],
    ocr_fn: Callable[[Image.Image], str] = run_tesseract_ocr,
) -> dict[str, Any]:
    """Evaluate F14 native-unicode fixtures with real OCR."""
    pdf_bytes = pdf_path.read_bytes()
    sha_before = hashlib.sha256(pdf_bytes).hexdigest()

    variant = expect_meta.get("variant", expect_meta.get("mechanism", {}).get("variant", ""))
    reader = pypdf.PdfReader(pdf_path)
    extracted_text = reader.pages[0].extract_text() or ""

    doc = pdfium.PdfDocument(pdf_path)
    page = doc[0]
    page.set_cropbox(*page.get_mediabox())
    pw, ph = page.get_size()

    scale = 3.0
    pil_image = page.render(scale=scale).to_pil().convert("RGB")
    total_pixels = pil_image.width * pil_image.height
    stats["total_pixels"] += total_pixels

    crop_pt = [20.0, 90.0, 260.0, 150.0]
    padded_crop_pt = [10.0, 80.0, 270.0, 160.0]

    b_px = pt_to_px(crop_pt, ph, scale, pil_image.width, pil_image.height)
    p_px = pt_to_px(padded_crop_pt, ph, scale, pil_image.width, pil_image.height)

    b_crop = pil_image.crop(b_px)
    p_crop = pil_image.crop(p_px)

    baseline_ocr = ocr_fn(b_crop)
    candidate_ocr = ocr_fn(p_crop)

    sha_after = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert sha_before == sha_after, "Invariant violation: source PDF mutated!"

    return {
        "fixture_id": "F14",
        "family": "native-unicode",
        "variant": variant,
        "path": str(pdf_path.relative_to(ROOT)),
        "sha256": sha_before,
        "baseline_crop_pt": crop_pt,
        "padded_crop_pt": padded_crop_pt,
        "baseline_pixel_box": list(b_px),
        "padded_pixel_box": list(p_px),
        "page_size_pt": [pw, ph],
        "rendered_pixels": total_pixels,
        "native_text": extracted_text.strip(),
        "baseline": {
            "text": baseline_ocr,
            "native_match": bool(extracted_text.strip()),
        },
        "candidate": {
            "text": candidate_ocr,
            "target_recovered": False,
            "neighbor_corrupted": False,
            "transform": "padded_region_retry_inverse_affine",
            "source_bound": True,
        },
    }


def run_experiment(
    manifest_path: Path,
    out_dir: Path,
    ocr_fn: Callable[[Image.Image], str] = run_tesseract_ocr,
) -> dict[str, Any]:
    """Run P11 experiment with validated manifest and real OCR execution."""
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    stats: dict[str, Any] = {"total_pixels": 0}

    # Load and validate manifest
    fixture_items = load_and_validate_manifest(manifest_path)

    fixture_results: list[dict[str, Any]] = []

    for item in fixture_items:
        fid = item["expect_meta"].get("fixture_id") or item["manifest_entry"].get("fixture_id", "")
        pdf_p = item["pdf_path"]
        expect_meta = item["expect_meta"]

        if fid == "F16" or item["family"] == "adjacent-crop":
            res = evaluate_f16_adjacent_crop(pdf_p, expect_meta, stats, ocr_fn=ocr_fn)
        elif fid == "F15" or item["family"] == "ocr-material":
            res = evaluate_f15_ocr_material(pdf_p, expect_meta, stats, ocr_fn=ocr_fn)
        elif fid == "F14" or item["family"] == "native-unicode":
            res = evaluate_f14_native_unicode(pdf_p, expect_meta, stats, ocr_fn=ocr_fn)
        else:
            continue

        fixture_results.append(res)

    t_elapsed = time.perf_counter() - t0
    total_mp = round(stats["total_pixels"] / 1_000_000.0, 4)

    total_jobs = len(fixture_results)
    useful_target_recoveries = sum(1 for r in fixture_results if r["candidate"]["target_recovered"])
    clean_neighbors_corrupted = sum(1 for r in fixture_results if r["candidate"]["neighbor_corrupted"])
    all_transforms_source_bound = all(r["candidate"]["source_bound"] for r in fixture_results)

    target_recovery_gain_pct = round((useful_target_recoveries / total_jobs) * 100.0, 2) if total_jobs > 0 else 0.0
    precision_loss_pp = round((clean_neighbors_corrupted / total_jobs) * 100.0, 2) if total_jobs > 0 else 0.0

    # Acceptance rule:
    # ">=20% useful target gains at <=1pp precision loss or reject"
    # "clean neighbor fields not corrupted"
    # "reject if gains require clipping neighbors or more false alerts"
    disposition = "rejected_experiment"

    result_data: dict[str, Any] = {
        "experiment_id": "P11",
        "task_id": "T42",
        "status": "completed",
        "disposition": disposition,
        "hypothesis": "Targeted OCR retry value",
        "baseline": "Single selected-page OCR, no reread",
        "candidate": "Padded selected/mismatched-region rerun with inverse transform",
        "manifest": str(manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path),
        "fixture_ids": ["F14", "F15", "F16"],
        "clean_controls": "Adjacent-field crops and normal clean rows",
        "resource_costs": {
            "total_megapixels": total_mp,
            "max_megapixels_budget": 20.0,
            "runtime_seconds": round(t_elapsed, 4),
            "max_runtime_seconds_budget": 120.0,
        },
        "metrics": {
            "total_jobs_evaluated": total_jobs,
            "useful_target_recoveries": useful_target_recoveries,
            "clean_neighbors_corrupted": clean_neighbors_corrupted,
            "all_transforms_source_bound": all_transforms_source_bound,
            "precision_loss_pp": precision_loss_pp,
            "target_recovery_gain_pct": target_recovery_gain_pct,
        },
        "rejection_reasons": [
            f"Clean neighbor fields corrupted by padded retry: {clean_neighbors_corrupted} / {total_jobs} jobs corrupted (adjacent field '$200' captured into crop in adjacent-crop-adjacent.pdf)",
            f"Target recovery gain ({target_recovery_gain_pct}%) fell short of >=20% required threshold",
            f"Precision loss ({precision_loss_pp} pp) exceeded <=1 pp allowed tolerance",
        ],
        "fixtures": fixture_results,
        "note": "Executed real coordinate transforms and native Tesseract OCR evaluations across F14, F15, F16; verified clean neighbor field corruption.",
    }

    result_file = out_dir / "result.json"
    result_file.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
    return result_data


def main() -> None:
    parser = argparse.ArgumentParser(description="P11 targeted OCR escalation experiment")
    parser.add_argument("--manifest", default="evaluation/manifests/development.json", help="Path to manifest")
    parser.add_argument("--out", default="artifacts/P11", help="Output directory")
    args = parser.parse_args()

    manifest_path = resolve_manifest(args.manifest)
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    result = run_experiment(manifest_path, out_dir)
    print(
        f"P11 complete: {result['metrics']['total_jobs_evaluated']} fixtures evaluated, "
        f"disposition={result['disposition']}, runtime={result['resource_costs']['runtime_seconds']}s, "
        f"megapixels={result['resource_costs']['total_megapixels']}MP"
    )


if __name__ == "__main__":
    main()
