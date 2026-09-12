# T18 run report — Pass the first integrated own-file evidence gate (G1)

- Task: T18 (`pdf-t18`), gate owner of **G1 — Real browser own-file evidence loop**
- Branch: `work/devin/t18` · Worktree: `worktrees/pdf-t18` · Base: `f25d3ee`
- Worker: `devin-t18` (Devin Local SWE-2, Mac)
- Final implementation commit: `c3f2c84c157c0e22a5cb4e4751761a6f21d0453e`

## What was delivered

`tests/gates/g1.spec.ts` (≈1,270 lines, 3 serial tests) implementing the
registered G1 scenario end-to-end against the **real built feature mounts and
the real app shell** — no mocked own-file processor, no mocked backend, no
skipped privacy check:

- **Leg 1 — own-file lifecycle (open mount, `__t08`):** real Chromium file
  chooser → `mapping-amount.pdf` (F01 interesting: text layer reads `$1,000`
  while raster paints `$100`) → real pdf.js native-text extraction (occurrence
  `estimated`-precision polygon) → real rasterize at 2× → unsupported +
  aborted capabilities → numeric region commit derived from the extracted
  polygon → real `RunCoordinator.startRun` plan `[native_text, render, ocr]`
  with the region bound to the OCR check → results fed through the real
  `receive()` admission path (OCR job drained post-render; `unsupported`
  terminal → `partial` run, completed results retained) → `prepareNewRun` →
  `requestCancel` (generation +1, check `cancelled`, zero cleanup failures) →
  renamed identical bytes → same sha256/`$1,000` reading → replace with
  `mapping-control.pdf` (clean control) → stale-generation message rejected →
  `sha256` = control bytes.
- **Leg 2 — OCR + source geometry (T15 privacy harness, `__t15`):** real
  Tesseract.js 7 reader on staged same-origin worker/core/`tessdata-fast-eng`
  model → `prepare` (fetched) → `open` → region plan bound to the real text
  occurrence polygon → `extract` produces real OCR occurrences; F07
  `geometry-90.pdf` rotated/`UserUnit` canonical extents + raster px; F03
  `scan-correct.pdf` text-layer words; F21 canary text/metadata/annotation
  markers; egress capture across network/console/storage/server-log channels.
- **Leg 3 — selected export → local reopen → offline:** report assembled +
  `seal()`ed in-page from the actual reader outputs → real T16 `ExportPanel`
  mounted → default options verified (no source PDF, no filename, no notes) →
  real browser **JSON + HTML downloads** → downloaded JSON asserted
  (display_name null, source_asset_id null, annotations [], 1 finding, every
  retained occurrence cited) → HTML self-contained (no `<script>`, no
  `http(s)://`) → reopened through the real T22 import mount (source-missing,
  replay-requires-original, wrong-bytes rejected, matching bytes verify) →
  reopened through the **real main app shell** (`#btn-open-report` →
  `#input-import-report` → finding visible in `#evidence-slip`) → second page
  in same context: OCR model served from verified IndexedDB slot
  (`ready_cached`, zero model fetches) → `context.setOffline(true)`:
  OCR extraction still succeeds with zero requests/zero failures.

## Exact results

| Command | Result |
|---|---|
| `bun x --no-install playwright test tests/gates/g1.spec.ts --reporter=list` | **3 passed (3.9s)** — leg1 958ms, leg2 774ms, leg3 990ms |
| `python3 scripts/gate.py G1` | exit 1 — `prerequisite unmet: Git evidence lookup failed` ×18 (accepted commits not ancestors of this branch; gate runs on merged main) |
| prereq validation vs `origin/main` | **verified: 19 / 19** (T01–T17, T22, T24) |

Verbatim transcripts: `commands.log`.

## Evidence produced by the run (committed under `artifacts/gates/G1/captures/`)

- `00-open-journey.json` — 46 records, **0 violations**, 23 same-origin GETs
- `01-geometry-ocr.json` — 45 records, **0 violations**
- `02-export-reopen.json` — 47 records, 20 violations **all channel=`downloads`**
  (the exported files legitimately carry canary text / sha256 / report_id /
  run_key — whitelisted); zero egress via request/console/storage/server
- `03-cache-warm-ocr.json` — 15 records, 0 violations (no model refetch)
- `04-offline-warm.json` — 1 record (the offline marker write), 0 violations,
  `offline: true`, 0 server hits
- `downloads/02-export.inkflip-report.{json,html}` — the real downloaded
  export artifacts
- `server-access.log` — same-origin GETs only
- `canary-manifest.json` — marker digests + honest limitations (never marker
  material)

## Honest limitations / blockers

1. **`python3 scripts/gate.py G1` cannot complete on this task branch by
   design**: it validates every prerequisite `accepted_commit` against `HEAD`.
   This branch predates the coordinator's receipt-refresh merges on main, so
   18/19 required tasks fail the ancestor check here. Against `origin/main`
   all 19 verify, and `origin/main`…`f25d3ee` contains no changes the spec
   touches (only native/ structure checks from T28). The gate command — the
   identical Playwright invocation above — is green on this code.
2. **App-composition gap (documented, not hidden):** the shipped shell has no
   single page composing open→inspect→export (T13 scope); the main workspace
   still shows the "inspection unavailable" notice for own-file PDFs. G1
   therefore drives the real built feature mounts (T08 open, T22 import), the
   test-owned T15 privacy harness (same production packages, same vite build),
   and the real app shell for report reopen — the same pattern T15's accepted
   suite uses.
3. **Browser automation boundary:** in-page capture sees
   fetch/XHR/WebSocket/console/storage/download channels and the static
   server log; a release profile still needs the proxy/firewall capture per
   planning.
4. **Offline scope:** asserted as warm-page offline extraction; the site ships
   no service worker, so cold offline navigation is out of scope by design.
5. **F24** is listed in `fixture_ids` but no F24 entry exists in
   `scripts/make_fixtures.py`'s manifest — not exercised; flagged for the
   coordinator rather than fabricated.

## Review status

`implemented_pending_review` — `review.md` must be written by the independent
reviewer (not the worker) per `docs/NATIVE_PASSES.md`; the receipt's review
block stays unclaimed until then.
