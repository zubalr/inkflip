# Independent Review — T45 (Evaluate original-preserving raster geometry only)

## Review Metadata
- **Task**: T45 / P14
- **Reviewed Commit**: `79f104fe711e74a88981447db00d98ca575f0a37`
- **Reviewer**: Antigravity (Teamwork Independent Reviewer)
- **Date**: 2026-09-13
- **Status**: `passed` (task requirements satisfied; candidate cleanly rejected based on observed evidence)
- **Disposition**: `completed` / `rejected_experiment` (`rejected_from_production`)

## Acceptance Criteria & Negative Control Verification
1. **Manifest parsing and comprehensive geometry population**:
   - Manifest dynamically loaded from `fixtures/manifest.json`.
   - Evaluated 14 fixtures spanning all 4 required geometry families:
     - F06 (`partial-clip`): `partial-clip-control.pdf`, `partial-clip-partial.pdf`, `partial-clip-triangle.pdf`
     - F07 (`origins-rotation`): `geometry-control.pdf`, `geometry-0.pdf`, `geometry-90.pdf`, `geometry-180.pdf`, `geometry-270.pdf`
     - F09 (`text-transform`): `text-transform-control.pdf` (with crosshair fiducial), `text-transform-skew.pdf`, `text-transform-rotated.pdf`
     - F15 (`ocr-material`): `ocr-material-control.pdf`, `ocr-material-sign-ambiguity.pdf`, `ocr-material-digit-ambiguity.pdf`
   - Manifest loader verified to fail terminally on empty, corrupted, or held-out manifests.
2. **Rendered fiducial displacement measurement**:
   - Located physical rendered fiducials directly in the raster (e.g. F09 crosshair intersection at (320, 60) and ink anchor centroids).
   - Reconstructed raster fiducial anchors exhibited up to 0.3803 px displacement under forward + inverse deskew roundtrip.
3. **Dynamic decision derivation from direct observations**:
   - Tested review counterexample: identity transform ($\theta = 0^\circ$) produced exactly 0.0% edge variance degradation, 0.0 px fiducial drift, 0.0 px subpixel drift, 0 clean controls corrupted, and `lost_registration_detected = False` (`candidate_accepted`).
   - Candidate deskew ($\theta = 1.0^\circ$) corrupted 4 / 4 clean controls and exhibited lost registration, triggering the non-negotiable rejection rule: `"Any lost registration or clean corruption rejects"`.
4. **Source and raster immutability (I01, I02, I04)**:
   - Source PDF bytes verified byte-identical before and after execution (zero byte mutations).
   - Candidate buffers allocated separately; canonical rasters remained unaltered.
   - Raw rasters (baseline, candidate, roundtrip) persisted into `artifacts/P14/rasters/`.
5. **Architectural & integration decision**:
   - Candidate is formally rejected from production (`rejected_from_production`).
   - Production pipeline preserves raw canonical rasters without automated geometric repair or warping.

## Evidence Summary
- **Tests**: 8 collected, 8 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python3 experiments/P14/run.py --manifest evaluation/manifests/development.json --out artifacts/P14` (exit 0)
  - `python3 experiments/P14/test_experiment.py` (8/8 passed)
  - `python3 scripts/task_acceptance.py task T45` (exit 0)
