/**
 * Bounded region specification (T08) — explicit user-selected geometry in
 * canonical page space (unrotated effective view, physical points, top-left
 * origin). A region is never inferred from text (GLOSSARY: "selected or
 * aligned explicitly").
 *
 * Rules:
 * - Numeric input must land inside the page bounds and have positive area;
 *   out-of-bounds or degenerate input is REJECTED with a reason, never
 *   silently clamped (I11-shaped honesty).
 * - Pointer drags are clamped to the surface so they always produce
 *   in-bounds boxes.
 * - The contract Region geometry records `exact` user-supplied polygon
 *   plus the page's raw→canonical transform id — provenance, not a
 *   reader-derived location claim.
 * - OCR context padding follows READER_ADAPTER_CONTRACT: 8 raster pixels
 *   or 10% of region height (larger), clipped to the raster — computed
 *   here so the preview can outline it honestly; the original region and
 *   the padded crop stay distinct.
 */
import type { PageMeta } from "../open/types";

/** Canonical-space rectangle: [x0, y0, x1, y1] in physical points. */
export type RegionBox = readonly [number, number, number, number];

/** Contract-shaped Region record (schema $defs/Region). */
export interface ContractRegion {
  readonly id: string;
  readonly page_index: number;
  readonly geometry: {
    readonly precision: "exact" | "estimated" | "page_only" | "unknown";
    readonly space: "canonical_page";
    readonly polygon: readonly (readonly [number, number])[] | null;
    readonly transform_ids: readonly string[];
    readonly basis: string;
  };
  readonly label: string;
}

export type RegionVerdict =
  | { readonly ok: true; readonly box: RegionBox }
  | { readonly ok: false; readonly reason: string };

const round6 = (v: number): number => Math.round(v * 1e6) / 1e6;

/**
 * Validate a user-entered canonical box against the page. Bounds violations
 * are explicit errors — a mistyped region is never snapped into the page.
 */
export function validateRegionBox(
  box: readonly [number, number, number, number],
  page: Pick<PageMeta, "widthPt" | "heightPt">,
): RegionVerdict {
  const [x0, y0, x1, y1] = box;
  if (![x0, y0, x1, y1].every((v) => Number.isFinite(v))) {
    return { ok: false, reason: "bounds must be finite numbers" };
  }
  if (x1 <= x0 || y1 <= y0) {
    return { ok: false, reason: "region needs positive width and height" };
  }
  if (x0 < 0 || y0 < 0 || x1 > page.widthPt || y1 > page.heightPt) {
    return {
      ok: false,
      reason: `region must stay inside the page (0–${round6(page.widthPt)} × 0–${round6(page.heightPt)} pt)`,
    };
  }
  return { ok: true, box: [x0, y0, x1, y1] };
}

/** Normalize two dragged canonical points into a box (clamped by caller). */
export function draggedBox(
  ax: number,
  ay: number,
  bx: number,
  by: number,
): RegionBox {
  return [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)];
}

/**
 * Contract Region record for a validated box. `transform_ids` binds the
 * page's raw→canonical record; the basis states the geometry source
 * (user-specified), so the polygon is never mistaken for a reader finding.
 */
export function regionToContract(
  box: RegionBox,
  page: PageMeta,
  ordinal: number,
  label: string,
): ContractRegion {
  const x0 = round6(box[0]);
  const y0 = round6(box[1]);
  const x1 = round6(box[2]);
  const y1 = round6(box[3]);
  return {
    id: `region_p${page.index}_${ordinal}`,
    page_index: page.index,
    geometry: {
      precision: "exact",
      space: "canonical_page",
      polygon: [
        [x0, y0],
        [x1, y0],
        [x1, y1],
        [x0, y1],
      ],
      transform_ids: [page.canonicalTransformId],
      basis:
        "user-specified region bounds in canonical page space; not a reader-derived location",
    },
    label: label.slice(0, 200),
  };
}

/** Bounding box of a canonical rect after mapping to display space. */
export function canonicalBoxToDisplay(
  box: RegionBox,
  page: Pick<PageMeta, "widthPt" | "heightPt" | "rotation">,
): RegionBox {
  const [ax, ay] = canonicalToDisplay(box[0], box[1], page);
  const [bx, by] = canonicalToDisplay(box[2], box[3], page);
  return [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)];
}

/**
 * OCR padding per READER_ADAPTER_CONTRACT: `max(8 raster px, 10% of region
 * height)` on every side, clipped to the raster. The input is the region's
 * bounding box in DISPLAY space (pt) — the same orientation as the raster —
 * so the 10%-of-height rule applies to the visible region height under any
 * quarter-turn. Returns the padded crop in raster pixels plus the pad used.
 */
export function paddedRasterRegion(
  displayBoxPt: RegionBox,
  scalePxPerPt: number,
  rasterWidthPx: number,
  rasterHeightPx: number,
): { x0: number; y0: number; x1: number; y1: number; padPx: number } {
  const heightPx = (displayBoxPt[3] - displayBoxPt[1]) * scalePxPerPt;
  const padPx = Math.max(8, 0.1 * heightPx);
  const x0 = Math.max(0, Math.floor(displayBoxPt[0] * scalePxPerPt - padPx));
  const y0 = Math.max(0, Math.floor(displayBoxPt[1] * scalePxPerPt - padPx));
  const x1 = Math.min(
    rasterWidthPx,
    Math.ceil(displayBoxPt[2] * scalePxPerPt + padPx),
  );
  const y1 = Math.min(
    rasterHeightPx,
    Math.ceil(displayBoxPt[3] * scalePxPerPt + padPx),
  );
  return { x0, y0, x1, y1, padPx };
}

/**
 * Display-space (post-rotation) point -> canonical point. The raster the
 * user drags on is in display space; storage is canonical/unrotated, so
 * every dragged coordinate crosses exactly the document rotation — the
 * inverse of the displayRotation records in packages/geometry.
 */
export function displayToCanonical(
  xDisplayPt: number,
  yDisplayPt: number,
  page: Pick<PageMeta, "widthPt" | "heightPt" | "rotation">,
): readonly [number, number] {
  const { widthPt: w, heightPt: h, rotation } = page;
  switch (rotation) {
    case 90:
      // display = (h - y, x)  =>  canonical = (y', h - x')
      return [yDisplayPt, h - xDisplayPt];
    case 180:
      return [w - xDisplayPt, h - yDisplayPt];
    case 270:
      // display = (y, w - x)  =>  canonical = (w - y', x')
      return [w - yDisplayPt, xDisplayPt];
    default:
      return [xDisplayPt, yDisplayPt];
  }
}

/** Canonical point -> display space (for overlay outlines). */
export function canonicalToDisplay(
  xPt: number,
  yPt: number,
  page: Pick<PageMeta, "widthPt" | "heightPt" | "rotation">,
): readonly [number, number] {
  const { widthPt: w, heightPt: h, rotation } = page;
  switch (rotation) {
    case 90:
      return [h - yPt, xPt];
    case 180:
      return [w - xPt, h - yPt];
    case 270:
      return [yPt, w - xPt];
    default:
      return [xPt, yPt];
  }
}

/** Display-space size of a page after rotation (quarter turns swap W/H). */
export function displaySize(
  page: Pick<PageMeta, "widthPt" | "heightPt" | "rotation">,
): readonly [number, number] {
  return page.rotation === 90 || page.rotation === 270
    ? [page.heightPt, page.widthPt]
    : [page.widthPt, page.heightPt];
}
