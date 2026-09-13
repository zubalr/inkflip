/**
 * Structural port types for the export feature (T16).
 *
 * The engine contract mirrors `@inkflip/reports/export` member-for-member,
 * but is declared structurally so this file stays free of cross-package
 * `.ts` import specifiers, which `apps/web/tsconfig.json` cannot yet
 * resolve — the same decoupling pattern as `state/store.ts`. The concrete
 * binding lands with app composition; every call the panel makes is on
 * this port.
 */

/** Inclusion request; mirrors ExportRequest in packages/reports/export. */
export interface ExportRequestLike {
  readonly scope?: "selection" | "run";
  readonly findings?: "all" | readonly string[];
  readonly occurrences?: "all" | "cited" | "none" | readonly string[];
  readonly crops?: "all" | "none" | readonly string[];
  readonly pageRenders?: "all" | "none" | readonly string[];
  readonly annotations?: boolean;
  readonly filename?: boolean;
  readonly sourcePdf?: Uint8Array | "carry" | null;
}

export interface ProjectionNoticesLike {
  readonly omittedOccurrenceCount: number;
  readonly omittedFindingIds: readonly string[];
  readonly deselectedFindingIds?: readonly string[];
  readonly missingAssetIds: readonly string[];
  readonly requiredContextAssetIds: readonly string[];
  readonly unlinkedOccurrenceIds: readonly string[];
  readonly requestedSourceMissing?: boolean;
  readonly omissions: readonly string[];
}

export interface ProjectionLike {
  readonly report: unknown;
  readonly notices: ProjectionNoticesLike;
}

export interface PreviewCountsLike {
  readonly findings: number;
  readonly occurrences: number;
  readonly producedOccurrences: number;
  readonly retainedOccurrences: number;
  readonly checks: number;
  readonly checksCompleted: number;
  readonly readers: number;
  readonly pagesKept: number;
  readonly pagesSelected: number;
  readonly pageCount: number;
  readonly regions: number;
  readonly transforms: number;
  readonly crops: number;
  readonly pageRenders: number;
  readonly annotations: number;
}

export interface ExportPreviewLike {
  readonly mode: string;
  readonly scope: string;
  readonly replay: string;
  readonly reportId: string;
  readonly documentSha256: string;
  readonly included: readonly string[];
  readonly omissions: readonly string[];
  readonly counts: PreviewCountsLike;
  readonly bytes: {
    readonly jsonBytes: number;
    readonly htmlBytes: number | null;
    readonly decodedAssetBytes: number;
    readonly encodedAssetChars: number;
  };
  readonly limits: {
    readonly jsonBytes: number;
    readonly decodedAssetBytes: number;
    readonly assetCount: number;
    readonly pngPixels: number;
  };
  readonly withinLimits: boolean;
  readonly sourcePdfIncluded: boolean;
  readonly filenameIncluded: boolean;
  readonly annotationsIncluded: boolean;
  readonly warnings: readonly string[];
}

/** The export engine port — satisfied by packages/reports/export/index.ts. */
export interface ExportEngine {
  project(source: unknown, request: ExportRequestLike): ProjectionLike;
  preview(
    report: unknown,
    options?: { html?: string | null; notices?: ProjectionNoticesLike },
  ): ExportPreviewLike;
  serializeJson(report: unknown): string;
  renderHtml(report: unknown): string;
  fileName(report: unknown, format: "json" | "html"): string;
}

/** Which optional categories the recorded run actually has to offer. */
export interface ExportAvailability {
  readonly hasSourcePdf: boolean;
  readonly hasFilename: boolean;
  readonly hasAnnotations: boolean;
  readonly hasPageRenders: boolean;
  readonly hasCrops: boolean;
}

/** One produced download payload. */
export interface ExportOutput {
  readonly name: string;
  readonly text: string;
}
