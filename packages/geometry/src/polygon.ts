/**
 * Canonical-space polygon helpers and clipping metadata.
 *
 * Geometry retains polygons, not just enclosing boxes (I02). Clipping
 * affects what is shown, never the underlying source occurrence: the
 * original polygon is always preserved, and partial overlap is reported
 * as partial, not as full visibility (COORDINATES.md "Precision, clipping
 * and order"). Canonical polygons may legitimately extend outside
 * `[0,W]×[0,H]` for out-of-crop observations; the clip result marks them
 * for the separate "outside displayed page" inset instead of snapping
 * them onto the page.
 */

import { require } from '../../contracts/src/index.ts';
import type { Box, Point } from '../../contracts/src/index.ts';
import { apply } from './affine.ts';
import type { Matrix } from '../../contracts/src/index.ts';

/** Minimum absolute signed area for a non-degenerate contract polygon. */
export const MIN_POLYGON_AREA = 1e-12;

/** Maximum polygon vertex count admitted by the schema. */
export const MAX_POLYGON_POINTS = 64;

/** Signed (shoelace) area; sign encodes winding, magnitude the area. */
export function signedArea(polygon: Point[]): number {
  let area = 0;
  for (let i = 0; i < polygon.length; i++) {
    const [x1, y1] = polygon[i]!;
    const [x2, y2] = polygon[(i + 1) % polygon.length]!;
    area += x1 * y2 - x2 * y1;
  }
  return area / 2;
}

/** Axis-aligned bounds of a polygon; used only as an acceleration index. */
export function polygonBounds(polygon: Point[]): Box {
  require(polygon.length > 0, 'GEOMETRY', 'Empty polygon has no bounds');
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const [x, y] of polygon) {
    if (x < x0) x0 = x;
    if (x > x1) x1 = x;
    if (y < y0) y0 = y;
    if (y > y1) y1 = y;
  }
  return [x0, y0, x1, y1];
}

/** Map every vertex through an affine transform (order preserved). */
export function transformPolygon(m: Matrix, polygon: Point[]): Point[] {
  return polygon.map((p) => apply(m, p));
}

/** Axis-aligned rectangle as a CCW polygon in a right/down-axis space. */
export function boxPolygon(box: Box): Point[] {
  const [x0, y0, x1, y1] = box;
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
}

/** Ray-cast point-in-polygon test (edge-inclusive within `eps`). */
export function pointInPolygon(p: Point, polygon: Point[], eps = 0): boolean {
  const [px, py] = p;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i]!;
    const [xj, yj] = polygon[j]!;
    // Edge-inclusive check: distance from segment within eps counts as hit.
    if (eps > 0) {
      const dx = xj - xi;
      const dy = yj - yi;
      const len2 = dx * dx + dy * dy;
      const t =
        len2 === 0
          ? 0
          : Math.max(0, Math.min(1, ((px - xi) * dx + (py - yi) * dy) / len2));
      const ex = px - (xi + t * dx);
      const ey = py - (yi + t * dy);
      if (ex * ex + ey * ey <= eps * eps) return true;
    }
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

export type ClipStatus = 'inside' | 'partial' | 'outside';

export interface ClipResult {
  /** Coarse visibility classification for overlay/inset routing. */
  status: ClipStatus;
  /**
   * Overlay polygon clipped to the effective view, or null when nothing
   * is visible. Never replaces `source`.
   */
  clipped: Point[] | null;
  /** The unmodified source polygon (never deleted or snapped). */
  source: Point[];
  /** True only when the whole polygon lies inside the view. */
  fullyVisible: boolean;
}

function clipEdge(
  points: Point[],
  inside: (p: Point) => boolean,
  intersect: (a: Point, b: Point) => Point,
): Point[] {
  const out: Point[] = [];
  for (let i = 0; i < points.length; i++) {
    const cur = points[i]!;
    const prev = points[(i + points.length - 1) % points.length]!;
    const curIn = inside(cur);
    const prevIn = inside(prev);
    if (curIn) {
      if (!prevIn) out.push(intersect(prev, cur));
      out.push(cur);
    } else if (prevIn) {
      out.push(intersect(prev, cur));
    }
  }
  return out;
}

/**
 * Sutherland–Hodgman clip of a canonical polygon against the effective
 * view `[0,w]×[0,h]` (canonical space is right/down, so the view bounds
 * are the positive extents). Metadata only: `source` is always the
 * untouched input and `status` distinguishes inside/partial/outside so
 * callers can render the "outside displayed page" inset honestly.
 */
export function clipToView(
  polygon: Point[],
  sizePt: Point,
): ClipResult {
  const [w, h] = sizePt;
  require(
    Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0,
    'GEOMETRY',
    'View size must be positive',
  );
  const source = polygon.map((p): Point => [p[0], p[1]]);
  let pts = source;
  pts = clipEdge(
    pts,
    (p) => p[0] >= 0,
    (a, b) => {
      const t = a[0] / (a[0] - b[0]);
      return [0, a[1] + t * (b[1] - a[1])];
    },
  );
  pts = clipEdge(
    pts,
    (p) => p[0] <= w,
    (a, b) => {
      const t = (a[0] - w) / (a[0] - b[0]);
      return [w, a[1] + t * (b[1] - a[1])];
    },
  );
  pts = clipEdge(
    pts,
    (p) => p[1] >= 0,
    (a, b) => {
      const t = a[1] / (a[1] - b[1]);
      return [a[0] + t * (b[0] - a[0]), 0];
    },
  );
  pts = clipEdge(
    pts,
    (p) => p[1] <= h,
    (a, b) => {
      const t = (a[1] - h) / (a[1] - b[1]);
      return [a[0] + t * (b[0] - a[0]), h];
    },
  );
  if (pts.length === 0) {
    // Fully outside: source polygon is preserved for the outside-view
    // inset; nothing is moved onto the page.
    return { status: 'outside', clipped: null, source, fullyVisible: false };
  }
  const unchanged =
    pts.length === source.length &&
    pts.every((p, i) => p[0] === source[i]![0] && p[1] === source[i]![1]);
  if (unchanged) {
    return { status: 'inside', clipped: source, source, fullyVisible: true };
  }
  return {
    status: 'partial',
    clipped: pts,
    source,
    fullyVisible: false,
  };
}
