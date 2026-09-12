/**
 * region-match-v1 — geometry-first, uncertainty-preserving alignment of
 * two readers' occurrences on one document page.
 *
 * Pipeline (planning/architecture/ALIGNMENT_AND_FINDINGS.md, contract
 * 1.0.0):
 *
 *   1. Only occurrences on the same page with non-null validated
 *      geometry enter localized matching. `page_only`/`unknown`
 *      precision (and degenerate polygons) are reported page-level —
 *      missing geometry is never recovered by finding the same string
 *      elsewhere (I04/I11).
 *   2. Fragments cluster into line-runs by baseline proximity; runs
 *      split on large horizontal gaps so two columns are never glued
 *      into one candidate. Left/right runs link into bounded local
 *      components through overlapping vertical bands or polygon
 *      intersection.
 *   3. Candidate spans are contiguous groups of at most four fragments
 *      on either side (split/merge provenance). A candidate pair must
 *      pass the geometric gate and a span's union must stay inside its
 *      line and inside any selected region — a user-selected region is
 *      a hard scope.
 *   4. Pair cost = 0.65*geometry + 0.20*order + 0.15*text distance,
 *      each clamped to [0,1]. Differing text is allowed — the amount
 *      demo depends on it — but digit/sign edits are never cheap.
 *   5. A bounded non-crossing assignment is solved per component. A
 *      pair is reported `unique` only when cost <= 0.45, the next
 *      competing assignment costs >= 0.12 more, and geometry/order
 *      agree on the block. Ties and contradictions abstain as
 *      `ambiguous` with every candidate kept accessible; components
 *      over 64 fragments per side abstain to region-level comparison.
 *
 * Score components are exported as algorithm diagnostics for review —
 * never probabilities (I06). The matcher never modifies an input
 * occurrence.
 */

