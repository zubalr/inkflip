/**
 * @inkflip/geometry — canonical page geometry and transform conformance.
 *
 * Implements COORDINATES.md contract version 1.0.0: the pdf_user ->
 * canonical transform C (UserUnit and effective view applied once),
 * display rotation R, raster scale S, OCR crop/resize composition O,
 * viewport/CSS mapping with DPR applied only at the backing canvas,
 * transform inversion with the 1e-5 pt composition bound, clipping
 * metadata that never deletes source polygons, and explicit-precision
 * contract Geometry objects (I02/I04: `polygon: null` iff `page_only`
 * or `unknown`).
 *
 * Shared contract types and primitives (`Matrix`, `Point`, `Box`,
 * `Page`, `Transform`, `Geometry`, `apply`, `inverse`, `ContractError`)
 * come from `@inkflip/contracts`; nothing here redefines them.
 */

export type {
  Box,
  Geometry,
  Matrix,
  Page,
  Point,
  Transform,
} from '../../contracts/src/index.ts';
export { ContractError } from '../../contracts/src/index.ts';

export {
  INVERSE_TOLERANCE_PT,
  MIN_DETERMINANT,
  apply,
  assertMatrix,
  assertVector,
  checkedInverse,
  compose,
  compose2,
  determinant,
  identity,
  inverse,
  inversePairError,
  isGeometryError,
  mapPoint,
  round6,
  roundMatrix,
  roundPoint,
  roundPolygon,
  scale,
  translate,
} from './affine.ts';

export {
  MAX_POLYGON_POINTS,
  MIN_POLYGON_AREA,
  boxPolygon,
  clipToView,
  pointInPolygon,
  polygonBounds,
  signedArea,
  transformPolygon,
} from './polygon.ts';
export type { ClipResult, ClipStatus } from './polygon.ts';

export {
  ID_PATTERN,
  MAX_TRANSFORM_IDS,
  TRANSFORM_OPERATIONS,
  ensureGeometryPage,
  ensurePage,
  makeGeometry,
  makeTransform,
} from './geometry.ts';
export type {
  GeometryInput,
  Precision,
  TransformInput,
  TransformOperation,
} from './geometry.ts';

export {
  backingScale,
  buildPage,
  canonicalSpace,
  canonicalTransform,
  chainPage,
  chainPageInverse,
  cropTranslate,
  cropTranslationRecord,
  cssSpace,
  displayRotation,
  displaySpace,
  displayTransformRecord,
  effectiveViewBox,
  ocrResize,
  ocrResizeRecord,
  ocrSpace,
  ocrToCanonical,
  pageToCanonical,
  pageToDisplay,
  pageToOcr,
  pageToRaster,
  pdfUserSpace,
  rasterScale,
  rasterSpace,
  rasterToCanonical,
  rasterTransformRecord,
  viewportRecord,
  viewportTransform,
} from './page.ts';
export type { BuiltPage, PageInput } from './page.ts';
