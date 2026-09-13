# Independent Review — T45 (Evaluate original-preserving raster geometry only)

## Review Metadata
- **Task**: T45 / P14
- **Reviewed Commit**: `bfd57611cd0e487bae5fc3426b0c2cfc1a9a67e0`
- **Reviewer**: Antigravity (Teamwork Reviewer)
- **Date**: 2026-09-13
- **Disposition**: `completed` / `rejected_experiment` (`rejected_from_production`)

## Acceptance Criteria Verification
1. **Measured clean-control corruption**:
   - Evaluated 9 fixtures including 5 clean controls across F06, F07, F09, F15.
   - Rendered real 2.0x rasters via PDFium; measured high-frequency edge variance and pixel differences.
   - Resampling rotation induced ~3.5% mean edge variance degradation (anti-aliasing blur) on sharp vector glyphs and ruled forms.
   - Resampling corrupts 5 / 5 clean controls, violating the non-negotiable negative control requirement.
2. **Subpixel coordinate drift and registration loss**:
   - Quantization on intermediate pixel grids produced up to 0.3536 px subpixel coordinate drift upon inverse mapping.
   - Triggered mandatory rejection criterion: "Any lost registration or clean corruption rejects".
3. **Source file preservation (I01, I04)**:
   - All input PDF fixtures verified byte-identical before and after execution (zero byte mutations).
4. **Canonical raster immutability (I02)**:
   - Evaluated candidate transforms on separately allocated image buffers with explicit source attribution (I16, I17); canonical rasters remained unaltered.
5. **Architectural & integration decision**:
   - Candidate is formally rejected from production.
   - Production pipeline preserves raw canonical rasters without automated geometric repair or warping.

## Evidence Summary
- **Tests**: 4 collected, 4 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python experiments/P14/run.py --manifest evaluation/manifests/development.json --out artifacts/P14` (1/1 passed)
  - `python experiments/P14/test_experiment.py` (4/4 passed)
  - `python3 scripts/task_acceptance.py task T45 --report artifacts/tasks/T45/receipt.json` (exit 0)
