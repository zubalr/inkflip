# pdf-8hn — T08 Review Follow-ups Audit

- **Task:** `pdf-8hn` ("T08 review follow-ups: stale handle on failed replace, unenforced OCR/raster caps, region label edit propagation, busy-refusal event")
- **Auditor:** Antigravity (Mac UI worker / independent reviewer)
- **Grant:** `bd show pdf-8hn --json` (Devin coordinator grant, 2026-09-12)
- **Base:** `aa6d039` (canonical `main`)
- **Branch:** `work/antigravity/pdf-8hn` in `worktrees/pdf-8hn`
- **Product Source Edits:** **0** (strictly preserved during frozen G1 batch)
- **Beads Writes:** **0** (read-only audit per coordinator directive)
- **Reproduction Script:** `artifacts/followups/pdf-8hn/repro.ts` (`bun artifacts/followups/pdf-8hn/repro.ts` exits 0 with all 4 confirmed)

---

## Executive Summary

All four findings from `artifacts/tasks/T08/review.md` (F1, F2, F3, F5) **still reproduce on canonical main `aa6d039`**. Every issue has been traced to exact source lines with executable minimal repros, and all four fixes are strictly bounded to local UI/adapter orchestration files without altering any public contract, schema, or gate prerequisite.

| # | Finding | Primary Source Site | Status on `main` | Fix Bounded? | Scope / Files |
|---|---|---|---|---|---|
| 1 | Stale handle on failed replace | `apps/web/src/features/open/controller.ts:172,178,191,201,220,251,267,308` | **Reproduced** | **Yes** (bounded) | `features/open/controller.ts` (~8 lines) |
| 2 | Unenforced OCR/raster caps | `apps/web/src/features/open/mount.tsx:40-49,111-115` | **Reproduced** | **Yes** (bounded) | `features/open/mount.tsx` (~10 lines) |
| 3 | Region label edit propagation | `apps/web/src/features/open/OpenWorkspace.tsx:333-338` | **Reproduced** | **Yes** (bounded) | `features/open/OpenWorkspace.tsx` (~5 lines) |
| 4 | Busy-refusal event | `apps/web/src/features/open/controller.ts:144-149` | **Reproduced** | **Yes** (bounded) | `features/open/controller.ts` (~6 lines) |

---

## Detailed Audit & Evidence

### 1. Stale handle on failed replace (Review F1)

- **Exact File & Lines:**
  - `apps/web/src/features/open/controller.ts:163-172`: Replacement begins and calls `this.host.requestClear("replace")`, bumping generation and destroying old document resources, but `this.handle` and `this.document` are not nulled.
  - `apps/web/src/features/open/controller.ts:174-178`: Rejection on candidate validation (`validateCandidate`).
  - `apps/web/src/features/open/controller.ts:186-192`: Rejection on `candidate.arrayBuffer()`.
  - `apps/web/src/features/open/controller.ts:196-202`: Rejection on `sha256Hex()`.
  - `apps/web/src/features/open/controller.ts:211-220`: Rejection on `adapter.open()`.
  - `apps/web/src/features/open/controller.ts:250-252`: Rejection on `adapter.pages()` (nulls `this.handle`, but leaves `this.document` stale).
  - `apps/web/src/features/open/controller.ts:266-268`: Rejection on `too_many_pages` (nulls `this.handle`, but leaves `this.document` stale).
  - `apps/web/src/features/open/controller.ts:293-312`: Outer catch block (neither is nulled).

- **Reproduction Evidence:**
  When candidate document A is open and candidate B is offered but fails validation (e.g. non-PDF MIME type), `controller.offer()` clears the host state back to `"idle"` via `this.host.requestClear("idle")`. However:
  ```ts
  controller.currentHandle; // still returns doc A's torn-down handle object!
  controller.currentDocument; // still returns doc A's metadata info!
  ```
  Verified via `artifacts/followups/pdf-8hn/repro.ts` (Item 1: `staleHandle !== null && staleDoc !== null && host.fileState === "idle"` is `true`).

