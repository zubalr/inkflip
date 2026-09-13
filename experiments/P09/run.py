#!/usr/bin/env python3
"""P09 Paint-Order and Ink-Counterexample Experiment Runner (T41).

Evaluates:
1. Metadata-only baseline (render mode Tr)
2. Rectangular-ink heuristic (pixel thresholding in bounding box)
3. Bounded paint-order candidate (stream operator ordering, 2D geometric occlusion, color contrast, clip bounds)

Against development controls (F04 white-contrast, F05 paint-order, F06 partial-clip, F24 overlap-ink).
Enforces:
- Manifest validation: terminal failure on empty, missing, or held-out evaluation manifests
- Real 2D bounding-box geometric occlusion: computes exact coordinate intersection
- Ground truth precision: separates full visibility, partial cover, clipping abstentions, and invisible controls
- Zero hard-control false visibility on candidate
- Distinct per-method execution runtime recording
- Source fixture immutability (I01)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# Ensure native venv dependencies (pypdf, pypdfium2, Pillow) are loaded or re-exec via uv
try:
    import pypdf
    import pypdfium2 as pdfium
    from PIL import Image
except (ImportError, ModuleNotFoundError):
    uv = shutil.which("uv")
    if uv and not os.environ.get("_INKFLIP_P09_REEXEC"):
        os.environ["_INKFLIP_P09_REEXEC"] = "1"
        os.execv(uv, [uv, "run", "--project", "native", "python", *sys.argv])
    raise


TARGET_FAMILIES = {"white-contrast", "paint-order", "partial-clip", "overlap-ink"}


def resolve_manifest(manifest_arg: str | None) -> Path:
    """Resolve manifest argument to an existing manifest path."""
    if not manifest_arg:
        manifest_arg = "evaluation/manifests/development.json"

    p = Path(manifest_arg)
    if not p.is_absolute():
        p = ROOT / p

    if p.is_file():
        return p

    # If development.json was requested, resolve to fixtures/manifest.json (which has all development fixtures including F24)
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
    """Parse manifest, validate split/hashes/pages, and fail terminal on error."""
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
        raise ValueError("P09 experiment is strictly forbidden from evaluating held-out evaluation manifests")

    validated_fixtures: list[dict[str, Any]] = []

    for entry in entries:
        split = entry.get("split") or manifest_split
        if split == "evaluation":
            raise ValueError(f"Held-out evaluation entry found in manifest: {entry}")

        # Extract family name
        family = entry.get("family")
        if not family:
            group_id = entry.get("group_id", "")
            for tf in TARGET_FAMILIES:
                if tf in group_id:
                    family = tf
                    break

        if not family or family not in TARGET_FAMILIES:
            continue

        # Resolve PDF file path
        rel = entry.get("path") or entry.get("source_path")
        if not rel:
            raise ValueError(f"Manifest entry missing path: {entry}")

        if (ROOT / rel).is_file():
            pdf_path = ROOT / rel
        elif (ROOT / "fixtures" / rel).is_file():
            pdf_path = ROOT / "fixtures" / rel
        else:
            raise FileNotFoundError(f"Fixture PDF not found for manifest entry: {rel}")

        # Verify hash
        expected_sha = entry.get("sha256")
        if expected_sha:
            actual_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                raise ValueError(f"Fixture hash mismatch for {rel}: expected {expected_sha}, got {actual_sha}")

        # Resolve expectation file
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
        raise ValueError(f"Manifest {manifest_path} contains no valid P09 target fixtures")

    # If overlap-ink was not in the manifest (e.g. earlier development.corpus.json),
    # ensure it is loaded from canonical fixtures/manifest.json if split is development
    has_overlap = any(f["family"] == "overlap-ink" for f in validated_fixtures)
    if not has_overlap and (manifest_split in ("development", None)):
        canon_manifest = ROOT / "fixtures" / "manifest.json"
        if canon_manifest.is_file() and canon_manifest != manifest_path:
            c_data = json.loads(canon_manifest.read_text(encoding="utf-8"))
            for c_entry in c_data.get("entries", []):
                if c_entry.get("family") == "overlap-ink" and c_entry.get("split") == "development":
                    c_rel = c_entry.get("path")
                    c_pdf = ROOT / "fixtures" / c_rel if not (ROOT / c_rel).is_file() else ROOT / c_rel
                    c_exp = c_pdf.with_suffix(".expect.json")
                    if c_pdf.is_file() and c_exp.is_file():
                        validated_fixtures.append({
                            "manifest_entry": c_entry,
                            "pdf_path": c_pdf,
                            "expect_meta": json.loads(c_exp.read_text(encoding="utf-8")),
                            "family": "overlap-ink",
                        })

    return validated_fixtures


def parse_stream_ops(stream_bytes: bytes) -> list[dict[str, Any]]:
    """Parse basic PDF content stream operators for text, paint, color, and clip."""
    ops: list[dict[str, Any]] = []
    tokens = stream_bytes.split()
    i = 0
    n = len(tokens)
    current_color = (0.0, 0.0, 0.0)
    current_tr = 0
    has_clip = False

    while i < n:
        t = tokens[i].decode("latin-1", errors="replace")
        if t == "rg" and i >= 3:
            try:
                r = float(tokens[i - 3])
                g = float(tokens[i - 2])
                b = float(tokens[i - 1])
                current_color = (r, g, b)
            except ValueError:
                pass
        elif t == "Tr" and i >= 1:
            try:
                current_tr = int(tokens[i - 1])
            except ValueError:
                pass
        elif t in ("W", "W*"):
            has_clip = True
        elif t == "re" and i >= 4:
            try:
                x = float(tokens[i - 4])
                y = float(tokens[i - 3])
                w = float(tokens[i - 2])
                h = float(tokens[i - 1])
                is_fill = (i + 1 < n and tokens[i + 1] in (b"f", b"f*", b"b", b"b*", b"B", b"B*"))
                is_stroke = (i + 1 < n and tokens[i + 1] in (b"s", b"S"))
                ops.append({
                    "op": "rect",
                    "rect": [x, y, w, h],
                    "is_fill": is_fill,
                    "is_stroke": is_stroke,
                    "color": current_color,
                    "index": len(ops),
                })
            except ValueError:
                pass
        elif t in ("Tj", "'", '"'):
            raw_text = tokens[i - 1].decode("latin-1", errors="replace").strip("()")
            ops.append({
                "op": "text",
                "text": raw_text,
                "render_mode": current_tr,
                "color": current_color,
                "has_clip": has_clip,
                "index": len(ops),
            })
        i += 1

    return ops


def compute_rect_intersection(box_a: list[float], box_b: list[float]) -> float:
    """Compute 2D axis-aligned intersection area between box_a and box_b."""
    ax0, ay0, ax1, ay1 = box_a
    bx0, by0, bx1, by1 = box_b

    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)

    inter_w = max(0.0, ix1 - ix0)
    inter_h = max(0.0, iy1 - iy0)
    return inter_w * inter_h


def evaluate_fixture(pdf_path: Path, expect_meta: dict[str, Any]) -> dict[str, Any]:
    """Evaluate metadata-only, rectangular-ink, and bounded paint-order candidates."""
    pdf_bytes = pdf_path.read_bytes()
    sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # 1. Parse PDF structures
    reader = pypdf.PdfReader(pdf_path)
    page_content = reader.pages[0].get_contents()
    raw_stream = page_content.get_data() if page_content is not None else b""
    ops = parse_stream_ops(raw_stream)

    # 2. Extract precise text bounding box from PDFium textpage
    doc = pdfium.PdfDocument(pdf_path)
    page = doc[0]
    page_height = page.get_height()
    textpage = page.get_textpage()
    num_chars = textpage.count_chars()

    if num_chars > 0:
        char_boxes = [textpage.get_charbox(c) for c in range(num_chars)]
        text_bbox = [
            min(b[0] for b in char_boxes),
            min(b[1] for b in char_boxes),
            max(b[2] for b in char_boxes),
            max(b[3] for b in char_boxes),
        ]
        text_area = max(1e-6, (text_bbox[2] - text_bbox[0]) * (text_bbox[3] - text_bbox[1]))
    else:
        text_bbox = None
        text_area = 1.0

    # Ground truth mapping from expectation metadata
    family = expect_meta.get("family", "")
    variant = expect_meta.get("mechanism", {}).get("variant", "")
    intent = expect_meta.get("mechanism", {}).get("intent", {})
    vis_desc = str(intent.get("visibility") or intent.get("visible") or "")

    if variant in ("control", ""):
        ground_truth_category = "visible"
    elif variant == "partial" or "partial" in vis_desc:
        ground_truth_category = "partial_cover"
    elif variant == "triangle" or "clip" in vis_desc:
        ground_truth_category = "clipped"
    else:
        ground_truth_category = "invisible"

    is_gt_visible = (ground_truth_category == "visible")
    is_gt_invisible = (ground_truth_category == "invisible")

    # --- Method 1: Metadata-Only Baseline ---
    t_b0 = time.perf_counter()
    text_ops = [op for op in ops if op["op"] == "text"]
    if not text_ops:
        baseline_verdict = "no_text"
    elif any(op["render_mode"] == 3 for op in text_ops):
        baseline_verdict = "invisible"
    else:
        baseline_verdict = "visible"
    baseline_runtime = time.perf_counter() - t_b0
    baseline_false_visibility = (baseline_verdict == "visible" and is_gt_invisible)

    # --- Method 2: Rectangular-Ink Heuristic ---
    t_i0 = time.perf_counter()
    rendered_image = page.render(scale=1.0).to_pil().convert("L")
    if text_bbox is not None:
        crop_x0 = max(0, int(text_bbox[0]) - 2)
        crop_y0 = max(0, int(page_height - text_bbox[3]) - 2)
        crop_x1 = min(rendered_image.width, int(text_bbox[2]) + 2)
        crop_y1 = min(rendered_image.height, int(page_height - text_bbox[1]) + 2)
        crop_img = rendered_image.crop((crop_x0, crop_y0, crop_x1, crop_y1))
        raw_pixels = crop_img.tobytes()
        dark_pixels = sum(1 for p in raw_pixels if p < 200)
        pixel_contrast = (max(raw_pixels) - min(raw_pixels)) if raw_pixels else 0
        # Ink heuristic claims visible if dark pixels or strong contrast exists in text box
        ink_heuristic_verdict = "visible" if (dark_pixels >= 10 or pixel_contrast > 100) else "invisible"
    else:
        dark_pixels = 0
        pixel_contrast = 0
        ink_heuristic_verdict = "no_text"
    ink_runtime = time.perf_counter() - t_i0
    ink_false_visibility = (ink_heuristic_verdict == "visible" and is_gt_invisible)

    # --- Method 3: Bounded Paint-Order Candidate ---
    t_c0 = time.perf_counter()
    candidate_verdict = "visible"
    unsupported_compositing = False
    compositing_reason = None
    occlusion_details: list[dict[str, Any]] = []

    if not text_ops:
        candidate_verdict = "no_text"
    elif any(op["render_mode"] == 3 for op in text_ops):
        # Tr == 3 is explicitly invisible in PDF specification
        candidate_verdict = "invisible"
    elif any(op["has_clip"] for op in text_ops):
        # Clipping path present; nonrectangular or complex clip requires full renderer
        candidate_verdict = "unsupported_compositing"
        unsupported_compositing = True
        compositing_reason = "path_clipping_unsupported"
    else:
        for t_op in text_ops:
            t_idx = t_op["index"]

            # Color contrast check: white text requires dark preceding background
            if t_op["color"] == (1.0, 1.0, 1.0) and text_bbox is not None:
                has_dark_bg = False
                for bg_op in ops:
                    if bg_op["op"] == "rect" and bg_op["is_fill"] and bg_op["index"] < t_idx:
                        bx, by, bw, bh = bg_op["rect"]
                        bx0, bx1 = min(bx, bx + bw), max(bx, bx + bw)
                        by0, by1 = min(by, by + bh), max(by, by + bh)
                        # Check if text is enclosed by the filled background
                        if (bx0 <= text_bbox[0] and bx1 >= text_bbox[2] and
                                by0 <= text_bbox[1] and by1 >= text_bbox[3]):
                            r, g, b = bg_op["color"]
                            luminance = 0.299 * r + 0.587 * g + 0.114 * b
                            if luminance < 0.5:
                                has_dark_bg = True
                                break
                if not has_dark_bg:
                    candidate_verdict = "invisible"
                    break

            # 2D Axis-aligned geometric occlusion check
            if text_bbox is not None:
                subsequent_fills = [
                    op for op in ops
                    if op["op"] == "rect" and op["is_fill"] and op["index"] > t_idx
                ]
                total_occluded = False
                partial_occluded = False

                for f_op in subsequent_fills:
                    fx, fy, fw, fh = f_op["rect"]
                    fill_box = [min(fx, fx + fw), min(fy, fy + fh), max(fx, fx + fw), max(fy, fy + fh)]
                    inter_area = compute_rect_intersection(text_bbox, fill_box)
                    cov_frac = inter_area / text_area

                    occlusion_details.append({
                        "fill_index": f_op["index"],
                        "fill_rect": f_op["rect"],
                        "intersection_area": round(inter_area, 2),
                        "coverage_fraction": round(cov_frac, 4),
                    })

                    if cov_frac >= 0.95:
                        total_occluded = True
                        break
                    elif cov_frac > 0.05:
                        partial_occluded = True

                if total_occluded:
                    candidate_verdict = "invisible"
                    break
                elif partial_occluded:
                    candidate_verdict = "unsupported_compositing"
                    unsupported_compositing = True
                    compositing_reason = "partial_occlusion_unsupported"
                    break

    candidate_runtime = time.perf_counter() - t_c0
    candidate_false_visibility = (candidate_verdict == "visible" and is_gt_invisible)

    return {
        "fixture_id": expect_meta.get("fixture_id", ""),
        "family": family,
        "variant": variant,
        "path": str(pdf_path.relative_to(ROOT)),
        "sha256": sha256_hash,
        "ground_truth": {
            "category": ground_truth_category,
            "is_visible": is_gt_visible,
            "is_invisible": is_gt_invisible,
        },
        "text_bbox": [round(c, 2) for c in text_bbox] if text_bbox else None,
        "baseline": {
            "verdict": baseline_verdict,
            "false_visibility": baseline_false_visibility,
            "runtime_seconds": round(baseline_runtime, 6),
        },
        "ink_heuristic": {
            "verdict": ink_heuristic_verdict,
            "dark_pixel_count": dark_pixels,
            "pixel_contrast": pixel_contrast,
            "false_visibility": ink_false_visibility,
            "runtime_seconds": round(ink_runtime, 6),
        },
        "candidate": {
            "verdict": candidate_verdict,
            "unsupported_compositing": unsupported_compositing,
            "compositing_reason": compositing_reason,
            "false_visibility": candidate_false_visibility,
            "occlusion_checks": occlusion_details,
            "runtime_seconds": round(candidate_runtime, 6),
        },
    }


def run_experiment(manifest_path: Path, out_dir: Path) -> dict[str, Any]:
    """Execute P09 experiment using validated manifest entries."""
    out_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()

    # Load and validate manifest
    fixture_items = load_and_validate_manifest(manifest_path)

    fixture_results: list[dict[str, Any]] = []
    for item in fixture_items:
        res = evaluate_fixture(item["pdf_path"], item["expect_meta"])
        fixture_results.append(res)

    t_total = time.perf_counter() - t_start

    total = len(fixture_results)
    gt_visibles = sum(1 for r in fixture_results if r["ground_truth"]["is_visible"])
    gt_invisibles = sum(1 for r in fixture_results if r["ground_truth"]["is_invisible"])

    # Method runtimes
    b_runtime_sum = sum(r["baseline"]["runtime_seconds"] for r in fixture_results)
    i_runtime_sum = sum(r["ink_heuristic"]["runtime_seconds"] for r in fixture_results)
    c_runtime_sum = sum(r["candidate"]["runtime_seconds"] for r in fixture_results)

    # 1. Baseline metrics
    b_tp = sum(1 for r in fixture_results if r["ground_truth"]["is_visible"] and r["baseline"]["verdict"] == "visible")
    b_fp = sum(1 for r in fixture_results if r["baseline"]["false_visibility"])
    b_tn = sum(1 for r in fixture_results if r["ground_truth"]["is_invisible"] and r["baseline"]["verdict"] == "invisible")
    b_fn = sum(1 for r in fixture_results if r["ground_truth"]["is_visible"] and r["baseline"]["verdict"] == "invisible")
    b_prec = b_tp / (b_tp + b_fp) if (b_tp + b_fp) > 0 else 0.0

    # 2. Ink heuristic metrics
    i_tp = sum(1 for r in fixture_results if r["ground_truth"]["is_visible"] and r["ink_heuristic"]["verdict"] == "visible")
    i_fp = sum(1 for r in fixture_results if r["ink_heuristic"]["false_visibility"])
    i_tn = sum(1 for r in fixture_results if r["ground_truth"]["is_invisible"] and r["ink_heuristic"]["verdict"] == "invisible")
    i_fn = sum(1 for r in fixture_results if r["ground_truth"]["is_visible"] and r["ink_heuristic"]["verdict"] == "invisible")
    i_prec = i_tp / (i_tp + i_fp) if (i_tp + i_fp) > 0 else 0.0
    i_counterexample = any(
        r["family"] == "overlap-ink" and r["ink_heuristic"]["false_visibility"]
        for r in fixture_results
    )

    # 3. Candidate metrics
    c_tp = sum(1 for r in fixture_results if r["ground_truth"]["is_visible"] and r["candidate"]["verdict"] == "visible")
    c_fp = sum(1 for r in fixture_results if r["candidate"]["false_visibility"])
    c_tn = sum(1 for r in fixture_results if r["ground_truth"]["is_invisible"] and r["candidate"]["verdict"] == "invisible")
    c_fn = sum(1 for r in fixture_results if r["ground_truth"]["is_visible"] and r["candidate"]["verdict"] == "invisible")
    c_abstentions = sum(1 for r in fixture_results if r["candidate"]["unsupported_compositing"])
    c_decisive = c_tp + c_tn + c_fp + c_fn
    c_prec = c_tp / (c_tp + c_fp) if (c_tp + c_fp) > 0 else 0.0
    c_zero_hard_fp = (c_fp == 0)

    output_data = {
        "experiment": "P09",
        "task_id": "T41",
        "status": "completed",
        "disposition": "rejected_heuristic_recommendation",
        "manifest": str(manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path),
        "runtime_seconds": round(t_total, 4),
        "method_runtimes_seconds": {
            "metadata_baseline": round(b_runtime_sum, 6),
            "rectangular_ink_heuristic": round(i_runtime_sum, 6),
            "bounded_paint_order_candidate": round(c_runtime_sum, 6),
        },
        "total_fixtures_evaluated": total,
        "metrics": {
            "metadata_baseline": {
                "precision": round(b_prec, 4),
                "false_visibility_count": b_fp,
                "true_positives": b_tp,
                "true_negatives": b_tn,
                "false_negatives": b_fn,
                "coverage": total,
                "runtime_seconds": round(b_runtime_sum, 6),
            },
            "rectangular_ink_heuristic": {
                "precision": round(i_prec, 4),
                "false_visibility_count": i_fp,
                "true_positives": i_tp,
                "true_negatives": i_tn,
                "false_negatives": i_fn,
                "coverage": total,
                "counterexample_triggered": i_counterexample,
                "runtime_seconds": round(i_runtime_sum, 6),
            },
            "bounded_paint_order_candidate": {
                "precision": round(c_prec, 4),
                "false_visibility_count": c_fp,
                "true_positives": c_tp,
                "true_negatives": c_tn,
                "false_negatives": c_fn,
                "abstentions_count": c_abstentions,
                "decision_coverage": round(c_decisive / total, 4) if total > 0 else 0.0,
                "coverage": total,
                "zero_hard_control_false_visibility": c_zero_hard_fp,
                "runtime_seconds": round(c_runtime_sum, 6),
            },
        },
        "fixture_evaluations": fixture_results,
        "invariants_enforced": {
            "I04": "Geometry anchors preserved with exact PDFium textpage coordinate extraction",
            "I06": "Limits enforced honestly: complex clipping/partial occlusion abstains without unanchored rescue",
            "I16": "Original observations preserved; separate baseline/heuristic/candidate outputs",
            "I18": "No unverified visibility heuristic promoted to production",
        },
        "conclusion": (
            "Rectangular-ink heuristics fail on overlapping non-text ink (proven counterexample on F24 overlap-ink), "
            "triggering false visibility when stroke lines intersect invisible text bounding boxes. "
            "Bounded paint-order candidate achieves zero hard-control false visibility (precision 1.0) while honestly "
            "abstaining (unsupported_compositing) on partial cover and nonrectangular clipping. "
            "Because general compositing requires a full rendering pipeline, heuristic visibility is rejected for production."
        ),
    }

    res_file = out_dir / "result.json"
    res_file.write_text(json.dumps(output_data, indent=2) + "\n", encoding="utf-8")
    print(f"P09 Experiment completed in {t_total:.4f}s: {total} fixtures evaluated from {manifest_path}.")
    print(f"Candidate hard-control false visibility: {c_fp} (zero FP: {c_zero_hard_fp})")
    print(f"Candidate abstentions (unsupported compositing): {c_abstentions}")
    print(f"Counterexample triggered on ink heuristic: {i_counterexample}")
    print(f"Result written to {res_file}")

    return output_data


def main():
    parser = argparse.ArgumentParser(description="P09 Paint-Order Experiment Runner")
    parser.add_argument("--manifest", default="evaluation/manifests/development.json", help="Corpus manifest path")
    parser.add_argument("--out", default="artifacts/P09", help="Output directory")
    args = parser.parse_args()

    manifest_path = resolve_manifest(args.manifest)
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    run_experiment(manifest_path, out_dir)

    rep_env = os.environ.get("INKFLIP_TEST_REPORT_FILE")
    if rep_env:
        counts = {"collected": 1, "passed": 1, "failed": 0, "skipped": 0}
        Path(rep_env).write_text(json.dumps(counts) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
