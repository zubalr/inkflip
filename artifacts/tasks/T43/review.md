# Independent Review — T43 (Evaluate secondary browser reader, decide explicitly)

## Review Metadata
- **Task**: T43 / P12
- **Reviewed Commit**: `435b6b020084f7b60ea45e994ba7a35606e1cefa`
- **Reviewer**: Antigravity (Teamwork Independent Reviewer)
- **Date**: 2026-09-13
- **Status**: `passed` (task requirements satisfied; candidate properly evaluated as blocked)
- **Disposition**: `blocked_missing_candidate_archive` (`default_unavailable`)

## Acceptance Criteria & Negative Control Verification
1. **Candidate manifest and asset digest verification**:
   - Audited candidate release asset metadata against S48 (`EmbedPDF v2.15.0`, `pdfium-dist.tar.gz`, 2,661,637 bytes, SHA-256 `31cba71f5620bec3ae2aab6606f148e42cba0cd34d56cf5b54998d771e62bd42`).
   - Confirmed asset size 2.66 MB satisfies the strict < 24 MiB chunk threshold.
2. **Offline containment and absence accounting**:
   - The candidate archive is not pre-bundled in the repository checkout.
   - Network fetches are prohibited under repository offline security invariants (I13/I14).
   - Preparation command (`curl -fL ...`) is blocked; script honestly records `status: "blocked"`, `disposition: "blocked_missing_candidate_archive"` without fabricating a download or simulating execution.
3. **Counterexample evaluation**:
   - Tested against tampered archive (checksum mismatch) and corrupted archive.
   - Verification logic extracts tar and validates WASM binary header (`\x00asm\x01\x00\x00\x00`).
   - Tampered archives immediately produce `candidate_rejected_integrity_mismatch` and are never accepted.
4. **Real browser reader verification**:
   - Real Playwright Chromium test binds local HTTP server serving PDF.js legacy build and development fixtures.
   - Renders `white-contrast-control.pdf` onto HTML5 `<canvas>`, verifies non-blank ink pixels rendered, and extracts text content (`$100`).
5. **Default reader integrity and candidate containment (I13, I14)**:
   - Playwright test proves `apps/web` does not import, reference, or bundle EmbedPDF or secondary WASM binaries.
   - Secondary candidate remains `default_unavailable`; browser core remains complete and standalone on PDF.js.

## Evidence Summary
- **Tests**: 4 collected, 4 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `python3 experiments/P12/check_manifest.py` (exit 0)
  - `bun run test:browser -- experiments/P12/browser.spec.ts` (4/4 passed)
  - `python3 scripts/task_acceptance.py task T43` (exit 0)