- **Root Cause & Impact:**
  `OpenController` only sets `this.handle` upon successful `adapter.open()` and `this.document` upon successful `metadataLoaded()`. If replacement clears document A and candidate B fails prior to that, the instance fields retain document A's references. While `OpenWorkspace.tsx` reacts to the `rejected`/`clear` event stream by clearing local state (`setDoc(null)`), external or harness callers inspecting `controller.currentHandle` or `controller.currentDocument` observe destroyed/stale document references while host state is `"idle"`.

- **Bounded Fix:**
  Strictly bounded to `apps/web/src/features/open/controller.ts`:
  1. In `offer()` upon initiating replace (`state !== "idle"`), immediately reset `this.handle = null; this.document = null;` before validating the new candidate.
  2. In all error/rejection paths and the outer catch block in `offer()`, ensure `this.handle = null; this.document = null;`.

---

### 2. Unenforced OCR/raster caps (Review F2)

- **Exact File & Lines:**
  - `apps/web/src/features/open/limits.ts:21-24,32-33,41-42`: Declares `maxOcrPagesPerRun` (5 desktop, 1 mobile) and `maxRasterPixels` (4,000,000 desktop, 2,000,000 mobile).
  - `apps/web/src/features/open/mount.tsx:40-49`: `createPdfJsReader` instantiation.
  - `apps/web/src/features/open/mount.tsx:111-115`: `adapter.plan()` in `startRun()`.

- **Reproduction Evidence:**
  1. **Raster pixel cap:** `mount.tsx:40-49` calls `createPdfJsReader(...)` without specifying `limits: { maxRasterPixels: profile.maxRasterPixels }`. Under `?profile=mobile` (`MOBILE_PROFILE`), `profile.maxRasterPixels` is `2_000_000`, but `resolveConfig()` defaults to `4_000_000`. The mobile raster budget is unenforced in the reader adapter.
  2. **OCR pages per run cap:** `mount.tsx:111-115` executes:
     ```ts
     const checks = adapter.plan(handle as never, {
       pages: [...pages],
       capabilities: ["native_text", "render", "ocr"],
       regions: regionBindings,
     });
     ```
     When 8 pages are selected on desktop, 8 OCR checks are planned (cap is 5). When 5 pages are selected on mobile, 5 OCR checks are planned (cap is 1). There is neither a UI warning nor a plan truncation enforcing `maxOcrPagesPerRun`.
  Verified via `artifacts/followups/pdf-8hn/repro.ts` (Item 2: both conditions return `true`).

- **Root Cause & Impact:**
  `OpenProfile` in `limits.ts` accurately transcribed the `settings.json` contract values, but the preview mount wiring omitted passing `profile.maxRasterPixels` to the reader factory and planned the `ocr` capability indiscriminately across all selected pages without checking `profile.maxOcrPagesPerRun`.

- **Bounded Fix:**
  Strictly bounded to `apps/web/src/features/open/mount.tsx` (and `OpenWorkspace.tsx` if OCR cap notice is surfaced):
  1. Pass `limits: { maxRasterPixels: profile.maxRasterPixels }` into `createPdfJsReader` in `mount.tsx:40-49`.
  2. In `startRun` in `mount.tsx:111-115`, restrict planned `ocr` checks to the first `profile.maxOcrPagesPerRun` pages (or pages carrying explicit region bindings up to that cap).

---

### 3. Region label edit propagation (Review F3)

- **Exact File & Lines:**
  - `apps/web/src/features/open/OpenWorkspace.tsx:333-338`: `onLabelChange` callback on `<RegionEditor>`.
  - `apps/web/src/features/open/OpenWorkspace.tsx:231-238`: `runStart` constructing `contractRegions`.

- **Reproduction Evidence:**
  In `OpenWorkspace.tsx`:
  ```tsx
  onLabelChange={(next) => {
    if (!previewRegion) return;
    const updated = new Map(regions);
    updated.set(previewPage, { ...previewRegion, label: next });
    setRegions(updated);
  }}
  ```
  `previewRegion` is of type `RegionEntry { box: RegionBox; region: ContractRegion; label: string }`.
  Updating `{ ...previewRegion, label: next }` alters the UI state `entry.label`, but leaves `entry.region.label` containing the stale commit-time label (e.g. `"Region 1"`).
  When the user clicks "Start Run", `runStart()` passes `entry.region` directly to `startRun()`:
  ```tsx
  for (const [pageIndex, entry] of regions) {
    if (selection.has(pageIndex)) contractRegions.set(pageIndex, entry.region);
  }
  ```
  Consequently, the emitted `ContractRegion` in the check plan retains the initial label, ignoring any subsequent user edits.
  Verified via `artifacts/followups/pdf-8hn/repro.ts` (Item 3: `labelDiverged === true`).

