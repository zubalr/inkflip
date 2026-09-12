/**
 * OCR crop/resize planning (T10) — the `O` transform chain of
 * planning/architecture/COORDINATES.md:
 *
 *   O = Scale(kx,ky) · Translate(-rx,-ry) · P      P = Scale(s) · R · C
 *
 * Every step is a recorded contract Transform (packages/geometry) so a
 * produced occurrence's pixel box can be mapped back to canonical page
 * points exactly. The user's original region and the padded OCR crop
 * are preserved separately (READER_ADAPTER_CONTRACT): padding is
 * max(8 raster px, 10% of region height), clipped to the raster.
 *
 * Bounds are enforced here, before pixels reach the engine:
 * - crop output pixels > `maxRasterPixels` → downscale by a recorded
 *   factor k (actual scale recorded + visible warning limitation);
 * - crop output edge > `maxRasterEdge` → likewise downscaled;
 * - impossible/degenerate geometry is rejected, never guessed (I11).
 */
import {
  compose,
  displayRotation,
  mapPoint,
  ocrResizeRecord,
  cropTranslationRecord,
  rasterTransformRecord,
  rasterScale,
  round6,
  transformPolygon,
  polygonBounds,
} from '../../geometry/src/index.ts';
import type {
  Matrix,
  Page,
  Point,
  Transform,
} from '../../contracts/src/index.ts';
import { OcrError, OCR_REASON, requireOcr } from './errors.ts';

/** A raster produced by the named render reader for one page. */
export interface PageRasterInfo {
  /** Space id suffix: `raster:<rasterId>`. */
  readonly rasterId: string;
  /** Reader id of the renderer that produced it (render_reader_id). */
  readonly renderReaderId: string;
  /** Physical-points-per-pixel scale used by the renderer, px/pt. */
  readonly scalePxPerPt: number;
  readonly widthPx: number;
  readonly heightPx: number;
}

/** A resolved user selection in canonical page space. */
export interface OcrRegionInput {
  /** Region id referenced by the check plan. */
  readonly id: string;
  /** Canonical-space polygon (Region.geometry.polygon). */
  readonly polygon: readonly Point[] | null;
  /** Free-form user label, e.g. a recorded 'single-line' choice. */
  readonly label: string;
}

export interface CropPlan {
  /** Integer padded+clipped crop origin/size in raster pixels. */
  readonly cropX: number;
  readonly cropY: number;
  readonly cropWidthPx: number;
  readonly cropHeightPx: number;
  /**
   * The user's region mapped to raster pixels BEFORE padding —
   * preserved separately from the padded crop (float bounds), or
   * null for a full-page check.
   */
  readonly regionPx: readonly [number, number, number, number] | null;
  /** Padding actually applied in raster px (0 for full-page crops). */
  readonly paddingPx: number;
  /** Recorded OCR resize factor (post-crop downscale; 1 = none). */
  readonly resizeK: number;
  /**
   * Fractional-destination clipping in output px `[right, bottom]`,
   * each in [0,1): the drawn destination is crop*resizeK while the
   * integer canvas is outW x outH. [0,0] when nothing is clipped.
   */
  readonly resizeClipPx: readonly [number, number];
  /** OCR input size entering the engine after resize. */
  readonly outWidthPx: number;
  readonly outHeightPx: number;
  /** `ocr:<ocrId>` space id for this crop. */
  readonly ocrId: string;
  /** raster_scale + crop_translation + ocr_resize records. */
  readonly transforms: Transform[];
  /** Honest notes (downsampled scale, clipped padding, ...). */
  readonly limitations: string[];
}

export interface CropBounds {
  /** Max pixels entering the engine per crop (default 4_000_000). */
  readonly maxRasterPixels: number;
  /** Max edge length entering the engine (default 8192). */
  readonly maxRasterEdge: number;
}

/**
 * canonical -> raster pixel map `S·R` for a page: display rotation R
 * then uniform raster scale S (the chain is `raster:` space, not
 * pdf_user, so C is not re-applied).
 */
export function canonicalToRaster(page: Page, scalePxPerPt: number): Matrix {
  const { matrix: r } = displayRotation(page.rotation, page.canonical_size_pt);
  return compose(rasterScale(scalePxPerPt), r);
}

