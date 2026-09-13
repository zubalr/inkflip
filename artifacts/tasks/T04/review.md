# Independent Peer Review — T04 (approved)

**Reviewer:** devin-review-t04 (SWE-2 subagent, independent — did not write this code)
**Candidate reviewed:** `e414d85` on `work/devin/t04` (implementation `7cda7a671c82e563e9bcc18f17dd63f6acb71f95`, base `c12e680`)
**Date:** 2026-09-12 · **Verdict: approved**

## Per-criterion verdicts — all PASS

- All four rotations/nonzero origins/UserUnit worked examples ≤1e-5pt: F07 (geometry-0/90/180/270 + control), F08 (UserUnit 0.5/1/2/10), 10k-point deterministic round-trip. `near()`/`nearMat()` assert the real bound on every anchor and matrix component. Reviewer hand-recomputed canonical/D/C⁻¹/recover matrices, geometry-270 below_crop chain, geometry-90 text anchor, skew parallelogram — all match golden exactly. Negative-origin MediaBox exercised; UserUnit applied exactly once.
- Singular transforms rejected: det≤1e-12 → `TRANSFORM` (0 and 1e-13 rejected, 1e-11 accepted); nonfinite/malformed → `NONFINITE`/`TYPE`.
- estimated/page-only polygons obey schema: `polygon===null` iff page_only/unknown enforced at construction; 3..64-vertex non-degenerate otherwise; emitted records pass real `validate()`; 13 invalid constructions rejected with correct codes.
- CSS/DPR criterion: sanctioned deferral per the criterion's own "once viewer integrates" clause; viewport zoom/pan vs independent goldens, page-bound records, DPR only at backingScale verified now.

## Substantiation

- Compose/inverse order verified by hand vs COORDINATES.md (`O = K·T·S·R·C`; `C·O⁻¹ = R⁻¹·S⁻¹·T⁻¹·K⁻¹`); stepwise chain equals composed output; ~200k randomized M·M⁻¹=I worst deviation 2.3e-10.
- Independent expectations genuine: `derive_expectations.py` uses `fractions.Fraction` + closed-form per-rotation equations, two derivation paths asserted equal — never executes the TS. `expected.json` regenerates byte-identical (`--check` exit 0). Anchored on published worked example + PDFium probe grids + fixture sha256/manifest.
- Clip honesty: inside/partial/outside correct on golden cases; source polygon deep-copied/untouched.
- Schema parity: ID pattern, ≤16 transform_ids, operation enum, field limits match `inkflip.schema.json`.
- Rerun reproduction: node 32/32 · task_acceptance T04 32/32 · pytest 6/6 · tsc -b exit 0 · derive --check fresh — all match commands.log.

## Worker caveats adjudicated

- `bun run verify` 1/49 failure confirmed T04-INDEPENDENT (T02 playwright install changed `test:browser` failure mode; identical without T04; documented in T02 commands.log:79-85 + proposal P2; fixed on main @7128350).
- oxlint env-blocked confirmed (missing platform binding; not in registered acceptance).
- Node 26.7.0 vs pinned 22.23.2 disclosed accurately; deterministic.

## Scope & evidence

15 files, all inside `packages/geometry/` + `tests/geometry/` + `artifacts/tasks/T04/`; planning/ untouched; no lockfile/manifest changes; receipt criteria cite only task-local paths.

## Non-blocking findings (follow-up to geometry owner)

1. LOW `clipToView` zero-area contact → `partial` + degenerate clipped polygon (`polygon.ts:183-199`); suggest treating zero-area clips as `outside`.
2. LOW `extent ?? DEFAULT_EXTENT` lets `[]` bypass the inverse-pair check (`affine.ts:168-177`, `geometry.ts:154`); `require(extent.length>0)` closes it.
3. INFO degenerate-area threshold 2× stricter than validator (conservative direction).
4. INFO vacuous `assert.ok(maxErr >= 0)` at `geometry.test.mjs:800` (real bound asserted separately).
5. INFO `pointInPolygon`/`mapPoint` exported but untested directly (probed correct; worth pinning).

## Verdict: approved

All acceptance criteria substantiated with genuine independently-derived evidence; counts reproduce exactly; verify failure provably pre-existing and already fixed on main; scope and evidence honesty clean.


---

## Delta review — 2026-09-13, evaluated `412fb9b2`

- **Reviewer:** devin-coordinator (acceptance refresh; not the implementing worker for this delta's shared changes)
- **Scope delta:** No owned files changed since the original review; the staleness was shared-input only (AGENTS.md, execution/config, bootstrap/coordination suites, merged fixture work).
- **Fresh run:** Re-ran all registered commands at `412fb9b2`: **47/47 green**, zero failures.
- **Verdict:** prior review stands; delta introduces no acceptance-relevant regression.
