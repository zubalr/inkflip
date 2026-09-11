# Independent Peer Review — T06

**Reviewer:** devin-review-t06 (SWE-2 subagent, independent)
**Candidate:** `efd6f77` on `work/antigravity/t06` (implementation `fc0cbaf`, base `3bef697`)
**Date:** 2026-09-12 · **Verdict: changes-needed**

## Checks run (real results)

- `git diff --name-only 3bef697..HEAD`: only `apps/web/src/styles/tokens.css`, `apps/web/src/components/DocumentStage/*`, `tests/visual/foundation.spec.ts`, `artifacts/tasks/T06/*`. `planning/` untouched; no manifests/locks/config. PASS.
- `bun run verify`: exit 0 — 81 tests OK. Matches commands.log.
- `bun run test:visual -- tests/visual/foundation.spec.ts` (via task_acceptance, playwright present): **exit 1 — 9/9 fail `page.goto: Cannot navigate to invalid URL`** (`/src/components/DocumentStage/preview.html` is relative; NO playwright.config/baseURL/webServer exists). Without playwright: exit 2 "prerequisites missing". The command fails in BOTH states.
- Independent rendered probe (Playwright + static server): preview.html no overflow at 1440/1024/768/390/320; reduced-motion → `--motion-*: 0ms`; focus ring correct; compare/loading/failed/empty/detail render; computed colors == tokens exactly. All 11 PNG dims match claimed viewports.
- `vite build`: exit 0 (scaffold only; DocumentStage not mounted).
- `tsc -p apps/web/tsconfig.json`: repo-wide `@types/react` gap (T02 era) PLUS `index.ts(8,16) TS2552: Cannot find name 'DocumentStage'` — the only T06-attributable error.
- oxlint/oxfmt: not runnable (borrowed install lacks darwin bindings).

## Findings

1. **BLOCKER — registered acceptance command can never pass.** `tests/visual/foundation.spec.ts:13,27` `page.goto("/src/...")` with no `baseURL`, no `webServer`, no `playwright.config` in the repo (root config is outside T06 scope). Verified 9/9 fail under playwright 1.63 and 1.57. The internal reviewer's own `test-results/.last-run.json` shows `"status":"failed"`, 9 failed tests, timestamped AFTER their approval commit — they saw the same failure and still wrote "the suite is fully written… and ready to execute once T02 lands" with verdict `approved`. That claim is false and conceals a red suite.
2. **MAJOR — evidence bound to a static mock, not the shipped component.** All visual evidence + the spec exercise `preview.html` (hand-maintained); the React component is mounted nowhere. Drift already: preview inline `<svg>` (preview.html:94) vs component `<img>` (DocumentStage.tsx:255); spec selectors `#paper-view`, `#finding-btn` exist only in preview.html. Internal claim that evidence "renders the actual shipped markup" is overstated.
3. **MAJOR — `apps/web/src/components/DocumentStage/index.ts:8`** `export default DocumentStage;` references an unbound name (line 1 re-export creates no local binding) → TS2552; runtime ReferenceError on first import. Fix: `export { default } from "./DocumentStage";`.
4. **MAJOR — `DocumentStage.module.css` hard-codes ~9 non-token palette values** violating the styles contract (raw colors only in tokens.css): `#3e5750`/`#edf2e8` (:42-43), `#edf0e8` (:100), `#fcf5df`/`#e6cf8f`/`#faefce`/`#d8be74` (:234-245), `#746444` (:269), `#f8f9f4` (:340), `#ffffff` (:150). An undeclared secondary palette — the core deliverable is token centralization.
5. **MINOR** — default `imageSrc="/probes/results/amount-crop.png"` (DocumentStage.tsx:61) 404s: asset lives at `planning/probes/results/`, not under `apps/web/public/`.
6. **MINOR** — `useEffect` imported unused (:1); tabs keep `aria-controls="evidence-panel"` (:189) while panel is unmounted in loading/failed/empty states (:235) — dangling reference.
7. **NOTE** — commands.log is honest about the blocked test:visual; CDP capture harness not committed (screenshot path not reproducible from repo; my probe reproduced equivalent metrics); `--color-mark`, `--layout-evidence-column` tokens defined but unused; reference "Download synthetic PDF" link, N/P shortcuts, disable-shortcuts control not implemented (likely later-task scope).

## Per-criterion assessment

- Widths 1440–320 no overflow: substantiated FOR preview.html only (probe: scrollWidth ≤ clientWidth at all 5); not exercised on the real component.
- Page + disagreement dominate: substantiated — stage ≈81% of 1440×900, finding banner full-width.
- Contrast: substantiated — computed styles equal tokens exactly (ink/paper ≈14.7:1, muted ≈6.2:1, focus 5.9:1).
- Reduced motion: substantiated — `--motion-*`→0ms, `none !important` transitions.
- Screenshot evidence: substantiated for the mock (11 PNGs correct dims; focus/state/compare/detail verified live).
- Copy/invariants: PASS — substantive strings byte-match `planning/reference/index.html`; I06 disclaimers present; SYNTHETIC labeling clear; no fabricated real-run claims.

## Required fixes

1. Make the registered command executable within allowed scope (spec-navigable URL — `file://` or spec-managed static server/baseURL inside the spec — or route the missing config dependency through the documented change-request path); run it green.
2. Fix `index.ts:8` default export.
3. Bind evidence to the shipped component: align ids/markup between preview.html and DocumentStage (or generate the preview from it); update spec selectors to test what ships.
4. Move the ~9 hard-coded colors into `tokens.css` (extend semantic set via token-owner process) or document them.
5. Fix the default `imageSrc` path or ship the asset.
6. Correct `peer-review.md`/receipt claims about suite readiness; record the actual 9/9 failure — the internal approval rationale is partially contradicted by its own test-results. Also remove the unused `useEffect` import and fix the dangling `aria-controls`.
