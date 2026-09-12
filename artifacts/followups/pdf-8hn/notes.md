# pdf-8hn — T08 Review Follow-ups Implementation Report (Revision 2)

- **Task:** `pdf-8hn` ("T08 review follow-ups: stale handle on failed replace, unenforced OCR/raster caps, region label edit propagation, busy-refusal event")
- **Worker:** Antigravity (Mac UI worker / independent reviewer)
- **Grant:** `bd show pdf-8hn --json` (Devin coordinator grant converted to IMPLEMENTATION on 2026-09-13; owner-authorized revision 2 per independent review)
- **Base:** `aa6d039` (canonical `main`), atop initial audit commit `4fe6be0` and round-1 candidate `40db355`
- **Branch:** `work/antigravity/pdf-8hn` in `worktrees/pdf-8hn`
- **Allowed Paths for Revision:**
  - `apps/web/src/features/open/controller.ts`
  - `apps/web/src/features/open/mount.tsx`
  - `apps/web/src/features/open/OpenWorkspace.tsx`
  - `tests/browser/open.spec.ts` (narrowly included per owner authorization for affected 25-page selection assertion)
  - `tests/browser/pdf-8hn.spec.ts` (focused Playwright regression suite)
  - `artifacts/followups/pdf-8hn/` evidence
- **Beads Writes:** **0** (no mutations performed on canonical Beads tracker)

---

## Round-1 Review Feedback & Resolutions

Independent review of candidate `40db355` by Descartes (Codex subagent `01a097f9-fac6-7353-9fa2-f5f55a0393a0`, report at `/private/tmp/inkflip-pdf-8hn-review-40db355.md`) requested two changes:

1. **Existing browser acceptance test (`tests/browser/open.spec.ts:746`)**:
   - *Feedback:* The test expected all 19 selected pages to have OCR, but `maxOcrPagesPerRun: 5` capped OCR to 5 pages while preserving `native_text` and `render` on all 19 pages.
   - *Resolution:* Updated `tests/browser/open.spec.ts:742-748` to preserve complete `native_text` and `render` coverage across all 19 selected pages and assert the intentional 5-page OCR cap (`ocrPages.size === 5`). All 13 tests in `open.spec.ts` now pass (100%).

2. **Silent OCR truncation and explicit region omission (`mount.tsx` / `OpenWorkspace.tsx`)**:
   - *Feedback:* Six selected region-bearing desktop pages led to one explicit region receiving no OCR check without pre-start UI indication.
   - *Resolution:* In `OpenWorkspace.tsx`, memoized the planned OCR vs. omitted pages:
     - Surfaced `#ocr-limit-notice` before `startRow`. When selected pages exceed `profile.maxOcrPagesPerRun`, the notice informs the user which pages include OCR and confirms all selected pages receive native text and rendering.
     - When explicit region pages exceed the cap (e.g. 6 region-bearing pages), `#ocr-limit-notice` renders a warning explicitly identifying the omitted region page(s).
     - In the preview page row, `[data-testid=preview-ocromitted]` alerts the user directly if the active preview page's region exceeds the OCR cap.
     - Added test `F2b` in `tests/browser/pdf-8hn.spec.ts` verifying this exact flow with 6 region-bearing pages.

3. **Reproduction script independence (`artifacts/followups/pdf-8hn/repro.ts`)**:
   - *Feedback:* Ensure cap and label sections verify behavior independently through actual adapter contracts.
   - *Resolution:* Re-architected `repro.ts` items 2 & 3 to instantiate `createPdfJsReader` and invoke `adapter.plan()` directly with reader handles and region bindings, asserting real `CheckPlan` outputs.

---

## Executive Summary

| # | Finding | Primary Source Site | Status | Resolution |
|---|---|---|---|---|
| 1 | Stale handle on failed replace | `apps/web/src/features/open/controller.ts` | **Resolved** | Nulled `handle` and `document` on replace initiation and across all rejection/error catch paths. |
| 2 | Unenforced OCR/raster caps & UI surfacing | `apps/web/src/features/open/mount.tsx`, `OpenWorkspace.tsx` | **Resolved** | Passed `limits: { maxRasterPixels: profile.maxRasterPixels }` to reader; capped planned OCR checks to `profile.maxOcrPagesPerRun` in `startRun` prioritizing explicit user regions; surfaced cap and affected pages before starting via `#ocr-limit-notice` and `preview-ocromitted`. |
| 3 | Region label edit propagation | `apps/web/src/features/open/OpenWorkspace.tsx` | **Resolved** | Updated `onLabelChange` callback to synchronize nested `entry.region.label` alongside `entry.label`. |
| 4 | Busy-refusal event | `apps/web/src/features/open/controller.ts` | **Resolved** | Emitted `{ type: "rejected", generation, kind: "open_failed", error }` on `this.busy` refusal. |

---

## Verification Evidence

