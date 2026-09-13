# T44 Task Review: Native RapidOCR Complement Experiment (P13)

## Task Information
- **Task ID**: T44
- **Beads ID**: pdf-t44
- **Gate**: G4
- **Disposition**: `rejected_experiment`
- **Deliverables**:
  - `experiments/P13/`
  - `artifacts/P13/`
  - `docs/experiments/P13.md`
  - `artifacts/tasks/T44/`

## Acceptance Criteria Verification
1. **Complementary useful failures at fixed precision and memory budget or reject**:
   - Evaluated RapidOCR v3.8.1 against native Tesseract baseline within 1GiB memory budget.
   - RapidOCR rejected due to missing locked weight artifacts in upstream manifest and supply-chain / memory footprint constraints.
2. **Explicit missing-model and OOV behavior**:
   - Missing weights produce explicit typed audit status (`unavailable_due_to_missing_weights`), refusing silent or dynamic downloads.
3. **No runtime network**:
   - Zero network requests permitted or executed (`--network none` policy respected).
4. **No consensus-as-truth (I16)**:
   - Preserves independent reader observations; engine agreement is not treated as ground truth.
5. **Full raw and negative outcomes documented**:
   - Complete negative outcome, rationale, and recommendation recorded in `artifacts/P13/result.json` and `docs/experiments/P13.md`.

## Evidence Summary
- **Tests**: 5 collected, 5 passed, 0 failed, 0 skipped.
- **Verification Command**:
  - `python experiments/P13/run.py --manifest evaluation/manifests/development.json --out artifacts/P13` (1/1 passed)
  - `python experiments/P13/test_experiment.py` (4/4 passed)
