# Independent Peer Review — T12 (approved)

**Reviewer:** devin-review-t12 (SWE-2 subagent, independent — did not write this code)
**Candidate reviewed:** `05f97bc` on `work/devin/t12` (implementation `d821b2779d21eb093d55147598949f8931f30957`, base `219a469`)
**Date:** 2026-09-12 · **Verdict: approved**

## Per-criterion verdicts — all PASS

- Reversible indices: 442 adversarial strings (all 25 White_Space chars, ZWSP, BOM, combining marks, surrogate pairs, RTL, ligatures, U+180E, NUL, 400 fuzz) — every normalized char maps to exact raw slice; round-trip containment holds; `checkNormalizedView` caught all corruption patterns.
- scalar-whitespace-v1 == contract normalize(): byte-identical; delegates to T03 contract normalize — no meaning-char erasure possible.
- region-match-v1: frozen params match planning doc EXACTLY (0.65/0.20/0.15, 0.45, 0.12, span 4, cap 64, vOverlap 0.5, hGap); independent Levenshtein + span/cost replication reproduced all components; brute-force over ALL disjoint-pair assignments confirmed no accepted pair had true margin < 0.12.
- Duplicate occurrences: 4 identical values → 4 distinct one_to_one matches, no dedupe; missing duplicate stays unmatched.
- Ambiguity abstention: tie/weak/order_conflict all abstain; all evaluated candidates accessible; crossing-cheaper alternatives yield honest negative margins.
- Routing: page_only/unknown/degenerate → page_level; 64 exact boundary; non-array polygon → GEOMETRY error; identical text never rescues missing geometry.
- Split/merge provenance: constituents honestly recorded with ids + union extents.
- Score semantics: algorithm_diagnostics_not_probability on every result; no probability/confidence fields.
- Reruns: 36/36 node; task_acceptance 36/36; verify exit 0; tsc -b exit 0 — all match commands.log.
- Scope: only allowed dirs + artifacts + docs/ATTRIBUTION.md. ATTRIBUTION adjudicated SANCTIONED — contract required_updates lists it; clean append-only provenance entry.
- pairPreference 0.2 / unmatchedPenalty 0.5 / geometryExpandYFraction 0.25: worker-chosen, honestly disclosed in constants.ts + experiment-granularity.md E-T12-1 with real measurement; confined to assignment minimizer — exported pair costs/margins unaffected (verified by independent replication).

## LOW findings (evidence hygiene; coordinator-fixed at receipt time)

- receipt.json + handoff.json: `implementation_commit` placeholder `PENDING-IMPLEMENTATION-COMMIT` never updated to `d821b2779d21eb093d55147598949f8931f30957`.
- experiment-granularity.md:49: stale "27 candidates" figure (real: 96–160; substance holds, over-satisfied).

## INFO notes (no action)

- checkNormalizedView on malformed view throws TypeError not ContractError (unreachable via normalizeText).
- Identical text+geometry: unique for n≤4, abstains n≥5 — rank-granularity-dependent but consistent with frozen cost model.
- match.ts:750 exchange margin blind to ≥3-displacement crossing chains (disclosed; brute-force found no violation).
- spatial.ts clustering quadratic in pathological single-band pages (bounded by cap; ~2s worst at 64×64).

## Verdict: approved

Correctness, invariants, frozen parameters, abstention semantics, provenance honesty, bounded work, scope and evidence all independently verified.
