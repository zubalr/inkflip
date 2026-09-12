/**
 * @inkflip/compare/alignment — region-match-v1 bounded matching.
 *
 * Public surface: `alignPage` plus the frozen parameters, score
 * components (algorithm diagnostics, never probabilities) and the
 * bounded-work counters that evidence "no unbounded quadratic
 * matching". Shared contract types come from `@inkflip/contracts`;
 * geometry helpers from `@inkflip/geometry`; neither is redefined.
 */

export { REGION_MATCH_V1, SCORE_SEMANTICS } from './constants.ts';
export {
  normalizedTextDistance,
  scalarLevenshtein,
} from './text.ts';
export {
  boundsOf,
  boundsWithin,
  boxArea,
  boxPolygonOf,
  buildBlocks,
  buildLineRuns,
  horizontalGap,
  horizontalGapTolerance,
  medianFragmentHeight,
  polygonsIntersect,
  unionBounds,
  verticalOverlap,
} from './spatial.ts';
export type {
  Block,
  Fragment,
  LineRun,
  SpatialCounters,
} from './spatial.ts';
export { alignPage } from './match.ts';
export type {
  Abstention,
  AbstentionReason,
  AlignableOccurrence,
  AlignedOccurrence,
  AlignmentDiagnostics,
  AlignmentOptions,
  AlignmentResult,
  AlignmentStatus,
  AmbiguityReason,
  AmbiguousEntry,
  AcceptedMatch,
  CandidateView,
  OrderDifference,
  Provenance,
  RegionScope,
  ScoreComponents,
} from './match.ts';
