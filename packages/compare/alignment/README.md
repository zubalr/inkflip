# `@inkflip/compare/alignment` — region-match-v1 (T12)

Geometry-first, uncertainty-preserving alignment of two readers'
occurrences on one document page. Conservative by construction: it never
fabricates geometry, never collapses duplicate occurrences, never picks
a first match to break a tie, and reports every score component as an
**algorithm diagnostic — never a probability** (I06).

## Pipeline

1. **Classify.** Only same-page occurrences with validated `exact` or
   `estimated` geometry and a non-degenerate polygon enter localized
   matching. `page_only`/`unknown`/degenerate inputs are reported
   page-level; identical text elsewhere cannot rescue them (I04/I11). A
   selected region is a hard scope — not a hint to take the nearest text
   anywhere on the page.
2. **Spatial index.** Fragments cluster into line-runs by vertical-band
   overlap (≥ 0.5 of the smaller height); runs split on horizontal gaps
   > `min(1.5 × median line height, 24 pt)` so two columns are never
   glued into one candidate. Left/right runs link into bounded local
   components through band overlap or polygon intersection.
3. **Candidates.** Contiguous spans of 1–4 fragments per side carry
   split/merge provenance; a pair must pass the geometric gate and its
   union must stay inside its line/region.
4. **Cost.** `0.65·geometry + 0.20·order + 0.15·text`, each clamped to
   [0,1]. Text distance is scalar Levenshtein normalized by max length,
   with material scalars (digits, currency, signs, dashes) never cheap
   to edit (F15).
5. **Bounded assignment.** A non-crossing minimum-cost solve per
   component, `O(n·m·16)` on components capped at 64 fragments per side;
   larger components abstain to region-level comparison. A pair reports
   `unique` only when cost ≤ 0.45, the next competing assignment —
   including bounded local exchanges that let a losing fragment rematch
   or stay unmatched — costs ≥ 0.12 more, and geometry/order agree.
   Ties, inversions and weak agreements stay `ambiguous` with every
   evaluated candidate kept accessible.

## Files

| file | contents |
| --- | --- |
| `constants.ts` | frozen `REGION_MATCH_V1` parameters + `SCORE_SEMANTICS` |
| `text.ts` | scalar Levenshtein with material-substitution cost |
| `spatial.ts` | fragment/line-run/block construction + counters |
| `match.ts` | classification, candidate spans, pair costs, bounded assignment, margin/exchange abstention, order differences |
| `index.ts` | public surface |

## Result vocabulary

`unique` · `ambiguous` (`tie` | `order_conflict` | `weak`) · `unmatched`
· `abstained` (`component_too_large`) · `page_level` · `out_of_scope`;
matches carry `one_to_one` / `one_to_many` / `many_to_one` /
`many_to_many` provenance plus per-side extents, margins and the three
score components. `order_differences` reports emission-order inversions
between matched units as diagnostics — changed column order is
information, never an accessibility verdict.

## Executable example

```sh
node --input-type=module -e '
import { alignPage } from "./packages/compare/alignment/index.ts";
import { normalizeText } from "./packages/compare/normalization/index.ts";
const geo = (b) => ({ precision: "exact", space: "canonical_page",
  polygon: b ? [[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]] : null,
  transform_ids: [], basis: "demo" });
const occ = (id, o, t, b) => ({ id, page_index: 0, ordinal: o,
  normalized_text: normalizeText(t).text, geometry: geo(b) });
const res = alignPage(
  [occ("l0", 0, "$1,000.00", [0, 0, 80, 10])],
  [occ("r0", 0, "$1,O00.00", [0, 0, 80, 10])]);
console.log(res.matches[0].provenance, res.matches[0].components);
'
```

Tests: `node --test tests/alignment/alignment.test.mjs`
