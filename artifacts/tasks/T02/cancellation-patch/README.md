# Tesseract worker cancellation repair

Astra implemented this narrow dependency repair for Beads `pdf-ebz` after
independent T10 review. The pinned upstream constructor hides a live worker
until initialization finishes and can leave readiness unresolved on rejection.
The maintained source patch adds an optional AbortSignal and releases the raw
transport on abort, initialization rejection and worker error. It rejects
outstanding jobs and prevents dispatch after termination.

The patch keeps the existing Promise API and worker protocol. The application
and tests must bundle the declared package source entry; upstream prebuilt
client dist files do not contain the patch. Staged worker/core/model bytes are
unchanged. T10 still owns reader deadlines, generation guards and consumption
of verified model bytes; this dependency repair alone does not accept T10.

Evidence from macOS arm64, September 12, 2026:

- `unit-green.log`: 11 installed-constructor lifecycle tests pass on Node 22.23.2.
- `browser-green.log`: four real Chromium worker cases pass. The worker sends
  independent local tick requests; abort stops those requests at load,
  loadLanguage, initialize and after readiness. No OCR model is loaded.
- `unpatched-unit-red.log`: original 7.0.0 fails four assertions, then seven
  cases are cancelled because initialization remains unresolved. This is
  negative-control evidence, not a passing or fully executed suite.
- `unpatched-success-control.log`: original successful initialization and
  recognition control passes.
- `unpatched-browser-red.log`: original ready worker keeps sending requests
  after abort (19 to 27 during the observation window), so the physical
  cleanup assertion fails.
- `frozen-verification.log`: 24 frozen dependency checks pass, including patch,
  installed source/types and exact declaration checks.
- `build-tests.log`: all 46 registered TEST-02 Python cases pass, including
  seven patch tampering cases and the nested 11 + 4 JavaScript cases.

`fresh-installs.log` records two fresh Mac clones of source candidate
`68d31df54734e2d086f0915346b04a20e2e8d1e2`: both frozen Bun 1.4.0 installs,
installed patch checks, 11 constructor tests and lock-drift checks pass.
Independent review is collected separately before integration. No worker protocol, frozen planning, asset hash or acceptance
assertion has been relaxed.
