/**
 * Bounded spatial index for region-match-v1.
 *
 * Localized occurrences become fragments; fragments sharing a vertical
 * band cluster into line-runs (split on large horizontal gaps so two
 * columns never fuse into one candidate line); left and right line-runs
 * link into bounded local components when their vertical bands overlap
 * or their union polygons intersect. Every structure here is local —
 * no whole-page pairwise pass is ever required.
 */

import { pointInPolygon, polygonBounds } from '../../geometry/src/index.ts';
import type { Box, Point } from '../../contracts/src/index.ts';
import { REGION_MATCH_V1 } from './constants.ts';

export function boundsOf(polygon: readonly Point[]): Box {
  return polygonBounds(polygon as Point[]);
}

export function unionBounds(a: Box, b: Box): Box {
  return [
    Math.min(a[0], b[0]),
    Math.min(a[1], b[1]),
    Math.max(a[2], b[2]),
    Math.max(a[3], b[3]),
  ];
}

export function boxArea(b: Box): number {
  return Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
}

export function boxPolygonOf(b: Box): Point[] {
  return [
    [b[0], b[1]],
    [b[2], b[1]],
    [b[2], b[3]],
    [b[0], b[3]],
  ];
}

/** Vertical overlap of two bands as a fraction of the smaller height. */
export function verticalOverlap(a: Box, b: Box): number {
  const overlap = Math.min(a[3], b[3]) - Math.max(a[1], b[1]);
  if (overlap <= 0) return 0;
  const minH = Math.min(a[3] - a[1], b[3] - b[1]);
  if (minH <= 0) return 0;
  return Math.min(1, overlap / minH);
}

/** Horizontal gap between two boxes; 0 when they touch or overlap. */
export function horizontalGap(a: Box, b: Box): number {
  return Math.max(0, Math.max(a[0] - b[2], b[0] - a[2]));
}

export function boundsWithin(inner: Box, outer: Box, eps = 1e-9): boolean {
  return (
    inner[0] >= outer[0] - eps &&
    inner[1] >= outer[1] - eps &&
    inner[2] <= outer[2] + eps &&
    inner[3] <= outer[3] + eps
  );
}

function segmentsIntersect(
  a1: Point,
  a2: Point,
  b1: Point,
  b2: Point,
): boolean {
  const d = (o: Point, p: Point, q: Point) =>
    (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0]);
  const d1 = d(b1, b2, a1);
  const d2 = d(b1, b2, a2);
  const d3 = d(a1, a2, b1);
  const d4 = d(a1, a2, b2);
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
    ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) {
    return true;
  }
  const on = (p: Point, q: Point, r: Point) =>
    Math.min(p[0], r[0]) - 1e-9 <= q[0] &&
    q[0] <= Math.max(p[0], r[0]) + 1e-9 &&
    Math.min(p[1], r[1]) - 1e-9 <= q[1] &&
    q[1] <= Math.max(p[1], r[1]) + 1e-9;
  if (Math.abs(d1) <= 1e-9 && on(b1, a1, b2)) return true;
  if (Math.abs(d2) <= 1e-9 && on(b1, a2, b2)) return true;
  if (Math.abs(d3) <= 1e-9 && on(a1, b1, a2)) return true;
  if (Math.abs(d4) <= 1e-9 && on(a1, b2, a2)) return true;
  return false;
}

/**
 * Conservative polygon intersection: bounding-box quick reject, then
 * edge crossing or vertex containment (edge-inclusive, so touching
 * polygons count as intersecting — the admission errs toward keeping a
 * candidate, never toward dropping one).
 */
