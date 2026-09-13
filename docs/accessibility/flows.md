# Accessibility flows — TEST-37

What `tests/a11y/flows.spec.ts` verifies against the **real app** (Vite dev
server booted from `apps/web`, public routes only). Companion to
`tests/a11y/primitives.spec.ts` (T07 control-level contracts on the preview
harness). Acceptance command: `bun run test:a11y` (Playwright, `tests/a11y`).

Run date basis for findings below: 2026-09-13, Chromium via Playwright 1.57,
axe-core 4.13 (`@axe-core/playwright`), tags
`wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`.

## Test targets

| Target                   | Route / entry                                                                             | What it mounts                                                                                                                                               |
| ------------------------ | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Bundled example document | `/#/workspace?example=true`                                                               | `Workspace` + `ViewerStage` over `EXAMPLE_DOC` (ambiguous amount finding, page-level finding, order-only finding). No report → no CoveragePanel/ExportPanel. |
| Captured scan report     | `/#/workspace?example=scan`                                                               | `examples/scan/report.json` through the real import gate → ViewerStage + CoveragePanel + replay status + ExportPanel.                                        |
| Sealed contract report   | `#input-import-report` → `planning/contracts/examples/valid/native-evidence.inkflip.json` | Same surfaces; 2 of 3 checks completed (alignment check recorded `unsupported`) → partial coverage.                                                          |

## Legs

### 1. Core flow, keyboard only (`core flow: every control operated by keyboard only`)

`?example=scan`. No `locator.click()` anywhere in the leg — only `.focus()`,
`page.keyboard.*`, `el.press()` and file-input `setInputFiles` (the file
chooser is a native OS surface, not page UI).

- Real `Tab` walk from page top traverses header controls, `#viewer-stage`,
  the view-mode tab, zoom/fit/rotate controls, the shortcuts toggle, all 25
  text-equivalent `Select` buttons, prev/next finding, and reaches the finding
  cards. Focus never falls back to `document.body`.
- `Enter` on a `role="option"` finding card selects it (`aria-selected`), the
  alignment detail expands, and the findings counter updates.
- `Enter` on a candidate button picks the occurrence (`aria-pressed`,
  `highlightSelected`) and **returns focus to the originating card**; `Escape`
  returns focus without picking.
- `f` cycles Page → Reading → Compare; `+`/`-` zoom; `r` rotates; focused
  toolbar buttons respond to `Enter`.
- A note is drafted and saved by keyboard; typing `f` inside the notes
  `textarea` does **not** trigger the mode shortcut (single-character keys are
  suppressed in text entry — `ViewerStage.handleStageKeyDown` skips
  INPUT/TEXTAREA targets).
- Export: a findings checkbox toggles via `Space`, the `aria-live` preview
  publishes the deselection, and `Enter` on "Download portable JSON" produces
  the `role="status"` success message.
- `#btn-close-doc` via `Enter` returns to the intake surface.

### 2. Focus restoration (`replace-confirmation dialog …`)

`?example=scan` + offering a replacement file through `#input-open-pdf` while
focused on `#btn-header-open-pdf` opens `ReplaceConfirmDialog`
(`role="dialog"`, `aria-modal`). Focus moves inside the dialog, `Tab` cycles
within it, `Escape` and the "Keep this file" cancel path both restore focus to
`#btn-header-open-pdf`. The open report is preserved after cancel.

### 3. Announcements (`announcements: ambiguous amount alternatives …`)

