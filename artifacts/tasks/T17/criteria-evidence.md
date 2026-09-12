# T17 Acceptance Criteria Evidence

Task: **T17** — Earn the browser amount demo and prepared manifest
Role: **demo-engineer**
Branch: `work/antigravity/t17`
Base: `b2b5db3ad497c27ca7988dffcfdec618e697b89a`
Implementation Commit: `d39e607feda6f8d6c3443c678ac013435c5533b1`

## Acceptance Criteria Verification Summary

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Renamed identical bytes produce same reading | EXECUTED / PASS | `tests/browser/amount.spec.ts` (test 1), `screenshots/live-intake.png` |
| 2 | Modified bytes cannot replay old prepared result | EXECUTED / PASS | `tests/browser/amount.spec.ts` (test 2) |
| 3 | Live and prepared paths label provenance correctly | EXECUTED / PASS | `tests/browser/amount.spec.ts` (test 3), `screenshots/amount-demo-card.png`, `screenshots/live-intake.png` |
| 4 | Real source downloadable | EXECUTED / PASS | `tests/browser/amount.spec.ts` (test 4), HTTP status 200 + SHA-256 match |
| 5 | Actual timing visible, not decorative scan animation | EXECUTED / PASS | `tests/browser/amount.spec.ts` (test 5), `screenshots/amount-demo-card.png` |
| 6 | Clean counterpart renders equal under same renderer | EXECUTED / PASS | `tests/browser/amount.spec.ts` (test 6), `screenshots/pixel-match.png` |

---

### Criterion 1: Renamed identical bytes produce same reading
- **Verification**: `tests/browser/amount.spec.ts` uploads `fixtures/public/mapping-amount.pdf` under the arbitrary name `renamed-accounting-invoice-2026.pdf`.
- **Finding**: The UI extracts text based on content bytes, yielding `$1,000`. The file's SHA-256 (`04898afc...`) matches the canonical fixture regardless of the filename. Renaming `mapping-control.pdf` to `completely-different-name-control.pdf` yields `$100` and its matching hash (`19031ea0...`).
- **Invariants upheld**: I01 (preserve original bytes), I02 (content-addressed identity), I18 (evidence binds to exact bytes).

### Criterion 2: Modified bytes cannot replay old prepared result
- **Verification**: `tests/browser/amount.spec.ts` appends comment bytes to `mapping-amount.pdf`, producing a tampered hash.
- **Finding**: The demo client detects the hash discrepancy against the prepared manifest, refuses to replay canned findings, displays the tamper alert box (`#replay-notice.tamper-warning`) with text `"Modified bytes detected: hash does not match prepared manifest. Prepared report replay rejected. Executed live."`, and runs live reader extraction with `window.__lastLiveResult.replayedPrepared === false`.
- **Invariants upheld**: I13 (source/model provenance), I18 (claims derive from exact shipped artifacts).

### Criterion 3: Live and prepared paths label provenance correctly
- **Verification**: On initial load, `#provenance-badge` shows `prepared`, has `data-provenance="prepared"`, and uses CSS class `badge-prepared`.
- **Finding**: After file intake via `#file-input`, `#provenance-badge` transitions to `live`, updates `data-provenance="live"`, and applies class `badge-live`. Prepared vs live execution origin is unambiguous.

### Criterion 4: Real source downloadable
- **Verification**:
  - `GET /examples/amount/mapping-amount.pdf`: status 200, Content-Type `application/pdf`, SHA-256 `04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80` (exact byte match to `fixtures/public/mapping-amount.pdf`).
  - `GET /examples/amount/mapping-control.pdf`: status 200, Content-Type `application/pdf`, SHA-256 `19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed` (exact byte match to `fixtures/public/mapping-control.pdf`).
  - `GET /examples/amount/manifest.json`: status 200, schema version 1.0.0, cataloging all 4 fixture files and hashes.
  - `GET /examples/amount/report.json`: status 200, validated against `@inkflip/contracts` with `checkSchema` (0 errors) and `validateReport` (passes sealed run key and report digest checks).

### Criterion 5: Actual timing visible, not decorative scan animation
- **Verification**:
  - `#timing-display` displays numeric milliseconds (`142 ms` on prepared load; updated to live `performance.now()` execution time upon upload).
  - No decorative scan animations, spinning loading placeholders, or fake progress bars exist (`.spinner, .scan-line, .fake-scan, .loading-bar` count === 0).
  - Recorded execution time in client state is a real measured number (`> 0 ms`).

### Criterion 6: Clean counterpart renders equal under same renderer
- **Verification**:
  - `mapping-amount.pdf` and `mapping-control.pdf` are both rendered to HTML5 canvas at scale 2.0 via pinned PDF.js 6.3.289.
  - Canvas pixel comparison across all rendered pixels asserts `diffCount === 0` (100% pixel match).
  - Text content extraction from the same reader confirms `mapping-amount.pdf` yields `$1,000` while `mapping-control.pdf` yields `$100`.
  - Visual display is completely indistinguishable, but extracted text diverges due to ToUnicode CMap mapping.

### Criterion 7: Accessibility (WCAG AA)
- **Verification**: Automated AxeBuilder scan on the demo card reports 0 critical or serious violations.
