/**
 * Contract-facing builders for `Transform` and `Geometry` objects.
 *
 * These builders emit schema-shaped records (see generated types in
 * `@inkflip/contracts`) with the semantic rules already enforced at
 * construction time rather than left to a later validation pass:
 *
 * - Transform inverses are computed eagerly and the stored pair must
 *   compose within 1e-5 pt on the caller's extent, so singular or
 *   precision-amplifying transforms are rejected where they are made.
 * - Geometry precision is explicit and never inferred. `page_only` and
 *   `unknown` carry `polygon: null` (I04: no precise highlight without
 *   independently supplied geometry); `exact` and `estimated` require a
 *   non-degenerate 3..64-vertex polygon.
 */

import { require } from '../../contracts/src/index.ts';
import type {
  Geometry,
  Matrix,
  Point,
  Transform,
} from '../../contracts/src/index.ts';
import {
  INVERSE_TOLERANCE_PT,
  assertMatrix,
  assertVector,
  checkedInverse,
  roundMatrix,
  roundPolygon,
} from './affine.ts';
import {
  MAX_POLYGON_POINTS,
  MIN_POLYGON_AREA,
  signedArea,
} from './polygon.ts';

/** Schema id pattern shared by transform ids and geometry references. */
export const ID_PATTERN = /^[a-z][a-z0-9_-]{0,95}$/;

/** Schema cap on `transform_ids` per geometry. */
export const MAX_TRANSFORM_IDS = 16;

export const TRANSFORM_OPERATIONS = new Set([
  'page_box_to_canonical',
  'display_rotation',
  'raster_scale',
  'crop_translation',
  'viewport',
  'ocr_resize',
]);

export type TransformOperation = Transform['operation'];

export type Precision = Geometry['precision'];

function assertId(id: unknown, what: string): asserts id is string {
  require(
    typeof id === 'string' && ID_PATTERN.test(id),
    'ID',
    `${what} must match ${ID_PATTERN}`,
  );
}

export interface TransformInput {
  id: string;
  pageIndex: number;
  fromSpace: string;
  toSpace: string;
  matrix: Matrix;
  operation: TransformOperation;
  precision: 'exact' | 'estimated';
  source: string;
  /**
   * Points over which the stored matrix/inverse pair must compose within
   * 1e-5 pt. An explicit extent must contain at least one finite point.
   * Default probes cover origin, unit axes and a +/-10,000-pt square.
   */
  extent?: Point[];
}

/**
 * Default composition-check extent: origin, unit axes and a +/-10,000 pt
 * square (roughly 3.5 m of physical page — far beyond real pages). Callers
 * pass the actual domain extent when a transform maps a specific range.
 */
const DEFAULT_EXTENT: Point[] = [
  [0, 0],
  [1, 0],
  [0, 1],
  [1e4, 1e4],
  [-1e4, -1e4],
];

/**
 * Overlay error budget in physical points: the viewer's p95 <= 2px bound
 * is the tightest downstream consumer, so transform storage may not
 * amplify its own 6-decimal rounding beyond ~2pt of induced error.
 */
export const OVERLAY_BUDGET_PT = 2;

/** Storage rounding bound per component (6 decimal places). */
const STORAGE_STEP = 5e-7;

/**
 * Build a contract `Transform`.
 *
 * - The stored matrix is rounded to 6 decimals (finite only, -0 -> 0).
 * - The inverse is computed eagerly on the *stored* matrix and the exact
 *   pair must compose within 1e-5 pt on the extent (singular and
 *   numerically pathological transforms are rejected).
 * - The stored inverse is itself rounded, then checked componentwise
 *   against the exact inverse within 1e-5 — the same rule the report
 *   validator applies.
 * - Round-off amplification guard: a stored inverse entry of magnitude M
 *   amplifies the 5e-7 storage step into M*5e-7 pt of mapping error; it
 *   must not exceed the overlay budget, so extreme dimensions/extents
 *   that destroy stored precision are rejected rather than silently
 *   degraded.
 */
