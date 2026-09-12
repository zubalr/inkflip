/**
 * Page-space transforms per planning/architecture/COORDINATES.md.
 *
 * Spaces: `pdf_user:pN` (original unrotated user space, UserUnit/72 inch
 * units), `canonical:pN` (unrotated effective view, top-left origin,
 * physical points), `display:pN` (canonical after the document's
 * quarter-turn rotation), `raster:<id>` (integer pixel grid),
 * `ocr:<id>` (crop/resized pixels), `css:<viewport>` (CSS pixels after
 * fit/zoom/pan).
 *
 *   C = [u,0,0,-u,-u*cx0, u*cy1]      pdf_user -> canonical
 *   W = u*(cx1-cx0), H = u*(cy1-cy0)  canonical size in physical points
 *   D = R * C                          pdf_user -> display
 *   P = Scale(s) * R * C               pdf_user -> raster
 *   O = Scale(kx,ky) * Translate(-rx,-ry) * P   pdf_user -> ocr
 *
 * UserUnit and the effective box are applied exactly once, in C; every
 * downstream matrix composes on top of C and never rescales by u again.
 */

import { require } from '../../contracts/src/index.ts';
import type {
  Box,
  Matrix,
  Page,
  Point,
  Transform,
} from '../../contracts/src/index.ts';
import {
  compose,
  identity,
  inverse,
  round6,
  roundMatrix,
  scale,
  translate,
} from './affine.ts';
import { ensurePage, makeTransform } from './geometry.ts';

/** Contract space identifiers (COORDINATES.md "Spaces"). */
export const pdfUserSpace = (pageIndex: number): string =>
  `pdf_user:p${pageIndex}`;
export const canonicalSpace = (pageIndex: number): string =>
  `canonical:p${pageIndex}`;
export const displaySpace = (pageIndex: number): string =>
  `display:p${pageIndex}`;
export const rasterSpace = (rasterId: string): string => `raster:${rasterId}`;
export const ocrSpace = (ocrId: string): string => `ocr:${ocrId}`;
export const cssSpace = (viewportId: string): string => `css:${viewportId}`;

const ROTATIONS = new Set([0, 90, 180, 270]);

function assertBox(box: unknown, what: string): asserts box is Box {
  require(
    Array.isArray(box) && box.length === 4 && box.every(Number.isFinite),
    'GEOMETRY',
    `${what} must be 4 finite numbers`,
  );
  require(
    (box as Box)[2]! > (box as Box)[0]! && (box as Box)[3]! > (box as Box)[1]!,
    'GEOMETRY',
    'Invalid page box',
  );
}

function assertRotation(rotation: number): asserts rotation is Page['rotation'] {
  require(
    ROTATIONS.has(rotation),
    'GEOMETRY',
    `Unsupported rotation ${String(rotation)}`,
  );
}

function assertUserUnit(u: number): void {
  require(
    typeof u === 'number' && Number.isFinite(u) && u > 0,
    'GEOMETRY',
    'user_unit must be a positive finite number',
  );
}

function assertPositive(v: number, what: string): void {
  require(
    typeof v === 'number' && Number.isFinite(v) && v > 0,
    'GEOMETRY',
    `${what} must be a positive finite number`,
  );
}

function assertFiniteNumber(v: number, what: string): void {
  require(
    typeof v === 'number' && Number.isFinite(v),
    'NONFINITE',
    `${what} must be finite`,
  );
}

/**
 * Effective view = CropBox ∩ MediaBox (CropBox defaults to MediaBox).
 * MediaBox, CropBox and effective view are not synonyms; unknown original
 * boxes stay null in the record. An empty intersection is unsupported
 * page geometry — it is rejected, never guessed (I11).
 */
export function effectiveViewBox(
  mediaBox: Box | null,
  cropBox: Box | null,
): Box {
  if (mediaBox !== null) assertBox(mediaBox, 'media_box');
  if (cropBox !== null) assertBox(cropBox, 'crop_box');
  require(
    mediaBox !== null || cropBox !== null,
    'GEOMETRY',
    'Effective view requires a crop or media box',
  );
  if (mediaBox === null) return cropBox as Box;
  if (cropBox === null) return mediaBox;
  const view: Box = [
    Math.max(mediaBox[0], cropBox[0]),
    Math.max(mediaBox[1], cropBox[1]),
    Math.min(mediaBox[2], cropBox[2]),
    Math.min(mediaBox[3], cropBox[3]),
  ];
  require(
    view[2]! > view[0]! && view[3]! > view[1]!,
    'GEOMETRY',
    'Effective view is empty',
  );
  return view;
}

