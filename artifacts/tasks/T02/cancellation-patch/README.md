# Tesseract worker cancellation repair

Astra implemented this narrow dependency repair for Beads `pdf-ebz` after
independent T10 review. The pinned upstream constructor hides a live worker
until initialization finishes and can leave readiness unresolved on rejection.
The maintained source patch adds an optional AbortSignal and releases the raw
transport on abort, initialization rejection and worker error. It rejects
posted jobs and prevents dispatch after termination.

The patch keeps the existing Promise API and worker protocol. The application
and tests must bundle the declared package source entry; upstream prebuilt
client dist files do not contain the patch. Staged worker/core/model bytes are
unchanged. T10 still owns reader deadlines, generation guards and consumption
of verified model bytes; this dependency repair alone does not accept T10.

Independent review also reproduced an upstream input-loader limitation:
aborting during a stalled URL/FileReader/canvas load stops the worker but leaves
that input-loading promise pending. This patch does not change those loaders.
T10's approved port accepts prepared Uint8Array bytes only, with materialization
inside its owned deadline. A real browser case verifies cancellation before
that byte input posts a job. This is a scoped transport repair, not a claim that
all upstream `recognize()` input types become cancellable.

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
  one patch positive control, six tamper cases and the nested 11 + 4 JavaScript cases.

`fresh-installs.log` records two fresh Mac clones of source candidate
`68d31df54734e2d086f0915346b04a20e2e8d1e2`: both frozen Bun 1.4.0 installs,
installed patch checks, 11 constructor tests and lock-drift checks pass.
Independent review is collected separately before integration. No worker protocol, frozen planning, asset hash or acceptance
assertion has been relaxed.

## Review revision

`review-round1.md` records Pauli's exact68d31df review, including the input-loader
limitation scoped above and the accepted-input binding finding. The registered
TEST-02 wrapper now clears the standalone negative-control package override;
a sentinel regression executes both real suites despite an inherited override.
The browser suite adds a prepared-byte cancellation case (5 cases total).

The supported Bun re-patch command initially included an empty `.bun-tag` cache
marker. It was removed from the prepared copy before regenerating the patch.
Frozen verification now checks the patch's complete target list in addition to
hashes; a test rejects an extra target even when its patch digest is updated.
The final patch modifies only the constructor and its type declaration.

`revision2-frozen.log`: 25 checks pass. `revision2-build-tests.log`: 48 Python
cases pass, including 11 constructor + 5 real-browser JavaScript cases; the
sentinel case repeats those two suites. `revision2-verify.log`: 115 registered
coordination/bootstrap checks pass. The constructor bytes remain identical to
68d31df; its type comment now states the scope precisely.

`independent-linux-proof-68d31df.log` records the independent fresh Linux x86_64
Bun1.4.0/Node22.23.2 install, eight installed-patch checks, eleven constructor
cases and no Git drift. This evidence binds to68d31df before the type-comment
and test-binding revision. No real OCR is claimed by this repair.

## Reviewed integration

Pauli (`01a093db-42d8-79d3-befb-0b7680c3e405`) approved exact `185d51d` for the documented constructor, transport and posted-job scope; see `review-final-185d51d.md`. Merging current main changed only Beads audit entries and produced `cb24f8ab802ea688b941f914a2dddf6c421880d0`. On that merged candidate, Node 22.23.2/Bun 1.4.0 frozen install passed without lock drift, 25 frozen dependency checks passed, 48 Python build tests passed (including the 11 constructor and 5 browser cases), and 115 verify tests passed. The `merged-*.log` files preserve actual output. These checks establish this repair, not fresh T02 or T10 task acceptance. Existing product receipts still require the planned integrated revalidation. Git whitespace inspection is clean for source; raw TAP failure logs and the generated patch retain their original whitespace and valid context markers.
