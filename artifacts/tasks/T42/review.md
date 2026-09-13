# Independent Review — T42 (Run targeted OCR escalation experiment)

## Review Metadata
- **Task**: T42 / P11
- **Reviewed Commit**: `9c5fecee63b494632464f36b4abb6d72a454f3c8`
- **Reviewer**: Antigravity (Teamwork Reviewer)
- **Date**: 2026-09-13
- **Disposition**: `completed` / `rejected_experiment`

## Acceptance Criteria Verification
1. **>=20% useful target gains at <=1pp precision loss or reject**:
   - Useful target recoveries: 1 out of 8 evaluated jobs (12.5%), falling short of the >=20% gain requirement.
   - Precision loss on neighbor boundaries: 12.5 pp (1 corrupted boundary out of 8 jobs), far exceeding the <=1.0 pp allowed loss.
2. **Clean neighbor fields not corrupted**:
   - On `adjacent-crop-adjacent.pdf` (F16), context padding captured the adjacent neighbor field `$200` into the `$100` crop box.
   - Fails the non-negotiable negative control requirement: clean neighbor fields were corrupted.
3. **Every accepted transform source-bound**:
   - All candidate transformations are explicitly attributed as `padded_region_retry_inverse_affine` and preserve source binding (I16, I17).
4. **Failed/modelmissing jobs remain denominator**:
   - Full 8-job denominator preserved across F14, F15, F16; no jobs omitted or dropped.
5. **Full raw receipt retained**:
   - Detailed raw observations, bounding boxes, text, timing, and pixel counts recorded in `artifacts/P11/result.json`.
6. **Resource bounds respected**:
   - Total megapixels processed: 3.19 MP (budget <= 20.0 MP).
   - Execution time: ~0.54s (budget <= 120.0s).

## Evidence Summary
- **Tests**: 4 collected, 4 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python experiments/P11/run.py --manifest evaluation/manifests/development.json --out artifacts/P11` (1/1 passed)
  - `python experiments/P11/test_experiment.py` (4/4 passed)
  - `python3 scripts/task_acceptance.py task T42 --report artifacts/tasks/T42/receipt.json` (exit 0)
