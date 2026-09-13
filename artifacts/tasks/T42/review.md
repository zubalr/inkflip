# Independent Review — T42 (Run targeted OCR escalation experiment)

## Review Metadata
- **Task**: T42 / P11
- **Evaluated Commit**: `d484425a3837f08414dbee51becc9d77c6301712`
- **Worker Evaluation**: Antigravity Worker
- **Review Status**: Review Pending (Worker evaluation completed and substantiated; independent review pending coordinator dispatch)
- **Date**: 2026-09-13
- **Disposition**: `completed` / `rejected_experiment`

## Counterexample and Defect Verification
1. **Elimination of Mocked/Hardcoded OCR**:
   - Real PIL image cropping and actual Tesseract OCR execution across all fixtures.
   - Point-to-pixel coordinate transform `pt_to_px()` verified: maps PDF points to top-left PIL image coordinates with edge clamping.
   - Independent scoring verifies whether `target_str` and `neighbor_str` actually appear in the baseline vs candidate OCR text.
2. **Counterexample Confirmation**:
   - Tested mocked empty OCR (`ocr_fn=lambda img: ""`): verified target recoveries = 0 and neighbor corruptions = 0.
3. **Manifest Validation**:
   - Tested empty manifest rejection: raises `ValueError` immediately.
   - Tested held-out evaluation manifest rejection: raises `ValueError` immediately.
   - Tested explicitly missing manifest path: raises `FileNotFoundError` without fallback.
4. **Real OCR Measurements**:
   - `adjacent-crop-clipped.pdf`: unpadded baseline crop reads '100', padded crop recovers '$100'.
   - `adjacent-crop-adjacent.pdf`: baseline crop isolates '$100', padded crop captures neighbor into '$100 $200' (corrupting neighbor boundary).

## Acceptance Criteria Verification
1. **>=20% useful target gains at<=1ppprecision loss or reject**:
   - Useful target recoveries: 1 out of 8 evaluated jobs (12.5%, failing >=20% threshold).
   - Precision loss on neighbor boundaries: 12.5 pp (1 corrupted boundary out of 8 jobs, failing <=1.0 pp allowed loss).
   - Cleanly triggered mandatory rejection.
2. **clean neighbor fields not corrupted**:
   - On `adjacent-crop-adjacent.pdf` (F16), context padding captured the adjacent neighbor field ($200) into the $100 crop box, corrupting clean neighbor boundaries. Fails non-negotiable negative control.
3. **every accepted transform source-bound**:
   - All candidate transformations attributed as `padded_region_retry_inverse_affine` with strict source binding and inverse mapping (I16, I17).
4. **failed/modelmissing jobs remain denominator**:
   - Full 8-job denominator preserved across F14, F15, F16; no jobs dropped.
5. **full raw receipt retained.**:
   - Detailed raw observations, bounding boxes, text, timing, and pixel costs recorded in `artifacts/P11/result.json`.

## Evidence Summary
- **Tests**: 9 collected, 9 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python experiments/P11/run.py --manifest evaluation/manifests/development.json --out artifacts/P11` (exit 0)
  - `python experiments/P11/test_experiment.py` (9/9 passed)
