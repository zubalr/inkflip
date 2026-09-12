# T12 experiment receipt — assignment granularity and margin model

Two design alternatives were measured on synthetic smoke harnesses during
implementation and rejected; the chosen parameters are documented in
`packages/compare/alignment/constants.ts` and `match.ts`. No evaluation
fixtures or reserved labels were touched — inputs were hand-constructed
occurrence lists.

## E-T12-1: unweighted granularity (rejected)

**Setup.** Three left/right occurrences on one line (`"Item $100"`,
`"Item $200"` left; `"Item"`, `"$200"` fragmented right in the same
region): identical geometry, contiguous spans of 1–4 fragments allowed.

**Measured behavior (before `pairPreference`).** The whole-line `3:3`
span pairing won the bounded assignment over three `1:1` pairings:
averaging a local text difference across the longer concatenated string
made the blob cheaper than the sum of per-fragment costs. All three
occurrences on both sides surfaced as `ambiguous` — the engine lost
per-fragment localization exactly where the demo needs it.

**Decision.** Added `pairPreference` (0.2): a per-pair bookkeeping term
inside the assignment minimizer only, never part of the reported pair
cost. At `0.2 >= minMargin` a coarser decomposition can never be a
near-tie, while same-granularity competition remains pure cost. Re-run:
three `unique` one_to_one matches, margins 0.155–0.2, split/merge spans
still win whenever their pair cost genuinely dominates (verified by the
`one_to_many` test).

## E-T12-2: non-crossing margin only (rejected)

**Setup.** Five identical `"x"` occurrences at identical geometry on both
sides — the spec's tie case ("repeated identical strings retain separate
ordinals; a tie remains `ambiguous`").

**Measured behavior (before exchange pass).** Forbidding a chosen pair
inside the non-crossing model could only reach coarser/finer
decompositions, floored at the `pairPreference` margin (0.2) or the
unmatched penalty (0.5): every margin stayed `>= 0.12`, so `tie`
abstention could never fire — dead acceptance logic.

**Decision.** Kept the non-crossing optimum (crossing assignments are
never *accepted* — the geometry/order agreement requirement), but
compute each chosen pair's margin as the min of (a) the non-crossing
re-solve and (b) bounded local exchanges: every candidate pair sharing a
fragment may conflict with at most two other chosen pairs, and displaced
fragments are rescued by a fresh bounded solve or left unmatched.
Re-run: all five occurrences `ambiguous` with `reason: tie`,
`margin: 0.1 < 0.12`, 27 candidates accessible per contested unit.

**Rejected along the way:** accepting crossing assignments outright
(violates the geometry/order agreement requirement — a positional cross
must surface as ambiguity, never as a `unique` claim) and first-match
short-circuiting (spec forbids first-match-wins).