import { ContractError, require } from '../../contracts/src/index.ts';
import type {
  Box,
  Geometry,
  Occurrence,
  Point,
} from '../../contracts/src/index.ts';
import { REGION_MATCH_V1, SCORE_SEMANTICS } from './constants.ts';
import { normalizedTextDistance } from './text.ts';
import {
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
import type { Block, Fragment, LineRun, SpatialCounters } from './spatial.ts';

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/** The occurrence fields the matcher reads — a subset of contract Occurrence. */
export type AlignableOccurrence = Pick<
  Occurrence,
  'id' | 'page_index' | 'ordinal' | 'normalized_text' | 'geometry'
>;

/** Optional hard scope: a canonical-space region polygon. */
export interface RegionScope {
  readonly polygon: readonly Point[];
}

export interface AlignmentOptions {
  /** Page to align; required when inputs span more than one page. */
  readonly page_index?: number;
  /**
   * User-selected region: a hard scope. Only fragments intersecting it
   * participate and candidate unions must stay inside its bounds —
   * never an instruction to take the nearest text anywhere on the page.
   */
  readonly region?: RegionScope | null;
}

/** The three clamped cost inputs and their weighted sum. Diagnostics. */
export interface ScoreComponents {
  readonly geometry_distance: number;
  readonly order_distance: number;
  readonly text_distance: number;
  readonly cost: number;
}

/** 'one_to_one' | 'many_to_one' | 'one_to_many' | 'many_to_many'. */
export type Provenance =
  | 'one_to_one'
  | 'many_to_one'
  | 'one_to_many'
  | 'many_to_many';

/** An accepted unique match with its split/merge provenance. */
export interface AcceptedMatch {
  readonly left_occurrence_ids: string[];
  readonly right_occurrence_ids: string[];
  readonly provenance: Provenance;
  readonly components: ScoreComponents;
  /** Cost gap to the next competing assignment (>= minMargin). */
  readonly margin: number;
  readonly extent_left: Box;
  readonly extent_right: Box;
}

/** One evaluated candidate pairing, kept accessible under ambiguity. */
export interface CandidateView {
  readonly left_occurrence_ids: string[];
  readonly right_occurrence_ids: string[];
  readonly components: ScoreComponents;
}

export type AmbiguityReason = 'tie' | 'order_conflict' | 'weak';

/**
 * A matched unit the engine refuses to settle: the next competing
 * assignment was too close (`tie`), emission order contradicted
 * geometry (`order_conflict`), or the best available agreement was
 * still too weak to claim (`weak`). Every evaluated candidate stays
 * accessible — abstention, never first-match-wins.
 */
export interface AmbiguousEntry {
  readonly reason: AmbiguityReason;
  readonly left_occurrence_ids: string[];
  readonly right_occurrence_ids: string[];
  readonly components: ScoreComponents;
  readonly margin: number;
  readonly candidates: CandidateView[];
}

export type AbstentionReason = 'component_too_large';

/** A component that exceeded the bounded-matching cap. */
export interface Abstention {
  readonly reason: AbstentionReason;
  readonly left_occurrence_ids: string[];
  readonly right_occurrence_ids: string[];
  readonly fragment_counts: [number, number];
}

/** Per-occurrence outcome vocabulary (extends the contract's finding terms). */
export type AlignmentStatus =
  | 'unique'
  | 'ambiguous'
  | 'unmatched'
  | 'abstained'
  | 'page_level'
  | 'out_of_scope';

export interface AlignedOccurrence {
  readonly occurrence_id: string;
  readonly status: AlignmentStatus;
  /**
   * Index into `matches`, `ambiguous` or `abstentions` when the status
   * is unique/ambiguous/abstained; null otherwise.
   */
  readonly detail_index: number | null;
}

/** A matched pair whose emission order disagrees between the readers. */
export interface OrderDifference {
  readonly kind: 'emission_order_differs';
  readonly match_index: number;
  readonly left_occurrence_ids: string[];
  readonly right_occurrence_ids: string[];
  readonly order_distance: number;
}

export interface AlignmentDiagnostics {
  readonly localized_occurrences: { left: number; right: number };
  readonly page_level_occurrences: { left: number; right: number };
  readonly out_of_scope_occurrences: { left: number; right: number };
  readonly degenerate_geometry: { left: number; right: number };
  readonly line_runs: { left: number; right: number };
  readonly unlinked_line_runs: { left: number; right: number };
  readonly blocks: number;
  readonly blocks_abstained: number;
  readonly candidate_spans: { left: number; right: number };
  readonly candidate_pairs: number;
  /** Bounded-work counters: no whole-page pairwise pass exists. */
  readonly line_link_checks: number;
  readonly span_gate_checks: number;
  readonly assignment_cells: number;
  readonly assignments_solved: number;
  readonly matches_unique: number;
  readonly matches_ambiguous: number;
  readonly unmatched_left: number;
  readonly unmatched_right: number;
  readonly order_inversions: number;
  readonly median_fragment_height: number;
  readonly horizontal_gap_tolerance: number;
}

export interface AlignmentResult {
  readonly algorithm: 'region-match-v1';
  readonly score_semantics: typeof SCORE_SEMANTICS;
  readonly page_index: number;
  readonly region_scoped: boolean;
  readonly left: AlignedOccurrence[];
  readonly right: AlignedOccurrence[];
  readonly matches: AcceptedMatch[];
  readonly ambiguous: AmbiguousEntry[];
  readonly abstentions: Abstention[];
  readonly order_differences: OrderDifference[];
  /** Occurrence ids that never entered localized matching (I04/I11). */
  readonly page_level: {
    readonly left_occurrence_ids: string[];
    readonly right_occurrence_ids: string[];
  };
  readonly diagnostics: AlignmentDiagnostics;
}

// ---------------------------------------------------------------------------
// Input classification
// ---------------------------------------------------------------------------

function checkOccurrenceShape(o: AlignableOccurrence, side: string): void {
  require(
    o !== null && typeof o === 'object',
    'TYPE',
    `${side} occurrence must be an object`,
  );
  require(
    typeof o.id === 'string' && o.id.length > 0 && o.id.length <= 128,
    'TYPE',
    `${side} occurrence id must be a short string`,
  );
  require(
    Number.isInteger(o.page_index) && o.page_index >= 0,
    'TYPE',
    `${side} occurrence ${o.id} page_index must be a nonnegative integer`,
  );
  require(
    Number.isInteger(o.ordinal) && o.ordinal >= 0,
    'TYPE',
    `${side} occurrence ${o.id} ordinal must be a nonnegative integer`,
  );
  require(
    typeof o.normalized_text === 'string',
    'TYPE',
    `${side} occurrence ${o.id} normalized_text must be a string`,
  );
  const g = o.geometry as Geometry;
  require(
    g !== null &&
      typeof g === 'object' &&
      (g.precision === 'exact' ||
        g.precision === 'estimated' ||
        g.precision === 'page_only' ||
        g.precision === 'unknown') &&
      (g.polygon === null || Array.isArray(g.polygon)),
    'GEOMETRY',
    `${side} occurrence ${o.id} geometry is malformed`,
  );
}

function finitePolygon(polygon: unknown): polygon is Point[] {
  if (!Array.isArray(polygon) || polygon.length < 3) return false;
  return polygon.every(
    (p) =>
      Array.isArray(p) &&
      p.length === 2 &&
      Number.isFinite(p[0]) &&
      Number.isFinite(p[1]),
  );
}

function polygonArea2(polygon: readonly Point[]): number {
  let area = 0;
  for (let i = 0; i < polygon.length; i++) {
    const [x1, y1] = polygon[i]!;
    const [x2, y2] = polygon[(i + 1) % polygon.length]!;
    area += x1 * y2 - x2 * y1;
  }
  return area / 2;
}

type Bucket = 'localized' | 'page_level' | 'out_of_scope';

interface Classified {
  bucket: Bucket;
  fragment: Fragment | null;
  degenerate: boolean;
}

/**
 * Localized requires validated precise geometry (I04): exact/estimated
 * precision AND a finite non-degenerate polygon AND — when a region is
 * selected — actual intersection with the region. Everything else is
 * page_level or out_of_scope; it is never rescued by matching text.
 */
function classify(
  o: AlignableOccurrence,
  occurrenceIndex: number,
  pageIndex: number,
  region: RegionScope | null,
): Classified {
  if (o.page_index !== pageIndex) {
    return { bucket: 'out_of_scope', fragment: null, degenerate: false };
  }
  const g = o.geometry;
  if (g.polygon === null) {
    return { bucket: 'page_level', fragment: null, degenerate: false };
  }
  if (g.precision !== 'exact' && g.precision !== 'estimated') {
    return { bucket: 'page_level', fragment: null, degenerate: false };
  }
  if (!finitePolygon(g.polygon) || polygonArea2(g.polygon) === 0) {
    return { bucket: 'page_level', fragment: null, degenerate: true };
  }
  if (region !== null && !polygonsIntersect(g.polygon, region.polygon)) {
    return { bucket: 'out_of_scope', fragment: null, degenerate: false };
  }
  const bounds = boundsOf(g.polygon);
  return {
    bucket: 'localized',
    degenerate: false,
    fragment: {
      occurrenceIndex,
      occurrenceId: o.id,
      ordinal: o.ordinal,
      polygon: g.polygon,
      bounds,
      centerY: (bounds[1] + bounds[3]) / 2,
      height: bounds[3] - bounds[1],
      normalizedText: o.normalized_text,
    },
  };
}

// ---------------------------------------------------------------------------
// Candidate spans and pair costs
// ---------------------------------------------------------------------------

interface Span {
  readonly startGeo: number;
  readonly length: number;
  readonly members: Fragment[];
  readonly bounds: Box;
  readonly polygon: Point[];
  readonly text: string;
  readonly ordinalMean: number;
  readonly ordinalRankMean: number;
}

interface Pairing {
  readonly key: string;
  readonly left: Span;
  readonly right: Span;
  readonly components: ScoreComponents;
}

const pairKey = (ls: number, ll: number, rs: number, rl: number) =>
  `${ls}+${ll}~${rs}+${rl}`;

/**
 * Contiguous runs of 1..maxSpanFragments within one line-run. Union
 * geometry stays inside the run (and inside the region when scoped) —
 * a span can never glue two columns because runs already split there.
 */
function enumerateSpans(
  run: LineRun,
  geoBase: number,
  ordinalRank: Map<number, number>,
  regionBounds: Box | null,
  out: Span[],
): void {
  const frags = run.fragments;
  for (let s = 0; s < frags.length; s++) {
    let bounds: Box | null = null;
    let text = '';
    let ordinalSum = 0;
    let rankSum = 0;
    for (
      let len = 1;
      len <= REGION_MATCH_V1.maxSpanFragments && s + len <= frags.length;
      len++
    ) {
      const f = frags[s + len - 1]!;
      bounds = bounds === null ? f.bounds : unionBounds(bounds, f.bounds);
      text += f.normalizedText;
      ordinalSum += f.ordinal;
      rankSum += ordinalRank.get(f.occurrenceIndex)!;
      if (regionBounds !== null && !boundsWithin(bounds, regionBounds)) {
        break;
      }
      out.push({
        startGeo: geoBase + s,
        length: len,
        members: frags.slice(s, s + len),
        bounds,
        polygon: boxPolygonOf(bounds),
        text,
        ordinalMean: ordinalSum / len,
        ordinalRankMean: rankSum / len,
      });
    }
  }
}

function expandedBounds(b: Box, exX: number, exY: number): Box {
  return [b[0] - exX, b[1] - exY, b[2] + exX, b[3] + exY];
}

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/**
 * Geometry distance: 1 minus the overlap ratio of expanded line
 * extents, falling back to center distance normalized by the candidate
 * window when expanded extents still do not overlap.
 */
function geometryDistance(
  left: Span,
  right: Span,
  gapTol: number,
  blockBounds: Box,
): number {
  const exY =
    REGION_MATCH_V1.geometryExpandYFraction *
    Math.min(
      left.bounds[3] - left.bounds[1],
      right.bounds[3] - right.bounds[1],
    );
  const el = expandedBounds(left.bounds, gapTol / 2, exY);
  const er = expandedBounds(right.bounds, gapTol / 2, exY);
  const ix0 = Math.max(el[0], er[0]);
  const iy0 = Math.max(el[1], er[1]);
  const ix1 = Math.min(el[2], er[2]);
  const iy1 = Math.min(el[3], er[3]);
  const inter = Math.max(0, ix1 - ix0) * Math.max(0, iy1 - iy0);
  const union = boxArea(el) + boxArea(er) - inter;
  if (inter > 0 && union > 0) {
    return clamp01(1 - inter / union);
  }
  const cx =
    (left.bounds[0] + left.bounds[2]) / 2 -
    (right.bounds[0] + right.bounds[2]) / 2;
  const cy =
    (left.bounds[1] + left.bounds[3]) / 2 -
    (right.bounds[1] + right.bounds[3]) / 2;
  const diag = Math.hypot(
    blockBounds[2] - blockBounds[0],
    blockBounds[3] - blockBounds[1],
  );
  if (diag <= 0) return 1;
  return clamp01(Math.hypot(cx, cy) / diag);
}

/**
 * region-match-v1 pair gate: polygon intersection, or overlapping
 * vertical bands plus a bounded horizontal gap.
 */
function pairAdmitted(
  left: Span,
  right: Span,
  gapTol: number,
  counters: SpatialCounters,
): boolean {
  counters.span_gate_checks++;
  if (polygonsIntersect(left.polygon, right.polygon)) return true;
  return (
    verticalOverlap(left.bounds, right.bounds) >=
      REGION_MATCH_V1.verticalOverlapMin &&
    horizontalGap(left.bounds, right.bounds) <= gapTol
  );
}

function pairCost(
  left: Span,
  right: Span,
  gapTol: number,
  blockBounds: Box,
): ScoreComponents {
  const g = geometryDistance(left, right, gapTol, blockBounds);
  const o = clamp01(Math.abs(left.ordinalRankMean - right.ordinalRankMean));
  const t = normalizedTextDistance(left.text, right.text);
  const cost =
    REGION_MATCH_V1.weightGeometry * g +
    REGION_MATCH_V1.weightOrder * o +
    REGION_MATCH_V1.weightText * t;
  return {
    geometry_distance: g,
    order_distance: o,
    text_distance: t,
    cost: clamp01(cost),
  };
}

// ---------------------------------------------------------------------------
// Bounded non-crossing assignment
// ---------------------------------------------------------------------------

interface AssignmentMove {
  readonly kind: 'skip_left' | 'skip_right' | 'match';
  readonly a: number;
  readonly b: number;
}

interface AssignmentSolution {
  readonly cost: number;
  readonly pairs: Pairing[];
}

interface SolveCounters {
  cells: number;
  solves: number;
}

/**
 * Minimum-cost non-crossing one-to-one assignment between the two
 * geometrically ordered fragment sequences of one bounded component.
 * A move either leaves one fragment unmatched (unmatchedPenalty each)
 * or consumes a candidate span pair — the same minimum-cost assignment
 * a bipartite solver would find, restricted to the non-crossing
 * pairings geometry allows inside one region. O(n*m*16) cells on a
 * component already capped at maxComponentFragments per side.
 *
 * The minimized value is Σ pair costs + unmatchedPenalty per unmatched
 * fragment − pairPreference per pair: the last term is the bounded
 * granularity preference that keeps per-fragment matches ahead of
 * whole-line blob spans (see constants.ts). It is a bookkeeping term
 * only — acceptance thresholds apply to the raw pair cost.
 */
function solveAssignment(
  nLeft: number,
  nRight: number,
  pairCostByKey: Map<string, { cost: number; pairing: Pairing }>,
  forbiddenKey: string | null,
  counters: SolveCounters,
): AssignmentSolution {
  counters.solves++;
  const P = REGION_MATCH_V1.unmatchedPenalty;
  const E = REGION_MATCH_V1.pairPreference;
  const K = REGION_MATCH_V1.maxSpanFragments;
  const cols = nRight + 1;
  const dp = new Float64Array((nLeft + 1) * cols);
  const back = new Array<AssignmentMove | null>((nLeft + 1) * cols).fill(null);
  dp[0] = 0;
  for (let i = 0; i <= nLeft; i++) {
    for (let j = 0; j <= nRight; j++) {
      if (i === 0 && j === 0) continue;
      counters.cells++;
      let best = Infinity;
      let move: AssignmentMove | null = null;
      // Match moves first: on an exact cost tie a concrete pairing is
      // preferred, and the smaller span wins within equal cost.
      for (let a = 1; a <= K && a <= i; a++) {
        for (let b = 1; b <= K && b <= j; b++) {
          const key = pairKey(i - a, a, j - b, b);
          if (key === forbiddenKey) continue;
          const entry = pairCostByKey.get(key);
          if (entry === undefined) continue;
          const total = dp[(i - a) * cols + (j - b)]! + entry.cost - E;
          if (total < best) {
            best = total;
            move = { kind: 'match', a, b };
          }
        }
      }
      if (i > 0) {
        const total = dp[(i - 1) * cols + j]! + P;
        if (total < best) {
          best = total;
          move = { kind: 'skip_left', a: 0, b: 0 };
        }
      }
      if (j > 0) {
        const total = dp[i * cols + (j - 1)]! + P;
        if (total < best) {
          best = total;
          move = { kind: 'skip_right', a: 0, b: 0 };
        }
      }
      dp[i * cols + j] = best;
      back[i * cols + j] = move;
    }
  }
  const pairs: Pairing[] = [];
  let i = nLeft;
  let j = nRight;
  while (i > 0 || j > 0) {
    const move = back[i * cols + j];
    if (move === null || move === undefined) break;
    if (move.kind === 'match') {
      pairs.push(
        pairCostByKey.get(pairKey(i - move.a, move.a, j - move.b, move.b))!
          .pairing,
      );
      i -= move.a;
      j -= move.b;
    } else if (move.kind === 'skip_left') {
      i -= 1;
    } else {
      j -= 1;
    }
  }
  return { cost: dp[nLeft * cols + nRight]!, pairs };
}

// ---------------------------------------------------------------------------
// Per-block matching
// ---------------------------------------------------------------------------

interface BlockOutcome {
  matches: { match: AcceptedMatch; pairing: Pairing }[];
  ambiguous: { entry: AmbiguousEntry; pairing: Pairing }[];
  spanCounts: { left: number; right: number };
  pairsEvaluated: number;
}

function provenanceOf(a: number, b: number): Provenance {
  if (a === 1 && b === 1) return 'one_to_one';
  if (a > 1 && b === 1) return 'many_to_one';
  if (a === 1 && b > 1) return 'one_to_many';
  return 'many_to_many';
}

const ids = (members: Fragment[]) => members.map((f) => f.occurrenceId);

function matchBlock(
  block: Block,
  gapTol: number,
  regionBounds: Box | null,
  counters: SpatialCounters,
  solveCounters: SolveCounters,
): BlockOutcome {
  // Geometric reading order: runs sorted by (top, left), members by x.
  const leftRuns = [...block.leftRuns].sort(
    (a, b) => a.bounds[1] - b.bounds[1] || a.bounds[0] - b.bounds[0],
  );
  const rightRuns = [...block.rightRuns].sort(
    (a, b) => a.bounds[1] - b.bounds[1] || a.bounds[0] - b.bounds[0],
  );

  // Ordinal rank inside the block, normalized to [0,1] per side.
  const rankOf = (frags: Fragment[]) => {
    const byOrdinal = [...frags].sort((a, b) => a.ordinal - b.ordinal);
    const m = new Map<number, number>();
    const n = byOrdinal.length;
    byOrdinal.forEach((f, i) => {
      m.set(f.occurrenceIndex, n > 1 ? i / (n - 1) : 0);
    });
    return m;
  };
  const leftRank = rankOf(block.left);
  const rightRank = rankOf(block.right);

  const leftSpans: Span[] = [];
  const rightSpans: Span[] = [];
  const geoPosLeft = new Map<number, number>();
  const geoPosRight = new Map<number, number>();
  let geoBase = 0;
  for (const run of leftRuns) {
    enumerateSpans(run, geoBase, leftRank, regionBounds, leftSpans);
    for (let k = 0; k < run.fragments.length; k++) {
      geoPosLeft.set(run.fragments[k]!.occurrenceIndex, geoBase + k);
    }
    geoBase += run.fragments.length;
  }
  geoBase = 0;
  for (const run of rightRuns) {
    enumerateSpans(run, geoBase, rightRank, regionBounds, rightSpans);
    for (let k = 0; k < run.fragments.length; k++) {
      geoPosRight.set(run.fragments[k]!.occurrenceIndex, geoBase + k);
    }
    geoBase += run.fragments.length;
  }

  // Candidate pairs through the geometric gate, indexed for the solver.
  const pairCostByKey = new Map<string, { cost: number; pairing: Pairing }>();
  const allPairs: Pairing[] = [];
  for (const ls of leftSpans) {
    for (const rs of rightSpans) {
      if (!pairAdmitted(ls, rs, gapTol, counters)) continue;
      const components = pairCost(ls, rs, gapTol, block.bounds);
      const pairing: Pairing = {
        key: pairKey(ls.startGeo, ls.length, rs.startGeo, rs.length),
        left: ls,
        right: rs,
        components,
      };
      pairCostByKey.set(pairing.key, { cost: components.cost, pairing });
      allPairs.push(pairing);
    }
  }

  const optimal = solveAssignment(
    block.left.length,
    block.right.length,
    pairCostByKey,
    null,
    solveCounters,
  );

  // Optimal-pair lookup per fragment for the exchange pass below.
  const optimalLeftOf = new Map<number, Pairing>();
  const optimalRightOf = new Map<number, Pairing>();
  for (const p of optimal.pairs) {
    for (const f of p.left.members) optimalLeftOf.set(f.occurrenceIndex, p);
    for (const f of p.right.members) optimalRightOf.set(f.occurrenceIndex, p);
  }

  /**
   * Margin for one chosen pair: the scalarized cost delta of the
   * cheapest competing assignment. Two bounded competition views:
   *
   *  (A) the non-crossing re-solve with this pair forbidden — coverage
   *      and decomposition competition inside the same model; and
   *
   *  (B) local exchanges: every candidate pair sharing a fragment with
   *      this pair may conflict with at most two other chosen pairs;
   *      the fragments it displaces are rescued by a fresh bounded
   *      solve or left unmatched. Crossing assignments are never
   *      *accepted* — the optimum stays geometry-consistent — but a
   *      near-priced crossing alternative is real competition and must
   *      sink the margin into abstention (the duplicate tie).
   */
  const exchangeMargin = (pairing: Pairing): number => {
    let best = Infinity;
    const P = REGION_MATCH_V1.unmatchedPenalty;
    const E = REGION_MATCH_V1.pairPreference;
    for (const q of allPairs) {
      if (q.key === pairing.key) continue;
      const shares =
        q.left.members.some((f) => pairing.left.members.includes(f)) ||
        q.right.members.some((f) => pairing.right.members.includes(f));
      if (!shares) continue;
      const conflicted = new Set<Pairing>([pairing]);
      for (const f of q.left.members) {
        const o = optimalLeftOf.get(f.occurrenceIndex);
        if (o !== undefined) conflicted.add(o);
      }
      for (const f of q.right.members) {
        const o = optimalRightOf.get(f.occurrenceIndex);
        if (o !== undefined) conflicted.add(o);
      }
      // Chosen pair plus at most two displaced neighbours.
      if (conflicted.size > 3) continue;
      const leftSet = new Set<number>();
      const rightSet = new Set<number>();
      for (const cp of conflicted) {
        for (const f of cp.left.members) leftSet.add(f.occurrenceIndex);
        for (const f of cp.right.members) rightSet.add(f.occurrenceIndex);
      }
      const qLeft = new Set(q.left.members.map((f) => f.occurrenceIndex));
      const qRight = new Set(q.right.members.map((f) => f.occurrenceIndex));
      let newlyCovered = 0;
      for (const x of qLeft) if (!leftSet.has(x)) newlyCovered++;
      for (const x of qRight) if (!rightSet.has(x)) newlyCovered++;
      // Displaced fragments rescue-pair among themselves or stay
      // unmatched — a mini non-crossing solve on the affected window.
      const dispL = [...leftSet]
        .filter((x) => !qLeft.has(x))
        .sort(
          (a, b) => geoPosLeft.get(a)! - geoPosLeft.get(b)!,
        );
      const dispR = [...rightSet]
        .filter((x) => !qRight.has(x))
        .sort(
          (a, b) => geoPosRight.get(a)! - geoPosRight.get(b)!,
        );
      const posL = new Map(dispL.map((x, i) => [x, i] as const));
      const posR = new Map(dispR.map((x, i) => [x, i] as const));
      const miniPairs = new Map<
        string,
        { cost: number; pairing: Pairing }
      >();
      for (const cand of allPairs) {
        const lpos = cand.left.members.map((f) => posL.get(f.occurrenceIndex));
        const rpos = cand.right.members.map((f) =>
          posR.get(f.occurrenceIndex),
        );
        if (lpos.some((p) => p === undefined) || rpos.some((p) => p === undefined)) {
          continue;
        }
        const lNums = lpos as number[];
        const rNums = rpos as number[];
        const lContig = lNums.every((p, i) => i === 0 || p === lNums[i - 1]! + 1);
        const rContig = rNums.every((p, i) => i === 0 || p === rNums[i - 1]! + 1);
        if (!lContig || !rContig) continue;
        miniPairs.set(pairKey(lNums[0]!, lNums.length, rNums[0]!, rNums.length), {
          cost: cand.components.cost,
          pairing: cand,
        });
      }
      const rescue = solveAssignment(
        dispL.length,
        dispR.length,
        miniPairs,
        null,
        solveCounters,
      );
      let removed = 0;
      for (const cp of conflicted) removed += E - cp.components.cost;
      const alt =
        optimal.cost +
        removed +
        (q.components.cost - E) -
        P * newlyCovered +
        rescue.cost;
      const delta = alt - optimal.cost;
      if (delta < best) best = delta;
    }
    return best;
  };

  // Competing candidates for one chosen unit, kept accessible: every
  // evaluated pair touching any member fragment of either of its spans,
  // cheapest first — the whole ambiguity set, not just same-span rivals.
  const candidatesFor = (pairing: Pairing): CandidateView[] =>
    allPairs
      .filter(
        (p) =>
          p.left.members.some((f) => pairing.left.members.includes(f)) ||
          p.right.members.some((f) => pairing.right.members.includes(f)),
      )
      .map((p) => ({
        left_occurrence_ids: ids(p.left.members),
        right_occurrence_ids: ids(p.right.members),
        components: p.components,
      }))
      .sort((a, b) => a.components.cost - b.components.cost);

  // Acceptance: cost <= 0.45 AND the next competing assignment costs
  // >= 0.12 more. Failing units abstain — `tie` when the margin fails,
  // `weak` when the best agreement is still too expensive.
  const provisional: { pairing: Pairing; margin: number; accepted: boolean }[] =
    [];
  for (const pairing of optimal.pairs) {
    const alt = solveAssignment(
      block.left.length,
      block.right.length,
      pairCostByKey,
      pairing.key,
      solveCounters,
    );
    const exchange = exchangeMargin(pairing);
    const margin = Math.min(alt.cost - optimal.cost, exchange);
    provisional.push({
      pairing,
      margin,
      accepted:
        pairing.components.cost <= REGION_MATCH_V1.acceptCost &&
        margin >= REGION_MATCH_V1.minMargin,
    });
  }

  // Geometry/order agreement on the block: among provisionally accepted
  // pairs, the emission order of left units and their right partners
  // must not invert. Any pair taking part in an inversion is demoted to
  // ambiguous (order_conflict) — reported, never silently chosen.
  const accepted = provisional.filter((p) => p.accepted);
  const conflicted = new Set<Pairing>();
  for (let a = 0; a < accepted.length; a++) {
    for (let b = a + 1; b < accepted.length; b++) {
      const pa = accepted[a]!.pairing;
      const pb = accepted[b]!.pairing;
      const dl = pa.left.ordinalMean - pb.left.ordinalMean;
      const dr = pa.right.ordinalMean - pb.right.ordinalMean;
      if (dl * dr < 0) {
        conflicted.add(pa);
        conflicted.add(pb);
      }
    }
  }

  const out: BlockOutcome = {
    matches: [],
    ambiguous: [],
    spanCounts: { left: leftSpans.length, right: rightSpans.length },
    pairsEvaluated: allPairs.length,
  };
  for (const { pairing, margin, accepted: ok } of provisional) {
    if (ok && !conflicted.has(pairing)) {
      out.matches.push({
        match: {
          left_occurrence_ids: ids(pairing.left.members),
          right_occurrence_ids: ids(pairing.right.members),
          provenance: provenanceOf(
            pairing.left.length,
            pairing.right.length,
          ),
          components: pairing.components,
          margin,
          extent_left: pairing.left.bounds,
          extent_right: pairing.right.bounds,
        },
        pairing,
      });
    } else {
      const reason: AmbiguityReason = conflicted.has(pairing)
        ? 'order_conflict'
        : margin < REGION_MATCH_V1.minMargin
          ? 'tie'
          : 'weak';
      out.ambiguous.push({
        entry: {
          reason,
          left_occurrence_ids: ids(pairing.left.members),
          right_occurrence_ids: ids(pairing.right.members),
          components: pairing.components,
          margin,
          candidates: candidatesFor(pairing),
        },
        pairing,
      });
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Public entry point
// ---------------------------------------------------------------------------

/**
 * Align two readers' occurrences on one page. `left` and `right` are
 * never modified. The result preserves every occurrence — identical
 * strings at different positions keep separate identities and each
 * gets its own candidates.
 */
export function alignPage(
  left: AlignableOccurrence[],
  right: AlignableOccurrence[],
  options: AlignmentOptions = {},
): AlignmentResult {
  require(
    Array.isArray(left) && Array.isArray(right),
    'TYPE',
    'occurrence lists must be arrays',
  );
  const seen = new Set<string>();
  for (const o of left) {
    checkOccurrenceShape(o, 'left');
    require(!seen.has(o.id), 'ID', `duplicate left occurrence id ${o.id}`);
    seen.add(o.id);
  }
  seen.clear();
  for (const o of right) {
    checkOccurrenceShape(o, 'right');
    require(!seen.has(o.id), 'ID', `duplicate right occurrence id ${o.id}`);
    seen.add(o.id);
  }

  let pageIndex = options.page_index;
  if (pageIndex === undefined) {
    const pages = new Set<number>();
    for (const o of left) pages.add(o.page_index);
    for (const o of right) pages.add(o.page_index);
    if (pages.size > 1) {
      throw new ContractError(
        'PAGE',
        'alignPage requires options.page_index when inputs span pages',
      );
    }
    pageIndex = pages.size === 1 ? [...pages][0]! : 0;
  }
  require(
    Number.isInteger(pageIndex) && pageIndex >= 0,
    'PAGE',
    'page_index must be a nonnegative integer',
  );

  const region = options.region ?? null;
  if (region !== null) {
    require(
      finitePolygon(region.polygon) && polygonArea2(region.polygon) !== 0,
      'GEOMETRY',
      'selected region must be a finite non-degenerate polygon',
    );
  }
  const regionBounds = region === null ? null : boundsOf(region.polygon);

  const counters: SpatialCounters = {
    line_link_checks: 0,
    span_gate_checks: 0,
  };
  const solveCounters: SolveCounters = { cells: 0, solves: 0 };

  const classifiedL = left.map((o, i) => classify(o, i, pageIndex!, region));
  const classifiedR = right.map((o, i) => classify(o, i, pageIndex!, region));
  const leftFrags = classifiedL.flatMap((c) =>
    c.fragment === null ? [] : [c.fragment],
  );
  const rightFrags = classifiedR.flatMap((c) =>
    c.fragment === null ? [] : [c.fragment],
  );

  const medianH = medianFragmentHeight([...leftFrags, ...rightFrags]);
  const gapTol = horizontalGapTolerance(medianH);

  const leftRuns = buildLineRuns(leftFrags, gapTol, 0);
  const rightRuns = buildLineRuns(rightFrags, gapTol, leftRuns.length);
  const { blocks, unmatchedLeft, unmatchedRight } = buildBlocks(
    leftRuns,
    rightRuns,
    gapTol,
    counters,
  );

  const matches: AcceptedMatch[] = [];
  const ambiguous: AmbiguousEntry[] = [];
  const abstentions: Abstention[] = [];
  const leftStatus = new Map<
    number,
    { status: AlignmentStatus; detail: number }
  >();
  const rightStatus = new Map<
    number,
    { status: AlignmentStatus; detail: number }
  >();
  const byId = (frags: Fragment[]) => {
    const m = new Map<string, Fragment>();
    for (const f of frags) m.set(f.occurrenceId, f);
    return m;
  };
  let spanCounts = { left: 0, right: 0 };
  let pairsEvaluated = 0;

  for (const block of blocks) {
    const leftById = byId(block.left);
    const rightById = byId(block.right);
    if (block.tooLarge) {
      const index = abstentions.length;
      abstentions.push({
        reason: 'component_too_large',
        left_occurrence_ids: block.left.map((f) => f.occurrenceId),
        right_occurrence_ids: block.right.map((f) => f.occurrenceId),
        fragment_counts: [block.left.length, block.right.length],
      });
      for (const f of block.left) {
        leftStatus.set(f.occurrenceIndex, {
          status: 'abstained',
          detail: index,
        });
      }
      for (const f of block.right) {
        rightStatus.set(f.occurrenceIndex, {
          status: 'abstained',
          detail: index,
        });
      }
      continue;
    }
    const outcome = matchBlock(
      block,
      gapTol,
      regionBounds,
      counters,
      solveCounters,
    );
    spanCounts = {
      left: spanCounts.left + outcome.spanCounts.left,
      right: spanCounts.right + outcome.spanCounts.right,
    };
    pairsEvaluated += outcome.pairsEvaluated;
    for (const { match } of outcome.matches) {
      const index = matches.length;
      matches.push(match);
      for (const id of match.left_occurrence_ids) {
        leftStatus.set(leftById.get(id)!.occurrenceIndex, {
          status: 'unique',
          detail: index,
        });
      }
      for (const id of match.right_occurrence_ids) {
        rightStatus.set(rightById.get(id)!.occurrenceIndex, {
          status: 'unique',
          detail: index,
        });
      }
    }
    for (const { entry } of outcome.ambiguous) {
      const index = ambiguous.length;
      ambiguous.push(entry);
      // The contested unit and every accessible candidate keep the
      // `ambiguous` status; a `unique` verdict elsewhere always wins.
      const mark = (
        id: string,
        byIdMap: Map<string, Fragment>,
        statusMap: Map<number, { status: AlignmentStatus; detail: number }>,
      ) => {
        const frag = byIdMap.get(id);
        if (frag === undefined) return;
        if (statusMap.get(frag.occurrenceIndex)?.status === 'unique') return;
        statusMap.set(frag.occurrenceIndex, {
          status: 'ambiguous',
          detail: index,
        });
      };
      for (const id of entry.left_occurrence_ids) mark(id, leftById, leftStatus);
      for (const id of entry.right_occurrence_ids) {
        mark(id, rightById, rightStatus);
      }
      for (const c of entry.candidates) {
        for (const id of c.left_occurrence_ids) mark(id, leftById, leftStatus);
        for (const id of c.right_occurrence_ids) {
          mark(id, rightById, rightStatus);
        }
      }
    }
  }

  // Fragments in unlinked line-runs, fragments the solver skipped and
  // pairings the acceptance gate dropped are all unmatched — a reader
  // omission, an extra reading, unsupported mapping or an alignment
  // failure, phrased downstream as "No matching reading found here",
  // never "text is missing from the document".
  for (const f of leftFrags) {
    if (!leftStatus.has(f.occurrenceIndex)) {
      leftStatus.set(f.occurrenceIndex, { status: 'unmatched', detail: -1 });
    }
  }
  for (const f of rightFrags) {
    if (!rightStatus.has(f.occurrenceIndex)) {
      rightStatus.set(f.occurrenceIndex, { status: 'unmatched', detail: -1 });
    }
  }

  const alignedLeft: AlignedOccurrence[] = left.map((o, i) => {
    const c = classifiedL[i]!;
    if (c.bucket !== 'localized') {
      return { occurrence_id: o.id, status: c.bucket, detail_index: null };
    }
    const s = leftStatus.get(i)!;
    return {
      occurrence_id: o.id,
      status: s.status,
      detail_index: s.detail < 0 ? null : s.detail,
    };
  });
  const alignedRight: AlignedOccurrence[] = right.map((o, i) => {
    const c = classifiedR[i]!;
    if (c.bucket !== 'localized') {
      return { occurrence_id: o.id, status: c.bucket, detail_index: null };
    }
    const s = rightStatus.get(i)!;
    return {
      occurrence_id: o.id,
      status: s.status,
      detail_index: s.detail < 0 ? null : s.detail,
    };
  });

  // Page-level order differences: inversions between the emission order
  // of accepted left units and the emission order of their right
  // partners (e.g. two columns emitted in opposite order). Reported as
  // diagnostics, never as a verdict (I06).
  const ordById = (list: AlignableOccurrence[]) => {
    const m = new Map<string, number>();
    for (const o of list) m.set(o.id, o.ordinal);
    return m;
  };
  const leftOrd = ordById(left);
  const rightOrd = ordById(right);
  const matched = matches.map((m, i) => ({
    i,
    leftOrd: Math.min(...m.left_occurrence_ids.map((id) => leftOrd.get(id)!)),
    rightOrd: Math.min(
      ...m.right_occurrence_ids.map((id) => rightOrd.get(id)!),
    ),
  }));
  matched.sort((a, b) => a.leftOrd - b.leftOrd);
  const involved = new Set<number>();
  let inversions = 0;
  for (let a = 0; a < matched.length; a++) {
    for (let b = a + 1; b < matched.length; b++) {
      if (matched[a]!.rightOrd > matched[b]!.rightOrd) {
        inversions++;
        involved.add(matched[a]!.i);
        involved.add(matched[b]!.i);
      }
    }
  }
  const orderDifferences: OrderDifference[] = [...involved].map((i) => ({
    kind: 'emission_order_differs',
    match_index: i,
    left_occurrence_ids: matches[i]!.left_occurrence_ids,
    right_occurrence_ids: matches[i]!.right_occurrence_ids,
    order_distance: matches[i]!.components.order_distance,
  }));

  const count = (list: Classified[], bucket: Bucket) =>
    list.filter((c) => c.bucket === bucket).length;

  return {
    algorithm: REGION_MATCH_V1.version,
    score_semantics: SCORE_SEMANTICS,
    page_index: pageIndex,
    region_scoped: region !== null,
    left: alignedLeft,
    right: alignedRight,
    matches,
    ambiguous,
    abstentions,
    order_differences: orderDifferences,
    page_level: {
      left_occurrence_ids: left
        .filter((_, i) => classifiedL[i]!.bucket === 'page_level')
        .map((o) => o.id),
      right_occurrence_ids: right
        .filter((_, i) => classifiedR[i]!.bucket === 'page_level')
        .map((o) => o.id),
    },
    diagnostics: {
      localized_occurrences: {
        left: count(classifiedL, 'localized'),
        right: count(classifiedR, 'localized'),
      },
      page_level_occurrences: {
        left: count(classifiedL, 'page_level'),
        right: count(classifiedR, 'page_level'),
      },
      out_of_scope_occurrences: {
        left: count(classifiedL, 'out_of_scope'),
        right: count(classifiedR, 'out_of_scope'),
      },
      degenerate_geometry: {
        left: classifiedL.filter((c) => c.degenerate).length,
        right: classifiedR.filter((c) => c.degenerate).length,
      },
      line_runs: { left: leftRuns.length, right: rightRuns.length },
      unlinked_line_runs: {
        left: unmatchedLeft.length,
        right: unmatchedRight.length,
      },
      blocks: blocks.length,
      blocks_abstained: blocks.filter((b) => b.tooLarge).length,
      candidate_spans: spanCounts,
      candidate_pairs: pairsEvaluated,
      line_link_checks: counters.line_link_checks,
      span_gate_checks: counters.span_gate_checks,
      assignment_cells: solveCounters.cells,
      assignments_solved: solveCounters.solves,
      matches_unique: matches.length,
      matches_ambiguous: ambiguous.length,
      unmatched_left: alignedLeft.filter((a) => a.status === 'unmatched')
        .length,
      unmatched_right: alignedRight.filter((a) => a.status === 'unmatched')
        .length,
      order_inversions: inversions,
      median_fragment_height: medianH,
      horizontal_gap_tolerance: gapTol,
    },
  };
}
