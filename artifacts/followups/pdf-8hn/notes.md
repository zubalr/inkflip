# pdf-8hn — T08 Review Follow-ups Implementation Report

- **Task:** `pdf-8hn` ("T08 review follow-ups: stale handle on failed replace, unenforced OCR/raster caps, region label edit propagation, busy-refusal event")
- **Worker:** Antigravity (Mac UI worker / independent reviewer)
- **Grant:** `bd show pdf-8hn --json` (Devin coordinator grant converted to IMPLEMENTATION on 2026-09-13)
- **Base:** `aa6d039` (canonical `main`), atop initial audit commit `4fe6be0`
- **Branch:** `work/antigravity/pdf-8hn` in `worktrees/pdf-8hn`
- **Product Source Edits:** **3 files** strictly within allowed paths:
  - `apps/web/src/features/open/controller.ts`
  - `apps/web/src/features/open/mount.tsx`
  - `apps/web/src/features/open/OpenWorkspace.tsx`
- **Focused Regression Spec:** `tests/browser/pdf-8hn.spec.ts` (4 Playwright browser tests, 100% passing)
- **Verification Script:** `artifacts/followups/pdf-8hn/repro.ts` (`bun artifacts/followups/pdf-8hn/repro.ts` exits 0 with all 4 confirmed resolved)
- **Beads Writes:** **0** (no mutations performed on canonical Beads tracker)

---

## Executive Summary

All four findings from `artifacts/tasks/T08/review.md` (F1, F2, F3, F5) have been implemented and verified on branch `work/antigravity/pdf-8hn`. Every change is strictly bounded to the explicitly permitted paths, preserving all contracts, schemas, and receipts.

| # | Finding | Primary Source Site | Status | Resolution |
|---|---|---|---|---|
| 1 | Stale handle on failed replace | `apps/web/src/features/open/controller.ts` | **Resolved** | Nulled `handle` and `document` on replace initiation and across all rejection/error catch paths. |
| 2 | Unenforced OCR/raster caps | `apps/web/src/features/open/mount.tsx` | **Resolved** | Passed `limits: { maxRasterPixels: profile.maxRasterPixels }` to reader; capped planned OCR checks to `profile.maxOcrPagesPerRun` in `startRun` prioritizing explicit user regions. |
| 3 | Region label edit propagation | `apps/web/src/features/open/OpenWorkspace.tsx` | **Resolved** | Updated `onLabelChange` callback to synchronize nested `entry.region.label` alongside `entry.label`. |
| 4 | Busy-refusal event | `apps/web/src/features/open/controller.ts` | **Resolved** | Emitted `{ type: "rejected", generation, kind: "open_failed", error }` on `this.busy` refusal. |

---

## Implementation Details

### 1. Stale handle on failed replace (Review F1)
- **File:** `apps/web/src/features/open/controller.ts`
- **Changes:**
  - Upon starting replacement (`state !== "idle"`), immediately reset `this.handle = null; this.document = null;`.
  - In all rejection branches (`validateCandidate`, `candidate.arrayBuffer()`, `sha256Hex()`, `adapter.open()`, `adapter.pages()`, `too_many_pages`), explicitly null `this.handle` and `this.document`.
  - In the outer `catch (error)` handler and `state === "clearing"` branch, reset `this.handle = null; this.document = null;`.
  - Also ensure `candidate.arrayBuffer()` and `sha256Hex()` failure catch blocks emit a `rejected` event before returning so listeners observe the failure.

### 2. Unenforced OCR/raster caps (Review F2)
- **File:** `apps/web/src/features/open/mount.tsx`
- **Changes:**
  - In `createPdfJsReader({...})`, added `limits: { maxRasterPixels: profile.maxRasterPixels }`. Under desktop profile this provides 4,000,000 pixels; under mobile profile this enforces the 2,000,000 pixel cap.
  - In `startRun()`, separated check planning into base capabilities (`native_text`, `render` for all selected pages) and OCR capability:
    - Prioritizes pages with explicit user-defined region bindings (`regions.has(p)`).
    - Caps total OCR planned pages to `profile.maxOcrPagesPerRun` (5 on desktop, 1 on mobile).
    - Preserves all selected pages in the run total and base checks without violating OCR resource caps.
  - Exported `getLastStartRunRegions: () => lastStartRunRegions` on `globalThis.__t08` to enable deterministic browser verification.

