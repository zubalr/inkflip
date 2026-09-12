/**
 * Affine matrix primitives over the canonical contract layout.
 *
 * All matrices use the contract's six-component column-vector form
 * `[a,b,c,d,e,f]` with `x' = a*x + c*y + e`, `y' = b*x + d*y + f`
 * (planning/architecture/COORDINATES.md). Composition is right-to-left:
 * `compose(A, B)` applies B first, then A.
 *
 * Shared contract types and the authoritative `apply`/`inverse`/
 * `ContractError`/`require` primitives come from `@inkflip/contracts`
 * (T03); this package does not redefine them.
 */

import {
  ContractError,
  apply,
  inverse as contractInverse,
  require,
} from '../../contracts/src/index.ts';
import type { Matrix, Point } from '../../contracts/src/index.ts';

export { apply };

/**
 * Contract `inverse` typed on the `Matrix` tuple. Throws
 * `ContractError('TRANSFORM')` when |det| <= 1e-12.
 */
export function inverse(m: Matrix): Matrix {
  return contractInverse(m) as Matrix;
}

/** Maximum absolute round-trip error accepted for a matrix/inverse pair. */
export const INVERSE_TOLERANCE_PT = 1e-5;

/** Minimum absolute determinant for an invertible transform (contract). */
export const MIN_DETERMINANT = 1e-12;

/** Identity matrix. */
export function identity(): Matrix {
  return [1, 0, 0, 1, 0, 0];
}

/** Translation by (tx, ty). */
export function translate(tx: number, ty: number): Matrix {
  return [1, 0, 0, 1, tx, ty];
}

/** Axis-aligned scale; `scale(s)` scales both axes. */
export function scale(sx: number, sy = sx): Matrix {
  return [sx, 0, 0, sy, 0, 0];
}

/**
 * Right-to-left column composition: `compose(A, B, C)` is `A·B·C`,
 * i.e. the point transform that applies C first, then B, then A.
 */
export function compose(...ms: Matrix[]): Matrix {
  require(ms.length > 0, 'TRANSFORM', 'compose needs at least one matrix');
  return ms.reduce((acc, m) => compose2(acc, m));
}

/** `A·B` — apply B first, then A. Matches planning contractlib.compose. */
export function compose2(a: Matrix, b: Matrix): Matrix {
  const [a0, a1, a2, a3, a4, a5] = a;
  const [b0, b1, b2, b3, b4, b5] = b;
  return [
    a0 * b0 + a2 * b1,
    a1 * b0 + a3 * b1,
    a0 * b2 + a2 * b3,
    a1 * b2 + a3 * b3,
    a0 * b4 + a2 * b5 + a4,
    a1 * b4 + a3 * b5 + a5,
  ];
}

/** Determinant of the linear part: `a*d - b*c`. */
export function determinant(m: Matrix): number {
  return m[0] * m[3] - m[1] * m[2];
}

/**
 * Contract storage rounding: six decimal places, finite only, negative
 * zero normalized to zero (COORDINATES.md "Precision, clipping and order").
 */
export function round6(n: number): number {
  require(
    typeof n === 'number' && Number.isFinite(n),
    'NONFINITE',
    'Transform number must be finite',
  );
  const r = Math.round(n * 1e6) / 1e6;
  return r === 0 ? 0 : r;
}

/** Round every component of a matrix to contract storage precision. */
export function roundMatrix(m: Matrix): Matrix {
  return m.map(round6) as Matrix;
}

/** Round a point to contract storage precision. */
export function roundPoint(p: Point): Point {
  return [round6(p[0]), round6(p[1])];
}

/** Round every vertex of a polygon to contract storage precision. */
export function roundPolygon(points: Point[]): Point[] {
  return points.map(roundPoint);
}

/** Assert a value is a finite number array of exactly `n` entries. */
export function assertVector(
  value: unknown,
  n: number,
  what: string,
): asserts value is number[] {
  require(
    Array.isArray(value) &&
      value.length === n &&
      value.every((v) => typeof v === 'number'),
    'TYPE',
    `${what} must be ${n} numbers`,
  );
  for (const v of value) {
    require(Number.isFinite(v), 'NONFINITE', `${what} must be finite`);
  }
}

/** Assert a six-component affine matrix is well-formed and finite. */
export function assertMatrix(m: unknown): asserts m is Matrix {
  assertVector(m, 6, 'matrix');
}

/**
 * Worst absolute error of the matrix/inverse pair over `points`, tested in
 * both directions (`M·M⁻¹` and `M⁻¹·M` applied to each probe point). The
 * contract bound is 1e-5 physical points on the test extent; at extreme
 * coordinates relative error also matters, so callers pass the actual page
 * extent they will map.
 */
export function inversePairError(
  m: Matrix,
  inv: Matrix,
  points: Point[],
): number {
  require(
    Array.isArray(points) && points.length > 0,
    'TRANSFORM',
    'Inverse check extent must contain at least one point',
  );
  let worst = 0;
  const fwd = compose2(m, inv);
  const bwd = compose2(inv, m);
  for (const p of points) {
    assertVector(p, 2, 'extent point');
    const a = apply(fwd, p);
    const b = apply(bwd, p);
    worst = Math.max(
      worst,
      Math.abs(a[0] - p[0]),
      Math.abs(a[1] - p[1]),
      Math.abs(b[0] - p[0]),
      Math.abs(b[1] - p[1]),
    );
  }
  return worst;
}

/**
 * Invert a matrix, then verify the pair on `points`. Singular or
 * near-singular matrices (|det| <= 1e-12) and pairs whose composition
 * error exceeds 1e-5 pt on the extent are rejected — never silently
 * accepted with degraded precision.
 */
export function checkedInverse(m: Matrix, extent: Point[]): Matrix {
  const inv = inverse(m); // throws ContractError TRANSFORM when |det|<=1e-12
  const err = inversePairError(m, inv, extent);
  require(
    err <= INVERSE_TOLERANCE_PT,
    'TRANSFORM',
    `Matrix/inverse composition error ${err} exceeds ${INVERSE_TOLERANCE_PT}pt`,
  );
  return inv;
}

/** Apply a sequence of matrices right-to-left to a point. */
export function mapPoint(p: Point, ...ms: Matrix[]): Point {
  let out: Point = [p[0], p[1]];
  for (let i = ms.length - 1; i >= 0; i--) out = apply(ms[i]!, out);
  return out;
}

/** Assert a ContractError code surface is not widened by accident. */
export function isGeometryError(
  exc: unknown,
  code: string,
): exc is ContractError {
  return exc instanceof ContractError && exc.code === code;
}
