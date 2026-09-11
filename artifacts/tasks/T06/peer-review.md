# Independent Cross-App Peer Review — T06 (ZCode)

**Task:** T06 — Translate selected composition into tokens and visual foundations
**Beads issue:** `pdf-t06`
**Candidate reviewed:** `320db1c` on `origin/work/antigravity/t06` (delivery incl. evidence commits `fc0cbaf`, `653f1e2`, `320db1c`, `efd6f77`; implementation commit under review `fc0cbaf`)
**Base:** `3bef697`
**Reviewer:** zcode peer reviewer (ZCode app session `sess_45afbe2c-a9f0-4525-a19c-e208568cba24`, model GLM-5.3-Flash), independent of the Antigravity worker and of the internal review by `antigravity-peer-reviewer`
**Review worktree:** fresh worktree at candidate `320db1c`, branch `review/zcode/t06` (read-only except this file; the Antigravity internal review previously at this path is preserved on `work/antigravity/t06` and at `efd6f77`)
**Date:** 2026-09-12
**Verdict: changes-needed** (one blocking harness finding; the component and evidence work is otherwise strong and verified)

This review is independent: every check below was executed by this reviewer in a
fresh worktree; the internal review's conclusions were read only after the
findings below were established, and nothing is echoed from it.

## Commands actually executed by this reviewer

Environment: macOS arm64 worktree at `320db1c`. T02 is still in progress, so the
repo has no lockfile and no `node_modules/.bin/playwright` anywhere; the
reviewer supplied a throwaway runner (`@playwright/test@1.63.0` under
`/tmp/pw-runner`, symlinked as the gitignored `node_modules/` in the review
worktree, removed after review) plus, where stated, an external-only
Playwright config. No repository file was modified for these runs.

| # | Command | Exit | Result |
|---|---|---|---|
| 1 | `bun run verify` | 0 | 81 tests pass (bootstrap 49, native-bootstrap 2, coordination 30); self-check reports 16 commands |
| 2 | `bun x --no-install playwright test tests/visual/foundation.spec.ts` (registry argv shape) | 1 | **9 failed / 0 passed** — `page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL` on every test |
| 3 | Same + reviewer config with `baseURL: file://…/apps/web` | 1 | **9 failed** — `net::ERR_FILE_NOT_FOUND at file:///src/components/...` (file scheme cannot join root-relative paths) |
| 4 | Same + reviewer config with `baseURL: http://127.0.0.1:8931` (static server on `apps/web`) | 0 | **9 passed (930 ms)** — all five overflow widths, dominance, contrast, reduced-motion, focus assertions pass |
| 5 | Manual audit of `DocumentStage.module.css` | — | 10 raw hex color literals; 41 declaration lines with raw px values (see F2) |
| 6 | PNG evidence inspection (desktop-1440, mobile-320, state-failed, focus-state) | — | Authentic renders of the shipped preview; states, focus ring, and narrow-width layout match the claims |
| 7 | Contrast arithmetic recomputation from `tokens.css` values | — | ink/paper ≈ 14.7:1, muted/paper ≈ 6.1:1, teal/paper ≈ 6.2:1, rust/paper ≈ 6.7:1, focus non-text ≈ 5.9:1 — all meet the receipt's stated targets |

Run 2 was executed with the exact argv the registry will use once T02 lands
(`bun x --no-install playwright test`, plus the contract's file filter). Runs 3
and 4 isolate the failure cause and prove the assertions themselves are sound.

## Per-criterion assessment

1. **"1440/1024/768/390/320 widths have no page overflow"** — criterion content
   **verified** (run 4: all five overflow tests pass; `mobile-320.png` and
   `mobile-390.png` show clean wrapping with no clipping; the worker's CDP
   evidence is authentic), but see F1: the registered command that must
   demonstrate this cannot pass as committed.
2. **"page and disagreement dominate"** — **verified.** `desktop-1440.png` shows
   the paper panel and the full-width disagreement banner dominating the
   hierarchy; the suite's dominance assertions (stage > 600×400, finding
   ≥ 76 px) pass in run 4.
3. **"contrast checks meet stated targets"** — **verified.** Run 4's computed
   DOM contrast test passes; the receipt's specific claims (muted ≥ 4.5,
   teal/rust ≥ 5, focus non-text ≥ 3, ink ≥ 10) independently recompute to
   ≈ 6.1 / 6.2 / 6.7 / 5.9 / 14.7 (run 7).
4. **"reduced motion disables flips"** — **verified with a note.** The suite
   asserts `--motion-state/--motion-panel` collapse to 0 under
   `prefers-reduced-motion`, and `DocumentStage.module.css` additionally forces
   `transition: none !important` in its own reduced-motion block (defense in
   depth). The note: no test asserts an actual flip/transition is visually
   static; the token mechanism plus CSS fallback makes this acceptable at T06.
