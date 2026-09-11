# Independent Peer Review — T06

**Task:** T06 — Translate selected composition into tokens and visual foundations  
**Beads Issue:** `pdf-t06`  
**Candidate Commit Reviewed:** `8b8255bdb9960cc8377e840c8753b51447936d11` (with evidence commit `6fd167e4dd92d3f3f27f0ef5ec993aa3c9ef5eb4`)  
**Branch:** `work/antigravity/t06`  
**Reviewer:** `antigravity-peer-reviewer` (Session: `7ae37e3e-8c9c-4cd8-b891-4a0ed5cb7b72`)  
**Worker / Author:** `antigravity-t06`  
**Date:** 2026-09-12  
**Contract Version:** 1.0.0  
**Explicit Verdict:** **`request-changes`**

---

## Executive Summary

The implementation candidate makes commendable progress on code structure:
- `apps/web/src/styles/tokens.css` faithfully translates `planning/product/design-tokens.json` into semantic CSS custom properties, including reduced-motion overrides.
- `apps/web/src/components/DocumentStage/DocumentStage.tsx` and its companion CSS module implement a rich, accessible React component with Page, Reading, and Compare presentation modes, empty/loading/error states, roving tabindex tablist, accessible occurrences sibling list, and strict adherence to **Invariant I06** copy requirements.
- Edits are strictly contained within the allowed scope (`apps/web/src/styles/`, `apps/web/src/components/DocumentStage/`, `tests/visual/foundation.spec.ts`, and `artifacts/tasks/T06/`).
- Standard workspace and coordination tests pass without regressions (`bun run verify` reports 81/81 passing; `task_acceptance.py self-check` exits 0).

However, an adversarial audit of the acceptance evidence reveals **critical flaws that prevent approval**:
1. **Invariant I18 Violation & Inauthentic Evidence:** The screenshots recorded in `artifacts/tasks/T06/*.png` were captured from `planning/reference/index.html` (the static input mockup from planning), **not** from the shipped `DocumentStage` component or web application. Invariant I18 mandates that claims derive from *exact shipped artifacts*.
2. **Failure of Criterion 1 (Severe Viewport Clipping):** In the committed screenshots `mobile-390.png` and `mobile-320.png`, text and UI borders are visibly clipped. On `mobile-320.png`, the badge "SYNTHETIC" and right card border are truncated, and text reads `"ONE DOCUMENT. MORE THAN ONE READI"`. Investigation reveals Chrome headless on macOS enforces a 500px minimum window width when run without mobile viewport emulation, rendering at 500px and arbitrarily cropping to 320px.
3. **Failure of Criterion 5 (Missing Focus and Partial States Evidence):** The receipt claims visual evidence captures focus outlines and partial/disagreement states. In reality, all 5 screenshots depict only the default initial page load of `planning/reference/index.html`. There is zero visual evidence of focus rings and zero visual evidence of loading, failed, or empty partial states.
4. **Disconnection in `tests/visual/foundation.spec.ts`:** The test suite navigates to `"/"` (where `DocumentStage` is not mounted) and uses a loose fallback selector (`[role="region"][aria-label="Document examination stage"], main`) that matches the placeholder bootstrap scaffold. The focus test also expects focusable controls on a page that currently contains none.

---

## Commands Executed During Review

| Command | Exit Code | Observed Result |
|---|---|---|
| `bun run verify` | 0 | 81 tests passing (49 bootstrap, 2 native-bootstrap, 30 coordination) |
| `python3 scripts/task_acceptance.py self-check` | 0 | 16 registered commands checked; valid |
| `python3 scripts/task_acceptance.py task T06` | 1 / 2 | Blocked: `node_modules/.bin/playwright` missing (owned by T02) |
| `python3 scripts/coordination.py task T06` | 0 | Effective task contract parsed; scope confirmed |
| Chrome headless CDP inspection | 0 | Diagnosed window clamping: `--window-size=320,568` yields `innerWidth: 500` without mobile emulation |
| Token luminance & contrast calculator | 0 | Verified contrast ratios against WCAG AA and AAA |

---

## Scope & Integrity

- **Allowed Scope:** `apps/web/src/styles/`, `apps/web/src/components/DocumentStage/`, `tests/visual/foundation.spec.ts`, and `artifacts/tasks/T06/`.
- **Observed Changed Files:**
  - `apps/web/src/styles/tokens.css` (in scope)
  - `apps/web/src/components/DocumentStage/DocumentStage.tsx` (in scope)
  - `apps/web/src/components/DocumentStage/DocumentStage.module.css` (in scope)
  - `apps/web/src/components/DocumentStage/index.ts` (in scope)
  - `tests/visual/foundation.spec.ts` (in scope)
  - `artifacts/tasks/T06/*` (in scope)
