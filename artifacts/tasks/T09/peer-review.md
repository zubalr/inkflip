# Independent Peer Review — T09

**Task:** T09 — Implement PDF.js rendering/text reader adapter  
**Beads Issue:** `pdf-t09`  
**Candidate Commit Reviewed:** `fcd03358b109561b046de57574cfea50eaccef6a` (implementation `b6aad4da`, evidence `b9f2aef`, proposal `fcd0335`) on `work/devin/t09`  
**Base Commit:** `d1c02afe39928ea4bcd41dc4446efd1c59248d35`  
**Reviewer:** `devin-cloud-review-t09` (Devin Cloud session `7a7e1d4fd3fc4b449c6c82f76c91e426`, https://app.devin.ai/sessions/7a7e1d4fd3fc4b449c6c82f76c91e426; isolated clone, not the implementer)  
**Review Branch:** `review/devin/t09`  
**Date:** 2026-09-12  
**Contract Version:** 1.0.0 (`python3 scripts/coordination.py task T09`)  
**Verdict:** `approved` (with recorded F10/F11 limitation and non-blocking findings below)

---

## Executive Summary

Candidate `fcd0335` delivers `@inkflip/readers-pdfjs` and the TEST-09 Playwright suite strictly within the T09 allowed scope. All six acceptance criteria are substantiated by real Chromium tests that I re-ran independently (10/10, exit 0) and by file-by-file inspection of `packages/readers-pdfjs/src/*.ts`:

- **Pinned pair / injection (I13, I14):** The adapter never resolves a pdf.js version itself; the caller injects the `pdfjs-dist@6.3.289` legacy module and `workerSrc`. `document.ts` copies the caller bytes into an adapter-owned `Uint8Array`, verifies the caller-supplied SHA-256 before `getDocument`, and opens with `isEvalSupported:false`, `enableXfa:false`, local `cMapUrl`/`standardFontDataUrl`/`wasmUrl`/`iccUrl` only. No network, no persistence, no PDF actions/links/attachments/scripting path exists; rendering uses `AnnotationMode.ENABLE` (static appearance streams only).
- **Raw text (I03):** `text.ts` emits `raw_text: item.str` verbatim from `getTextContent({disableNormalization:true, includeMarkedContent:true})`, ordinal = 0-based TextItem index, marked-content records counted but never emitted; `normalized_text`/`normalization_map` come from `contracts.normalize` only. Tests compare against a direct same-build `getTextContent` call as ground truth.
- **Occurrence identity (I02, I04):** every occurrence carries `reader_id`, `page_index`, `ordinal`, `raw_source_locator`, `geometry.precision: "estimated"` (or `page_only`/null polygon for degenerate extents), and `id = occurrenceId(runKey, readerId, page, ordinal, locator)`. I validated emitted `Occurrence`, `Page`, `CheckPlan`, `CheckResult`, `Reader` and `ReaderManifest` objects against `planning/contracts/inkflip.schema.json` (`$defs`) with `jsonschema` — all valid.
- **Coordinates:** canonical `C = [u,0,0,-u,-u*cx0,u*cy1]` from `@inkflip/geometry`; `getViewport({scale:1}).transform` is compared to `R*C` per page (`viewportVerified`) and mismatches only downgrade to limitations, never repaired. UserUnit applied once (F08 0.5/1/2/10, 4 Mpx cap recorded honestly).
- **Bounded, cancellable rendering (I17):** `onContinue` yields via `setTimeout`, deadline timer + `AbortSignal` both call `RenderTask.cancel()`, canvas released to 0×0 in every exit path. Beyond the candidate's pre-aborted-signal test, I probed a genuinely mid-flight abort and observed the real `RenderTask.promise` reject with `RenderingCancelledException`, the adapter throw `cancelled/user_cancel`, and the canvas at 0×0.
- **Honest capability limits:** text reader manifest marks `native_text: supported` (5 recorded limits), `reading_order: approximate`, everything else `unavailable`; render reader marks only `render: supported`. Unavailable checks terminate `unsupported` with `unsupported:`-prefixed reasons. No glyph-paint / per-character provenance is claimed anywhere.

The F10/F11 fixture gap is real, pre-existing (fixture catalog: F10 `status: specified`, F11 `status: contract examples only`; T05 manifest has no such entries) and honestly recorded by the candidate. See the adjudication section: **approve with limitation**, with a required fixture-owner follow-up and a recommended in-suite strengthening.

---

## Scope & Boundary Audit

- **Allowed Scope:** `packages/readers-pdfjs/`, `tests/readers/pdfjs.spec.ts`, evidence `artifacts/tasks/T09/`, registered proposal `docs/proposals/T09.md`.
- **Diff Stat** (`git diff d1c02afe39928ea4bcd41dc4446efd1c59248d35..fcd0335 --stat`):
  ```
  artifacts/tasks/T09/commands.log       | 102 ++++
  artifacts/tasks/T09/handoff.json       |  74 +++
  artifacts/tasks/T09/receipt.json       |  76 +++
  artifacts/tasks/T09/run.json           |  46 ++
  docs/proposals/T09.md                  |  59 +++
  packages/readers-pdfjs/README.md       |  93 ++++
  packages/readers-pdfjs/src/adapter.ts  | 377 ++++++++++++++
  packages/readers-pdfjs/src/config.ts   | 119 +++++
  packages/readers-pdfjs/src/document.ts | 297 ++++++++++++
  packages/readers-pdfjs/src/errors.ts   |  84 ++++
  packages/readers-pdfjs/src/index.ts    |  60 +++
  packages/readers-pdfjs/src/manifest.ts | 170 +++++++
  packages/readers-pdfjs/src/render.ts   | 286 +++++++++++
  packages/readers-pdfjs/src/text.ts     | 296 +++++++++++
  packages/readers-pdfjs/src/types.ts    | 128 +++++
  packages/readers-pdfjs/tsconfig.json   |   2 +
  tests/readers/pdfjs.spec.ts            | 863 +++++++++++++++++++++++++++++++++
  17 files changed, 3132 insertions(+)
  ```
- **Boundary Checks:**
  - No changes outside allowed scope; `planning/` untouched; no `package.json`/`bun.lock` changes (no new dependencies — `pdfjs-dist` is the T02 frozen pin, `@inkflip/contracts`/`@inkflip/geometry` are existing workspace packages).
  - `packages/readers-pdfjs/tsconfig.json` adds `emitDeclarationOnly` + `allowImportingTsExtensions` (in scope; matches how the suite bundles `.ts` sources with `bun build`).
  - No deleted assertions, no skips, no baseline refreshes. `run.json`/`commands.log` counts match my reproduction.
  - Test-time serving of `pdf.mjs`/`pdf.worker.mjs` from `apps/web/node_modules/pdfjs-dist/legacy/build/` (frozen-lockfile install) is a reasonable, recorded measured decision: T02 staged only the data assets publicly, and the adapter stays injection-based.
  - Dead code: none material found. `types.ts` structural typing covers exactly the API surface used.

---

## Criterion-by-Criterion Evaluation

| Acceptance Criterion | Result | Evidence & Analysis |
|---|---|---|
| **Real mapping and clean PDFs processed through bytes** | **PASS** | `document.ts` `openDocument`: caller `Uint8Array` is copied (`bytes.slice()`), SHA-256 recomputed and compared to the caller digest (mismatch → `parser_error`, tested in "open verifies digest…"), then `getDocument({data})`. Tests F01 (`mapping-amount.pdf` vs `mapping-control.pdf`) and F02 (`covered-amount.pdf` vs `covered-control.pdf`) fetch real T05 bytes over loopback; F01 emits `$1,000` while rasters are byte-identical (looks right / reads wrong); F02 emits both `$1,000` and `$100` with dark-pixel parity to the control. `bytesAfter` digest asserts input bytes are unchanged. |
| **raw text not injected** | **PASS** | `text.ts`: `raw_text: item.str`, no trimming/joining/reordering; empty-string TextItems are preserved as occurrences with `polygon: null` rather than dropped (I03). Tests deep-equal `occurrences.map(raw_text)` against a direct `getTextContent({disableNormalization:true, includeMarkedContent:true})` on the same pinned build, ordinals equal TextItem indices, `normalized_text`/`normalization_map` recomputed with `contracts.normalize`. |
| **occurrence geometry/rotation/UserUnit verified** | **PASS** | F07: `page.rotation` 0/90/180/270, `effective_view_box [20,40,500,390]`, `C == [2,0,0,-2,-40,780]` (COORDINATES.md analytic value), `getViewport({scale:1}).transform == pageToDisplay(R*C)` within 1e-6 (independent oracle), raster dims `[960,700]`/`[700,960]`. Occurrence polygons are recomputed in-test from raw TextItem transform/width/ascent/descent through `C` — note this recomputation shares the adapter's formula (it proves T04 mapping consistency, not an independent extent oracle; acceptable given "estimated" precision). F08: `user_unit` 0.5/1/2/10 exact, canonical size `520u × 400u`, fiducial right edge at `472u*scale` px (no double scaling), u=10 hits the 4 Mpx cap with recorded limitation. `media_box`/`crop_box` honestly `null`. |
| **no full glyph-paint provenance claim** | **PASS** | Every occurrence: `precision ∈ {estimated, page_only}`, limitations include "not a glyph-paint or per-character provenance"; manifests/readers serialized and asserted free of exact/per-glyph claims; `getOperatorList` never used. Schema-validated by me (`$defs/Occurrence`, `$defs/ReaderManifest`). |
| **render cancellation releases task/canvas** | **PASS** | `render.ts` lines 186–255: `onContinue` → `setTimeout`, deadline timer and abort both call `task.cancel()`, `releaseCanvas` (w/h → 0) on every non-`done` outcome and after `getImageData`. Candidate test: pre-aborted signal into `renderPage` creates and cancels a real `RenderTask`, canvas spy asserts 0×0, subsequent render completes 960×700; adapter-level pre-aborted `extract` → `cancelled/user_cancel`; text mid-walk cancel keeps `produced = retained = 1`. Reviewer probe (untracked): abort 1 ms after `render()` → `RenderTask.promise` rejected `RenderingCancelledException`, adapter threw `cancelled/user_cancel`, canvas 0×0. See finding F-3 on wording. |
| **unavailable structure check is unsupported** | **PASS** | `adapter.ts` `plan()` accepts any capability but `extract()` routes non-`native_text`/`render`/`reading_order` to `unsupported` with named `unsupported:` reasons and `produced_occurrence_count 0`; test "unavailable capabilities terminate unsupported…" covers structure/ocr/object_render_mode/paint_overlap/crop_metadata/alignment. `describe()` marks the same capabilities `unavailable`. |

Invariants: I02 ✔, I03 ✔, I04 ✔ (viewport-verified gating), I13 ✔ (version/build/adapter_version present; see F-4 on `asset_hashes`), I14 ✔ (browser-only, no native dependency), I17 ✔ (typed `ReaderError` taxonomy, per-check terminal results, generation-scoped `close`).

---

## Verification Commands & Reproduction

Executed in this review clone at `fcd0335` after `bun install --frozen-lockfile`, `bun x playwright install chromium`, `uv sync --frozen --project native` (Node v22.23.2, Bun 1.4.0, uv 0.12.13, Python 3.13.15):

| Command | Exit Code | Time | Outcome |
|---|---|---|---|
| `bun run test:browser -- tests/readers/pdfjs.spec.ts` | 0 | 4.3s | 10 passed, 0 failed, 0 skipped |
| `python3 scripts/task_acceptance.py task T09` | 0 | 4.4s | collected 10 / passed 10 / failed 0 / skipped 0 |
| `bun x --no-install tsc -b tsconfig.json` | 0 | 0.1s (incremental; first run also clean) | clean |
| `bun run verify` | 0 | 1.6s | 49 bootstrap + 2 native-bootstrap + 30 coordination tests OK; the `test evidence invalid: required tests failed=0 skipped=1` line is the intentional negative-control output of `test_all_skipped_gate_scenarios_fail`, not a failure |
| `bun run build:web` | 0 | 0.3s | Vite build, 18 modules, `dist/` written |

Reviewer-only probes (untracked spec files, deleted after use; not part of the candidate):

| Probe | Result |
|---|---|
| Mid-flight abort (1 ms after `render()`) via `renderPage` | `RenderTask.promise` → `rejected:RenderingCancelledException`; adapter `cancelled/user_cancel`; canvas 0×0 |
| `jsonschema` (native venv) validation of dumped `CheckPlan`×2, `Occurrence`×7, `CheckResult`×2, `Page`, `Reader`×2, `ReaderManifest`×2 against `planning/contracts/inkflip.schema.json` `$defs` | all valid |
| F11-mechanism PDF synthesized with `scripts/make_fixtures.py` writer (`$100` painted at four positions, same recipe T26 used) run through `adapter.extract` | `completed`; four `$100` occurrences with 4 distinct ids, ordinals 2–5, 4 distinct polygons — no value-only dedupe |

No pre-existing failures were observed on the base; all checks are green on the candidate.

---

## Review Findings & Observations

Severity scale: high = blocks acceptance; medium = should be fixed in a follow-up before the coordinator relies on the path; low = quality/accuracy nit.

- **F-1 (medium, non-blocking) — `resource_limit` orphans already-emitted chunks.** `text.ts` pushes the occurrence, and only then throws `resource_limit` when `retainedIds.length > maxOccurrencesPerCheck`; chunks flushed before that point were already delivered through `emitChunk`, yet `adapter.ts` catches and returns `failOutcome(check, 'failed', reason)` with `produced_occurrence_count 0` / `retained_occurrence_ids []`. The adapter's own comment ("Occurrences emitted through emitChunk (== produced count)") is violated on this path, and this path is untested. Suggested fix: report the count/ids emitted so far (mirroring the cancelled path) or drop the over-cap item before emitting and terminate with the retained set. Not blocking: the cap is 20 000 items/check, and the T11 coordinator terminalizes over-limit checks independently.
- **F-2 (low) — F11 test exercises T03, not the adapter.** "F10/F11 absent…; ordinal identity preserves duplicates" asserts file absence and then calls `contracts.occurrenceId` directly; the adapter is not invoked, so the test proves nothing about T09's own duplicate handling. The adapter *does* behave correctly (my probe above), and F01 proves raw pass-through, but the committed coverage is weaker than the test title/receipt wording suggests. Recommended: synthesize the F10 (no `/ToUnicode`) and F11 (repeated value at four positions) PDFs in-suite with the `scripts/make_fixtures.py` writer, as the merged T26 suite does, and run them through `extract`.
- **F-3 (low) — cancellation wording overstates what is observed.** `render.ts` header says cancellation "awaits the resulting RenderingCancelledException"; the code resolves the outcome immediately on abort and does not await `task.promise`. `receipt.json` says the test exercises the "RenderingCancelledException path"; the test observes the adapter's `cancelled` outcome and the 0×0 canvas, not the pdf.js exception. Behaviour is correct (confirmed by probe); adjust the comment/receipt text.
- **F-4 (low) — pinned-pair hashes computed but never bound.** The suite computes SHA-256 of `pdf.mjs`/`pdf.worker.mjs` and logs them, but `createPdfJsReader` is called without `mainSha256`/`workerSha256`, so `describe()` manifests carry `asset_hashes: []` and the hashes are never asserted. I13 is met at the version/build level; recommend passing the hashes in-suite and asserting them in the manifests (the app wiring task should do the same).
- **F-5 (info)** — `renderPage` with an already-aborted signal still creates a `RenderTask` before cancelling it (the adapter-level `extract` short-circuits earlier, so no user-visible effect).
- **F-6 (info)** — Empty-string TextItems (pdf.js EOL markers) are emitted as occurrences with `raw_text: ""` and `polygon: null`. This is faithful to I03 and schema-valid; downstream consumers (T11/T12) should expect them.
- **Positive:** genuinely independent test oracles (direct `getTextContent`, `@inkflip/geometry` `pageToDisplay`, analytic `C`, raster byte-identity and dark-pixel parity); honest `null` for `media_box`/`crop_box`; measured decisions in `handoff.json` (resource_limit→`failed`, `viewportVerified` gating, node_modules pair serving, direct `renderPage` cancel proof) are all reasonable and accurately described; nothing in the evidence is fabricated.

---

## F10/F11 Adjudication

**Facts.** The effective contract lists fixture IDs F01, F02, F07, F08, F10, F11. `fixtures/public/` and `fixtures/development/` contain no `mapping-missing.pdf` or `duplicates.pdf`; `fixtures/manifest.json` has no F10/F11 entries; `scripts/make_fixtures.py` recipes cover only F01/F02/F03/F07/F08. `planning/quality/fixture-catalog.json` itself records F10 as `status: "specified"` and F11 as `status: "contract examples only"` — the gap predates T09 and belongs to the fixture owner (T05 lane). The candidate did not fabricate fixtures: it asserts absence (so the test fails loudly the day the files appear), records the limitation in `receipt.json`/`handoff.json`, and filed `docs/proposals/T09.md` asking T05 to generate canonical F10/F11 or the coordinator to narrow T09's fixture list. The merged T26 review faced the same gap and was approved with an in-suite synthesized substitute plus a fixture-owner dependency request.

**Is the substitute coverage honest?** Yes as to honesty — nothing is overclaimed in the limitation text — but it is thin as to substance: the committed F11 substitute tests a T03 function, not the adapter (F-2), and there is no F10 substitute beyond F01's raw pass-through equivalence. To close that evidentiary gap for this review I ran the F11 mechanism through the adapter myself (four `$100` at distinct positions → four distinct occurrences/ids/polygons), and the F01/F02 raw-equality assertions already demonstrate that whatever pdf.js decodes (including with a missing/malformed map) is passed through unchanged, which is F10's expected invariant ("preserve raw API output/missingness").

**Recommendation: approve with limitation** (do not block). The six acceptance criteria are independent of F10/F11 and are fully substantiated; the adapter mechanisms F10/F11 would exercise are verified by inspection, by F01/F02, and by my probe; the gap is a planning/fixture-owner debt already visible in the fixture catalog, and blocking a correct adapter on it would only stall G1 without producing the fixtures. Conditions attached to this approval:

1. Coordinator to record the F10/F11 limitation on `pdf-t09` and act on `docs/proposals/T09.md` (either T05 generates canonical `mapping-missing.pdf`/`duplicates.pdf` in `fixtures/development/` with manifest entries, or the T09 fixture list is narrowed). When the files land, TEST-09's absence assertion will fail by design and must be replaced by real F10/F11 runs before the G1 gate receipt is considered fresh.
2. Recommended (not required for acceptance): the worker replaces the contracts-only ordinal test with in-suite synthesized F10/F11 PDFs run through `adapter.extract` (F-2), and addresses F-1/F-3/F-4 in a follow-up commit.

---

## Verdict

**`approved`**

Candidate `fcd0335` (implementation `b6aad4d`) satisfies all six acceptance criteria with real, independently reproduced evidence, stays strictly within scope, keeps `planning/` byte-identical, declares capabilities and limitations honestly, and handles the pre-existing F10/F11 fixture gap without fabrication. Findings F-1..F-4 are non-blocking follow-ups; the F10/F11 fixture debt is assigned to the fixture owner via the registered proposal.