- **Ambiguous amount alternatives** (`?example=true`,
  `finding-ambig-amounts`): each candidate button's accessible name carries its
  alternative — `$1,000.00` (occurrences #1/#2, identical text labelled "k of n
  at distinct positions") and `$10,000.00` (pypdf). After keyboard selection,
  focus lands on the finding `option`, whose expanded accessible name contains
  the `Ambiguous — candidates kept` badge and both amounts.
- **Page-level state**: selecting `finding-page1-unknown` renders
  `#page-level-geometry-notice`, a `role="status" aria-live="polite"` region
  announcing "applies to Page 2 as a whole. No localized bounding coordinates
  exist …".
- **Partial coverage**: the example document publishes the page-0 limit "OCR
  verification was not run on page 0." inside `#accessible-text-equivalent`
  (`role="region"`, labelled). The imported sealed report shows `1 Unsupported`
  in the stats group, lists `c_alignment` under `role="list"` "Incomplete
  checks detail" with the recorded reason, summarizes "2 checks completed · 1
  incomplete or unsupported", and the `aria-live="polite"` export preview
  reports "Checks complete 2 / 3".

### 4. 400% zoom (`400% zoom equivalent …`)

Viewport `320×256` (the 1280px-at-400% reflow equivalent). No
`documentElement`-level horizontal overflow; a finding selects via keyboard;
the in-app `+` shortcut reaches `400%` with overflow contained inside the
stage's scroll container (the page itself still does not scroll horizontally);
`n` finding navigation and text-equivalent `Select` focus remain operable.

### 5. Reduced motion (`reduced motion: prefers-reduced-motion …`)

Baseline: `#document-paper` has a live `120ms` transform transition
(`--motion-state`). With `page.emulateMedia({ reducedMotion: "reduce" })`:
`matchMedia` reports reduce, `--motion-state` computes to `0ms`
(`tokens.css:71`), and the universal `global.css:41` rule drops computed
`transition-duration`/`animation-duration` to `0.01ms` on the paper container
and the Button-component export buttons.

### 6. Automated sweep (two axe legs)

- `loaded workspace states`: intake surface, `?example=true` listed,
  `?example=scan` listed — all zero serious/critical.
- `with a finding expanded`: **fails honestly** — see finding T37-F1. Full
  node detail is written to `artifacts/a11y/axe-expanded-finding.json` on each
  run.

## Product findings

Severity is about the accessibility contract, not code quality. None of these
were patched — T37 scope is tests/docs/artifacts only.

### T37-F1 — `nested-interactive` (axe, serious): finding `option` hosts focusable controls

`apps/web/src/features/viewer/ViewerStage.tsx` (~lines 347-424): each finding
card is `role="option"` + `tabindex="0"` and, once expanded, renders candidate
buttons (`OccurrenceCandidates`), the notes `textarea` and note buttons
(`FindingNotes`) inside the option element. axe-core reports
`nested-interactive` (serious) on the expanded card:

```
serious | nested-interactive | #finding-item-f_3b9b34d179df717d
  "Element has focusable descendants"
```

ARIA 1.2 marks `option` as children-presentational, so per-spec an assistive
technology may strip the nested controls' semantics (Chromium keeps
`role=button`; WebKit/Safari+VoiceOver is the risky combination and is a
manual-receipt item). Suggested direction for the owning task: make the card a
non-widget container (e.g. group/article with an inner selectable control) or
move interactive content out of the `option`.

### T37-F2 — page-level notice overclaims when occurrences carry estimated geometry