- **Root Cause & Impact:**
  `onLabelChange` only updated the shallow `label` field of the `RegionEntry` wrapper without updating the nested `region.label` property on the inner `ContractRegion` record.

- **Bounded Fix:**
  Strictly bounded to `apps/web/src/features/open/OpenWorkspace.tsx:333-338`:
  Update `onLabelChange` to synchronize `region.label`:
  ```tsx
  onLabelChange={(next) => {
    if (!previewRegion) return;
    const trimmed = next.trim() || "Region 1";
    const updated = new Map(regions);
    updated.set(previewPage, {
      ...previewRegion,
      label: next,
      region: {
        ...previewRegion.region,
        label: trimmed.slice(0, 200),
      },
    });
    setRegions(updated);
  }}
  ```

---

### 4. Busy-refusal event (Review F5)

- **Exact File & Lines:**
  - `apps/web/src/features/open/controller.ts:144-149`:
    ```ts
    if (this.busy) {
      return {
        ok: false,
        error: makeError("open_failed", OPEN_COPY.malformed, "open:busy"),
      };
    }
    ```
  - `apps/web/src/features/open/OpenWorkspace.tsx:154-160`:
    ```tsx
    const offer = useCallback(
      async (candidate: FileCandidate) => {
        setError(null);
        await controller.offer(candidate);
      },
      [controller],
    );
    ```

- **Reproduction Evidence:**
  When an offer is already in flight (`this.busy === true`) and another candidate is offered:
  - `controller.offer()` returns `{ ok: false, error: ... }` with detail `"open:busy"`.
  - Crucially, `this.emit(...)` is **never called** — no `rejected` event is emitted.
  - In `OpenWorkspace.tsx`, calling `offer()` first calls `setError(null)`, then awaits `controller.offer(candidate)` without checking the returned value.
  - Because `OpenWorkspace.tsx` only updates error state via `controller.subscribe((event) => { if (event.type === "rejected") setError(event.error); })`, the busy error is completely swallowed: any prior error display is cleared, and no error notice is rendered.
  Verified via `artifacts/followups/pdf-8hn/repro.ts` (Item 4: returns `true`).

- **Root Cause & Impact:**
  Every other rejection path in `OpenController.offer()` emits a `rejected` event so that subscriber views stay synchronised with controller state. The early `this.busy` guard returned a failure object directly without emitting a corresponding `rejected` event.

- **Bounded Fix:**
  Strictly bounded to `apps/web/src/features/open/controller.ts:144-149`:
  Emit a `rejected` event before returning:
  ```ts
  if (this.busy) {
    const err = makeError("open_failed", OPEN_COPY.malformed, "open:busy");
    this.emit({
      type: "rejected",
      generation: this.host.currentGeneration,
      kind: err.kind,
      error: err,
    });
    return {
      ok: false,
      error: err,
    };
  }
  ```

---

## Verification & Baseline Integrity

1. **Current Playwright Browser Suite Baseline:**
   ```bash
   $ bun run test:browser -- tests/browser/open.spec.ts
   # 13 collected, 13 passed, 0 failed, 0 skipped (11.7s) — exit 0
   ```
2. **Deterministic Reproduction Suite:**
   ```bash
   $ bun artifacts/followups/pdf-8hn/repro.ts
   # Item 1 reproduced: true
   # Item 2 reproduced: true
   # Item 3 reproduced: true
   # Item 4 reproduced: true
   ```
3. **Workspace Discipline:**
   - No files modified under `apps/web/src/`, `packages/`, `scripts/`, or `planning/`.
   - No writes or mutations performed on the Beads database.
   - Ready to be applied as a normal implementation grant once Gate G1 lands.
