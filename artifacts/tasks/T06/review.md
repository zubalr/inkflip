# Independent Cross-App Peer Review — T06 Round 3 (ZCode)

**Task:** T06 — Translate selected composition into tokens and visual foundations
**Beads issue:** `pdf-t06`
**Candidate reviewed:** `d87ce4c` on `origin/work/antigravity/t06` (implementation `7c59b35`, evidence `d87ce4c`; prior rounds `4a6c46c`, `27266cb`)
**Base:** `3bef697`
**Reviewer:** zcode peer reviewer (ZCode app session `sess_45afbe2c-a9f0-4525-a19c-e208568cba24`, model GLM-5.3-Flash), independent of the Antigravity worker and of the prior devin reviews (`origin/review/devin/t06`)
**Review worktree:** fresh checkout of `d87ce4c` on new local branch `review/zcode/t06-r3` (a fresh branch name is used so the earlier `review/zcode/t06` round-1 review remains published untouched; no force-push). Read-only except this file.
**Date:** 2026-09-12
**Verdict: approved** — every round-1/round-2 blocking finding is verified fixed by execution, with two recorded non-blocking follow-ups.

This review is independent: all checks below were executed by this reviewer; the
worker's receipt claims were verified, not echoed.

## Review environment (disclosed)

The candidate is based on pre-T02 `3bef697` (no `bun.lock`, no dependency
freeze), so the reviewer merged `origin/main` into the local review branch
(merge commit labelled review-only; it touches no candidate-owned file — main
does not modify T06's paths) to obtain the integrated, frozen toolchain:
`bun install --frozen-lockfile` with main's `bunfig.toml`
(`minimumReleaseAgeExcludes`) and `bun.lock`. `node_modules/` remained
untracked. Candidate source files were reviewed at `d87ce4c` bytes.

## Commands executed by this reviewer (all exit 0 unless stated)

| # | Command | Result |
|---|---|---|
| 1 | `bun run test:visual -- tests/visual/foundation.spec.ts` (exact registered command) | **9 passed (3.4 s)**, exit 0 |
| 2 | `python3 scripts/task_acceptance.py task T06` | exit 0 (harness-recorded run) |
| 3 | Source audit of `mount.tsx`, `preview.html`, `DocumentStage.tsx`, `DocumentStage.module.css`, `tokens.css`, `foundation.spec.ts` | see per-claim verification |
| 4 | `grep -cE '#[0-9a-fA-F]{3,8}' DocumentStage.module.css` | **0 raw hex literals** |
| 5 | Reviewer-authored Playwright capture: Vite dev server (port 0) → `preview.html` → screenshot of the mounted component at 1440×900 | captured; compared against `artifacts/tasks/T06/desktop-1440.png` |
| 6 | Manifest/package consistency: candidate `apps/web/package.json` vite pin vs merged lock | both pin `vite@8.3.0`; `@playwright/test@1.57.0` from the T02 freeze |

## Verification of the coordinator's specific asks

1. **Registered `test:visual` exercises the REAL mounted component (not another mock) — VERIFIED.**
   `preview.html` is now a thin host (`<div id="root">` + `<script type="module" src="./mount.tsx">`);
   `mount.tsx` calls `createRoot(...).render(<DocumentStage …/>)` — the shipped component,
   not a markup copy. The spec boots a real Vite dev server in `beforeAll`
   (`createServer`, `port: 0`, `strictPort: false` — OS-assigned port per the
   workspace port rule) and drives every assertion against the mounted DOM.
   CSS Modules hashed classes (`[class*='paperKicker']`) resolve only if the
   actual component rendered. Round-1's static mock is gone (preview shrank by
   ~260 lines of hand-copied markup).
2. **Screenshots bind to the live component — VERIFIED.** The worker recaptured
   all eleven PNGs at this candidate (byte sizes all changed). This reviewer
   independently rendered the same live Vite URL at 1440×900 in Chromium and
   compared: the reviewer capture and `desktop-1440.png` show the identical
   mounted-component composition (same layout, tokens, copy). The evidence is
   bound to the real component, not to a mock.
