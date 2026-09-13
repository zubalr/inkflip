# Independent Review — T44 (Evaluate one native RapidOCR complement)

## Review Metadata
- **Task**: T44 / P13
- **Evaluated Commit**: `12e521e98fbd4f3c97f0db6c906e5377e9c8ac6b`
- **Worker Evaluation**: Antigravity Worker
- **Review Status**: Review Pending (Worker evaluation completed and substantiated; independent review pending coordinator dispatch)
- **Date**: 2026-09-13
- **Disposition**: `completed` / `candidate_evaluated_unintegrated` (`default_not_installed`)

## Acceptance Criteria & Negative Control Verification
1. **Isolated Environment & Official Models**:
   - Installed in experiment-local environment (`experiments/P13/.venv`) with `rapidocr==3.8.1`, `onnx==1.22.0`, `onnxruntime==1.30.0`.
   - Staged official PP-OCRv5 mobile English models with trusted SHA-256 digests:
     - `ch_PP-OCRv5_det_mobile.onnx`: `4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae`
     - `en_PP-OCRv5_rec_mobile.onnx`: `c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8`
2. **Protobuf Wire Validation & Counterexample**:
   - `is_valid_onnx_model` parses protobuf field tags and wire types and verifies digest.
   - Rejection proven for junk-ONNX counterexample `b"\x08" + b"\x00" * 127` as invalid protobuf wire format.
3. **Real Candidate & Baseline Execution**:
   - Baseline: Native Tesseract 5.5.3 completed 8/8 fixtures (~0.53s total), persisting PNG rasters to `artifacts/P13/rasters/`.
   - Candidate: RapidOCR inference executed across all 8 development rasters, generating raw boxes, text, and confidences (~0.95s total).
4. **Memory Containment**:
   - Cached engine instance and optimized limit parameters bound peak RSS to ~324 MB, strictly within the 1 GiB budget.
5. **No Consensus-as-Truth & Integration Decision**:
   - Candidate and baseline outputs are reported as distinct reader observations; shared pixels are never treated as consensus truth (Invariant I17).
   - Candidate requires ~43 MB of model weights and additional runtime dependencies without displacing native Tesseract.
   - Candidate remains `default_not_installed`; native Tesseract remains the sole production OCR engine.

## Evidence Summary
- **Tests**: 13 collected, 13 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python experiments/P13/run.py --manifest evaluation/manifests/development.json --out artifacts/P13` (exit 0)
  - `python experiments/P13/test_experiment.py` (13/13 passed)
