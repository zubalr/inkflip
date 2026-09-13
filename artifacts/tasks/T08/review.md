# T08 independent review — local file validation and page/region selection

- **Reviewer:** devin-review-t08 (independent SWE-2 subagent; did not write the implementation)
- **Candidate:** `944cca58cdcbb43b03dfc6156fb7f94b35954c84` (impl `eefc39d`, evidence `0adaadf` + `944cca5`; formal eval `run.json`/`eval.json` at `0adaadf`)
- **Branch reviewed:** `review/devin/t08` in `worktrees/review-devin-t08`
- **Verdict:** **approved**

All five acceptance criteria are exercised by real assertions against the real
production path — a Vite dev server mounting `features/open/preview.html` +
`mount.tsx`, which wires the pinned pdf.js 6.3.289 legacy pair, the T09
`PdfJsReaderAdapter` and the T11 `RunCoordinator`. Nothing at the contract
surface is mocked; the only test-side machinery is a real-xref PDF generator
(parsed genuinely by pdf.js) and structural `FileCandidate` stand-ins used to
spy on read calls for the declared-size gate.

## Reproduced counts

```
$ bun install --frozen-lockfile          # fresh deps in this review worktree
$ bun run test:browser -- tests/browser/open.spec.ts
  13 collected, 13 passed, 0 failed, 0 skipped (12.2s, 1 worker) — exit 0
```

Matches `eval.json`/`receipt.json`/`run.json` (13/13/0/0). HEAD `944cca5`
differs from evaluated `0adaadf` only by the added `eval.json`, so the eval
remains fresh. `node_modules/.bin/oxlint` on the owned paths: 0 warnings, 0
errors (15 files, 96 rules). `tsc -p apps/web/tsconfig.json --noEmit`: 602
baseline-class errors repo-wide (TS7016/TS7006/TS7026, `@types/react`
unresolvable under the isolated linker); owned files contribute **0**
non-baseline errors — worker's claim verified.

## Criterion-by-criterion audit

1. **"20MiB/1000-page and mobile limits exercised without giant allocations" — faithful.**
   `validateCandidate` runs `validateCandidateSize` on declared metadata
   *before* `slice()`/`arrayBuffer()` (validate.ts:106-114). The spec proves
   it with spies through the real `controller.offer`: a `DESKTOP_MAX+1` and a
   `MOBILE_MAX+1` candidate are rejected `too_large` with `sliceReads=0`,
   `fullReads=0` (open.spec.ts:409-442, 479-497), the DOM showing
   `#open-error-too_large`. The inclusive boundary (`size == DESKTOP_MAX`)
   passes to the real reader with a tiny generated PDF. The 1000-page test
   opens a real generated 156 KiB PDF (`<1 MiB` asserted), shows
   "Pages 1–48 of 1000" through a bounded 48-row window, reaches page 1000
   via jump, and rejects 1001 pages as the distinct `too_many_pages`.
   Mobile pins `?profile=mobile`, asserts `profile.id`, the "10 MiB" copy,
   and the 5-page cap. No allocation >1 MiB anywhere in the suite.
2. **"wrong MIME/header, encrypted and malformed are distinct" — faithful.**
   Four real files through the real input: `image/png`+PNG bytes →
   `#open-error-not_pdf` with detail `mime:image/png`; `application/pdf`+
   plain text → `#open-error-not_pdf` with `header:no-%PDF-magic`; a real
   `/Encrypt`-dictionary PDF → `#open-error-encrypted` (real
   `PasswordException` → `encrypted:*` reason); a truncated real PDF →
   `#open-error-malformed` (real `InvalidPDFException` → `parser_error:*`).
   The spec asserts ≥3 distinct canonical messages, `mime:` vs `header:`
   detail distinction, and an enabled idle drop zone after each rejection.
   MIME and header share `not_pdf` — the contract's own taxonomy
   (`input.notpdf` covers both, per copy.json) — with distinct detail ids;
   `encrypted`/`malformed`/`too_large`/`too_many_pages` are separate kinds:
   five distinct `OpenError.kind` buckets exercised.
3. **"new file revokes old generation first" — faithful.**
   A schema-valid `MessageFactory` message stamped with generation A is
   rejected `{ok:false, code:'stale_generation'}` by the real
   `MessageAuthority` before and after replacement (authority.ts:122-127 —
   registry is run-scoped). The replacement dialog is exercised both ways:
   cancel leaves generation, event log and document untouched; confirm emits
   `clear` recording retired gen A, `teardown` recording gen A+1 (strictly
   greater — the coordinator's `requestClear` bumps `generation` before
   `fileCleanup.teardownAll()`, coordinator.ts:777 vs 791-794), then
   `validated`/`opened`/`metadata` for doc B under the new generation with a
   different sha256. Ordering and inequality are asserted, not narrated.
