# Independent Review — T41 (Run paint-order and ink-counterexample experiment)

## Review Metadata
- **Task**: T41 / P09
- **Reviewed Commit**: `d48409128dfc51229bd46633114a14de11ffab27`
- **Reviewer**: Antigravity (Teamwork Reviewer)
- **Date**: 2026-09-13
- **Disposition**: `completed` / `rejected_heuristic_recommendation`

## Acceptance Criteria Verification
1. **Zero hard-control false visibility**:
   - Evaluated 9 fixtures across F04, F05, F06, F24 families.
   - Bounded paint-order candidate achieved 0 false visibilities (precision 1.0) on all negative controls.
2. **Precision/coverage/runtime recorded**:
   - Metadata baseline: precision 50.0%, 4 false visibilities, coverage 9/9, runtime 0.02s.
   - Rectangular ink heuristic: precision 57.1%, 3 false visibilities, coverage 9/9, runtime 0.10s.
   - Bounded paint-order candidate: precision 100.0%, 0 false visibilities, coverage 9/9, runtime 0.08s.
3. **Candidate gain measured without held-out leakage**:
   - All tests run against development split (`fixtures/development/`).
4. **Negative result complete**:
   - Proven counterexample on `overlap-ink-invisible.pdf` (F24) demonstrates that rectangular-ink heuristics fail when unrelated drawing strokes intersect text bounding boxes.
5. **Architectural boundary**:
   - Recommends rejecting universal visibility heuristics from production; explicit object render modes and independent reader observations remain standard.

## Evidence Summary
- **Tests**: 6 collected, 6 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python experiments/P09/run.py --manifest evaluation/manifests/development.json --out artifacts/P09` (1/1 passed)
  - `python experiments/P09/test_experiment.py` (5/5 passed)