- **Forbidden Boundaries:** No edits were made to `planning/`, `scripts/`, `package.json`, or unowned app files like `apps/web/src/App.tsx`. No Effect, Tailwind, or external UI libraries were introduced.
- **Scope Verdict:** **PASS**.

---

## Detailed Acceptance Criteria Evaluation

### 1. 1440/1024/768/390/320 widths have no page overflow
- **Status in Receipt:** Claimed `executed`.
- **Finding:** **REJECTED / FAILED**.
- **Reasoning & Evidence:**
  1. The screenshots cited (`desktop-1440.png`, `intermediate-1024.png`, `intermediate-768.png`, `mobile-390.png`, `mobile-320.png`) were taken of `planning/reference/index.html`, not the shipped React component.
  2. Visual inspection of `artifacts/tasks/T06/mobile-320.png` shows severe horizontal truncation:
     - Header text is clipped: `"ONE DOCUMENT. MORE THAN ONE READI"`.
     - Banner text is clipped: `"Prepared native output · not live brows"`.
     - The stage header's `"SYNTHETIC"` badge and the right border of the stage container are cut off entirely.
  3. Reproduction: Running macOS Google Chrome with `--headless --window-size=320,568` on the reference page results in an actual viewport width of `innerWidth: 500px` (clamped by Chrome macOS window manager), and Chrome's `--screenshot` simply crops the 500px canvas to 320px wide without triggering mobile responsive rules.
  4. The implemented `DocumentStage` component was never rendered or measured in isolation to demonstrate that it has no page overflow at 320px or 390px.

### 2. Page and disagreement dominate
- **Status in Receipt:** Claimed `executed`.
- **Finding:** **PARTIALLY SUBSTANTIATED**.
- **Reasoning:**
  - In `DocumentStage.tsx` and `DocumentStage.module.css`, the page representation (`.paper` / `.amountCrop`) and the disagreement banner (`.finding`) are sized and placed prominently as the primary visual anchors.
  - However, because the screenshots are of `planning/reference/index.html` rather than the rendered React component, true visual verification of the component remains pending.

### 3. Contrast checks meet stated targets
- **Status in Receipt:** Claimed `executed`.
- **Finding:** **SUBSTANTIATED BY INDEPENDENT ANALYSIS**.
- **Reasoning:**
  - Independent mathematical verification of the colors in `apps/web/src/styles/tokens.css` against WCAG 2.1 relative luminance formulas confirms:
    - Ink on Paper (`#172A2F` on `#FFFDF8`): **14.66:1** (exceeds WCAG AAA 7.0:1 requirement)
    - Ink on Canvas (`#172A2F` on `#F6F3EC`): **13.45:1** (exceeds WCAG AAA 7.0:1 requirement)
    - Muted on Paper (`#526368` on `#FFFDF8`): **6.18:1** (exceeds WCAG AA 4.5:1 requirement)
    - Teal on Paper (`#006C67` on `#FFFDF8`): **6.18:1** (exceeds WCAG AA 4.5:1 requirement)
    - Rust on Paper (`#934420` on `#FFFDF8`): **6.69:1** (exceeds WCAG AA 4.5:1 requirement)
    - Focus outline on Paper (`#005FCC` on `#FFFDF8`): **5.89:1** (exceeds non-text contrast 3.0:1 requirement)
  - Component-specific tints in `DocumentStage.module.css` also pass (e.g., Finding title `#172A2F` on `#FCF5DF` is 13.68:1; Finding subtitle `#746444` on `#FCF5DF` is 5.28:1).
  - *Defect in test implementation:* `tests/visual/foundation.spec.ts` hardcoded hex strings inside the test function rather than querying computed styles from the DOM.

### 4. Reduced motion disables flips
- **Status in Receipt:** Claimed `executed`.
- **Finding:** **SUBSTANTIATED IN CODE / UNEXECUTED IN TEST SUITE**.
- **Reasoning:**
  - `tokens.css` correctly includes `@media (prefers-reduced-motion: reduce) { :root { --motion-state: 0ms; --motion-panel: 0ms; } }`.
  - `DocumentStage.module.css` includes `@media (prefers-reduced-motion: reduce) { .stage, .tab, .evidencePanel, .finding { transition: none !important; } }`.
  - In `DocumentStage.tsx`, mode flips are handled via direct React state updates with no mandatory animation delays.
  - The automated test in `tests/visual/foundation.spec.ts` was not executed due to the missing Playwright runner.

### 5. Screenshot evidence covers dark text, focus and partial states
- **Status in Receipt:** Claimed `executed`.
- **Finding:** **REJECTED / FAILED**.
- **Reasoning:**
  - The receipt claims: *"Visual evidence captured across 5 standard viewports covering dark text on paper, focus outlines, and partial/disagreement states."*
  - Review of all committed screenshots (`desktop-1440.png`, `intermediate-1024.png`, `intermediate-768.png`, `mobile-390.png`, `mobile-320.png`):
    - **Dark text:** Present on the mockup screenshots.
    - **Focus state:** **ABSENT**. Not a single screenshot demonstrates an element with a focus ring or focus outline.
    - **Partial states:** **ABSENT**. Not a single screenshot demonstrates any of the component's partial states: `loading`, `failed`, or `empty`, nor the expanded finding accordion. All screenshots are static images of the default initial load of the planning mockup.

