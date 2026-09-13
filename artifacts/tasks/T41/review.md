# Independent Review — T41 (Run paint-order and ink-counterexample experiment)

## Review Metadata
- **Task**: T41 / P09
- **Reviewed Commit**: `89bcffce37c44af88b0dd29f4196710b8f48d4e1`
- **Reviewer**: Antigravity Reviewer (Session `agy-review-t41-v2fix`)
- **Date**: 2026-09-13
- **Disposition**: `completed` / `rejected_heuristic_recommendation`

## Counterexample and Defect Verification
1. **Manifest Validation**:
   - Tested empty manifest rejection (`{"entries": []}`): raises `ValueError` immediately and terminates.
   - Tested held-out evaluation manifest rejection (`split: "evaluation"`): raises `ValueError` immediately and terminates.
   - Manifest parsing now loads and validates entries from `fixtures/manifest.json`.
2. **2D Bounding-Box Occlusion Geometry**:
   - Evaluated exact character-level text bounding boxes from `pypdfium2` textpage against subsequent fill rectangles.
   - Verified that a disjoint rectangle (e.g. corner of page) does not cause false occlusion.
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
2. **Precision/coverage/runtime recorded**:
   - Metadata baseline: precision 66.7%, 2 false visibilities, coverage 9/9, runtime <0.001s.
   - Rectangular ink heuristic: precision 80.0%, 1 false visibility (counterexample), coverage 9/9, runtime ~0.005s.
   - Bounded paint-order candidate: precision 100.0%, 0 false visibilities, decision coverage 77.8% (7/9, 2 abstentions), runtime <0.001s.
3. **Candidate gain measured without held-out leakage**:
   - All tests run against development split (`fixtures/development/`).
4. **Negative result complete**:
   - Proven fatal counterexample on `overlap-ink-invisible.pdf` (F24) demonstrates that rectangular-ink heuristics fail when unrelated drawing strokes intersect text bounding boxes.
5. **Architectural boundary**:
   - Recommends rejecting universal visibility heuristics from production; explicit object render modes and independent reader observations remain standard.

## Evidence Summary
- **Tests**: 9 collected, 9 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python experiments/P09/run.py --manifest evaluation/manifests/development.json --out artifacts/P09` (1/1 passed)
  - `python experiments/P09/test_experiment.py` (8/8 passed)
