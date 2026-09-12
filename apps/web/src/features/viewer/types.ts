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
