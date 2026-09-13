# Independent Review — T42 (Run targeted OCR escalation experiment)

## Review Metadata
- **Task**: T42 / P11
- **Reviewed Commit**: `c4824885c9abbd2d59f9a810a011d1abe28d5349`
- **Reviewer**: Antigravity Reviewer (Session `agy-review-t42-v2fix`)
- **Date**: 2026-09-13
- **Disposition**: `completed` / `rejected_experiment`

## Counterexample and Defect Verification
1. **Elimination of Mocked/Hardcoded OCR**:
   - Replaced variant-name based booleans (`variant == 'clipped'`) with real PIL image cropping and actual Tesseract OCR execution.
   - Point-to-pixel coordinate transform `pt_to_px()` verified: accurately maps PDF points to top-left PIL image coordinates with edge clamping.
   - Independent scoring verifies whether `target_str` and `neighbor_str` actually appear in the baseline vs candidate OCR text.
2. **Counterexample Confirmation**:
   - Tested mocked empty OCR (`ocr_fn=lambda img: ""`): correctly verified that target recoveries = 0 and neighbor corruptions = 0. No recoveries or corruptions occur without actual OCR text evidence.
3. **Manifest Validation**:
   - Tested empty manifest rejection (`{"entries": []}`): raises `ValueError` immediately.
   - Tested held-out evaluation manifest rejection (`split: "evaluation"`): raises `ValueError` immediately.
4. **Real OCR Measurements**:
   - `adjacent-crop-clipped.pdf`: unpadded baseline crop reads `'100'`, padded crop recovers `'$100'`.
   - `adjacent-crop-adjacent.pdf`: baseline crop isolates `'$100'`, padded crop captures neighbor into `'$100 $200'` (corrupting neighbor boundary).

## Acceptance Criteria Verification
1. **>=20% useful target gains at <=1pp precision loss or reject**:
   - Useful target recoveries: 1 out of 8 evaluated jobs (12.5%), falling short of the >=20% gain requirement.
   - Precision loss on neighbor boundaries: 12.5 pp (1 corrupted boundary out of 8 jobs), far exceeding the <=1.0 pp allowed loss.
   - Triggered mandatory rejection of experiment.
2. **Clean neighbor fields not corrupted**:
   - On `adjacent-crop-adjacent.pdf` (F16), context padding captured the adjacent neighbor field `$200` into the `$100` crop box.
   - Fails the non-negotiable negative control requirement: clean neighbor fields were corrupted.
3. **Every accepted transform source-bound**:
   - All candidate transformations are explicitly attributed as `padded_region_retry_inverse_affine` and preserve source binding (I16, I17).
4. **Failed/modelmissing jobs remain denominator**:
   - Full 8-job denominator preserved across F14, F15, F16; no jobs omitted or dropped.
5. **Full raw receipt retained**:
   - Detailed raw observations, bounding boxes, text, timing, and pixel counts recorded in `artifacts/P11/result.json`.

## Evidence Summary
- **Tests**: 9 collected, 9 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python experiments/P11/run.py --manifest evaluation/manifests/development.json --out artifacts/P11` (1/1 passed)
  - `python experiments/P11/test_experiment.py` (8/8 passed)
  - `python3 scripts/task_acceptance.py task T42` (exit 0)