5. **"screenshot evidence covers dark text, focus and partial states."** —
   **verified.** All eleven PNGs exist; sampled images are genuine renders
   covering dark text, the focus ring, compare mode, expanded detail, and
   loading/failed/empty states.

Invariants: **I06** upheld (disagreement copy explicitly disclaims truth,
safety, fraud verdicts; "Not a verdict about the amount"). **I18** largely
upheld (SYNTHETIC badge, "No real transaction" kicker, occurrence readers
named) with one honesty nit (F3: a placeholder SVG captioned "Actual crop").

## Findings

### F1 — BLOCKING (changes needed): the registered acceptance command cannot pass as committed
`tests/visual/foundation.spec.ts` navigates to the root-relative
`/src/components/DocumentStage/preview.html`, but no `playwright.config.*`
exists anywhere in the candidate, so `page.goto` raises "Cannot navigate to
invalid URL" for all 9 tests (run 2, exact registry argv shape). The worker's
own evidence honestly recorded the runner as pending T02, and the internal
review did not execute the spec; with T02 still pending, no one has run it
until now. Once T02 lands, this suite will still fail 9/9.

Required fix (small): commit a Playwright config that serves the component
surface — e.g. `tests/visual/playwright.config.ts` with a `webServer` static
server on an OS-assigned port and `use.baseURL`, matching run 4 — and reference
it from the `test:visual` registry argv (`--config tests/visual/playwright.config.ts`).
This needs a one-line allowed-scope addition (`tests/visual/` config file) for
the writer, which the coordinator can grant; the reviewer considers it trivially
justified. Alternatively the coordinator may assign the config to T02's
registry activation — but T06's acceptance should not close while its own
contract command fails.

### F2 — Medium: token-centralization rule violated inside the owned module
`apps/web/src/styles/tokens.css` declares itself "The only place raw
color/spacing/type values are defined; components consume these custom
properties via var(--token)." `DocumentStage.module.css` contains 10 raw hex
colors (e.g. `#3e5750`, `#edf2e8`, `#fcf5df`, `#e6cf8f`, `#faefce`, `#d8be74`,
`#746444`) and 41 raw px declarations (font sizes 11/32/54 px, paddings, radii).
Token-centralized styling is an explicit review criterion for this task. Either
promote the reused state colors (banner yellows, success greens, muted text
tones) into semantic tokens, or record a scoped proposal amending the rule for
component-local one-off values. Not blocking on visual merit — the palette is
faithful to the warm paper/ink + teal/rust direction — but the written rule and
the code currently disagree.

### F3 — Low (follow-up required by T17): placeholder crop presented with an actuality caption
`DocumentStage` defaults `imageSrc` to `/probes/results/amount-crop.png`, which
does not exist under `apps/web/public/` (404 when the component mounts in the
real app). `preview.html` substitutes a hand-drawn SVG `$100` while the caption
beneath reads "Actual crop · PDFium 149.0.7825.0 render". As contract-example
scaffolding this is tolerable, but an "actual" claim over a drawn stand-in is
the kind of drift I18 forbids long-term. Suggested: caption the preview stand-in
"Placeholder for the generated crop (real bytes at T17)" and track the real
asset + component default for T17/T13. Non-blocking for T06.

### F4 — Info: preview markup duplicates the component
`preview.html` shares the shipped CSS files (good — the tests do exercise the
real styles and tokens) but hand-copies the markup, so component and preview can
drift. Accepted as the T06 vehicle; retire or generate the preview from the
component when T13 integrates the real composition.

### F5 — Info: candidate predates the T02 dependency freeze
The candidate branches from pre-T02 `3bef697`; `bun install --frozen-lockfile`
is impossible on this branch alone. Expected for parallel work; per freshness
rules the coordinator must re-run acceptance on the merged candidate after
integration, where runs 1–4 should be repeated against the frozen runner.

## What is good (verified, not echoed)

- The component is real, accessible work: roving-tabindex tabs, arrow/Home/End
  keyboard handling, `role` structure, live-region status boxes, occurrence
  list usable without the canvas, zoom/rotation controls.
- Copy matches the approved direction exactly ("The amount that reads
  differently", "The picture is not the text layer", explicit I06 disclaimer).
- The evidence set is authentic: every sampled PNG is a genuine render of the
  shipped preview; the numbers in `commands.log` match this reviewer's runs.
- Reduced motion is handled twice (token media query + module fallback).
- Scope discipline is clean: no file outside the allowed surface (plus
  artifacts), no new frameworks or UI libraries, no Effect/Tailwind/StyleX.

## Verdict

**changes-needed**, solely on F1: T06's own registered acceptance command fails
9/9 as committed, proven by execution. The fix is a small config + registry
argv coordination. F2 should be resolved or explicitly waived by the
coordinator in the same pass. F3/F4 are recorded follow-ups, not acceptance
blocks. Once F1 lands and the merged candidate re-runs green (runs 1–4 against
the frozen T02 runner), this reviewer sees no remaining obstacle to acceptance
on the content itself.

— zcode peer reviewer, 2026-09-12
