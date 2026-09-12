# pdf-8hn — T08 Review Follow-ups Implementation Report (Revision 3 / Final)

- **Task:** `pdf-8hn` ("T08 review follow-ups: stale handle on failed replace, unenforced OCR/raster caps, region label edit propagation, busy-refusal event")
- **Worker:** Antigravity (Mac UI worker / independent reviewer)
- **Grant:** `bd show pdf-8hn --json` (Devin coordinator grant converted to IMPLEMENTATION on 2026-09-13; owner-authorized revisions per independent review)
- **Base:** `aa6d039` (canonical `main`), atop initial audit commit `4fe6be0`, round-1 candidate `40db355`, and revision-2 candidate `c631a48`
- **Branch:** `work/antigravity/pdf-8hn` in `worktrees/pdf-8hn`
- **Authorized Scope:**
  - `apps/web/src/features/open/controller.ts`
  - `apps/web/src/features/open/mount.tsx`
  - `apps/web/src/features/open/OpenWorkspace.tsx`
  - `tests/browser/open.spec.ts` (narrowly included per owner authorization for affected 25-page selection assertion)
  - `tests/browser/pdf-8hn.spec.ts` (focused Playwright regression suite, 6/6 passing)
  - `artifacts/followups/pdf-8hn/` evidence
- **Beads Writes:** **0** (strictly read-only on canonical Beads tracker)

---

## Review Iteration Summary

1. **Round 1 Review (`40db355`) by Descartes (`01a097f9-fac6-7353-9fa2-f5f55a0393a0`):**
   - *Findings:* Existing 25-page selection test asserted OCR on all pages; 6 region-bearing pages omitted 6th page OCR without pre-start UI indication.
   - *Fixes:* Aligned `open.spec.ts:742-748` assertion to reflect intentional 5-page OCR cap; added `#ocr-limit-notice` and `preview-ocromitted` to `OpenWorkspace.tsx`; added regression test `F2b`.

2. **Round 2 Re-Review (`c631a48`) by Dirac (`01a09808-5db6-7e62-a1f6-649312ca05b3`):**
   - *Findings:* Both P2 findings resolved; 18/18 affected browser tests passed.
   - *P3 Polish:* In `OpenWorkspace.tsx:396`, phrasing `"The first 5 selected pages"` was inaccurate when regions were prioritized. Change copy to explain region priority and add mixed-selection regression proving notice matches actual plan.

3. **Round 3 Resolution (Current / Final):**
   - Updated notice copy in `OpenWorkspace.tsx` to:
     `OCR is capped at ${profile.maxOcrPagesPerRun} pages per run (prioritizing explicit regions). Pages ${plannedOcrPages.map((p) => p + 1).join(", ")} will include OCR; all ${selectedPages.length} selected pages will be checked with native text and rendering.`
   - Added test `F2d` in `tests/browser/pdf-8hn.spec.ts` for mixed selection (pages 1–8 selected, explicit region on page 8), confirming notice lists `8, 1, 2, 3, 4` and actual plan executes `ocr` on pages `[7, 0, 1, 2, 3]` with bound region on page 8.

---

## Executive Summary of Implemented Fixes

| # | Finding | Primary Source Site | Status | Resolution |
|---|---|---|---|---|
| 1 | Stale handle on failed replace | `apps/web/src/features/open/controller.ts` | **Resolved** | Nulled `handle` and `document` on replace initiation and across all rejection/error catch paths. |
| 2 | Unenforced OCR/raster caps & UI surfacing | `apps/web/src/features/open/mount.tsx`, `OpenWorkspace.tsx` | **Resolved** | Passed `limits: { maxRasterPixels: profile.maxRasterPixels }` to reader; capped planned OCR checks to `profile.maxOcrPagesPerRun` in `startRun` prioritizing explicit user regions; surfaced cap and affected pages before starting via `#ocr-limit-notice` and `preview-ocromitted` with region-priority explanation. |
| 3 | Region label edit propagation | `apps/web/src/features/open/OpenWorkspace.tsx` | **Resolved** | Updated `onLabelChange` callback to synchronize nested `entry.region.label` alongside `entry.label`. |
| 4 | Busy-refusal event | `apps/web/src/features/open/controller.ts` | **Resolved** | Emitted `{ type: "rejected", generation, kind: "open_failed", error }` on `this.busy` refusal. |

---

## Verification Evidence

