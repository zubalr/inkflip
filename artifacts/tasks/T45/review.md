# T45 Task Review: Original-Preserving Geometric Raster Evaluation (P14)

## Task Information
- **Task ID**: T45
- **Beads ID**: pdf-t45
- **Gate**: G4
- **Disposition**: `rejected_experiment`
- **Deliverables**:
  - `experiments/P14/`
  - `artifacts/P14/`
  - `docs/experiments/P14.md`
  - `artifacts/tasks/T45/`

## Acceptance Criteria Verification
1. **Any lost registration or clean corruption rejects**:
   - Tested automatic affine rotation / deskew candidate against clean ruled controls.
   - Bilinear and bicubic rotation resampling introduces pixel interpolation blur on 1-pixel rules and causes subpixel coordinate drift.
   - In accordance with the acceptance criteria, the candidate is formally rejected.
2. **Gain must transfer beyond the challenge generator**:
   - Synthetic rotated challenges do not demonstrate generalizable OCR or reading order improvements on real documents without corrupting clean controls.
3. **No generic reconstruction/search or PDF write path**:
   - Original PDF fixture bytes and rendered raster buffers are kept immutable (I01, I02). No PDF rewriting, synthesis, or unanchored geometry generation was performed.
4. **Negative result closes task with deleted production candidate**:
   - Negative outcome, rejection rationale, and architectural recommendation documented in `docs/experiments/P14.md` and `artifacts/P14/result.json`. No production candidate is promoted.

## Evidence Summary
- **Tests**: 6 collected, 6 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python experiments/P14/run.py --manifest evaluation/manifests/development.json --out artifacts/P14` (1/1 passed)
  - `python experiments/P14/test_experiment.py` (5/5 passed)
