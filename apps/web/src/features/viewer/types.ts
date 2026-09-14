import type {
  Finding,
  Occurrence,
  Reader,
  Page,
  Geometry,
} from "../../../../../packages/contracts/src/index.ts";

export type ViewerMode = "page" | "reading" | "compare";
export type RotationDegree = 0 | 90 | 180 | 270;

export interface OccurrenceHighlight {
  id: string;
  findingId: string;
  readerId: string;
  pageIndex: number;
  ordinal: number;
  totalOccurrences: number;
  text: string;
  geometry: Geometry;
  alignment: "unique" | "ambiguous" | "unmatched" | "page_level" | "not_applicable";
  isSelected: boolean;
}

export interface ViewerState {
  mode: ViewerMode;
  pageIndex: number;
  zoom: number; // 25 to 400
  rotation: RotationDegree;
  pan: { x: number; y: number };
  selectedFindingId: string | null;
  selectedOccurrenceId: string | null;
  shortcutsEnabled: boolean;
}

export interface ViewerDoc {
  pages: Page[];
  readers: Reader[];
  occurrences: Occurrence[];
  findings: Finding[];
}

/**
 * A real rendered page in display space (intrinsic page rotation already
 * applied by the reader adapter). The viewer never reconstructs a page
 * from extracted text — it either paints these pixels or says plainly
 * that no source is available.
 */
export interface PageRasterView {
  readonly widthPx: number;
  readonly heightPx: number;
  readonly scalePxPerPt: number;
  readonly imageData: Uint8ClampedArray;
  readonly limitations: readonly string[];
}

export type ViewerPaintStatus = "loading" | "ready" | "unavailable" | "error";

/**
 * Paint a report page through the session/PDF.js render boundary.
 * `scalePxPerPt` is the requested CSS-pixel density per display-space
 * point; the adapter may clamp it. Returns null when no usable source
 * or page image exists. `signal` cancels a stale request.
 */
export type RenderPageFn = (
  pageIndex: number,
  scalePxPerPt: number,
  signal: AbortSignal,
) => Promise<PageRasterView | null>;