/**
 * Canonical transform `C = [u,0,0,-u,-u*cx0, u*cy1]` and canonical size
 * `[W,H] = u * (view span)` in physical points. The effective box and
 * UserUnit enter exactly here — once.
 */
export function canonicalTransform(
  view: Box,
  userUnit: number,
): { matrix: Matrix; sizePt: Point } {
  assertBox(view, 'effective_view_box');
  assertUserUnit(userUnit);
  const [cx0, cy0, cx1, cy1] = view;
  return {
    matrix: [userUnit, 0, 0, -userUnit, -userUnit * cx0, userUnit * cy1],
    sizePt: [userUnit * (cx1 - cx0), userUnit * (cy1 - cy0)],
  };
}

/**
 * Clockwise display rotation in top-left canonical space. Returns the
 * matrix and the display size (`[H,W]` for the quarter turns).
 */
export function displayRotation(
  rotation: Page['rotation'],
  sizePt: Point,
): { matrix: Matrix; size: Point } {
  assertRotation(rotation);
  const [w, h] = sizePt;
  switch (rotation) {
    case 0:
      return { matrix: [1, 0, 0, 1, 0, 0], size: [w, h] };
    case 90:
      return { matrix: [0, 1, -1, 0, h, 0], size: [h, w] };
    case 180:
      return { matrix: [-1, 0, 0, -1, w, h], size: [w, h] };
    case 270:
      return { matrix: [0, -1, 1, 0, 0, w], size: [h, w] };
  }
}

/** Raster scale `s` pixels per physical point (uniform). */
export function rasterScale(scalePxPerPt: number): Matrix {
  assertPositive(scalePxPerPt, 'raster scale');
  return scale(scalePxPerPt);
}

/** OCR crop translation: crop origin (rx,ry) in raster pixels. */
export function cropTranslate(rx: number, ry: number): Matrix {
  assertFiniteNumber(rx, 'crop x');
  assertFiniteNumber(ry, 'crop y');
  return translate(-rx, -ry);
}

/** OCR resize by (kx,ky); `ocrResize(k)` resizes both axes. */
export function ocrResize(kx: number, ky = kx): Matrix {
  assertPositive(kx, 'resize kx');
  assertPositive(ky, 'resize ky');
  return scale(kx, ky);
}

/**
 * Viewport transform display -> CSS pixels: zoom `z` then pan
 * `(panX,panY)`. Device-pixel ratio is deliberately absent here — it is
 * applied only when crossing to the backing canvas, never to overlay
 * DOM coordinates (see {@link backingScale}).
 */
export function viewportTransform(input: {
  zoom: number;
  panX?: number;
  panY?: number;
}): Matrix {
  assertPositive(input.zoom, 'zoom');
  const panX = input.panX ?? 0;
  const panY = input.panY ?? 0;
  assertFiniteNumber(panX, 'panX');
  assertFiniteNumber(panY, 'panY');
  return compose(translate(panX, panY), scale(input.zoom));
}

/**
 * CSS -> backing-canvas pixel scale. This is the only place DPR enters:
 * DOM overlay coordinates remain CSS pixels and are never multiplied by
 * DPR a second time.
 */
export function backingScale(dpr: number): Matrix {
  assertPositive(dpr, 'device pixel ratio');
  return scale(dpr);
}

export interface PageInput {
  index: number;
  /** Original MediaBox, or null when unknown (e.g. PDF.js page.view only). */
  mediaBox?: Box | null;
  /** Original CropBox, or null when unknown. */
  cropBox?: Box | null;
  /**
   * Explicit effective view (e.g. a reader's reported view). When both
   * original boxes are known the derived CropBox∩MediaBox must agree
   * with it within 1e-5; otherwise the explicit value is the view.
   */
  viewBox?: Box;
  userUnit?: number;
  rotation?: Page['rotation'];
  boxSource: string;
  /** Transform id for the raw-to-canonical record (default t_pN_canonical). */
  transformId?: string;
  limitations?: string[];
}

export interface BuiltPage {
  page: Page;
  /** The page's `raw_to_canonical` transform record (C). */
  canonical: Transform;
  /** Canonical size in physical points, `[W,H]`. */
  canonicalSizePt: Point;
  /** Effective view used for C (derived or explicit). */
  effectiveView: Box;
}

const VIEW_TOLERANCE = 1e-5;

/**
 * Build the contract `Page` record plus its raw-to-canonical transform.
 * UserUnit and the effective box are applied once, in C; canonical size
 * is `u * view span` exactly.
 */