### 1. Existing Full Browser Suite (`tests/browser/open.spec.ts`)
```bash
$ bun run test:browser -- tests/browser/open.spec.ts
$ python3 scripts/task_acceptance.py run test:browser tests/browser/open.spec.ts

Running 13 tests using 1 worker

[1/13] tests/browser/open.spec.ts:189:1 › valid PDF opens locally with metadata, count, default selection and raster
[2/13] tests/browser/open.spec.ts:217:1 › drop zone accepts a real dropped file
[3/13] tests/browser/open.spec.ts:243:1 › wrong MIME, wrong header, encrypted and malformed are distinct errors
[4/13] tests/browser/open.spec.ts:320:1 › 20MiB size gate rejects before any byte read; boundary passes to the reader
[5/13] tests/browser/open.spec.ts:403:1 › mobile profile: 10MiB gate and 5-page selection cap
[6/13] tests/browser/open.spec.ts:457:1 › 1000-page boundary: real generated PDF opens; 1001 is a distinct error
[7/13] tests/browser/open.spec.ts:507:1 › new file revokes the old generation before teardown; stale messages rejected
[8/13] tests/browser/open.spec.ts:631:1 › 25 pages: select-all caps visibly; the plan enumerates exactly the selection
[9/13] tests/browser/open.spec.ts:704:1 › region drag and numeric entry stay inside page bounds; padding explicit
[10/13] tests/browser/open.spec.ts:779:1 › rotated page: drag converts to canonical bounds inside page extent
[11/13] tests/browser/open.spec.ts:817:1 › huge page opens; region validation quotes its real bounds
[12/13] tests/browser/open.spec.ts:841:1 › no document data reaches the URL, storage or any network request
[13/13] tests/browser/open.spec.ts:937:1 › clear releases the document and returns the drop zone to idle
  13 passed (11.7s)
# Exit code: 0
```

### 2. Focused Playwright Browser Regression Suite (`tests/browser/pdf-8hn.spec.ts`)
```bash
$ bun run test:browser -- tests/browser/pdf-8hn.spec.ts
$ python3 scripts/task_acceptance.py run test:browser "tests/browser/pdf-8hn.spec.ts"

Running 5 tests using 1 worker

[1/5] tests/browser/pdf-8hn.spec.ts:116:1 › F1: failed replace nulls currentHandle and currentDocument
[2/5] tests/browser/pdf-8hn.spec.ts:168:1 › F2: reader limits receive profile.maxRasterPixels and startRun enforces maxOcrPagesPerRun
[3/5] tests/browser/pdf-8hn.spec.ts:221:1 › F3: edited region label propagates to contract region in check plan
[4/5] tests/browser/pdf-8hn.spec.ts:277:1 › F5: busy refusal emits rejected event and surfaces error
[5/5] tests/browser/pdf-8hn.spec.ts:342:1 › F2b: surfaces OCR cap notice before starting and warns on omitted region pages
  5 passed (8.3s)
# Exit code: 0
```

### 3. Deterministic Standalone Verification Suite (`artifacts/followups/pdf-8hn/repro.ts`)
```bash
$ bun artifacts/followups/pdf-8hn/repro.ts
=== pdf-8hn Fix Verifications (work/antigravity/pdf-8hn) ===

--- Item 1: Stale handle/document on failed replace ---
Offer outcome ok: false
Host fileState: idle
currentHandle nulled: true
currentDocument nulled: true
Item 1 resolved: true

--- Item 2: Unenforced OCR/raster caps ---
MOBILE_PROFILE.maxRasterPixels: 2000000
createPdfJsReader config maxRasterPixels: 2000000
Raster cap enforced in mobile reader adapter: true
Selected pages count: 8
Native checks planned via adapter.plan: 8
Render checks planned via adapter.plan: 8
OCR checks planned via adapter.plan (capped at 5): 5
OCR per-run cap enforced: true
Item 2 resolved: true

--- Item 3: Region label edit propagation ---
UI displayed entry.label: Total Amount Bounding Box
Contract entry.region.label: Total Amount Bounding Box
Planned check bound region_id: region_p0_1
Contract record synchronized with UI edit and bound to plan: true
Item 3 resolved: true

--- Item 4: Busy-refusal event ---
Concurrent offer outcome ok: false
Concurrent offer error detail: open:busy
Emitted rejected event for busy refusal: true
Item 4 resolved: true

============================================================
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
✓ built in 208ms
# Exit code: 0
```

---

## Bounded Diff Summary

```diff
 apps/web/src/features/open/OpenWorkspace.tsx | 44 +++++++++++++++++++++++++++++++++++++++--
 apps/web/src/features/open/controller.ts    | 58 +++++++++++++++++++++++++++++++++++++++++++++++-----------
 apps/web/src/features/open/mount.tsx         | 27 ++++++++++++++++++++++----
 artifacts/followups/pdf-8hn/notes.md         | (documentation updated with revision 2 details)
 artifacts/followups/pdf-8hn/repro.ts         | (independent reader/plan verification script)
 tests/browser/open.spec.ts                   | 13 ++++++++++---
 tests/browser/pdf-8hn.spec.ts                | (5-test focused Playwright browser regression spec)
```

No files outside the authorized scope were touched. Zero writes to Beads database. Branch `work/antigravity/pdf-8hn` is clean and ready for independent re-review.
