# Independent Review — T43 (Evaluate secondary browser reader, decide explicitly)

## Review Metadata
- **Task**: T43 / P12
- **Evaluated Commit**: `eb2392a2618347876db003c685d3f7333de62d7f`
- **Worker Evaluation**: Antigravity Worker
- **Review Status**: Review Pending (Worker evaluation completed and substantiated; independent review pending coordinator dispatch)
- **Date**: 2026-09-13
- **Disposition**: `completed` / `candidate_verified_unintegrated` (`default_unavailable`)

## Acceptance Criteria & Browser Harness Verification
1. **Candidate manifest and asset digest verification**:
   - Staged candidate release asset `pdfium-dist.tar.gz` (Source S48, EmbedPDF v2.15.0).
   - Verified SHA-256: `31cba71f5620bec3ae2aab6606f148e42cba0cd34d56cf5b54998d771e62bd42`.
   - Asset size: 2,661,637 bytes (~2.54 MiB, strictly < 24 MiB limit).
2. **Browser Harness Execution**:
   - Executed via Playwright Chromium harness (`experiments/P12/browser.spec.ts`) independent of `apps/web`.
   - Proves C API execution: `FPDF_InitLibrary`, `FPDF_LoadMemDocument`, `FPDFText_LoadPage`, `FPDFText_CountChars`, `FPDFText_GetUnicode`, and `FPDFText_GetCharBox`.
   - Successfully extracts text and character bounding box geometry from target fixtures F01, F07, F10, F11.
3. **Controls & Reproducibility**:
   - Same-reader control: double-load of the same fixture produces identical character counts, Unicode sequences, and exact bounding box coordinates (0 deviation).
   - Zero runtime network egress: network requests intercepted and verified to be zero during WASM initialization and PDF parsing.
4. **Counterexample evaluation**:
   - Tested against corrupted archive and digest mismatch: triggers `candidate_rejected_integrity_mismatch`.
5. **Production Isolation & Integration Decision**:
   - Playwright test verifies `apps/web` contains zero imports, references, or dependencies on EmbedPDF or PDFium.
   - Candidate provides 0% complementary gain on standard vector text; rejected from production web app.
   - Candidate remains `default_unavailable`; PDF.js remains the sole browser reader.

## Evidence Summary
- **Tests**: 7 collected, 7 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python experiments/P12/check_manifest.py` (exit 0)
  - `bun run test:browser -- experiments/P12/browser.spec.ts` (7/7 passed)
