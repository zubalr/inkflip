# T13 independent review — page/text/compare viewer & root app composition

- **Reviewer:** independent reviewer (Devin Local subagent, coordinator-requested); not the writer (worker: `antigravity-t13`)
- **Round-4 candidate:** `6f9d526` evidence on `77d9046` fix (merged into this branch); earlier rounds: `baf3b13`/`9c161e1` (R3), `af685aa`/`ab38b9e` (R2), `5d68193`/`5f644ca` (R1)
- **Checkout:** `original/worktrees/review-devin-t13`
- **Round-4 verdict: APPROVED** — the round-3 P1 is verifiably fixed and survived a 9-case hostile-shape probe (every non-canonical shape either renders honestly or fails closed into `#import-error`; nothing crashes the React tree and nothing fabricates geometry); both round-3 P3s are resolved with real wired effects; suite is 11/11 reproduced in this checkout, T08 open regression 13/13, verify 116/116, build clean, scope clean, receipt honest.

## Round-4 verification (`77d9046` + `6f9d526`)

| Check | Result |
|---|---|
| `bun run test:browser -- tests/browser/viewer.spec.ts` | **11/11 pass (4.5s)** in this worktree — includes the writer's 2 new regression tests (polygon:null import; FileDrop→PDF drop validation) |
| `bun run test:browser -- tests/browser/open.spec.ts` (T08 regression) | **13/13 pass (11.2s)** — App.tsx wiring changes did not break the open suite |
| `bun run verify` | **49 bootstrap + 2 native + 65 coordination OK; self-check 16** — 116/116 claim confirmed |
| `bun run build:web` | clean production build, 51 modules, exit 0 |
| Round-4 adversarial probe spec (9 probes, preserved at `artifacts/tasks/T13/independent-review-probe-r4.spec.ts`) | **9/9 pass** — details below |
| `run.json` binding | binds `77d904684f…` (impl commit), 11/11, exit 0; `receipt.json` `implementation_commit` matches |
| `acceptance_criteria_evidence` | dict keyed by all **5 exact contract criterion strings**; verified against `coordination.py task T13` output |
| Scope `96ab535..6f9d526` | only the five sanctioned files + `features/viewer/` + the 2 previously-sanctioned page CSS modules + `tests/browser/viewer.spec.ts` + T13 artifacts — **no new out-of-scope files**; round-4 delta itself touched only `App.tsx`, `Workspace.tsx`, `viewer.spec.ts`, artifacts |

### Round-3 P1 — polygon:null import gate — FIXED and adversarially verified

Gate is now `occ.geometry.polygon !== null && !Array.isArray(occ.geometry.polygon)` (Workspace.tsx:344) — accepts canonical `null` (page-level) and arrays. Canonical schema confirmed: `Geometry.polygon = anyOf[point-tuple array minItems 3, null]`; `Finding.occurrence_ids` is a required array, so requiring it is consistent. Hostile-shape probe results (each on a fresh workspace mount, asserting `#root` stays alive):

| Injected shape | Observed behavior | Verdict |
|---|---|---|
| `polygon:null` + `precision:"page_only"` (canonical) | mounts; selecting finding → `#page-level-geometry-notice` visible; zero `#highlight-` elements | honest |
| `polygon:null` + claimed `precision:"exact"` + `alignment:"unique"` | mounts; notice still shown (CanvasOverlay checks `polygon === null`, not just precision); no box | honest — the lie cannot fabricate geometry |
| `polygon:"str"` / `{x:1}` / `42` | `#import-error` "occurrence missing required geometry or page_index", `#viewer-stage` absent | fail closed |
| missing `geometry` / `geometry:null` / `geometry:7` | `#import-error`, app alive | fail closed |
| `polygon:[1,2,3]` (number array — passes `Array.isArray`) | mounts; `<polygon points="NaN,NaN …">` → measured boundingBox 0×0 — inert, invisible, no crash | honest output of malformed input |
| `polygon:[null,null,null]` | render `TypeError` → `ViewerErrorBoundary` → `#import-error` "Cannot read properties of null (reading '0')", `#root` children ≥1 | fail closed via boundary |
| `polygon:[]` and `polygon:[[0,0],[1,0]]` (<3 pts) | mounts; SVG filter drops them; zero `#highlight-` elements; no crash | honest (silent — see P3 nit) |
| mixed report: one `polygon:null` + one valid 4-pt polygon + a finding each | both findings listed; exact finding → `#highlight-occ-mixed-box` visible + no notice; page-level finding → notice + no box | honest per-occurrence |

