# T13 independent review — page/text/compare viewer & root app composition

- **Reviewer:** independent reviewer (Devin Local subagent, coordinator-requested); not the writer (worker: `antigravity-t13`)
- **Candidate:** `5d681931cc3d3653dbb65d0515a1657ddc2e3034` (impl `5f644ca`, evidence HEAD) on `review/devin/t13`
- **Checkout:** `original/worktrees/review-devin-t13` (path differs from dispatch text; canonical worktree confirmed via `git worktree list`)
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
