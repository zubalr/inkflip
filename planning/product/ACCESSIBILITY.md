# Accessibility acceptance plan

Target WCAG 2.2 AA behaviors for the application; this is not a claim that the inspected PDFs are accessible or that the product certifies their accessibility. The test suite combines automated checks with actual keyboard/screen-reader operation. Test targets remain proposed until receipts exist.

| Test | Procedure | Acceptance |
|---|---|---|
| A01 Complete keyboard investigation | Open example, flip, choose reader, select occurrence, open details, export, clear without pointer | Every action reachable; logical focus; no trap; visible focus never covered |
| A02 Canvas alternative | Hide canvas and use the named reading list | File/page/reader/occurrence/limits and export still understandable; no fake transcription of raster |
| A03 Region selection | Select via numeric boundaries or occurrence keyboard action | Same canonical region as pointer path; padding announced before OCR |
| A04 Dialog focus | Open export/replace/help; Tab/Shift-Tab; Escape | Focus stays in active modal, background inert, Escape returns trigger, unsaved choices not silently lost |
| A05 Reflow | 320 CSS px, 200% text, 400% zoom at desktop baseline | No outer horizontal overflow or clipped action/error; 2D PDF pan stays inside stage |
| A06 Contrast | Compute all foreground/background tokens and inspect focus/overlay combinations | Text 4.5:1 normal, 3:1 large; active UI/focus indicator >=3:1 against adjacent surface |
| A07 Non-color meaning | Grayscale render or ignore colors | Reader identity, ambiguity, coverage and priority remain available as text/styles |
| A08 Reduced motion | Emulate prefers-reduced-motion | No crossfade/panel animation; no autoplay or fake scan; all state changes clear |
| A09 Progress/errors | Slow OCR, failed model, cancellation, unsupported check | Polite stage announcements, no repeated percentage chatter; errors associated with check and recovery action |
| A10 Screen readers | NVDA+Firefox on Windows, VoiceOver+Safari on macOS/iOS | Reader tabs, result list, dialog and download workflow work; record actual platform versions |
| A11 Virtualization | Navigate many occurrences then change page/filter | Focus retained or explicitly moved to filter heading; selected item not silently unmounted |
| A12 Text direction | Arabic/CJK native readings, LTR amount with RTL filename | Direction-isolated display; Unicode strings unchanged; logical order and visual order not conflated |
| A13 Shortcuts | Type in annotation, numeric region and file dialogs | No single-character action triggers while typing; shortcuts can be disabled |
| A14 Touch | 390×844, browser text enlargement, on-screen keyboard | >=44px targets, no hover dependency, sticky actions do not obscure focus |

Use axe as a useful automated signal, not certification. Zero serious/critical automated violations and zero blocked critical keyboard flows gate release. Manual screen-reader test failures are not waived by an automated score. Copy must keep ambiguity/incomplete work prominent; interpreting zero findings as a safety certificate is a design defect even when ARIA is syntactically correct.

Record screenshots, DOM snapshots, test version, browser/AT version, steps, observed result and remaining limitation. Permissioned human clarity tasks are optional recruitment-dependent evidence; keyboard and automated tests are not optional. See `quality/TEST_MATRIX.md` and task T37 for implementation mapping.
