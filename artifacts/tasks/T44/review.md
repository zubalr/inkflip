# Independent Review — T44 (Evaluate one native RapidOCR complement)

## Review Metadata
- **Task**: T44 / P13
- **Reviewed Commit**: `7f592576b92f7e7e6ae8d5b8ff3199bc4ca364e0`
- **Reviewer**: Antigravity (Teamwork Independent Reviewer)
- **Date**: 2026-09-13
- **Status**: `passed` (task requirements satisfied; candidate properly evaluated as blocked)
- **Disposition**: `blocked_missing_dependency_and_weights` (`default_not_installed`)

## Acceptance Criteria & Negative Control Verification
1. **Manifest parsing and fixture validation**:
   - Manifest loaded and validated from `fixtures/manifest.json`.
   - Evaluated 8 development fixtures across F14 (`native-unicode`), F15 (`ocr-material`), and F16 (`adjacent-crop`).
   - Manifest loader verified to fail terminally on empty, corrupted, or held-out manifests.
2. **Actual baseline execution across manifest fixtures**:
   - Evaluated all 8 fixtures using native Tesseract 5.5.3 on 2.0x rasters rendered via PDFium.
   - Captured exact per-fixture timing (~0.05s–0.12s), raster pixel dimensions, and raw OCR output.
   - Raw PNG rasters persisted to disk in `artifacts/P13/rasters/` for durable verification.
3. **Failure denominator accounting**:
   - Tesseract execution logic preserves nonzero exit codes, timeouts, and missing binaries as terminal failures.
   - Tested counterexample: mocked nonzero Tesseract exit code produces `status: "failed"` and is recorded in the denominator, never falsely counted as a successful empty-text run.
4. **Candidate provenance, PP-OCRv5 mobile English audit, and counterexamples**:
   - Audited candidate against Source S47: `RapidOCR v3.8.1` with `PP-OCRv5 mobile English` configuration (`en_PP-OCRv5_mobile_det.onnx`, `en_PP-OCRv5_mobile_rec.onnx`).
   - Implemented binary protobuf header validation (`is_valid_onnx_model`).
   - Tested review counterexample: dummy files containing `"not an ONNX model"` fail binary validation and trigger `candidate_rejected_corrupted_weights`, proving unverified models cannot be marked available.
   - Offline containment invariant enforces that external package and model downloads are blocked; attempted preparation recorded honestly.
5. **Memory and containment measurement**:
   - Process tree peak RSS measured via `resource.getrusage` at 55.88 MB, well within the 1 GiB memory budget.
   - Documented platform containment behavior (macOS `RLIMIT_AS` non-enforcement audited via getrusage).
6. **Integration decision**:
   - RapidOCR candidate remains `default_not_installed`.
   - Native Tesseract remains the sole primary native OCR engine.

## Evidence Summary
- **Tests**: 8 collected, 8 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python3 experiments/P13/run.py --manifest evaluation/manifests/development.json --out artifacts/P13` (exit 0)
  - `python3 experiments/P13/test_experiment.py` (8/8 passed)
  - `python3 scripts/task_acceptance.py task T44` (exit 0)