No probe produced a white screen (`#root` empty) and none produced a fabricated visible box from non-geometry data.

### Round-3 P3s — resolution verified

- **`onOpenFile`/`onImportReport` wired — real effects, not stubs.** `App.tsx` tracks `activeDoc`; `onImportReport` persists the imported doc, `onOpenFile` clears it when a validated PDF arrives, new `onCloseDoc` prop clears it on close. Probed live: import report → Home → back to Workspace → doc remounts as "Imported Report · 1 pages · 1 findings" (round-trips through the seam). This is bookkeeping persistence through the composition root — an honest host seam, not a pretend pipeline.
- **FileDrop→PDF path now suite-covered** (spec test 11: drop `%PDF-` file → no viewer mount, `#pdf-received-notice` names the file). Code re-inspected: `handlePdfCandidate` still runs T08's real `resolveProfile()` + `validateCandidate()`, still shows the explicit "inspection pipeline is unavailable" notice, still mounts zero findings — no canned-data regression.

### Round-4 residual observations (all P3-level, non-blocking advisories)

- **Precedence quirk (verified live):** with `activeDoc` set, Home's "Try the example" (`onNavigateWorkspace(true)`, explicit `?example=true` intent) mounts the stale imported report, not `EXAMPLE_DOC` — `initialDoc || (initialWithExample ? EXAMPLE_DOC : null)` gives the persisted doc precedence over explicit navigation intent. Example is still reachable via Load Example after closing. Suggested: `initialWithExample ? EXAMPLE_DOC : (initialDoc ?? null)` or clear `activeDoc` on example navigation.
- **Gate is permissive on polygon contents** (arrays of non-tuples mount and render inert NaN/0×0 polygons; `null` points trip the boundary). Never fabricates and never white-screens, but tightening to tuple validation (`Array.isArray(pt) && pt.length>=2 && pt.every(Number.isFinite)`) would reject earlier and more honestly. T22's strict importer remains the validating gate downstream.
- **`polygon:[]`/`[<3 points]` with `precision:"exact"` renders neither box nor notice** — silent absence of geometry. Not fabrication; arguably should surface the page-level notice whenever no drawable polygon exists.
- **Cosmetic carry-overs:** finding without `page_index` still prints "Page NaN" in the card (gate doesn't check it — canonical requires it); accessible layer labels a `polygon:null`+`precision:"exact"` occurrence "(exact)" while the canvas correctly shows the page-level notice (label/decision mismatch, cosmetic); `ViewerErrorBoundary key={docTitle}` could retain error state if a different doc imports under an identical display name (remount clears it — edge).

### Round-4 verdict rationale

The only round-3 blocker (P1) is fixed in exactly the right place and verified against canonical schema plus nine hostile import shapes — including the specific trap of `polygon:null` under a claimed localized precision, which renders honestly page-level rather than fabricating a box. Both advisories were resolved with real wired effects rather than prop deletion. All criteria remain green on a reproduced 11/11 suite plus a 13/13 T08 regression; run.json binds the implementation commit; scope is unchanged from the sanctioned set. Residual items are P3 polish advisories for integration, none blocking. **APPROVED.**

---

## Round 3 (superseded — kept for the record)

- **Reviewer:** independent reviewer (Devin Local subagent, coordinator-requested); not the writer (worker: `antigravity-t13`)
- **Round-3 candidate:** `baf3b13` evidence on `9c161e1` fix (merged into this branch); earlier rounds: `af685aa`/`ab38b9e` (R2), `5d68193`/`5f644ca` (R1)
- **Checkout:** `original/worktrees/review-devin-t13`
- **Round-3 verdict: changes-required** — every round-2 finding is verifiably fixed (PDF path is now honest + genuinely validated, Home/workspace overflow is 0px at 360px, malformed JSON fails closed under a real error boundary, 9/9 suite green), but the new import shape-gate added this round **rejects canonical reports containing page-level (`polygon: null`) occurrences** — a self-inconsistent overreach that must be relaxed before acceptance.

## Round-3 verification (`9c161e1` + `baf3b13`)

| Check | Result |
|---|---|
| `bun run test:browser -- tests/browser/viewer.spec.ts` | **9/9 pass (4.3s)** — includes new P1/P2 regression tests the writer added |
| `run.json` binding | binds `9c161e1bf3…`, 9/9, exit 0; `receipt.json` `implementation_commit` matches |
| `acceptance_criteria_evidence` | all 5 keys resolve via `criterion_evidence()` |
| Scope `96ab535..baf3b13` | only the five sanctioned files + viewer dir + 2 sanctioned page CSS modules + artifacts — clean |

### Round-2 findings — verification results

- **P1 fabricated PDF path — FIXED.** `handlePdfCandidate` now runs T08's real `resolveProfile()` + `validateCandidate()` (size gate → ≤1 KiB `%PDF-` header sniff, no canned doc on any path). Probed: valid-header `my-tax-return.pdf` → `#pdf-received-notice` *"PDF received: my-tax-return.pdf. In-browser inspection pipeline is unavailable in this viewer build. Open an exported report (.inkflip.json) to inspect findings."* — `stage=0`, zero findings, header shows "No document loaded". 25 MiB `MZ`-binary named `x.pdf` → `#import-error` *"This file exceeds the 20 MiB local browser limit"*, no mount. No fabrication anywhere.
- **P2 Home 154px overflow — FIXED.** `.navLinks` wraps at ≤767px, links hide ≤480px, `.page` gets `overflow-x:hidden`, `.actionRow` stacks ≤390px. Measured `scrollWidth − clientWidth = 0` on Home at 360px **and** on Workspace with an imported doc mounted.
- **P2 degenerate-JSON crash — FIXED.** `handleImportReportText` now shape-gates (object, nonempty `pages`, per-page `index`+`canonical_size_pt`, per-occurrence `page_index`+`geometry`, per-finding `id`+`occurrence_ids`) and `ViewerErrorBoundary` wraps `ViewerStage` with `#import-error` fallback. Probed 6 malformed inputs (`{"pages":[],"findings":[]}`, occurrence without `geometry`, page without `canonical_size_pt`, finding without `id`, `pages:"x"`, primitive `42`) — **all fail closed**: app stays mounted (`#root` children=1), `stage=0`, `#import-error` visible. No white screen.
- **P3s — resolved/accepted.** `document.display_name` honored (fixture has `null` → filename fallback, correct); `onOpenFile`/`onImportReport` remain unwired props (harmless API seam, noted); FileDrop "Drop one PDF" copy is T08-owned and the notice now discloses the JSON path.

### Round-3 findings

- **P1 — Import gate rejects canonical `polygon: null` occurrences.** `Workspace.tsx` occurrence check requires `Array.isArray(occ.geometry.polygon)`; canonical schema says `Geometry.polygon` is `anyOf: [point-array, null]` — `null` is the valid encoding for `page_only`/`unknown` precision (the app's own `EXAMPLE_DOC` ships `occ-p1-pagelevel` with `polygon: null`, and criterion 4 tests exactly this). Probe: a canonical report containing a page-level occurrence → rejected with *"occurrence missing required geometry or page_index"*. Consequence: any T16-exported report containing a page-level finding **cannot be reopened** — breaks Journey D and is self-inconsistent (the example doc itself wouldn't round-trip). Fix: accept `polygon === null` (page-level) or validate point-tuples properly, e.g. `polygon === null || (Array.isArray(polygon) && polygon.length >= 3 && polygon.every(pt => Array.isArray(pt) && pt.length >= 2))`.
- **P3 — FileDrop→PDF path untested for non-PDF drops.** `handleFileCandidate` routes any non-`.json` drop to `handlePdfCandidate` — correct in code (validation catches it) but only the input path is covered by the suite. Advisory.
- **P3 — `onOpenFile`/`onImportReport` props still unwired by `App.tsx`.** Dead API surface; either wire or drop before integration. Advisory.

### Round-3 verdict rationale

All round-2 blockers are genuinely fixed and verified adversarially; the suite is 9/9 with real regression coverage. One defect remains: the new import gate rejects a canonical occurrence shape — a functional break in the report-import entry the last two rounds were about, with a one-condition fix. Returning to worker for that; expect a fast close next round. Probe spec preserved at `artifacts/tasks/T13/independent-review-probe-r3.spec.ts` (run under `tests/browser/` during review).

---

## Round-2 (superseded — kept for the record)

- **Round-2 candidate:** `af685aa` evidence on `ab38b9e` fix; round-1 candidate was `5d68193`
- **Round-2 verdict: changes-required** — the report-import entry is now real and most round-1 findings are fixed, but the same fix introduced a **fabricated PDF-open path** (canned findings shown under the user's filename), the overflow fix did not cover the Home page, and malformed import JSON crashes the whole app.

| Check | Result |
|---|---|
| `bun run test:browser -- tests/browser/viewer.spec.ts` | **6/6 pass (3.1s)** — new "document open and report import entry integration" test included |
| `run.json` binding | binds `ab38b9e5…` (the fix commit), 6/6, exit 0 |
| `acceptance_criteria_evidence` | all 5 keys still resolve via `criterion_evidence()` |
| Scope `96ab535..af685aa` | only the five sanctioned files + viewer dir + 2 sanctioned page CSS modules + artifacts — **no new out-of-scope files** |
| Report import (P1-F1) | **REAL**: canonical `native-evidence.inkflip.json` mounts `ViewerStage` with its own data ("native-evidence.inkflip.json · 1 pages · 1 findings") via `#input-import-report` **and** via real `FileDrop` drag-drop; invalid JSON → clean `#import-error` `role=alert`, no viewer mounted; "Open saved report" entries on Home hero, workspace header and empty state |
| Toolbar wrap (P2-F2) | `.toolbarGroup` now `flex-wrap:wrap` + `max-width:100%`/media query; criterion-3 spec now asserts `scrollWidth ≤ clientWidth` at 360px and passes in compare mode |
| P3-F4/F5 | keyboard assertions (n/p/Enter) added to criterion-1 test; default-page fabrication → `clampedPageIndex`; honest "0 of N" counter; `findingCard`/`findingCardSelected` split fixed; all `occurrence_ids` of a finding now co-highlight |

### Round-2 findings

- **P1 — PDF open path fabricates analysis (P1-F1 partially fixed, regression).** Dropping or choosing any PDF mounts `EXAMPLE_DOC` under the user's real filename: probe dropped `my-tax-return.pdf` → header reads `my-tax-return.pdf · 2 pages · 3 findings` listing the canned invoice findings ("Amount reads differently #1/#2", "Font metadata…"). The file's bytes are never read (`handlePdfFileChange`/`handleFileCandidate` only call `setDocTitle(file.name)` + `setDoc(EXAMPLE_DOC clone)`); T08's `validate.ts` size/MIME/`%PDF-`/encrypted checks are bypassed entirely, so a 50 MB `.exe` named `x.pdf` also "opens". Meanwhile `FileDrop` copy claims "Your file is processed in this browser." For an evidence inspector this is a fabricated-result presentation — worse than the round-1 dead affordance. Fix: either wire T08's `OpenController` genuinely, show an explicit "received — inspection pipeline unavailable" state without canned findings, or remove the PDF affordance (keep `FileDrop` for JSON import only and fix its copy).
- **P2 — Home page still overflows 154px at 360px (P2-F2 incomplete).** `.navLinks` (nav cluster, 307px, right=514) can't wrap/shrink; spec calls for a compact header/menu below 390px. Workspace is fixed; the landing is not.
- **P2 — Import robustness: degenerate JSON crashes the entire app.** `{"pages":[],"findings":[]}` passes the shallow `Array.isArray` gate → `ViewerStage` hits `currentPage === undefined` → `TypeError: …reading 'limitations'` → React unmounts the whole tree (`#root` children = 0, white screen, no error boundary). Same for occurrences missing `geometry` (`occ.geometry.polygon` throws) or finding objects missing fields ("Page NaN" misrenders). The import gate must validate required shapes (nonempty pages, per-occurrence geometry object) or wrap the mount in an error boundary and fail closed into `#import-error`.
- **P3 — Import is duck-typed, not canonical-schema validated.** Any JSON with `pages`+`findings` arrays mounts. Acceptable as an interim entry since T22's strict importer isn't in this base and will mount through the lease — but it must not crash or misrender (see P2 above). `docTitle` also ignores `document.display_name` (fixture shows filename fallback — minor).
- **P3 — FileDrop copy vs behavior.** Drop zone says "Drop one PDF here" but JSON is also accepted (good behavior, stale copy); `onOpenFile`/`onImportReport` props are defined but `App.tsx` passes neither — dead API surface for now.

### Round-2 verdict rationale

Criteria remain green (6/6 reproduced, including the new import-mount test), the report-import **entry** is real, scope is clean, and run.json binds the fix commit. Blocked on: the fabricated PDF path (P1), incomplete overflow fix on Home (P2), and the import crash (P2). Probe spec preserved at `artifacts/tasks/T13/independent-review-probe-r2.spec.ts` (run under `tests/browser/` during review).

---

## Round 1 (superseded — kept for the record)

- **Candidate:** `5d681931cc3d3653dbb65d0515a1657ddc2e3034` (impl `5f644ca`, evidence HEAD) on `review/devin/t13`
- **Verdict: changes-required** — all five acceptance criteria independently reproduced and probed (the geometry/sync/a11y machinery is genuinely sound), but the composition half of the contract purpose is unmet: there is **no report-import entry and no document-open path at all**, plus a real narrow-screen layout violation and a scope deviation.

## Reproduced commands (this worktree, real counts)

| Command | Worker claim | Reproduced |
|---|---|---|
| `bun run test:browser -- tests/browser/viewer.spec.ts` | 5/5 in 3.0s | **5 passed, 0 fail/skip (4.0s), exit 0** |
| `bun run test:browser -- tests/browser/open.spec.ts` (T08 regression) | — | **13/13 pass** — App.tsx rewrite did not break the open suite |
| `bun run verify` | 116/116 | **49 bootstrap + 2 native + 65 coordination OK; self-check 16** — claim confirmed |
| `bun x oxlint <owned files>` | 0/0 | 0 warnings, 0 errors, 96 rules |
| `bun x oxfmt --check <owned files>` | clean | all matched files correctly formatted |
| CSS token audit (`#[0-9a-f]{3,8}` / `rgba?(`) | 0 literals | **0 raw color literals** in `features/viewer/` + `pages/` |
| `python3 -c criterion_evidence(T13, receipt)` | — | **all 5 keys resolve**, every evidence path task-local + nonempty |

The browser spec mounts the **real** app: an ephemeral Vite dev server serving `apps/web` → real `App.tsx` → `Workspace` → `ViewerStage`/`CanvasOverlay`/`ComparePanes`/`AccessibleTextLayer`. No stubs, no test-only knobs found (`?example=true` is a genuine product route for the prepared example per Journey A, also reachable from the Home "Try the example" button; `data-*` attributes are descriptive state, not behavioral switches).

`run.json` binds `evaluated_commit: 5f644caa…` (the impl commit), 1 command, exit 0, 5/5. `receipt.json` `acceptance_criteria_evidence` resolves all five contract criteria through `acceptance_receipts.criterion_evidence()` (verified by executing the function, not by eyeball).

## Criterion-by-criterion audit (worker test + my adversarial probes)

Probe spec preserved at `artifacts/tasks/T13/independent-review-probe.spec.ts` (run under `tests/browser/` during review; 5 probes).

**1. Click/keyboard finding selects correct duplicate/page after zoom/rotation — PASS.**
Selection binds `finding.occurrence_ids[0]` → `#highlight-<occ-id>`; `normalized_text` appears **only** in fixture data and is never searched (grep-verified). `CanvasOverlay.mapPoint` applies the canonical rotation matrix then zoom scale. Beyond the suite's 150%/90° case I probed 200%/270°: `occ-p0-dup2` mapped to `700,1024 700,864 740,864 740,1024` — exactly `(cx,cy)→(cy,w−cx)·2` for `w=612` — and `occ-p0-dup1` to a disjoint box (`300,1024…`); selecting each finding lit only its own occurrence. Keyboard verified working: stage `N`/`P` cycles findings, `Enter`/`Space` on focused `role=option` finding items, and the accessible layer's Select buttons — all select and page-navigate correctly (probe P2). The committed spec only exercises click despite its title (F4).

**2. Two views sync without scroll loop — PASS.**
`ComparePanes.tsx:39-80` uses an `isSyncingRef` leader flag reset via `requestAnimationFrame` — a real loop-breaker, plus proportional (ratio) sync for unequal scroll ranges. Probe: `left.scrollTop=400` → 10 samples × 70 ms showed `[400,400]` stable on both panes, zero oscillation; `right.scrollTop=40` → left converged to 40 and stayed; no A→B→A bounce. One theoretical edge noted as F6.

**3. Narrow screen stacks instead of squeezing — PASS, with a related defect (F2).**
Real CSS: `@media (max-width: 767px)` in `ComparePanes.module.css` flips the grid to `flex-direction: column`; `workspaceGrid` stacks at ≤1099px. At 360px both panes are full available width (294px each, `y` 260→863 stacked), both reachable, evidence slip stacked below — not squeezed. **However** `documentElement.scrollWidth − clientWidth = 153px`: the `.toolbarGroup` zoom cluster (`ViewerStage.module.css:24`) is ~480px min-content and cannot wrap/shrink, so the outer page scrolls horizontally — violating UX spec "Stage toolbar wraps to two rows… outer page never scrolls horizontally". The criterion's pane-stacking assertion passes; the defect is adjacent and real (F2).

**4. Unknown geometry stays page-level — PASS.**
`precision ∈ {page_only, unknown}` or `polygon == null` renders `#page-level-geometry-notice` (role=status, real copy); the SVG filters out null/<3-point polygons — zero fabricated boxes. Probed: keyboard-selecting the page-level finding navigates to page index 1, notice survives rotate+zoom, `#highlight-occ-p1-pagelevel` never exists, no crash (I02 honored).

**5. Canvas has equivalent reachable content and limits — PASS.**
`#accessible-text-equivalent` is a labelled `role=region` listing every occurrence per reader with ordinals, precision and per-occurrence Select buttons (keyboard-reachable), plus reader **and** page limitations ("OCR verification was not run on page 0" present). Canvas has `role="img"` + `aria-label`. Axe audit over wcag2a/2aa/21a/21aa/22aa → 0 serious/critical (I14 honored).

## Findings

- **P1-F1 — No report-import entry / no document-open path in the composition (contract purpose unmet).**
  Purpose: *"Own root application composition and public Home/Workspace routes. Integrate the hero and report-import entry with the viewer."* The hero is integrated, but **nothing in the shell can open a document or a saved report**: `Workspace.tsx` `doc` state can only become the hardcoded `EXAMPLE_DOC` or `null` — no `FileDrop` mount (T08's `features/open` is in this base and unused), no file input, no drop handler, no "Open saved report" affordance, no prop/route for an imported report. Home's "Open locally"/"Open Workspace" both dead-end at an empty workspace whose copy claims *"Drop a PDF file here"* — a false affordance. T13 is the **only** owner of `App.tsx`/`pages/` (checked all contracts): T16's export and T22's `features/import` have no mount point, so unless this composition gains the entry, the import machinery stays unreachable. Fix expected: wire a real open/import entry (mount `features/open` `FileDrop`, an "Open saved report" action, or a documented host seam accepting a `ViewerDoc`) and remove or make true the drop-zone copy.
- **P2-F2 — Horizontal page overflow at ≤~480px viewports.** `.toolbarGroup` (ViewerStage.module.css:24-28) has no `flex-wrap`/shrink; the mode-tabs+zoom cluster (~480px) overflows the 360px viewport → 153px horizontal document scroll. Violates the narrow-screen spec even though the pane-stacking criterion itself passes. Fix: allow the toolbar group to wrap/shrink below the breakpoint.
- **P2-F3 — Scope deviation: 2 files outside `allowed_scope`.** `apps/web/src/pages/Home.module.css` and `apps/web/src/pages/Workspace.module.css` are not covered by the five named scope entries (only `Home.tsx`/`Workspace.tsx` under `pages/`). They are adjunct CSS Modules required by the owned files, tokens-clean, conflict-free — same adjudication class as T16's sanctioned `package.json`/`tsconfig` additions — but the deviation must be recorded/sanctioned, not silent.
- **P3-F4 — Spec title overclaims keyboard coverage.** Criterion-1 test says "click/keyboard" but only clicks. Keyboard paths do work (probed); add a keyboard assertion for honest coverage.
- **P3-F5 — Minor implementation nits.** `ViewerStage.tsx:41-52` fabricates a default 612×792 `Page` when `pageIndex` is out of range (masks inconsistent docs — mildly in tension with I02 spirit); `:319` counter renders "1 of N" when nothing is selected (`+1 || 1`); `:345` applies `findingCardSelected` class to every finding card; `handleSelectFinding` highlights only `occurrence_ids[0]` so counterpart occurrences of one finding never co-highlight.
- **P3-F6 — Canvas/scroll edge notes.** The `<canvas>` element is never painted (no draw code anywhere — the "rendered visual page" is a blank backing in all modes; acceptable scaffold given `ViewerDoc` carries no pixels, but the `aria-label` overpromises); in compare mode the right pane gets `renderCanvas={false}` so highlights float over blank paper; the sync flag drops a second scroll event arriving in the same frame (converges in practice — verified).

## Evidence & bookkeeping checks

- run.json binds impl commit `5f644caa…` ✓; commands.log transcript consistent with run.json; `verify-run T13` logic satisfied (receipt criteria resolve, paths task-local/nonempty).
- Worker self-review was committed at `artifacts/tasks/T13/review.md` — that path is the independent-review artifact per T08/T16 precedent and `acceptance_receipts.record` overwrites it with the committed review; this file supersedes it.
- My test runs regenerated the five screenshots; bytes were identical except `unknown-geometry-pagelevel.png`, which I restored to the committed version (`git status` clean except this review + probe spec).
- No edits outside the five scope files in `5f644ca` **other than** the two page CSS modules (F3); `planning/` untouched (verify snapshot test passes); no lockfile/schema/golden changes.

## Recommendation

Return to worker (or coordinator follow-up) for: **F1** (add the report-import/document-open entry to the owned composition and fix the dead affordance copy), **F2** (toolbar wrap below ~480px), **F3** (sanction or relocate the two CSS modules). F4–F6 are advisory. The five criteria need no rework — the viewer internals are solid.


---

## Delta review — 2026-09-13, evaluated `412fb9b2`

- **Reviewer:** devin-coordinator (acceptance refresh; not the implementing worker for this delta's shared changes)
- **Scope delta:** Owned scope delta (large): `App.tsx`/`Workspace.tsx` rewired by pdf-3g8 —
the dead-end "inspection pipeline is unavailable" surface is replaced by the
real session (open → run → report → viewer → export → reopen). This resolves
the original review's **F1** (missing report-import/document-open entry).
`viewer.spec.ts` updated to the real surface: invalid-PDF assertions now check
`#import-error`; the polygon:null import test uses the sealed canonical example
(the strict gate verifies the report digest, so a hand-patched report cannot
pass — page-level rendering stays covered by criterion 4).
- **Fresh run:** Re-ran all registered commands at `412fb9b2`: **11/11 green**, zero failures.
- **Verdict:** prior review stands; delta introduces no acceptance-relevant regression.