`apps/web/src/features/viewer/CanvasOverlay.tsx:66-74` shows
`#page-level-geometry-notice` ("…No localized bounding coordinates exist for
this reader.") whenever the selected finding's `alignment === "page_level"`,
even though the finding's named occurrences may carry `estimated` polygons —
and the highlight boxes are drawn. Observed on `?example=scan`
(`f_3b9b34d179df717d`): the live region announces "no bounding coordinates"
while 25 estimated-polygon highlights render. The copy should distinguish
"page-level claim" from "no coordinates exist", or key on actual geometry.

### T37-F3 — view-mode tablist is not keyboard-navigable

`apps/web/src/features/viewer/ViewerStage.tsx:186-207`: `role="tablist"` tabs
use roving `tabIndex` but implement no `ArrowLeft`/`ArrowRight`/`Home`/`End`
handling, so the two unselected tabs (`tabindex="-1"`) can never receive
keyboard focus — the tablist's own contract is broken. The mode function
itself stays keyboard-operable via the `f` stage shortcut (verified in the
core-flow leg), so this is a defect in the widget's expected interaction, not
a blocked flow.

### T37-F4 — dead transition tokens on finding cards

`apps/web/src/features/viewer/ViewerStage.module.css:143` and
`apps/web/src/features/findings/FindingCard.module.css:209` reference
`--duration-fast`/`--ease-standard`, which are never defined (tokens define
`--motion-state`/`--motion-panel`). The declarations are invalid and the
transitions never apply — harmless for motion-sensitive users, but the
intended card feedback is silently absent.

### Observations (not violations)

- The scan report puts ~44 tab stops inside `#viewer-stage` — mostly the 25
  per-occurrence `Select` buttons in the text equivalent. Correct order, but
  long; a skip mechanism or grouping would help heavy documents.
- Hash-only navigation between `/#/workspace` variants fires `hashchange`
  without remounting; a loaded document/report persists across the change and
  `?example=true` does not re-seed the example. Tests use `page.reload()` to
  get a clean state (`gotoFresh`).
- `#page-level-geometry-notice` is the only `role="status"` that fires on
  finding selection; selection state itself is conveyed by `aria-selected` on
  the focused option (correct listbox semantics).

## Manual checklist (second acceptance leg)

`python scripts/check_manual_receipts.py accessibility` is **not implemented
in this worktree** — the manual-receipt checker is the coordinator's
check-pointed scope. Until it exists that command leg reports blocked, which
is expected. The automated legs above cover what is machine-verifiable; the
items below are what a manual AT pass must still record (from
`planning/product/ACCESSIBILITY.md` A01–A14), with evidence under
`artifacts/a11y/manual/`:

| Case    | Manual procedure                                                                                                       | Blocking for release                                                               |
| ------- | ---------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| A01/A04 | Full keyboard pass incl. region-selection entry and every dialog's Tab/Escape/focus-return on the real OS/browser pair | Yes (automated covers workspace flow; region-selection open path needs a real run) |
| A02     | Canvas hidden: text equivalent alone explains file/page/reader/occurrence/limits and export                            | Yes — SR browse-mode read of `#accessible-text-equivalent`                         |
| A03     | Region selection by numeric boundary / occurrence action without pointer                                               | Yes — not exercised by automation                                                  |
| A05     | 320 CSS px reflow + 200% text + 400% browser zoom on real displays                                                     | Automated proxy passes; visual pan check is manual                                 |
| A06     | Contrast of all token pairs incl. focus ring vs. adjacent surfaces                                                     | Yes — needs measured ratios                                                        |
| A07     | Grayscale: reader identity, ambiguity, coverage, priority survive without color                                        | Yes — manual/visual                                                                |
| A08     | Reduced motion on real OS setting (not only emulation)                                                                 | Covered partially; OS-level confirmation manual                                    |
| A09     | Slow OCR / failed model / cancellation announcements — polite, no chatter                                              | Yes — needs a real run with slow/cancelled checks                                  |
| A10     | NVDA+Firefox on Windows, VoiceOver+Safari on macOS/iOS through open → findings → export                                | **Yes — highest value; T37-F1's real AT impact is decided here**                   |
| A11     | Many-occurrence navigation, page/filter change focus retention                                                         | Yes                                                                                |
| A12     | RTL/CJK reading display, direction isolation (`<bdi>` used in card readings)                                           | Yes — needs RTL fixture                                                            |
| A13     | Typing in notes/region inputs never triggers single-key shortcuts; shortcuts toggle works                              | Automated covers the note case; region input manual                                |
| A14     | Touch 390×844: 44px targets, no hover dependency                                                                       | Yes — device check                                                                 |

Record per run: browser/OS/AT exact versions, steps, observed result, and the
screenshot/DOM receipt path — actual results, not inferred conformance.