### 3. Region label edit propagation (Review F3)
- **File:** `apps/web/src/features/open/OpenWorkspace.tsx`
- **Changes:**
  - In `RegionEditor.onLabelChange`, updated the state setter to synchronize `previewRegion.region.label` with `trimmed.slice(0, 200)` alongside `previewRegion.label`.
  - When `runStart()` later harvests `contractRegions`, the resulting `ContractRegion` records carry the user-edited text instead of stale initial values (`"Region 1"`).

### 4. Busy-refusal event (Review F5)
- **File:** `apps/web/src/features/open/controller.ts`
- **Changes:**
  - In `offer()`, when `this.busy` is true, emit `{ type: "rejected", generation: this.host.currentGeneration, kind: err.kind, error: err }` before returning `{ ok: false, error: err }`.
  - UI listeners (`OpenWorkspace.tsx`) subscribe to controller events to render error notices; emitting `rejected` ensures busy refusals surface visibly to users and test harnesses instead of being silently swallowed.

---

## Verification Evidence

### 1. Deterministic Standalone Verification Suite
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
Configured reader adapter maxRasterPixels: 2000000
Raster cap enforced in mobile reader adapter: true
Selected pages count: 8
DESKTOP_PROFILE.maxOcrPagesPerRun: 5
Planned OCR pages count: 5
OCR per-run cap enforced: true
Item 2 resolved: true

--- Item 3: Region label edit propagation ---
UI displayed entry.label: Total Amount Bounding Box
Contract entry.region.label (passed to startRun): Total Amount Bounding Box
Contract record synchronized with UI edit: true
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

### 2. Focused Playwright Browser Regression Suite
```bash
$ bun run test:browser -- tests/browser/pdf-8hn.spec.ts
$ python3 scripts/task_acceptance.py run test:browser "tests/browser/pdf-8hn.spec.ts"

Running 4 tests using 1 worker

[1/4] tests/browser/pdf-8hn.spec.ts:116:1 › F1: failed replace nulls currentHandle and currentDocument
[2/4] tests/browser/pdf-8hn.spec.ts:168:1 › F2: reader limits receive profile.maxRasterPixels and startRun enforces maxOcrPagesPerRun
[3/4] tests/browser/pdf-8hn.spec.ts:221:1 › F3: edited region label propagates to contract region in check plan
[4/4] tests/browser/pdf-8hn.spec.ts:277:1 › F5: busy refusal emits rejected event and surfaces error
  4 passed (3.9s)
# Exit code: 0
```

### 3. Static Analysis & Build Verification
```bash
$ bun x --no-install oxlint apps/web/src/features/open tests/browser/pdf-8hn.spec.ts artifacts/followups/pdf-8hn/repro.ts
Found 0 warnings and 0 errors.
Finished in 10ms on 11 files with 96 rules using 14 threads.

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
✓ built in 586ms
# Exit code: 0
```

---

## Bounded Diff Summary

```diff
 apps/web/src/features/open/OpenWorkspace.tsx | 10 +++++++++-
 apps/web/src/features/open/controller.ts    | 58 +++++++++++++++++++++++++++++++++++++++++++++++-----------
 apps/web/src/features/open/mount.tsx         | 26 ++++++++++++++++++++++----
 artifacts/followups/pdf-8hn/notes.md         | (documentation updated)
 artifacts/followups/pdf-8hn/repro.ts         | (converted from audit repro to passing resolution verification)
 tests/browser/pdf-8hn.spec.ts                | (new focused Playwright browser regression spec)
```

No files outside the allowed paths were modified. No Beads database writes were performed. Branch `work/antigravity/pdf-8hn` is ready for coordinator Devin review and post-G1 integration.