export function buildPage(input: PageInput): BuiltPage {
  require(
    Number.isInteger(input.index) && input.index >= 0,
    'PAGE',
    'Page index must be a nonnegative integer',
  );
  const mediaBox = input.mediaBox ?? null;
  const cropBox = input.cropBox ?? null;
  const userUnit = input.userUnit ?? 1;
  const rotation = input.rotation ?? 0;
  assertUserUnit(userUnit);
  assertRotation(rotation);
  if (mediaBox !== null) assertBox(mediaBox, 'media_box');
  if (cropBox !== null) assertBox(cropBox, 'crop_box');

  let view: Box;
  if (mediaBox !== null || cropBox !== null) {
    view = effectiveViewBox(mediaBox, cropBox);
    if (input.viewBox !== undefined) {
      assertBox(input.viewBox, 'effective_view_box');
      const agree = view.every(
        (v, i) => Math.abs(v - input.viewBox![i]!) <= VIEW_TOLERANCE,
      );
      require(agree, 'GEOMETRY', 'Effective view conflicts with page boxes');
    }
  } else {
    require(
      input.viewBox !== undefined,
      'GEOMETRY',
      'Effective view requires boxes or an explicit view',
    );
    assertBox(input.viewBox, 'effective_view_box');
    view = input.viewBox;
  }

  require(
    typeof input.boxSource === 'string' &&
      input.boxSource.length > 0 &&
      input.boxSource.length <= 200,
    'GEOMETRY',
    'box_source must be 1..200 chars',
  );
  const limitations = input.limitations ?? [];
  require(
    limitations.length <= 32 &&
      limitations.every((l) => typeof l === 'string' && l.length <= 2000),
    'GEOMETRY',
    'limitations must be <=32 strings of <=2000 chars',
  );

  const { matrix, sizePt } = canonicalTransform(view, userUnit);
  const transformId = input.transformId ?? `t_p${input.index}_canonical`;
  const extent: Point[] = [
    [0, 0],
    [sizePt[0], 0],
    [0, sizePt[1]],
    [sizePt[0], sizePt[1]],
  ];
  const canonical = makeTransform({
    id: transformId,
    pageIndex: input.index,
    fromSpace: pdfUserSpace(input.index),
    toSpace: canonicalSpace(input.index),
    matrix,
    operation: 'page_box_to_canonical',
    precision: 'exact',
    source: input.boxSource,
    extent,
  });
  const page: Page = {
    index: input.index,
    media_box: mediaBox,
    crop_box: cropBox,
    effective_view_box: view,
    box_source: input.boxSource,
    user_unit: userUnit,
    rotation,
    canonical_size_pt: [round6(sizePt[0]), round6(sizePt[1])],
    raw_to_canonical_transform_id: canonical.id,
    limitations: [...limitations],
  };
  return { page, canonical, canonicalSizePt: page.canonical_size_pt, effectiveView: view };
}

/** Contract record for the display rotation `R` (canonical -> display). */
export function displayTransformRecord(
  page: Page,
  id = `t_p${page.index}_display`,
): Transform {
  const { matrix } = displayRotation(page.rotation, page.canonical_size_pt);
  return makeTransform({
    id,
    pageIndex: page.index,
    fromSpace: canonicalSpace(page.index),
    toSpace: displaySpace(page.index),
    matrix,
    operation: 'display_rotation',
    precision: 'exact',
    source: `Document /Rotate ${page.rotation} quarter-turn in top-left canonical space`,
    extent: [
      [0, 0],
      [page.canonical_size_pt[0], 0],
      [0, page.canonical_size_pt[1]],
      page.canonical_size_pt,
    ],
  });
}

/** Contract record for raster scale `s` px/pt (display -> raster). */
export function rasterTransformRecord(
  page: Page,
  scalePxPerPt: number,
  rasterId: string,
  id = `t_p${page.index}_raster_${rasterId}`,
): Transform {
  return makeTransform({
    id,
    pageIndex: page.index,
    fromSpace: displaySpace(page.index),
    toSpace: rasterSpace(rasterId),
    matrix: rasterScale(scalePxPerPt),
    operation: 'raster_scale',
    precision: 'exact',
    source: `Render scale ${scalePxPerPt} px/pt for raster:${rasterId}`,
  });
}

/** Contract record for an OCR crop translation (raster -> ocr). */
export function cropTranslationRecord(
  page: Page,
  rasterId: string,
  ocrId: string,
  rx: number,
  ry: number,
  id = `t_p${page.index}_crop_${ocrId}`,
): Transform {
  return makeTransform({
    id,
    pageIndex: page.index,
    fromSpace: rasterSpace(rasterId),
    toSpace: ocrSpace(ocrId),
    matrix: cropTranslate(rx, ry),
    operation: 'crop_translation',
    precision: 'exact',
    source: `OCR crop origin (${rx},${ry}) raster pixels for ocr:${ocrId}`,
  });
}