export function polygonsIntersect(
  p1: readonly Point[],
  p2: readonly Point[],
): boolean {
  const b1 = boundsOf(p1);
  const b2 = boundsOf(p2);
  if (
    b1[2] < b2[0] - 1e-9 ||
    b2[2] < b1[0] - 1e-9 ||
    b1[3] < b2[1] - 1e-9 ||
    b2[3] < b1[1] - 1e-9
  ) {
    return false;
  }
  for (const p of p1) {
    if (pointInPolygon(p, p2 as Point[], 1e-9)) return true;
  }
  for (const p of p2) {
    if (pointInPolygon(p, p1 as Point[], 1e-9)) return true;
  }
  for (let i = 0; i < p1.length; i++) {
    const a1 = p1[i]!;
    const a2 = p1[(i + 1) % p1.length]!;
    for (let j = 0; j < p2.length; j++) {
      if (segmentsIntersect(a1, a2, p2[j]!, p2[(j + 1) % p2.length]!)) {
        return true;
      }
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Fragments, line-runs and bounded local components
// ---------------------------------------------------------------------------

/** A localized occurrence reduced to what the matcher needs. */
export interface Fragment {
  /** Index into the side's occurrence list. */
  readonly occurrenceIndex: number;
  readonly occurrenceId: string;
  readonly ordinal: number;
  readonly polygon: readonly Point[];
  readonly bounds: Box;
  readonly centerY: number;
  readonly height: number;
  readonly normalizedText: string;
}

/** One horizontal run of same-band fragments — never spans a big gap. */
export interface LineRun {
  readonly id: number;
  readonly fragments: Fragment[];
  readonly bounds: Box;
  readonly polygon: Point[];
}

/**
 * A bounded local component: the fragments of linked left/right
 * line-runs. `tooLarge` is set when either side exceeds the component
 * cap — the whole component then abstains rather than running an
 * expensive global search.
 */
export interface Block {
  readonly id: number;
  readonly leftRuns: LineRun[];
  readonly rightRuns: LineRun[];
  readonly left: Fragment[];
  readonly right: Fragment[];
  readonly bounds: Box;
  readonly tooLarge: boolean;
}

/** Count of geometry comparisons performed (the bounded-work evidence). */
export interface SpatialCounters {
  line_link_checks: number;
  span_gate_checks: number;
}

/** Median fragment height across the page's localized fragments. */
export function medianFragmentHeight(frags: Fragment[]): number {
  if (frags.length === 0) return 0;
  const hs = frags.map((f) => f.height).sort((a, b) => a - b);
  const mid = hs.length >> 1;
  return hs.length % 2 === 1 ? hs[mid]! : (hs[mid - 1]! + hs[mid]!) / 2;
}

/** min(1.5 x median line height, 24 canonical points). */
export function horizontalGapTolerance(medianHeight: number): number {
  return Math.min(
    REGION_MATCH_V1.horizontalGapLineHeights * medianHeight,
    REGION_MATCH_V1.horizontalGapMaxPt,
  );
}

/**
 * Cluster fragments into lines by pairwise vertical-band overlap >=
 * 0.5 of the smaller height (transitive), then x-sort each cluster and
 * split it into runs wherever the horizontal gap exceeds `gapTol` — the
 * "do not glue two columns" guard, applied before any candidate exists.
 */
export function buildLineRuns(
  frags: Fragment[],
  gapTol: number,
  firstId: number,
): LineRun[] {
  const n = frags.length;
  if (n === 0) return [];
  const parent = frags.map((_, i) => i);
  const find = (x: number): number => {
    while (parent[x] !== x) {
      parent[x] = parent[parent[x]!]!;
      x = parent[x]!;
    }
    return x;
  };
  const union = (a: number, b: number) => {
    parent[find(a)] = find(b);
  };
  const sorted = frags
    .map((f, i) => ({ f, i }))
    .sort((x, y) => x.f.bounds[1] - y.f.bounds[1]);
  // Only pairs whose bands could overlap at all are compared: the scan
  // stops at the first fragment starting below the current one's end.
  for (let a = 0; a < n; a++) {
    const fa = sorted[a]!.f;
    for (let b = a + 1; b < n; b++) {
      const fb = sorted[b]!.f;
      if (fb.bounds[1] >= fa.bounds[3]) break;
      if (
        verticalOverlap(fa.bounds, fb.bounds) >=
        REGION_MATCH_V1.verticalOverlapMin
      ) {
        union(sorted[a]!.i, sorted[b]!.i);
      }
    }
  }
  const clusters = new Map<number, Fragment[]>();
  for (let i = 0; i < n; i++) {
    const root = find(i);
    let list = clusters.get(root);
    if (!list) clusters.set(root, (list = []));
    list.push(frags[i]!);
  }
  const runs: LineRun[] = [];
  for (const cluster of clusters.values()) {
    const byX = [...cluster].sort(
      (a, b) =>
        a.bounds[0] - b.bounds[0] || a.occurrenceIndex - b.occurrenceIndex,
    );
    let run: Fragment[] = [];
    let bounds: Box | null = null;
    const flush = () => {
      if (run.length === 0) return;
      runs.push({
        id: firstId + runs.length,
        fragments: run,
        bounds: bounds!,
        polygon: boxPolygonOf(bounds!),
      });
      run = [];
      bounds = null;
    };
    for (const f of byX) {
      if (bounds !== null && horizontalGap(bounds, f.bounds) > gapTol) {
        flush();
      }
      run.push(f);
      bounds = bounds === null ? f.bounds : unionBounds(bounds, f.bounds);
    }
    flush();
  }
  return runs;
}

/**
 * Link left and right line-runs into bounded local components. A link
 * requires polygon intersection or the candidate-region gate
 * (vertical-band overlap >= 0.5 of the smaller height AND horizontal
 * gap <= the page tolerance). A component that grows beyond
 * `maxComponentFragments` fragments on either side stops expanding and
 * is marked for abstention.
 */
export function buildBlocks(
  leftRuns: LineRun[],
  rightRuns: LineRun[],
  gapTol: number,
  counters: SpatialCounters,
): { blocks: Block[]; unmatchedLeft: LineRun[]; unmatchedRight: LineRun[] } {
  const nl = leftRuns.length;
  const nr = rightRuns.length;
  const parent = new Map<string, string>();
  const key = (side: string, id: number) => `${side}:${id}`;
  const find = (k: string): string => {
    let r = k;
    while (parent.get(r) !== r) r = parent.get(r!)!;
    parent.set(k, r);
    return r;
  };
  for (const l of leftRuns) parent.set(key('l', l.id), key('l', l.id));
  for (const r of rightRuns) parent.set(key('r', r.id), key('r', r.id));
  const linkedLeft = new Set<number>();
  const linkedRight = new Set<number>();
  // Right runs are scanned in y order; the inner loop stops at the
  // first run starting below the left run's band end, so the link pass
  // is proportional to local density, not page size.
  const rightByY = [...rightRuns].sort((a, b) => a.bounds[1] - b.bounds[1]);
  for (const l of leftRuns) {
    for (const r of rightByY) {
      if (r.bounds[1] >= l.bounds[3]) break;
      counters.line_link_checks++;
      const near =
        verticalOverlap(l.bounds, r.bounds) >=
          REGION_MATCH_V1.verticalOverlapMin &&
        horizontalGap(l.bounds, r.bounds) <= gapTol;
      if (near || polygonsIntersect(l.polygon, r.polygon)) {
        linkedLeft.add(l.id);
        linkedRight.add(r.id);
        parent.set(find(key('l', l.id)), find(key('r', r.id)));
      }
    }
  }
  const members = new Map<string, { l: LineRun[]; r: LineRun[] }>();
  for (const l of leftRuns) {
    const root = find(key('l', l.id));
    let m = members.get(root);
    if (!m) members.set(root, (m = { l: [], r: [] }));
    m.l.push(l);
  }
  for (const r of rightRuns) {
    const root = find(key('r', r.id));
    const m = members.get(root);
    if (m) m.r.push(r);
  }
  const blocks: Block[] = [];
  const unmatchedLeft: LineRun[] = [];
  const unmatchedRight: LineRun[] = [];
  for (const m of members.values()) {
    if (m.l.length === 0 || m.r.length === 0) continue;
    const left = m.l.flatMap((run) => run.fragments);
    const right = m.r.flatMap((run) => run.fragments);
    let bounds = m.l[0]!.bounds;
    for (const run of m.l) bounds = unionBounds(bounds, run.bounds);
    for (const run of m.r) bounds = unionBounds(bounds, run.bounds);
    const tooLarge =
      left.length > REGION_MATCH_V1.maxComponentFragments ||
      right.length > REGION_MATCH_V1.maxComponentFragments;
    blocks.push({
      id: blocks.length,
      leftRuns: m.l,
      rightRuns: m.r,
      left,
      right,
      bounds,
      tooLarge,
    });
  }
  for (const l of leftRuns) if (!linkedLeft.has(l.id)) unmatchedLeft.push(l);
  for (const r of rightRuns) {
    if (!linkedRight.has(r.id)) unmatchedRight.push(r);
  }
  return { blocks, unmatchedLeft, unmatchedRight };
}
