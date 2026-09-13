# T20 independent review — repeated/ambiguous/order/unmatched evidence UX

Reviewer: independent explore subagent (read-only), two rounds.
Implementation: `102b79e` (initial), `a3f1eef` (round-1 fixes), `cbfd8d4` (round-2 fixes).
Worker: Devin coordinator (this session).

## Round 1 — verdict: CHANGES-REQUIRED

### Blocker
- **F1** `OccurrenceCandidates.tsx` — candidate `onClick` lacked `stopPropagation`; clicks bubbled to the finding card's `onClick` → `handleSelectFinding` overwrote the pick (`occurrence_ids[0]` or `null`). First-candidate-wins persisted for mouse input; the spec only exercised keyboard. **Fixed in `a3f1eef`** + new pointer-click spec leg asserting the pick sticks and survives clicks inside the detail body.

### Majors
- **F2** `findings.ts` — order-only finding copy asserted "same readings" unconditionally, but `order_differences` entries can pair differing texts (a fabricated-certainty violation). **Fixed**: order-only findings are now emitted only when `groupText(left) === groupText(right)`; differing-text inversions remain `reading_difference` findings.
- **F3** `classify.ts` — one-sided `page_level` findings were classified `page_level` ("this comparison is page-level"), claiming a comparison that never ran. **Fixed**: one-sided kinds resolve before the `page_level` label.
- **F4** `findings.ts` — ambiguous findings named only the contested unit's spans; `entry.candidates` can touch rival occurrences that then vanished from the UI. **Fixed**: `occurrence_ids` now unions every evaluated candidate pair.

### Minors (fixed)
- F5 order-only findings no longer preselect; detail-panel clicks and keep-evidence Enter/Space no longer bubble into finding re-selection.
- F7 chosen occurrence renders `highlightSelected`; other named candidates render the pre-existing `highlightAmbiguous` dashed style.
- F8 redundant `aria-current` dropped (aria-pressed retained).
- F9 stale comment corrected.

## Round 2 — verdict: APPROVE-WITH-NOTES

All round-1 items verified fixed with correct semantics. New issues found and fixed in `cbfd8d4`:

- **N1** detail-panel `onKeyDown` stopPropagation killed global shortcuts (n/p/f/r/+/-) while focus was inside the detail — now shields only Enter/Space.
- **N2** candidate styling landed on settled differences' counterparts — now gated to ambiguous/order-only findings; settled named occurrences stay co-equal selected evidence.
- **N3 (pre-existing, exposed)** page-level notice keyed on `alignment === "not_applicable"` and lied for order-only findings naming polygon'd occurrences — now keys on actual polygon absence or `page_level` alignment.

## Inspected-but-untested seams (recorded honestly)

- The deterministic `?example=true` document exercises the ambiguous-finding UI; no real-pipeline fixture currently produces an `ambiguous` alignment entry, so F4's union path is verified by code inspection against `match.ts` `candidatesFor`, not by a browser run.
- No fixture combines an order inversion with a text difference; the F2 gate is verified against the match loop's identical `groupText` comparison (equal→order-only, differing→reading_difference are mutually exclusive by construction).
- Real-pipeline order-only and unmatched behavior *was* probed end-to-end against a Vite dev server with the real PDF.js/Tesseract stack before the spec existed (reordered-stream fixture → `emission_order_differs`; tiny fixture → unmatched), probe file removed after use.

## Known remaining limitations (accepted, recorded)

- `role="option"` finding cards contain focusable descendants (candidates, keep-evidence) — invalid strict listbox ARIA; pre-existing structure, changing it would churn T13 contract surface.
- `isOrderOnlyFinding` detects order-only findings via the basis marker string — imported reports with differently worded bases classify as `one_sided` rather than `order_only` (conservative under-label, never a false claim).
- `initialFindingId` useEffect re-fire and unclamped `pageOccurrences` filter — pre-existing, unreachable in current composition.
- CanvasOverlay.tsx / findings.ts sit outside the task brief's owned paths (viewer scope); disclosed here as coordinator-seam edits reviewed in this artifact.

## Verdict

Approve. Evidence-first semantics preserved: no fabricated certainty, order-only stays order-only, unmatched stays unmatched, every evaluated candidate stays individually addressable by id.