/** Contract record for an OCR resize (ocr -> ocr). */
export function ocrResizeRecord(
  page: Page,
  ocrId: string,
  kx: number,
  ky = kx,
  id = `t_p${page.index}_ocrresize_${ocrId}`,
): Transform {
  return makeTransform({
    id,
    pageIndex: page.index,
    fromSpace: ocrSpace(ocrId),
    toSpace: ocrSpace(ocrId),
    matrix: ocrResize(kx, ky),
    operation: 'ocr_resize',
    precision: 'exact',
    source: `OCR resize (${kx},${ky}) for ocr:${ocrId}`,
  });
}

/** Contract record for the display -> CSS viewport transform. */
export function viewportRecord(
  page: Page,
  viewportId: string,
  view: { zoom: number; panX?: number; panY?: number },
  id = `t_p${page.index}_viewport_${viewportId}`,
): Transform {
  return makeTransform({
    id,
    pageIndex: page.index,
    fromSpace: displaySpace(page.index),
    toSpace: cssSpace(viewportId),
    matrix: viewportTransform(view),
    operation: 'viewport',
    precision: 'exact',
    source: `Viewport zoom ${view.zoom} pan (${view.panX ?? 0},${view.panY ?? 0})`,
  });
}

// ---------------------------------------------------------------------------
// Composed math helpers (not contract records; the per-step records above
// carry provenance). D = R·C, P = S·R·C, O = K·T·S·R·C.
// ---------------------------------------------------------------------------

/** pdf_user -> canonical matrix C for a built page. */
export function pageToCanonical(built: BuiltPage): Matrix {
  return built.canonical.matrix;
}

/** pdf_user -> display matrix `D = R·C`. */
export function pageToDisplay(built: BuiltPage): Matrix {
  const { matrix: r } = displayRotation(
    built.page.rotation,
    built.canonicalSizePt,
  );
  return compose(r, built.canonical.matrix);
}

/** pdf_user -> raster matrix `P = Scale(s)·R·C`. */
export function pageToRaster(built: BuiltPage, scalePxPerPt: number): Matrix {
  return compose(rasterScale(scalePxPerPt), pageToDisplay(built));
}

/**
 * pdf_user -> OCR pixel matrix `O = Scale(kx,ky)·Translate(-rx,-ry)·P`.
 * An OCR crop never starts implicitly at the page origin: rx/ry are the
 * recorded raster-pixel crop origin.
 */
export function pageToOcr(
  built: BuiltPage,
  scalePxPerPt: number,
  crop: Point,
  resize: Point,
): Matrix {
  return compose(
    ocrResize(resize[0], resize[1]),
    cropTranslate(crop[0], crop[1]),
    pageToRaster(built, scalePxPerPt),
  );
}

/**
 * OCR pixel -> canonical matrix `C·O⁻¹` (recover a canonical point from an
 * OCR crop). Equivalently `R⁻¹·S⁻¹·T⁻¹·K⁻¹`; stored transforms keep the
 * forward direction, recovery composes their inverses in reverse order.
 */
export function ocrToCanonical(
  built: BuiltPage,
  scalePxPerPt: number,
  crop: Point,
  resize: Point,
): Matrix {
  const { matrix: r } = displayRotation(
    built.page.rotation,
    built.canonicalSizePt,
  );
  return compose(
    inverse(r),
    inverse(rasterScale(scalePxPerPt)),
    inverse(cropTranslate(crop[0], crop[1])),
    inverse(ocrResize(resize[0], resize[1])),
  );
}

/** Raster pixel -> canonical matrix `C·P⁻¹ = R⁻¹·S⁻¹`. */
export function rasterToCanonical(
  built: BuiltPage,
  scalePxPerPt: number,
): Matrix {
  const { matrix: r } = displayRotation(
    built.page.rotation,
    built.canonicalSizePt,
  );
  return compose(inverse(r), inverse(rasterScale(scalePxPerPt)));
}

/**
 * Compose a chain of contract Transform records for one page into a
 * single matrix (right-to-left: records are applied in array order).
 * Fails loudly if any record belongs to another page.
 */
export function chainPage(records: Transform[], pageIndex: number): Matrix {
  ensurePage(records, pageIndex);
  return records.reduceRight((acc, t) => compose(acc, t.matrix), identity());
}

/**
 * Invert a chain of contract Transform records for one page.
 */
export function chainPageInverse(
  records: Transform[],
  pageIndex: number,
): Matrix {
  ensurePage(records, pageIndex);
  return records.reduce(
    (acc, t) => compose(acc, t.inverse),
    identity(),
  );
}
