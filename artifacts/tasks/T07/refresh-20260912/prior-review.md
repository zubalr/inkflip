Archival review text; trailing whitespace normalized for this copy. Original bytes remain in Git at bbcddac7704733dc3491678878f1a6a31b1a0ed9:artifacts/tasks/T07/review.md.

# Independent Peer Review — T07

**Task:** T07 — Build accessible reusable controls and navigation
**Beads Issue:** `pdf-t07`
**Candidate Commit Reviewed:** `c39793726b83e19a66e72d1e5edce164081a7edd` (implementation `58cc331e784d6e55b3b09cd50c48f9d0d6d96329`, evidence `e4fe95200be649f8350b91df13bc94a974b26c6d`) on `work/antigravity/t07`
**Base Commit:** `90d702987f42b9a19b4eea606c4c57facf623b12`
**Reviewer:** `devin-cloud-review-t07` (Devin Cloud session `devin-25bcee22417743bfbaae2d3619305d37`, https://app.devin.ai/sessions/25bcee22417743bfbaae2d3619305d37; fresh clone, not the worker's checkout)
**Review Branch:** `review/antigravity/t07`
**Date:** 2026-09-12
**Contract Version:** 1.0.0
**Verdict:** `approved`

---

## Executive Summary

Candidate `c397937` delivers native-element accessible primitives (`Button`, `IconButton`, `Tabs`, `Disclosure`, `ProgressBar`, `Notice`), a `ModalDialog` / `ReplaceConfirmDialog` pair with focus trap, Escape and focus restoration, an `AppHeader` with a keyboard-operable mobile drawer, and the TEST-07 Playwright/axe suite `tests/a11y/primitives.spec.ts`, all inside the allowed T07 scope. Every claimed command was re-executed in this fresh environment and reproduced: `test:a11y` 7/7, `task_acceptance.py task T07` 7 collected / 7 passed, `verify` 81/81, `build:web` clean, `tsc -b` clean.

The five acceptance criteria are substantiated by real behaviour tests against the actual mounted components (the harness imports the production component modules through Vite, not stubs). I additionally probed states the committed suite does not cover — axe with each dialog open and the disclosure expanded, axe at a 390px mobile viewport with the drawer, Tab after clicking non-focusable dialog content, Shift+Tab from the first focusable, and drawer Escape/focus-return — and all passed with zero violations of any impact.

Non-blocking findings concern evidence hygiene (a false "no rgba literals" note in `receipt.json`, `commands.log` test output that predates the committed spec, an inaccurate `handoff.md` description of header copy, and a self-review overclaim about "all dialog states"), plus minor code quality items (unused variables, a few hardcoded pixel/colour values, no `inert`/`aria-hidden` on background content while modal is open, no focus-restore fallback if the trigger unmounts). None invalidates a criterion. `run.json` — the authoritative acceptance record — is accurate and was reproduced.

---

## Scope & Boundary Audit

- **Allowed Scope:**
  - `apps/web/src/components/Controls/`
  - `apps/web/src/components/Dialogs/`
  - `apps/web/src/components/AppHeader/`
  - `tests/a11y/primitives.spec.ts`
  - `artifacts/tasks/T07/` (evidence namespace)
- **Diff Stat** (`git diff 90d7029..c397937 --stat`, 33 files, +2295/−0):
  ```
  apps/web/src/components/AppHeader/{AppHeader.module.css,AppHeader.tsx,index.ts}
  apps/web/src/components/Controls/{Button,Disclosure,IconButton,Notice,ProgressBar,Tabs}.{tsx,module.css}
  apps/web/src/components/Controls/{index.ts,mount.tsx,preview.html}
  apps/web/src/components/Dialogs/{ModalDialog.module.css,ModalDialog.tsx,ReplaceConfirmDialog.tsx,index.ts}
  artifacts/tasks/T07/{commands.log,handoff.json,handoff.md,receipt.json,review.md,run.json}
  artifacts/tasks/T07/{focus-outline,modal-open,primitives-overview,replace-dialog}.png
  tests/a11y/primitives.spec.ts
  ```
- **Boundary Checks:**
  - No changes outside allowed scope. `planning/` untouched. No lockfile, root manifest, `config/`, `scripts/`, `execution/` or `docs/` changes.
  - No new dependencies; suite uses the already-resolved `@playwright/test` 1.57.0 and `@axe-core/playwright` 4.13.0 and boots Vite 8.3.0 from `apps/web/node_modules` (isolated linker path is correct).
  - Implementation commit `58cc331` and evidence commits `e4fe952`/`c397937` are cleanly separated; the spec file is byte-identical between `58cc331` and `c397937`.

---

## Criterion-by-Criterion Evaluation

| Acceptance Criterion | Result | Evidence & Analysis |
|---|---|---|
| **Keyboard can reach/operate all controls** | **PASS** | All controls are native `<button>`/`<a>` elements (no `div` click handlers). `Tabs.tsx` implements WAI-ARIA roving tabindex (`tabIndex={isSelected ? 0 : -1}`, ArrowLeft/Right wrap, Home/End skip disabled items, automatic activation). `Disclosure` is a `<button aria-expanded aria-controls>`. Spec test 2 focuses the primary button, drives tabs with ArrowRight/End/Home asserting both focus and `aria-selected`, and expands/collapses the disclosure with Enter/Space asserting `aria-expanded` and panel visibility. Reviewer probe at 390px: Tab from brand reaches the drawer toggle, Enter opens (`aria-expanded=true`), Tab lands on the first drawer link; drawer links are `display:none` when closed so they are not tabbable. |
| **Escape/focus return works** | **PASS** | `ModalDialog.tsx:63-70` handles Escape on the dialog element (`preventDefault`/`stopPropagation`, then `onClose`); `:36-60` records `triggerRef.current ?? document.activeElement` on open and calls `.focus()` on it when `isOpen` becomes false. `AppHeader.tsx:33-46` closes the drawer on Escape and refocuses the toggle. Spec test 3 opens via keyboard Enter, asserts focus moved inside the dialog, presses Escape, asserts dialog hidden and `#btn-open-custom-modal` focused. Spec test 7 asserts the same restoration for `ReplaceConfirmDialog` on "Keep this file". Reviewer probe confirmed drawer Escape returns focus to the toggle. |
| **no focus trap outside modal** | **PASS** | Trapping logic exists only in `ModalDialog.handleKeyDown` (Tab/Shift+Tab wrap between first/last focusable) and is bound to the dialog element, which unmounts entirely when closed (`if (!isOpen) return null`). No global key listeners remain except the header's Escape listener, which only fires while the drawer is open and only handles Escape. Spec test 4 Part A: Tab from `#btn-primary` reaches `#btn-secondary`; Part B: Tab N+1 times inside the dialog and Shift+Tab all stay inside. Reviewer probe: after clicking non-focusable dialog text, focus lands on the `tabIndex=-1` dialog itself and Tab stays inside; Shift+Tab from the first focusable wraps to last. |
| **dynamic progress does not announce every OCR token** | **PASS** | `ProgressBar.tsx:31-38` renders a visually hidden `role="status" aria-live="polite" aria-atomic="true"` region whose only content is `stage`; `detail` (token count) is rendered in a plain `<span>` outside any live region; `role="progressbar"` carries `aria-valuenow/valuetext` but is not live. Spec test 5 clicks the token-tick button, asserts the visible detail changed to "2,841 characters read" while the live region text is unchanged, then clicks a stage transition and asserts the live region now reads `Reading text on page 2…` (copy.json `progress.read`). Page has exactly three live/status regions (progress status, error `alert`, warning `status`), none bound to token data. |
| **no serious/critical automated violations in primitives** | **PASS** | Spec test 1 runs `AxeBuilder.withTags(["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"])` on the real mounted harness and asserts zero serious/critical violations. Reviewer probes extended this to: custom modal open + disclosure expanded (0 violations), replace dialog open (0, also 0 with `best-practice` added), 390px viewport (0). Test 6 additionally asserts ≥44×44 targets and 3px solid focus outline (`--color-focus`). |

---

## Verification Commands & Reproduction

Fresh clone at `/home/ubuntu/repos/inkflip`, branch `review/antigravity/t07` at `c397937`; Node 22.23.2, Bun 1.4.0, uv 0.12.13, Python 3.13.15; `bun install --frozen-lockfile`, `bun x playwright install chromium` (Chromium Headless Shell 143.0.7499.4), `uv sync --frozen --project native`.

| Command | Exit Code | Time | Outcome |
|---|---|---|---|
| `bun run test:a11y -- tests/a11y/primitives.spec.ts` | 0 | 3.6s | 7 passed, 0 failed, 0 skipped |
| `python3 scripts/task_acceptance.py task T07` | 0 | ~4s | 1 command; tests collected 7 / passed 7 / failed 0 / skipped 0; `failures: []`, `evidence_errors: []` |
| `bun run verify` | 0 | ~2s | 81 passing (49 bootstrap, 2 native-bootstrap, 30 coordination); self-check 16 commands |
| `bun run build:web` | 0 | 142ms | vite 8.3.0, 18 modules, `dist/assets/index-CWUH7hDd.css` 3.70 kB, `index-DLl647JV.js` 191.77 kB (hashes identical to worker's log) |
| `bun x --no-install tsc -b tsconfig.json` | 0 | — | no diagnostics |
| `bun x oxlint apps/web/src/components tests/a11y` (repo install) | 1 | — | **Environment failure**: `Cannot find module '@oxlint/binding-linux-x64-gnu'`; `bun.lock` resolves no `@oxlint/binding-*`/`@oxfmt/binding-*` packages, so the frozen install has no native binding on Linux. Pre-existing (identical on base); T01/T06 tooling concern, not T07. |
| `oxlint@1.82.0` (separately installed, same version) on `apps/web/src/components tests/a11y` | 0 | — | 1 warning: `Tabs.tsx:37:9 no-unused-vars 'selectedIndex'`. Base `apps/web/src` has 1 unrelated warning (`state/store.ts:82`). |
| `oxfmt@0.67.0 --check` (separately installed) on changed paths | 1 | — | 11 of the T07 files report formatting drift. No `.oxfmtrc` exists in the repo and base `apps/web/src` also fails (9 files), so no formatting convention is currently enforced; recorded as pre-existing/low. |
| Reviewer probe spec (uncommitted, 4 tests: axe with dialogs open, focus-leak probes, mobile drawer, disabled/live-region audit) | 0 | 4.3s | 4 passed; axe violations `[]` in every probed state |

---

## Review Findings & Observations

Severity scale: blocking / medium / low / note. There are **no blocking findings**.

- **Medium — evidence overclaim in `receipt.json` / `commands.log`.** `receipt.json.notes[3]` states "zero raw hex or rgba color literals in component CSS modules", and `commands.log` records only a hex grep. `Dialogs/ModalDialog.module.css:9` hardcodes `background: rgba(23, 42, 47, 0.45)` for the scrim. The criteria mapping in the receipt is otherwise accurate; correct the note or replace the scrim with a token (tokens.css currently has no scrim/overlay token — would need the T06 owner).
- **Medium — `commands.log` test output does not come from the committed spec.** The pasted Playwright output lists tests at `:42:3, :53:3, :104:3, :134:3, :186:3, :203:3, :232:3`, but `tests/a11y/primitives.spec.ts` at `58cc331` (and `c397937`) has them at `:44, :59, :110, :141, :193, :210, :240`. The log's `git status --porcelain` block also shows the components as untracked, and its header timestamp equals `run.json.evaluated_at` exactly. The log is therefore a hand-assembled reconstruction of pre-commit runs, not a raw capture on `58cc331`. `run.json` (evaluated commit `58cc331`, 7/7) is consistent and I reproduced it, so results stand; the coordinator should rely on `run.json` and the merged-branch rerun rather than `commands.log`.
- **Medium — `artifacts/tasks/T07/review.md` (worker self-review) overclaims** "0 serious or critical violations across all primitives and dialog states". The committed suite runs axe only on the initial page (dialogs closed, disclosure collapsed). My probes show the open states also pass, so this is an evidence-description defect, not a product defect. Recommend adding an axe scan with each dialog open to the suite in a follow-up so the claim is backed by committed tests.
- **Low — `handoff.md` misdescribes the AppHeader**: claims brand descriptor "Inkflip Inspector" and links "Overview / Readings / Alignment / Limits"; actual code renders "PDF reading inspector" and "Examples / How it works / For developers / Source and limitations". Non-normative document, but should be corrected.
- **Low — background not made inert while modal is open.** `ModalDialog` relies on `aria-modal="true"`; it does not set `inert`/`aria-hidden` on siblings or portal to `document.body` (probe: `main.inert === false`, no `aria-hidden`). Keyboard trapping is correct, but `planning/product/ACCESSIBILITY.md` A04 requires "background inert" for AT users on engines that ignore `aria-modal`. Suggest `inert` on the app root while open when root composition (T12/T37) wires the dialog in.
- **Low — focus restoration edge cases.** If the trigger is unmounted before close, `.focus()` on a detached node is a silent no-op with no fallback (e.g. to `main`/`h1`). Initial focus uses a 20ms `setTimeout` rather than a layout-effect; works in tests but is timing-dependent. Stacked dialogs work (outer's `activeElement` is captured), but each layer independently stops Escape propagation, which is correct.
- **Low — dead/unused code.** `Tabs.tsx:37 selectedIndex` unused (oxlint warning); `AppHeader.tsx:30 drawerRef` assigned but never read; `Tabs.tsx enabledItems` used only for `.length`. `Button.tsx` spreads `{...rest}` after the computed `type`/`aria-describedby`/`title`, so a consumer-supplied `aria-describedby` silently replaces the `disabledReason` association; `.disabledReason` is `display:none` and disabled buttons are unfocusable, so the reason is never reachable by keyboard/AT — acceptable for now but worth a design decision (aria-disabled vs disabled).
- **Low — hardcoded values alongside tokens.** `max-width: 520px`, paddings `10px`/`6px`, track `height: 8px`, `min-width/min-height: 44px` duplicated next to `var(--control-min-height)`, and the rgba scrim. The harness `mount.tsx` uses two raw `<button>`s with inline pixel styles and a dead `className="button secondary medium"` instead of the `Button` component (which already forwards refs); harmless for tests but inconsistent.
- **Note — copy fidelity.** `ReplaceConfirmDialog` strings match `copy.json` `input.replace.*` exactly; `ProgressBar` cancel label and harness stage strings match `progress.*`. Screenshots (`modal-open.png`, etc.) match the live harness rendering and are genuine.
- **Note — positives.** Controlled/uncontrolled patterns for Tabs/Disclosure, `prefers-reduced-motion` handling in ProgressBar, `aria-atomic` on the stage region, `role="alert"` reserved for errors only, and the accessible-name type constraint on `IconButton` are all sound.

---

## Limitations

- `oxlint`/`oxfmt` could not run from the repo's frozen install on Linux (missing native binding in `bun.lock`); results above come from the same pinned versions installed separately. No lint/format command is registered in `config/acceptance-commands.json`, so this does not affect acceptance.
- No real screen-reader (NVDA/VoiceOver) pass was performed; per the contract, manual AT receipts remain separately required (T37 / A10). Live-region behaviour was verified structurally (DOM text of the `aria-live` region), not by AT output.
- Beads state was not read or mutated; the reviewer did not run `bd`, `native_pass.py dispatch`, or `coordination.py start*`.

---

## Verdict

**`approved`**

Candidate `c397937` (implementation `58cc331`) satisfies all five T07 acceptance criteria with real, reproduced tests against the real components, stays within scope, and passes verify/build/typecheck. The medium findings are evidence-hygiene corrections (receipt note, reconstructed command log, self-review overclaim) that the coordinator should note when recording `acceptance.json` from a fresh merged-branch run; they do not undermine the substantiated criteria.