/**
 * Candidate ocr_resize factors for a downscaled crop, best first. The
 * record is exact only if `floor(crop * k)` reproduces the realized
 * integer output on both axes — i.e. k lies inside the half-open
 * interval
 *
 *   [max(outW/cropW, outH/cropH), min((outW+1)/cropW, (outH+1)/cropH))
 *
 * — and only if k is representable at the contract's six-decimal
 * storage precision: makeTransform rounds the matrix, and
 * CropPlan.resizeK is the same stored value, so the recorded factor
 * must already be a six-decimal value.
 *
 * Exactly three constant candidates at the interval's lower edge
 * (independent review, T10 arithmetic pass): `m = ceil(lo * 1e6)` is
 * the smallest representable value not below the floor-realization
 * lower bound; `m + 1` covers downward product rounding at a boundary;
 * `m - 1` allows a bounded smaller realization when the upward
 * candidates would push the output past a cap. The caller re-derives
 * and re-verifies the realized size for each candidate, so the record
 * and the realized output stay consistent by construction.
 */
function recordedResizeK(
  cropW: number,
  cropH: number,
  outW: number,
  outH: number,
): number[] {
  const lo = Math.max(outW / cropW, outH / cropH);
  const m = Math.ceil(lo * 1e6);
  return [m / 1e6, (m + 1) / 1e6, (m - 1) / 1e6];
}

/**
 * Plan one OCR crop. `region` is the resolved canonical selection
 * (null → full page). Returns the recorded chain; throws OcrError
 * (geometry_unavailable / resource_limit) for impossible input.
 */