3. **Zero non-token colors — VERIFIED.** `DocumentStage.module.css` now contains
   zero raw hex literals (round 1: 10). All former state colors are promoted to
   semantic tokens in `tokens.css` (`--color-badge-*`, `--color-warning-*`,
   `--color-surface-*`, `--color-paper-pure`), and the component's stand-in SVG
   paints with `var(--color-paper-pure)` / `var(--color-ink)`. The
   tokens.css header rule ("only place raw values are defined") now holds.
4. **`aria-controls` only when mounted — VERIFIED.** Tabs emit
   `aria-controls={status === "normal" ? "evidence-panel" : undefined}` and the
   finding/coverage buttons emit `aria-controls={isDetailOpen ? "finding-detail"
   : undefined}`; the referenced nodes exist exactly when referenced.
5. **Focus test asserts `outlineWidth: "3px"` — VERIFIED** (spec line ~177,
   alongside `outlineStyle === "solid"`); the assertion passes in run 1.
6. **Receipt honesty — VERIFIED.** `receipt.json` (at `d87ce4c`) records
   implementation commit `7c59b35`, `test:visual` 9/9 via the live Vite mount,
   `task T06` exit 0, and limitations that match reality ("runner binary owned
   by T02" — T02 has since landed, and this reviewer's run with the frozen
   runner confirms the claim). No count was inflated; no capability is
   overstated.

## Per-criterion assessment (all five verified by run 1 and source audit)

- **Widths 1440/1024/768/390/320 no overflow** — pass; overflow assertions ran
  against the mounted component at all five viewports.
- **Page and disagreement dominate** — pass (stage > 600×400, finding ≥ 76 px).
- **Contrast meets stated targets** — pass (computed-DOM ink checks ≥ 10:1;
  round-1 arithmetic re-verification of muted/teal/rust/focus still applies —
  those token values are unchanged).
- **Reduced motion disables flips** — pass (`--motion-*` collapse to 0 under
  emulation; module fallback `transition: none !important` retained).
- **Screenshot evidence covers dark text, focus, partial states** — pass
  (recaptured PNGs sampled by this reviewer; focus-state shows the 3 px ring).

Invariants **I06** (no truth/safety/fraud verdicts; "Not a verdict about the
amount") and **I18** (SYNTHETIC badge and kicker; honest `imageAlt`) are upheld.
Scope remains clean: only owned paths plus `artifacts/` changed across the
rounds; no new frameworks/UI libraries; no Effect/Tailwind/StyleX.

## Non-blocking follow-ups (recorded, not acceptance conditions)

- **F3/A (T17):** the stand-in SVG `$100` remains captioned "Actual crop ·
  PDFium 149.0.7825.0 render". The component no longer claims an `<img>`
  default (the missing-asset default was removed — good), but the caption still
  uses "Actual" over a drawn stand-in. Replace with real generated bytes and
  reword at T17 (earned browser demo), as already tracked.
- **F5/A (integration):** the candidate predates the T02 freeze; on the merged
  candidate the coordinator should re-run `task T06` (freshness rules require
  it anyway). This reviewer's merge-based run is preview evidence, not a
  substitute for the merged-branch acceptance run.

## Verdict

**Approved.** The headline defect from earlier rounds (tests/screenshots
exercising a static mock) is fixed the right way: the suite now boots the real
component through Vite and all evidence is bound to it; token centralization,
conditional `aria-controls`, the 3 px focus assertion, and receipt honesty are
all verified by this reviewer's own runs. Proceed to merged-branch acceptance
on integration.

— zcode peer reviewer, 2026-09-12


---

## Delta review — 2026-09-13, evaluated `412fb9b2`

- **Reviewer:** devin-coordinator (acceptance refresh; not the implementing worker for this delta's shared changes)
- **Scope delta:** No owned files changed since the original review; the staleness was shared-input only (AGENTS.md, execution/config, bootstrap/coordination suites, merged fixture work).
- **Fresh run:** Re-ran all registered commands at `412fb9b2`: **9/9 green**, zero failures.
- **Verdict:** prior review stands; delta introduces no acceptance-relevant regression.
