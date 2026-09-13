# pdf-8hn — Independent Implementation Review

- **Reviewer:** Devin (independent; did not write this code)
- **Candidate:** `5c83242` on `review/devin/pdf-8hn` (AGY delivered revision, rounds: `40db355` → `c631a48` → `5c83242`)
- **Base:** `aa6d039` (canonical main); prior audit at `4fe6be0`
- **Verdict:** **APPROVED**

---

## Verdict Summary

All four audited fixes are implemented correctly — not superficially — and verified
against the real collaborators (RunCoordinator state machine, pdf.js adapter
`plan`/`config`, contract Region record). Every rejection/catch path in
`OpenController.offer()` now drops both `handle` and `document`; the OCR cap is a
real per-run page cap with pre-start UI notice (not a silent drop); the raster
pixel cap is wired into the reader config; region label edits propagate into the
`ContractRegion` record consumed by `startRun`; and the busy refusal emits a
`rejected` event with the same `OpenError` it returns.

## Fix-by-fix verification

### 1. Stale handle/document on failed replace — controller.ts:143-360

- Replace-initiate path (state `selecting`/`running`/terminal): emits `clear` with
  the retiring generation, calls `host.requestClear("replace")` (generation
  increments BEFORE teardowns per coordinator.ts:767-800 — I07 preserved), then
  nulls `handle`+`document` (controller.ts:187-189).
- Every failure exit now nulls both refs: `clearing` rejection (165-166),
  `validateCandidate` rejection (194-195), `arrayBuffer` catch (207-208), sha256
  catch (226-227), `adapter.open` catch (250-251), `adapter.pages` catch (291-292),
  `too_many_pages` (308-309), and the outer contract-violation catch (336-337).
  The busy refusal deliberately does NOT null — the in-flight offer still owns
  those refs; nulling there would corrupt a live replace.
- **Byte-identity/cancel probe:** no sha-dedup or identity short-circuit exists in
  `offer()` (verified by grep — `sha256` is only computed for the new candidate
  and stored on success), so replace-initiate nulling cannot strand a "same
  bytes" fast path. `ReplaceConfirmDialog.onCancel` never reaches the controller;
  `controller.clear()` (363-374) is unchanged and self-consistent.
- **Consistency probe (task item 4):** every rejection path pairs the emit with
  `host.requestClear("idle")` except `clearing` (host already mid-clear;
  `requestClear` would throw `already clearing` per coordinator.ts:770-774 —
  correctly not called) and `busy` (nothing was touched — correctly not called).
  Ordering of emit→requestClear→null leaves no observable stale refs at any
  await/return boundary.
- Two paths that previously returned failure WITHOUT emitting (`bytes:unreadable`,
  `sha256:unavailable`) now emit `rejected` too — a small bonus consistency fix.

### 2. Unenforced OCR/raster caps — mount.tsx:49, 115-135; OpenWorkspace.tsx:240-264, 380-400

- `limits: { maxRasterPixels: profile.maxRasterPixels }` flows into
  `createPdfJsReader` → `resolveConfig` merge (config.ts:100) → consumed by
  `renderPage` scale clamp (render.ts:121-123) and `canvasMaxAreaInBytes`
  (document.ts:128). Verified live: `adapter.config.limits.maxRasterPixels` ===
  profile value on both desktop (4_000_000) and mobile (2_000_000) profiles.
- `startRun` splits the plan: `native_text`+`render` on all selected pages, `ocr`
  on `[...regionPages, ...nonRegionPages].slice(0, maxOcrPagesPerRun)` — a real
  per-run page cap matching the `limits.ts` contract ("settings
  *.max_ocr_pages_per_run"), prioritizing explicit user regions.
- `adapter.plan` resolves `region_id` per planned page only (adapter.ts:363), so
  passing bindings for beyond-cap region pages is harmless — no phantom checks.
  Check ids stay unique across the two calls (`chk_pN_<capability>`).
- Not a silent drop: `#ocr-limit-notice` renders before start (info when
  selection > cap; warning naming the omitted region pages when regions exceed
  the cap), and `preview-ocromitted` marks an omitted region page in the preview
  row. Component-side `plannedOcrPages` memo mirrors `startRun` semantics exactly
  (both filter `selection.pages()`-ordered arrays by `regions.has`).

### 3. Region label edit propagation — OpenWorkspace.tsx:363-376

- `onLabelChange` now writes `entry.region.label` = `trimmed.slice(0, 200)` with
  `"Region 1"` fallback — the exact normalization `commitRegion`/`regionToContract`
  apply at commit time (region.ts:111), while `entry.label` keeps the raw input
  for the controlled field. `runStart` ships `entry.region` into `startRun`, so
  the edited label reaches the contract record (asserted via
  `getLastStartRunRegions()`).

### 4. Busy-refusal event — controller.ts:144-156

- `rejected` event emitted with `kind: "open_failed"`, the same `OpenError`
  instance returned to the caller (`detail: "open:busy"`), and
  `generation: host.currentGeneration`. UI renders it identically to any other
  rejection — matches the event-stream contract.

## Scope check

`git diff aa6d039..5c83242 --stat`: 7 files —
`apps/web/src/features/open/{controller,mount,OpenWorkspace}.{ts,tsx}`,
`tests/browser/pdf-8hn.spec.ts` (new, 524 lines, 6 tests),
`tests/browser/open.spec.ts` (+16/-6), `artifacts/followups/pdf-8hn/{notes.md,repro.ts}`.
No fixtures, goldens, or shared outputs touched.
Note: `open.spec.ts` sits outside the literal "new spec" scope but is documented
as owner-authorized (notes.md §Authorized Scope) and is *required* — the old
assertion that every selected page carries `ocr` would fail under the enforced
cap. The replacement assertion is strictly stronger (asserts exactly 5 OCR pages
plus full native/render coverage).

## Verification executed (this checkout, fresh `bun install`)

| Command | Result |
|---|---|
| `bun artifacts/followups/pdf-8hn/repro.ts` | 4/4 items CONFIRMED RESOLVED, exit 0 |
| `python3 scripts/task_acceptance.py run test:browser tests/browser/pdf-8hn.spec.ts tests/browser/open.spec.ts` | 19/19 passed (6 pdf-8hn + 13 open), 15.4s |
| `bun run verify` | 49 + 2 + 65 unit tests OK + registry checks, exit 0 |
| `bun run build:web` | vite build OK, exit 0 |
| `oxlint` on all touched files | 0 warnings, 0 errors |

No `test.only`/`test.skip`/`fixme` in the specs. Worktree clean at `5c83242`.

## Non-blocking observations (P3)

1. In the replace path, `handle`/`document` are nulled AFTER
   `requestClear("replace")` returns (controller.ts:187-189). A synchronous
   `teardown`-event listener could still read `currentHandle` as the
   mid-teardown handle inside that window. There is no `await` between the two
   statements and every return/await boundary observes null — diagnostic-only,
   not a defect. Reversing the order would be equally valid.
2. `lastStartRunRegions` module-level mutable + `__t08.getLastStartRunRegions`
   (mount.tsx:101,175) is a test hook in production composition code — consistent
   with the file's existing `__t08` harness pattern, acceptable.
3. OCR-cap prioritization is duplicated between the `plannedOcrPages` memo and
   `startRun`. Identical today; if one ever changes, notice could misstate the
   plan. A shared helper would remove the drift risk — optional.
4. `repro.ts` item 3 re-implements the `onLabelChange` body inline rather than
   exercising the component (React/tsx not importable in that harness). The real
   path is covered end-to-end by spec F3 — adequate.