### 1. Existing Full Browser Suite (`tests/browser/open.spec.ts`)
```bash
$ bun run test:browser -- tests/browser/open.spec.ts
$ python3 scripts/task_acceptance.py run test:browser tests/browser/open.spec.ts

Running 13 tests using 1 worker

[1/13]  tests/browser/open.spec.ts:189:1 › valid PDF opens locally with metadata, count, default selection and raster
[2/13]  tests/browser/open.spec.ts:217:1 › drop zone accepts a real dropped file
[3/13]  tests/browser/open.spec.ts:243:1 › wrong MIME, wrong header, encrypted and malformed are distinct errors
[4/13]  tests/browser/open.spec.ts:320:1 › 20MiB size gate rejects before any byte read; boundary passes to the reader
[5/13]  tests/browser/open.spec.ts:403:1 › mobile profile: 10MiB gate and 5-page selection cap
[6/13]  tests/browser/open.spec.ts:457:1 › 1000-page boundary: real generated PDF opens; 1001 is a distinct error
[7/13]  tests/browser/open.spec.ts:507:1 › new file revokes the old generation before teardown; stale messages rejected
[8/13]  tests/browser/open.spec.ts:631:1 › 25 pages: select-all caps visibly; the plan enumerates exactly the selection
[9/13]  tests/browser/open.spec.ts:704:1 › region drag and numeric entry stay inside page bounds; padding explicit
[10/13] tests/browser/open.spec.ts:779:1 › rotated page: drag converts to canonical bounds inside page extent
[11/13] tests/browser/open.spec.ts:817:1 › huge page opens; region validation quotes its real bounds
[12/13] tests/browser/open.spec.ts:841:1 › no document data reaches the URL, storage or any network request
[13/13] tests/browser/open.spec.ts:937:1 › clear releases the document and returns the drop zone to idle
  13 passed (11.1s)
# Exit code: 0
```

### 2. Focused Playwright Browser Regression Suite (`tests/browser/pdf-8hn.spec.ts`)
```bash
$ bun run test:browser -- tests/browser/pdf-8hn.spec.ts
$ python3 scripts/task_acceptance.py run test:browser "tests/browser/pdf-8hn.spec.ts"

Running 6 tests using 1 worker

[1/6] tests/browser/pdf-8hn.spec.ts:116:1 › F1: failed replace nulls currentHandle and currentDocument
[2/6] tests/browser/pdf-8hn.spec.ts:168:1 › F2: reader limits receive profile.maxRasterPixels and startRun enforces maxOcrPagesPerRun
[3/6] tests/browser/pdf-8hn.spec.ts:221:1 › F3: edited region label propagates to contract region in check plan
[4/6] tests/browser/pdf-8hn.spec.ts:277:1 › F5: busy refusal emits rejected event and surfaces error
[5/6] tests/browser/pdf-8hn.spec.ts:342:1 › F2b: surfaces OCR cap notice before starting and warns on omitted region pages
[6/6] tests/browser/pdf-8hn.spec.ts:404:1 › F2d: mixed selection with region on page 8 prioritizes page 8 for OCR and notice matches plan
  6 passed (10.2s)
# Exit code: 0
```

### 3. Deterministic Standalone Verification Suite (`artifacts/followups/pdf-8hn/repro.ts`)
```bash
$ bun artifacts/followups/pdf-8hn/repro.ts
=== pdf-8hn Fix Verifications (work/antigravity/pdf-8hn) ===
--- Item 1: Stale handle/document on failed replace ---
Item 1 resolved: true
--- Item 2: Unenforced OCR/raster caps ---
Native checks planned via adapter.plan: 8
Render checks planned via adapter.plan: 8
OCR checks planned via adapter.plan (capped at 5): 5
Item 2 resolved: true
--- Item 3: Region label edit propagation ---
Contract record synchronized with UI edit and bound to plan: true
Item 3 resolved: true
--- Item 4: Busy-refusal event ---
Item 4 resolved: true
=== All 4 follow-up issues CONFIRMED RESOLVED ===
# Exit code: 0
```

### 4. Static Analysis & Build Verification
```bash
$ bun x --no-install oxlint apps/web/src/features/open tests/browser/open.spec.ts tests/browser/pdf-8hn.spec.ts artifacts/followups/pdf-8hn/repro.ts
Found 0 warnings and 0 errors.
Finished in 18ms on 12 files with 96 rules using 14 threads.

$ bun run build:web
$ python3 scripts/task_acceptance.py run build:web
vite v8.3.0 building client environment for production...
transforming...
✓ 51 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.55 kB │ gzip:  0.33 kB
dist/assets/index-CK80oKyc.css   20.13 kB │ gzip:  4.01 kB
dist/assets/index-BqjCALFT.js   229.93 kB │ gzip: 71.16 kB
✓ built in 201ms
# Exit code: 0
```

---

## Bounded Diff Summary

```diff
 apps/web/src/features/open/OpenWorkspace.tsx |  56 +++++++++-
 apps/web/src/features/open/controller.ts    |  58 +++++++++++++++++++++++++++++++++++++++++++++++-----------
 apps/web/src/features/open/mount.tsx         |  27 ++++++++++++++++++++++----
 artifacts/followups/pdf-8hn/notes.md         | (complete 3-round review documentation)
 artifacts/followups/pdf-8hn/repro.ts         |  69 ++++++++----
 tests/browser/open.spec.ts                   |  16 ++-
 tests/browser/pdf-8hn.spec.ts                | 475 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
```

Total: 19/19 browser tests passing. Clean worktree, zero Beads mutations, merge deferred to Devin post-G1.