4. **"page selection never silently excludes a page" — faithful.**
   Default selection is exactly page 1. `selectAll()` on 25 pages yields
   "20 of 25" with the cap notice visible *before* any run
   (`truncated`/`limitHit` → `#pages-limit-notice`, PagePicker.tsx:37,51-55);
   toggling page 21 is refused (count stays 20, `aria-pressed=false`,
   notice persists) — refusal-plus-notice, never quiet trimming
   (pages.ts:63-72, `addRange` atomic). The frozen plan's `data-page` set is
   asserted equal to exactly `{2..20}`, every selected page carries all
   three capabilities, and `snapshot().run.selectedPagesTotal === 19` is
   pinned by the coordinator. The mobile test exercises the 5-page cap the
   same way (6th page refused visibly).
5. **"no document metadata in URL" — faithful.**
   Canary filename (`confidential-T08C4N4RY.pdf`), page text
   (`T08C4N4RYSECRET`), full sha256 and the displayed sha tail: after
   select-all + region drag + Compare, `page.url()` is byte-identical to
   boot, `location.hash`/`search` empty, every captured request (>5,
   including Vite modules, `pdf.worker`, fonts) is same-origin loopback,
   method ∈ {GET, OPTIONS, HEAD}, free of every canary and of `%PDF`
   payloads; localStorage/sessionStorage/`document.cookie` empty; the
   filename appears exactly once as `data-testid=doc-label`.

## Source audit (contract conformance)

- **`validate.ts`** — declared-size gate on metadata alone precedes a bounded
  ≤1 KiB header slice; a concrete non-PDF declared type is wrong before the
  magic scan inside `validateCandidateHeader` (a wrong-MIME file still has
  its ≤1 KiB slice read first — bounded and honest, the decision is on the
  type). `GENERIC_TYPES` defers generic/absent types to the header, matching
  the "header decides" rule.
- **`region.ts`** — `validateRegionBox` rejects out-of-bounds/degenerate
  input with reasons quoting the real page bound (never clamps); the drag
  path clamps pointer points to the raster then *still validates* the final
  box (zero-area drags are rejected, not committed). `displayToCanonical`/
  `canonicalToDisplay`/`displaySize` verified identical to COORDINATES.md
  R0/R90/R180/R270 and `packages/geometry` `displayRotation` (the module
  re-implements rather than imports — consistent, and the app's tsconfig
  can't resolve cross-package `.ts`; `mount.tsx` carries the concrete
  wiring). `paddedRasterRegion` implements `max(8 raster px, 10% of region
  height)` clipped to the raster — the READER_ADAPTER_CONTRACT rule, and
  region/padded stay distinct outlines. `regionToContract` produces
  schema-valid `Region` records (`canonical_page`, `precision:"exact"`,
  `transform_ids:[raw_to_canonical id]`, honest `basis`, 6-decimal
  rounding).
- **`controller.ts`** — offer state machine matches RUNTIME_LIFECYCLE
  (`idle→validating_file→loading_metadata→selecting`, `clearing` refused);
  generation-first replacement via `requestClear("replace")`; `own()`-bound
  teardown emits under the new generation; `classifyOpenFailure` maps the
  adapter's public reason taxonomy (`encrypted:`/`resource_limit:`/
  `timeout:`/`parser_error:`) to distinct `OpenError.kind`s without leaking
  raw exception text; `requestClear("idle")` follows every rejection, so a
  failure never lands in `selecting`.
- **T09/T11 consumption is through real public APIs** — `adapter.open/pages/
  plan/extract/close`, `reader.reason`, `hexSha256`-equivalent digest check,
  `coordinator.openFile/fileValidated/metadataLoaded/requestClear/own/
  startRun/drainOutbox/receive/snapshot`, `MessageFactory`, `deriveRunKey`.
  `plan` binds regions by the contract `${capability}:p${page}` key; the ocr
  check on page 0 carries `region_p0_N`.
- **Scope** — `git diff 546accd...HEAD` touches only
  `apps/web/src/features/{open,selection}/`, `tests/browser/open.spec.ts`
  and `artifacts/tasks/T08/` evidence. `?profile=mobile` is a documented
  test affordance that can only tighten limits; the production resolver's
  coarse-pointer/<768 px heuristic matches CAPABILITIES.md narrow-screen
  support. `preview.html`/`mount.tsx` follow the T06 `components/Controls`
  preview+mount precedent and the `__t09` harness pattern.
- **Fixture honesty** — F17/F18/F19/F21 confirmed `status:"specified"` in
  `planning/quality/fixture-catalog.json` and absent from
  `fixtures/manifest.json` and the tree. The in-spec generated equivalents
  exercise the same attack surface: real `/Encrypt` dictionary → real
  `PasswordException`; real truncated body → real `InvalidPDFException`; a
  real 100 000 pt MediaBox through pdf.js metadata; a canary in filename,
  page text and digest. The limitation is recorded in `handoff.json` and the
  spec header. F17's unreadable-*region* aspect is check-phase behavior
  owned by later tasks; T08 covers its open/metadata half.
