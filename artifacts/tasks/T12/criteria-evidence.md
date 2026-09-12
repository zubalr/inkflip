# T12 acceptance criteria evidence

Every criterion was verified by `node --test tests/alignment/*.test.mjs`
(36 collected / 36 passed / 0 failed / 0 skipped) and re-executed by the
acceptance harness (`python3 scripts/task_acceptance.py task T12`, exit 0,
same counts). Test names below are the exact suite entries.

## "Digits/currency/sign/negation/combining marks cannot disappear"

Normalization (`tests/alignment/normalization.test.mjs`):

- `'1,000'`, `'1000'`, `'100'`, `'-100'`, `'−100'` (U+2212), `'+42.0'`,
  `'$1,000.50'`, `'€9.99'`, `'(100)'`, `'paid'`, `'not paid'` — all
  preserved scalar-exactly and still distinct after normalization
  ("digits, currency, signs and punctuation are never erased").
- `'cafe' + U+0301` survives as 5 scalars ("combining marks survive as
  separate scalars"); `'ﬁ'`, `'ﬃ'` never expand ("ligatures are
  preserved"); `'ABC ß İ'` is not casefolded; ZWSP/BOM survive because
  they are not `White_Space`.

Alignment (`tests/alignment/alignment.test.mjs`):

- `normalizedTextDistance('$1,000.00','$1,O00.00') === 2/15` — the
  `0`→`O` substitution costs 2 (material), never 1 ("differing text is
  allowed; material edits stay expensive").
- `normalizedTextDistance('not paid','paid') === 0.5` — negation loss is
  a measured distance, never erased.

## "four repeated equal values remain four occurrences"

F11 ("four repeated equal values remain four occurrences"): four `'100'`
occurrences per side at distinct positions → `left.length === 4`,
`right.length === 4`, all `unique`, four distinct `one_to_one` matches
covering `{l0..l3} × {r0..r3}`. The 4-vs-3 variant leaves `l2`
`unmatched` — never absorbed into a sibling's match.

## "ambiguous ties abstain"

Five identical `'x'` occurrences at identical geometry per side ("ambiguous
ties abstain with every candidate accessible"): `matches.length === 0`,
every ambiguous entry has `reason === 'tie'` and `margin === 0.1 < 0.12`,
`candidates.length >= 2`, and all ten occurrences report `ambiguous`.
Companion abstentions verified in the same run: `weak` (best agreement
above cost 0.45) and `order_conflict` (emission-order inversion inside a
linked block).

## "page-only inputs never become exact regional highlights"

"page_only and unknown precision never enter regional matching": a
`page_only` and an `unknown` left occurrence whose text is identical to
an exact-geometry right reading stay `page_level`; the right stays
`unmatched`; `res.page_level.left_occurrence_ids` lists both; no match
is produced — identical text cannot rescue missing geometry (I04/I11).
"degenerate polygons are page-level, never fabricated": a zero-area
polygon is `page_level` with `diagnostics.degenerate_geometry.left === 1`.

## "no unbounded quadratic matching."

"components over 64 fragments abstain to region-level comparison": a
70×70 linked component → `abstentions[0].reason === 'component_too_large'`,
`fragment_counts === [70,70]`, all occurrences `abstained`,
`blocks_abstained === 1` — the assignment solver never runs on it.
"work counters stay bounded: local windows, not page-quadratic": 20
isolated pairs → `span_gate_checks <= candidate_spans.left *
candidate_spans.right / 4` and `assignment_cells <= 65*65 *
assignments_solved` (every solve on a ≤64-fragment component grid).
