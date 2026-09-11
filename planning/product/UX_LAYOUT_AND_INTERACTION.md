# Visual composition and interaction specification

## Alternatives considered

**A — full-page flip canvas:** memorable and focused, but comparing long text requires repeated switching and hides limits. **B — two equal full-page panes:** excellent for engineers, but halves legibility on laptops and fails narrow screens. **C — document stage with an evidence slip:** a large document plus a compact selected-reading/evidence panel; supports a compelling flip without hiding the alternatives. **Choose C.** Compare mode can temporarily use two synchronized panes inside the stage; the default is not a dashboard.

## Desktop (>=1100 CSS px)

Maximum content width 1280, outer padding 32, header height 64. Header carries wordmark/descriptor left and Examples / How / For developers / Source right. Landing uses two editorial columns: the 64/1.07 serif headline, short body and 48px actions on the left (about520px), with a compact prepared-example stage on the right. The stage includes its reading switch, source crop, selected finding and coverage underneath. This keeps the actual disagreement visible above the fold. Body is18/1.5 with a comfortable line length. Opening a file expands into the workspace composition below; the compact hero is not the entire workspace.

Workspace stage: `grid-template-columns:minmax(0,1fr) 360px`, gap 24. Main paper has minimum width 480, height fit to viewport with a minimum 420 and bounded inner scrolling. Evidence slip contains the active reader name/version, a raw text region, selected finding and scoped coverage. Tools form one 48 px top toolbar; file title is truncatable local text with full accessible name, never a URL. Evidence detail uses a collapsible lower section, not several nested sidebars.

The wireframe below is the **expanded own-file workspace**; the landing uses the compact two-column hero illustrated in the reference.

```text
1280 maximum content width
┌─ 64h header: Inkflip / descriptor ───────── Examples / How / Developers ─┐
│  Your PDF can look right                                                │
│  and read wrong.              [Try the example] [Open locally]          │
├─ stage toolbar: Page | Reading | Compare ───── Fit / − / + / Rotate ─────┤
│  document paper / bounded page canvas       │ evidence slip 360px      │
│  generous paper margins                    │ named readers            │
│  active region + labelled border           │ plain-language finding   │
│                                            │ actual raw text          │
│                                            │ What was checked         │
├─ selected findings strip / next occurrence / Keep this evidence ────────┤
└─ six examples + how it works + developer continuation ──────────────────┘
```

## Intermediate (768–1099)

Outer padding24, heading52. Landing becomes one column; workspace evidence slip moves below the paper as a two-column summary. Compare mode stacks Page then Reading with shared selected region; do not squeeze two unreadable full pages. The findings strip scrolls horizontally with visible previous/next buttons and keyboard access, but every finding remains in a navigable list. Dialog width max 680, never viewport-edge clipped.

## Narrow (320–767)

Outer padding 16 (12 below 360), heading 42/1.08 at 390 and 36 below 360. Header reduces to brand plus a labeled Menu button. On the landing view, the live/prepared example stage follows the compact headline before longer explanatory copy, so the Page/Reading control and crop are immediately available. Hero actions stack with full-width48px targets below that stage; explanatory text follows. In the workspace, file actions remain in the accessible toolbar. Stage toolbar wraps to two rows; Page/Reading tabs stay visible. The paper is full width with fit-to-width default and deliberate inner pan after zoom; outer page never scrolls horizontally. Evidence appears immediately below the active crop, not offscreen in a hidden drawer. A sticky bottom bar offers “Findings” and “Keep evidence” only after results exist, above safe-area inset. It must not obscure keyboard focus or browser controls.

At390×844, the example label, amount crop and flip button must be visible together within the initial viewport; the detailed finding/coverage continuation may extend below it. The reference orders long explanatory copy after the stage on narrow screens. OCR on mobile is not implied by the gallery animation; show the lighter-profile limits before a user starts. At 400% desktop zoom, layout becomes the narrow composition rather than overlapping controls.

## Source synchronization

Page and reading selection use occurrence IDs. Selecting a finding sets page, region and reader pair, scrolls the page to the region using the current transform, and marks the matching raw spans. Never scroll by searching DOM text alone. Pointer selection leaves focus at the clicked control; keyboard activation moves focus to the detail heading and Escape returns it to the triggering finding. Hover previews must not be the only way to see evidence.

Zoom range is 25–400%, clamped by raster budget; rerender at improved resolution only when budget allows. CSS scaling remains available while a new bounded render loads. Pan uses space-drag only while stage focus is active; keyboard arrow buttons and scrollbars are always available. Rotate is view-only in quarter-turns, preserves source coordinates, and cancels/restarts only the render that depends on that viewport. OCR operates on its immutable recorded raster, not whatever view rotation happens afterward.

Repeated occurrences display “Occurrence 2 of 4” and page/location information. Ambiguous matches use dashed borders and a clear text label; unique API geometry uses a solid outline, estimated geometry a dotted outline. Reader A/B colors are paired with labels and different border styles. No red/green correctness palette. Structural modes and hypotheses do not reuse the appearance of measured reader differences.

## Keyboard and focus

All primary actions are native buttons/links. Tabs use roving tabindex, arrow movement and explicit Space/Enter activation when activation could download or compute. Region selection has a keyboard alternative: choose a text occurrence/line or enter four canonical boundaries; announce selected bounds and enable an explicit “Use region” button. Pointer drag is optional, never required.

Optional single-character shortcuts are confined to a focused stage and are disabled while editing any field: F flip, +/− zoom, R rotate, N/P next/previous finding. Provide a visible disable-shortcuts control; the application does not intercept global browser file/history shortcuts. Escape closes the top dialog, otherwise cancels a pending drag, never silently deletes evidence. Dialogs restore focus, label warnings and make the rest of the page inert.

## Motion and loading

Use 120 ms crossfade for Page/Reading, 180 ms panel expansion. No 3D card trick suggesting a live PDF process and no fake scan lines. Reduced-motion sets transitions to zero and uses static progress text. Skeletons are reserved for genuinely waiting previews, not replayed prepared results. Progress has named units/stage; model download and processing do not share a fabricated percentage.

The [reference](../reference/index.html) illustrates the selected composition with actual native fixture images. It is explicitly not a live browser processing implementation. Its screenshot audit is separate from eventual UI acceptance.