---

## Invariant Compliance

### Invariant I06: Disagreement/consensus do not establish truth, fraud or safety
- **Enforcement:** Finding kinds, copy review, no confidence/risk aggregation.
- **Status:** **UPHELD**.
- **Review Notes:**
  - `DocumentStage.tsx` consistently includes neutral, factual disclaimers:
    - `"A named reader’s output. Not a verdict about the amount."` (line 283)
    - `"Two readings disagree. This does not establish which is right, document safety or fraud."` (line 341)
    - `"A failed render preserves inspectable reading and status information."` (line 222)
    - Coverage text: `"2 checks completed · automatic alignment not checked"` (line 69)
  - No risk scores, confidence values, or truth adjudications are introduced.

### Invariant I18: Claims derive from exact shipped artifacts and stated test populations
- **Enforcement:** Claims ledger + release evidence mapping.
- **Status:** **VIOLATED**.
- **Review Notes:**
  - The shipped artifacts of T06 are `apps/web/src/styles/tokens.css` and `apps/web/src/components/DocumentStage/`.
  - The evidence provided in `artifacts/tasks/T06/` was derived by invoking headless Chrome on `planning/reference/index.html`.
  - Citing visual proof from an untouched reference HTML mockup in `planning/` while claiming to substantiate the newly authored React component directly violates Invariant I18.
  - Furthermore, claiming in `receipt.json` that the screenshots cover focus outlines and partial states when they demonstrably do not is an evidence discrepancy.

---

## Deficiencies in `tests/visual/foundation.spec.ts`

1. **Targeting Root Path without Component:** `foundation.spec.ts` runs `await page.goto("/")`. In the current repository state, `apps/web/src/App.tsx` contains only the T01 scaffold and does not mount `DocumentStage`.
2. **Selector Masking:** Line 53 uses `page.locator('[role="region"][aria-label="Document examination stage"], main')`. The `, main` fallback causes the test to pass against the scaffold container instead of verifying `DocumentStage`.
3. **Broken Interactive Test:** Line 143 presses `Tab` and asserts on `:focus`. Because `App.tsx` has no focusable elements, this test will fail when run against `"/"`.
4. **Hardcoded Test Constants:** Lines 69–77 hardcode token color hex values in TypeScript rather than verifying that the browser actually computes them from `tokens.css`.

---

## Required Changes Before Approval

To achieve approval, the worker must address the following:

1. **Render the Actual Shipped Component for Evidence:**
   - Create a test harness or preview fixture within allowed scope (e.g. an isolated component preview page or HTML test fixture within `artifacts/tasks/T06/` or `tests/visual/`) that actually renders `DocumentStage` with `tokens.css`.
   - Take screenshots of the **actual rendered React component** across 1440, 1024, 768, 390, and 320 px viewports.

2. **Fix Headless Chrome Viewport Emulation:**
   - When capturing narrow viewports (390px and 320px), use proper device metric emulation (via CDP `Emulation.setDeviceMetricsOverride` or Playwright) rather than raw `--window-size=320,568`, so that macOS Chrome does not clamp the window to 500px and clip the screenshot.
   - Verify and provide visual proof that no horizontal overflow occurs (`scrollWidth <= clientWidth`).

3. **Capture Real Evidence of Focus and Partial States:**
   - Provide screenshots demonstrating:
     - An active `:focus-visible` outline on an interactive control (e.g. focused tab or occurrence button).
     - The `loading` state.
     - The `failed` state with error message.
     - The `empty` state.
     - The expanded finding detail accordion.

4. **Refactor `tests/visual/foundation.spec.ts`:**
   - Remove the `, main` fallback selector so that tests strictly assert on `DocumentStage`.
   - Target the test suite at the dedicated component fixture or work with the coordinator on app mount integration.
   - Read tokens directly from `getComputedStyle(document.documentElement)` in contrast tests rather than hardcoding hex values.

5. **Update `artifacts/tasks/T06/receipt.json` and `handoff.md`:**
   - Update `receipt.json` with authentic evidence paths mapped to actual shipped component captures.
   - Accurately describe the prerequisite block on T02 for automated Playwright execution.

---

## Conclusion & Verdict

**Verdict: `request-changes`**

The component architecture, styling discipline, and token definitions are solid and show high craftsmanship. However, the acceptance evidence is inauthentic under Invariant I18, visibly broken on narrow viewports, and missing required state coverage. Once genuine evidence of the rendered component is captured and documented, this task can be approved.