export function makeTransform(input: TransformInput): Transform {
  assertId(input.id, 'transform id');
  require(
    Number.isInteger(input.pageIndex) && input.pageIndex >= 0,
    'PAGE',
    'Transform page index must be a nonnegative integer',
  );
  require(
    typeof input.fromSpace === 'string' && input.fromSpace.length <= 100,
    'TRANSFORM',
    'from_space too long',
  );
  require(
    typeof input.toSpace === 'string' && input.toSpace.length <= 100,
    'TRANSFORM',
    'to_space too long',
  );
  require(
    TRANSFORM_OPERATIONS.has(input.operation),
    'TRANSFORM',
    `Unknown transform operation ${String(input.operation)}`,
  );
  require(
    input.precision === 'exact' || input.precision === 'estimated',
    'TRANSFORM',
    'Transform precision must be exact or estimated',
  );
  require(
    typeof input.source === 'string' && input.source.length <= 2000,
    'TRANSFORM',
    'source too long',
  );
  assertMatrix(input.matrix);
  const matrix = roundMatrix(input.matrix);
  const exactInverse = checkedInverse(matrix, input.extent ?? DEFAULT_EXTENT);
  const inv = roundMatrix(exactInverse);
  // Contract rule (validateReport): stored inverse within 1e-5 of exact.
  for (let i = 0; i < 6; i++) {
    require(
      Math.abs(inv[i]! - exactInverse[i]!) <= INVERSE_TOLERANCE_PT,
      'TRANSFORM',
      'Stored inverse diverges from exact inverse',
    );
  }
  // Relative-error guard: the inverse is the amplification direction.
  const maxInv = Math.max(...inv.map((v) => Math.abs(v)));
  require(
    maxInv * STORAGE_STEP <= OVERLAY_BUDGET_PT,
    'TRANSFORM',
    `Inverse magnitude ${maxInv} amplifies storage rounding beyond the overlay budget`,
  );
  return {
    id: input.id,
    page_index: input.pageIndex,
    from_space: input.fromSpace,
    to_space: input.toSpace,
    matrix,
    inverse: inv,
    operation: input.operation,
    precision: input.precision,
    source: input.source,
  };
}

export interface GeometryInput {
  precision: Precision;
  polygon: Point[] | null;
  transformIds: string[];
  basis: string;
}

/**
 * Build a contract `Geometry` in `canonical_page` space. Enforces the
 * precision/polygon invariant exactly as the report validator does:
 * `polygon === null` iff precision is `page_only` or `unknown` — the
 * implementation can never emit a precise-looking polygon without an
 * independently supplied one (I04), nor attach null geometry to an
 * `exact`/`estimated` claim.
 */
export function makeGeometry(input: GeometryInput): Geometry {
  const { precision, polygon, transformIds, basis } = input;
  require(
    precision === 'exact' ||
      precision === 'estimated' ||
      precision === 'page_only' ||
      precision === 'unknown',
    'GEOMETRY',
    `Unknown precision ${String(precision)}`,
  );
  require(
    typeof basis === 'string' && basis.length <= 2000,
    'GEOMETRY',
    'basis too long',
  );
  require(
    Array.isArray(transformIds) && transformIds.length <= MAX_TRANSFORM_IDS,
    'ID',
    `transform_ids must be <= ${MAX_TRANSFORM_IDS}`,
  );
  for (const id of transformIds) assertId(id, 'transform id');
  const mustBeNull = precision === 'page_only' || precision === 'unknown';
  require(
    (polygon === null) === mustBeNull,
    'GEOMETRY',
    'Precision/polygon conflict',
  );
  if (polygon === null) {
    return {
      precision,
      space: 'canonical_page',
      polygon: null,
      transform_ids: [...transformIds],
      basis,
    };
  }
  assertPolygon(polygon);
  return {
    precision,
    space: 'canonical_page',
    polygon: roundPolygon(polygon),
    transform_ids: [...transformIds],
    basis,
  };
}

function assertPolygon(polygon: Point[]): void {
  require(
    Array.isArray(polygon) &&
      polygon.length >= 3 &&
      polygon.length <= MAX_POLYGON_POINTS,
    'GEOMETRY',
    `polygon needs 3..${MAX_POLYGON_POINTS} points`,
  );
  for (const p of polygon) assertVector(p, 2, 'polygon point');
  const rounded = roundPolygon(polygon);
  require(
    Math.abs(signedArea(rounded)) > MIN_POLYGON_AREA,
    'GEOMETRY',
    'Degenerate source polygon',
  );
}

/**
 * Page-identity guard: every transform referenced for a page must carry
 * that page_index. Page identity errors are release blockers, so binding
 * fails loudly instead of silently mapping through another page's chain.
 */
export function ensurePage(
  transforms: Transform[],
  pageIndex: number,
): Transform[] {
  for (const t of transforms) {
    require(
      t.page_index === pageIndex,
      'PAGE',
      `Transform ${t.id} belongs to page ${t.page_index}, not ${pageIndex}`,
    );
  }
  return transforms;
}

/**
 * Geometry-reference guard: every `transform_ids` entry must resolve to a
 * transform on the same page — mirrors the report validator's
 * `Geometry crosses transform pages` rule for pre-validation use.
 */
export function ensureGeometryPage(
  geometry: Geometry,
  transforms: Transform[],
  pageIndex: number,
): Geometry {
  const byId = new Map(transforms.map((t) => [t.id, t]));
  for (const id of geometry.transform_ids) {
    const t = byId.get(id);
    require(t !== undefined, 'REFERENCE', `Missing geometry transform ${id}`);
    require(
      t.page_index === pageIndex,
      'TRANSFORM',
      'Geometry crosses transform pages',
    );
  }
  return geometry;
}