- **Privacy/egress** — no `fetch`/XHR/`sendBeacon`/`createObjectURL`/
  storage writes in owned code; worker + cMaps/fonts/wasm/iccs are
  same-origin staged assets; the spec's request capture proves no egress.

## Findings

All minor; none block acceptance.

- **F1 (minor) — stale `currentDocument`/`currentHandle` after a failed
  replace.** `controller.ts:174-178, 187-201, 211-220`: every early
  rejection path in `offer()` leaves `this.document`/`this.handle` pointing
  at the *previous* (already torn-down) document; only the `pages()` /
  `too_many_pages` paths null `this.handle` (250-251, 267) and no path
  nulls `this.document`. `currentDocument` can therefore report a destroyed
  document while the host sits `idle`. Latent only — the view renders from
  the event stream (doc is cleared on `clear`/`rejected`) and mount
  consumers are gated by UI state — but the getters contradict the "no
  stale document" ordering the events enforce. Suggest nulling both on every
  rejection path in a follow-up.
- **F2 (minor) — two profile fields declared but never consumed.**
  `limits.ts:19-24,32-33,41-42` define `maxOcrPagesPerRun` (5 desktop /
  1 mobile) and `maxRasterPixels`, but nothing enforces or surfaces them:
  `mount.tsx:111-115` plans an `ocr` check on *every* selected page (up to
  20), exceeding the profile's OCR-per-run cap with no notice, and the
  mobile 2 Mpx raster cap is unenforced (the adapter keeps its 4 Mpx
  default; the preview request is ≈0.52 Mpx so harmless in practice).
  Plan-level only — checks are honestly enumerated and terminate
  `unsupported` at extract — but the settings.json contract values are dead
  config in T08's scope.
- **F3 (minor) — post-commit region label edits don't reach the contract
  record.** `OpenWorkspace.tsx:333-338` updates `entry.label` on
  `onLabelChange` but not `entry.region.label`; the `Region` bound into the
  plan keeps the commit-time label while the UI shows the new one.
- **F4 (informational) — rotation test proves bounds discipline, not a
  known anchor.** `RegionEditor.tsx:106-114` clamps the converted point into
  page bounds, so the committed canonical box is in-bounds by construction;
  the test asserts bounds + positive area (plus `meta.rotation===90` and a
  genuinely transposed raster), not an expected coordinate pair. Verified
  acceptable because the math is textually identical to COORDINATES.md and
  `packages/geometry`, and the adapter's `viewportVerified` flag supplies
  the runtime cross-check against S·R·C.
- **F5 (minor) — `open:busy` refusal emits no event.**
  `controller.ts:144-149` returns `open_failed` without a `rejected` event,
  so a programmatic concurrent offer would silently clear the workspace
  error state (`OpenWorkspace.tsx:154-160` clears the error, then ignores
  the outcome). Unreachable via the current UI (the input is disabled while
  `busy`).

## Not verified

- IndexedDB/CacheStorage/service-worker non-use — owned code contains no
  such API calls; the spec asserts localStorage/sessionStorage/cookies only.
- F17's unreadable-region *check-phase* behavior — owned by later tasks per
  the recorded limitation.
- oxfmt conformance — the repo carries no committed oxfmt config; the
  worker's documented baseline disagreement stands unadjudicated (lint is
  clean; not a registered command).
- The actual held-out fixture bytes for F17/F18/F19/F21 — confirmed absent;
  generated equivalents reviewed in their place.
- `documentPages()`'s eager per-page walk (document.ts:281-284) on real
  1000-page documents is asserted only for duration implicitly (suite
  timeout); no explicit bound beyond the page-count cap.

## Evidence

- `artifacts/tasks/T08/receipt.json`, `handoff.json`, `commands.log`,
  `run.json`, `eval.json` — internally consistent; criteria map to real
  executed assertions.
- This file: `artifacts/tasks/T08/review.md`.


---

## Delta review — 2026-09-13, evaluated `412fb9b2`

- **Reviewer:** devin-coordinator (acceptance refresh; not the implementing worker for this delta's shared changes)
- **Scope delta:** Owned scope delta: `features/open/OpenWorkspace.tsx` gained a lazy init
from `controller.currentDocument` so a remount after the `metadata` event still
renders the open document (composition wiring, pdf-3g8); `open.spec.ts` updated
to the real surface. Reviewed in the pdf-3g8 independent review rounds — the
lazy init reads controller state at mount, no behavior change on the original
selection/validation paths.
- **Fresh run:** Re-ran all registered commands at `412fb9b2`: **13/13 green**, zero failures.
- **Verdict:** prior review stands; delta introduces no acceptance-relevant regression.
