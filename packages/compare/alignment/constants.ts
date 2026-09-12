/**
 * region-match-v1 frozen parameters.
 *
 * These are the starting thresholds named by
 * `planning/architecture/ALIGNMENT_AND_FINDINGS.md` and frozen before
 * evaluation (T12/E02). They are algorithm diagnostics, not learned
 * weights and not probabilities — a consumer must not average them into
 * a confidence score (I06).
 */

export const REGION_MATCH_V1 = Object.freeze({
  version: 'region-match-v1' as const,

  /** Match-cost weights: geometry 0.65, order 0.20, text 0.15. */
  weightGeometry: 0.65,
  weightOrder: 0.2,
  weightText: 0.15,

  /** Accept a matched pair only when its cost is at most this. */
  acceptCost: 0.45,

  /**
   * Accept only when the next competing assignment costs at least this
   * much more than the chosen one. Below the margin the pair abstains
   * as `ambiguous` with every candidate kept accessible — never a
   * first-match-wins guess.
   */
  minMargin: 0.12,

  /**
   * Maximum contiguous fragments per candidate span on either side —
   * bounds split/merged-word recovery to local windows.
   */
  maxSpanFragments: 4,

  /**
   * A local component with more than this many candidate fragments on
   * either side abstains to region-level comparison instead of running
   * an expensive global search.
   */
  maxComponentFragments: 64,

  /** Candidate admission: vertical-band overlap >= this of smaller height. */
  verticalOverlapMin: 0.5,

  /** Candidate admission: horizontal gap <= this x median line height… */
  horizontalGapLineHeights: 1.5,
  /** …and never more than this many canonical points. */
  horizontalGapMaxPt: 24,

  /**
   * Per-fragment cost of leaving a reading unmatched inside the bounded
   * assignment. Set just above `acceptCost` so a barely-acceptable match
   * is preferred over two unmatched readings while a genuinely bad one
   * is not forced.
   */
  unmatchedPenalty: 0.5,

  /**
   * Per-pair granularity preference inside the bounded assignment
   * (this many cost units off each matched pair). Without it, merging
   * whole lines into one span would always "win" because the text
   * distance averages a local difference across the longer string —
   * defeating per-fragment localization. At 0.2 >= minMargin the
   * preference is decisive: a coarser decomposition can never be a
   * near-tie, while competition at the same granularity is still pure
   * cost. The acceptance cost thresholds above apply to the unmodified
   * pair cost, never to this bookkeeping term.
   */
  pairPreference: 0.2,

  /**
   * Geometry-distance expansion of candidate extents before the overlap
   * ratio: half the horizontal-gap tolerance each side and a quarter of
   * the smaller span height vertically.
   */
  geometryExpandYFraction: 0.25,
});

/**
 * Every exported score component is an algorithm diagnostic for review
 * and threshold evaluation — never a probability, confidence or risk
 * value (I06).
 */
export const SCORE_SEMANTICS = 'algorithm_diagnostics_not_probability';