export function planCrop(input: {
  readonly page: Page;
  readonly raster: PageRasterInfo;
  readonly checkId: string;
  readonly region?: OcrRegionInput | null;
  readonly bounds: CropBounds;
  /** Context padding floor in raster px (default 8). */
  readonly padMinPx?: number;
  /** Context padding as a fraction of region height (default 0.10). */
  readonly padHeightRatio?: number;
}): CropPlan {
  const { page, raster, checkId, region, bounds } = input;
  const padMin = input.padMinPx ?? 8;
  const padRatio = input.padHeightRatio ?? 0.1;
  requireOcr(
    Number.isFinite(raster.scalePxPerPt) && raster.scalePxPerPt > 0,
    OCR_REASON.GEOMETRY_UNAVAILABLE,
    'raster scale must be a positive finite number',
  );
  requireOcr(
    Number.isInteger(raster.widthPx) && raster.widthPx > 0 &&
      Number.isInteger(raster.heightPx) && raster.heightPx > 0,
    OCR_REASON.GEOMETRY_UNAVAILABLE,
    `raster must have positive integer pixels (got ${raster.widthPx}x${raster.heightPx})`,
  );

  const limitations: string[] = [];
  const canon2raster = canonicalToRaster(page, raster.scalePxPerPt);

  // Region polygon -> raster float bounds (the user's original region,
  // kept distinct from the padded crop below).
  let regionPx: [number, number, number, number] | null = null;
  if (region !== null && region !== undefined) {
    requireOcr(
      region.polygon !== null && region.polygon.length >= 3,
      OCR_REASON.GEOMETRY_UNAVAILABLE,
      `region ${region.id} has no usable polygon (page_only/unknown)`,
    );
    const mapped = transformPolygon(canon2raster, [...region.polygon]);
    const b = polygonBounds(mapped);
    requireOcr(
      b.every(Number.isFinite) && b[2] > b[0] && b[3] > b[1],
      OCR_REASON.GEOMETRY_UNAVAILABLE,
      `region ${region.id} maps to degenerate raster bounds`,
    );
    regionPx = [b[0], b[1], b[2], b[3]];
  }

  // Unpadded crop rectangle in raster px (float -> outward int bounds).
  const base: [number, number, number, number] = regionPx ?? [
    0,
    0,
    raster.widthPx,
    raster.heightPx,
  ];
  const regionH = base[3] - base[1];
  const pad = region === null || region === undefined
    ? 0
    : Math.max(padMin, Math.ceil(regionH * padRatio));

  let x0 = Math.floor(base[0] - pad);
  let y0 = Math.floor(base[1] - pad);
  let x1 = Math.ceil(base[2] + pad);
  let y1 = Math.ceil(base[3] + pad);

  // Clip to the raster; clipping is recorded, never fatal.
  const clippedX0 = Math.max(0, x0);
  const clippedY0 = Math.max(0, y0);
  const clippedX1 = Math.min(raster.widthPx, x1);
  const clippedY1 = Math.min(raster.heightPx, y1);
  if (
    clippedX0 !== x0 || clippedY0 !== y0 || clippedX1 !== x1 || clippedY1 !== y1
  ) {
    limitations.push(
      `crop_padding_clipped: requested (${x0},${y0})-(${x1},${y1}) ` +
        `clipped to raster ${raster.widthPx}x${raster.heightPx}`,
    );
  }
  x0 = clippedX0;
  y0 = clippedY0;
  x1 = clippedX1;
  y1 = clippedY1;
  requireOcr(
    x1 > x0 && y1 > y0,
    OCR_REASON.GEOMETRY_UNAVAILABLE,
    'crop rectangle is empty after clipping to the raster',
  );

  const cropW = x1 - x0;
  const cropH = y1 - y0;

  // Bounded OCR input: downscale when the crop exceeds pixel or edge
  // caps; the actual factor is recorded in the ocr_resize transform
  // and surfaced as a user-visible limitation (never silent).
  const pixels = cropW * cropH;
  const edge = Math.max(cropW, cropH);
  let k = 1;
  if (pixels > bounds.maxRasterPixels) {
    k = Math.min(k, Math.sqrt(bounds.maxRasterPixels / pixels));
  }
  if (edge > bounds.maxRasterEdge) {
    k = Math.min(k, bounds.maxRasterEdge / edge);
  }
  let outW = cropW;
  let outH = cropH;
  /** Fractional-destination clipping in output px: [right, bottom]. */
  let resizeClip: readonly [number, number] = [0, 0];
  if (k < 1) {
    outW = Math.max(1, Math.floor(cropW * k));
    outH = Math.max(1, Math.floor(cropH * k));
    requireOcr(
      outW * outH <= bounds.maxRasterPixels &&
        Math.max(outW, outH) <= bounds.maxRasterEdge,
      OCR_REASON.RESOURCE_LIMIT,
      `downscaled OCR input ${outW}x${outH} still exceeds caps`,
    );
    // The recorded factor maps recorded-space output pixels back to the
    // crop grid; it must floor-reproduce the realized integer output on
    // both axes and survive the contract's storage rounding. The
    // realized size is re-derived from each candidate so the record
    // stays exact; zero-dimension outputs are rejected, never clamped.
    let matched = false;
    for (const r of recordedResizeK(cropW, cropH, outW, outH)) {
      const w = Math.floor(cropW * r);
      const h = Math.floor(cropH * r);
      if (
        Number.isFinite(r) &&
        r > 0 &&
        w >= 1 &&
        h >= 1 &&
        w * h <= bounds.maxRasterPixels &&
        Math.max(w, h) <= bounds.maxRasterEdge
      ) {
        k = r;
        outW = w;
        outH = h;
        matched = true;
        break;
      }
    }
    requireOcr(
      matched,
      OCR_REASON.RESOURCE_LIMIT,
      `no recorded resize factor reproduces the bounded OCR input ` +
        `${outW}x${outH}`,
    );
    limitations.push(
      `downsampled: crop ${cropW}x${cropH}px exceeds caps; ` +
        `actual OCR scale ${round6(k)} (recorded in ocr_resize)`,
    );
    // The renderer draws the source crop to the fractional destination
    // cropW*k x cropH*k output px on the integer outW x outH canvas;
    // the right/bottom remainder is clipped. Presence is decided on the
    // actual computed difference (never storage rounding); each amount
    // is in [0,1) output px — in source/page units the clipped content
    // can be far larger under extreme downscale.
    resizeClip = [cropW * k - outW, cropH * k - outH];
    if (resizeClip[0] > 0 || resizeClip[1] > 0) {
      limitations.push(
        `ocr_resize_clipped: fractional destination ` +
          `${cropW * k}x${cropH * k} exceeds integer OCR input ` +
          `${outW}x${outH}; clipped right=${resizeClip[0]} ` +
          `bottom=${resizeClip[1]} output px`,
      );
    }
  }

  const ocrId = `ocr_${checkId}`;
  const transforms: Transform[] = [
    rasterTransformRecord(page, raster.scalePxPerPt, raster.rasterId),
    cropTranslationRecord(page, raster.rasterId, ocrId, x0, y0),
    ocrResizeRecord(page, ocrId, round6(k)),
  ];

  return {
    cropX: x0,
    cropY: y0,
    cropWidthPx: x1 - x0,
    cropHeightPx: y1 - y0,
    regionPx,
    paddingPx: pad,
    resizeK: round6(k),
    resizeClipPx: resizeClip,
    outWidthPx: outW,
    outHeightPx: outH,
    ocrId,
    transforms,
    limitations,
  };
}
