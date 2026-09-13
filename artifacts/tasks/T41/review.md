# Independent Review — T41 (Run paint-order and ink-counterexample experiment)

## Review Metadata
- **Task**: T41 / P09
- **Evaluated Commit**: `12e521e98fbd4f3c97f0db6c906e5377e9c8ac6b`
- **Worker Evaluation**: Antigravity Worker
- **Review Status**: Review Pending (Worker evaluation completed and substantiated; independent review pending coordinator dispatch)
- **Date**: 2026-09-13
- **Disposition**: `completed` / `rejected_heuristic_recommendation`

## Counterexample and Defect Verification
1. **Manifest Validation**:
   - Tested empty manifest rejection (`{"entries": []}`): raises `ValueError` immediately.
   - Tested held-out evaluation manifest rejection (`split: "evaluation"`): raises `ValueError` immediately.
   - Tested explicitly missing manifest path (`/tmp/.../development.json`): raises `FileNotFoundError` without fallback.
   - Manifest parsing loads and validates entries from `fixtures/manifest.json`.
2. **2D Bounding-Box Occlusion Geometry**:
   - Evaluated exact character-level text bounding boxes from `pypdfium2` textpage against subsequent fill rectangles.
   - Full occlusion (`paint-order-after.pdf`, 100% cover) correctly identifies invisible text.
   - Partial occlusion (`partial-clip-partial.pdf`, 43.3% cover) correctly abstains with `unsupported_compositing`.
3. **Contrast and Control Labeling**:
   - `white-contrast-control.pdf` (white text on dark fill background) correctly identified as visible.
   - `white-contrast-white.pdf` (white text on white page) correctly identified as invisible.
4. **Independent Method Runtimes**:
   - Measured and recorded distinct timers for each method:
     - `metadata_baseline`: <0.001s
     - `rectangular_ink_heuristic`: ~0.005s
     - `bounded_paint_order_candidate`: <0.001s

## Acceptance Criteria Verification
1. **Zero hard-control false visibility**:
   - Bounded paint-order candidate achieved 0 false visibilities (precision 1.0) on all negative controls.
2. **precision/coverage/runtime recorded**:
   - Metadata baseline: precision 66.7%, 2 false visibilities, coverage 9/9, runtime <0.001s.
   - Rectangular ink heuristic: precision 80.0%, 1 false visibility (counterexample), coverage 9/9, runtime ~0.005s.
   - Bounded paint-order candidate: precision 100.0%, 0 false visibilities, decision coverage 77.8% (7/9, 2 abstentions), runtime <0.001s.
3. **candidate gain measured without held-out leakage**:
   - All tests run against development split (`fixtures/development/`).
4. **negative result is complete**:
   - Proven fatal counterexample on `overlap-ink-invisible.pdf` (F24) demonstrates that rectangular-ink heuristics fail when unrelated drawing strokes intersect text bounding boxes.
5. **proposed merge has separate adapter capability review and full controls.**:
   - Recommends rejecting universal visibility heuristics from production; explicit object render modes and independent reader observations remain standard.

## Evidence Summary
- **Tests**: 10 collected, 10 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python experiments/P09/run.py --manifest evaluation/manifests/development.json --out artifacts/P09` (exit 0)
  - `python experiments/P09/test_experiment.py` (9/9 passed)
