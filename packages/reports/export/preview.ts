/**
 * Pre-export preview — computed from the final projected report object,
 * never from UI checkbox state (REPORT_EXPORT_IMPORT.md). Every count and
 * byte figure is measured on the actual export payload, so the preview a
 * user approves is exactly what the decoded file will contain.
 */
import type { Report } from "../../contracts/src/index.ts";
import { IMPORT_LIMITS } from "../validation/limits.ts";
import { decodeBase64, hasPngSignature } from "../validation/assets.ts";
import { serializeReportJson, reportJsonBytes } from "./serialize.ts";
import type { ProjectionNotices } from "./selection.ts";

export interface PreviewAsset {
  readonly id: string;
  readonly purpose: string;
  readonly decodedBytes: number;
  readonly encodedChars: number;
}

export interface PreviewCounts {
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

export interface PreviewBytes {
  /** Exact UTF-8 length of the canonical `.inkflip.json` payload. */
  readonly jsonBytes: number;
  /** Exact UTF-8 length of the rendered `.html` when computed. */
  readonly htmlBytes: number | null;
  /** Sum of decoded asset bytes embedded in the JSON payload. */
  readonly decodedAssetBytes: number;
  /** Sum of base64 payload characters carried in the JSON payload. */
  readonly encodedAssetChars: number;
  readonly assets: readonly PreviewAsset[];
}

export interface ExportPreview {
  readonly mode: Report["export"]["mode"];
  readonly scope: Report["export"]["scope"];
  readonly replay: Report["export"]["replay"];
  readonly reportId: string;
  readonly documentSha256: string;
  /** Disclosure categories exactly as recorded in `export.included`. */
  readonly included: readonly string[];
  /** Human-readable exclusion lines exactly as recorded in `export.omissions`. */
  readonly omissions: readonly string[];
  readonly counts: PreviewCounts;
  readonly bytes: PreviewBytes;
  /** Import-profile budgets the portable projection must stay inside. */
  readonly limits: {
    readonly jsonBytes: number;
    readonly decodedAssetBytes: number;
    readonly assetCount: number;
    readonly pngPixels: number;
  };
  /** False when the payload exceeds a bundle limit — explain, never silently reduce. */
  readonly withinLimits: boolean;
  readonly sourcePdfIncluded: boolean;
  readonly filenameIncluded: boolean;
  readonly annotationsIncluded: boolean;
  /** Ordered disclosure/warning lines for the preview surface. */
  readonly warnings: readonly string[];
}

// Copy lines below mirror planning/product/copy.json export.* keys so the
// preview text is the product copy, not paraphrase.
const COPY = {
  sourceWarning:
    "This includes every page and any hidden content in the original file. A crop is not a safe redaction.",
  cropWarning:
    "Review the actual crop for nearby private information. Cropping is not a redaction guarantee.",
  pageRenderWarning:
    "These images show complete pages, not only the selected crop. Review them before sharing.",
  replayAbsent:
    "Original PDF not included. This report can be inspected, but replay requires the matching original.",
  replayPresent: "Original PDF included. Replay also requires the recorded reader environment.",
  noAssets: "Screenshot-only diagnostic · not replayable",
} as const;

/**
 * Measure the projected report and build the preview. `html` may carry the
 * already-rendered document so its byte count is exact; when omitted the
 * HTML size is reported as null rather than estimated.
 */
export function buildExportPreview(
  report: Report,
  options: { html?: string | null; notices?: ProjectionNotices } = {},
): ExportPreview {
  const jsonBytes = reportJsonBytes(report).length;
  const assets: PreviewAsset[] = [];
  let decodedTotal = 0;
  let encodedTotal = 0;
  let crops = 0;
  let pageRenders = 0;
  let assetBytesExceeded = false;
  let pngPixelsExceeded = false;
  let pngEdgeExceeded = false;
  const assetLimitWarnings: string[] = [];

  for (const a of report.assets) {
    // Byte accounting decodes the actual payload the file carries — the
    // preview reflects the decoded contents, not declared metadata.
    const decodedBytes = decodeBase64(a.data_base64);
    const decoded = decodedBytes.length;
    decodedTotal += decoded;
    encodedTotal += a.data_base64.length;
    if (a.purpose === "crop") crops++;
    if (a.purpose === "page_render") pageRenders++;
    if (decoded > IMPORT_LIMITS.maxAssetBytes) {
      assetBytesExceeded = true;
      assetLimitWarnings.push(
        `Asset ${a.id} exceeds per-asset byte limit (${decoded} bytes vs cap ${IMPORT_LIMITS.maxAssetBytes} bytes).`,
      );
    }
    if (a.media_type === "image/png") {
      let width = a.pixel_size ? a.pixel_size[0] : 0;
      let height = a.pixel_size ? a.pixel_size[1] : 0;
      let pixels = width * height;
      if (decodedBytes.length >= 24 && hasPngSignature(decodedBytes)) {
        const dv = new DataView(
          decodedBytes.buffer,
          decodedBytes.byteOffset,
          decodedBytes.byteLength,
        );
        const payloadW = dv.getUint32(16);
        const payloadH = dv.getUint32(20);
        width = Math.max(width, payloadW);
        height = Math.max(height, payloadH);
        pixels = Math.max(pixels, payloadW * payloadH);
      }
      if (pixels > IMPORT_LIMITS.maxPngPixels) {
        pngPixelsExceeded = true;
        assetLimitWarnings.push(
          `Asset ${a.id} exceeds PNG pixel limit (${pixels} pixels vs cap ${IMPORT_LIMITS.maxPngPixels} pixels).`,
        );
      }
      if (width > IMPORT_LIMITS.maxPngEdge || height > IMPORT_LIMITS.maxPngEdge) {
        pngEdgeExceeded = true;
        assetLimitWarnings.push(
          `Asset ${a.id} exceeds PNG dimension edge limit (${Math.max(width, height)} px vs cap ${IMPORT_LIMITS.maxPngEdge} px).`,
        );
      }
    }
    assets.push({
      id: a.id,
      purpose: a.purpose,
      decodedBytes: decoded,
      encodedChars: a.data_base64.length,
    });
  }
  const produced = report.checks.reduce((n, c) => n + c.produced_occurrence_count, 0);
  const retained = report.checks.reduce((n, c) => n + c.retained_occurrence_ids.length, 0);
  const exp = report.export;
  const warnings: string[] = [];
  if (exp.mode === "replayable") {
    warnings.push(COPY.sourceWarning, COPY.replayPresent);
  } else if (exp.mode === "diagnostic") {
    warnings.push(COPY.noAssets, COPY.replayAbsent);
  } else {
    warnings.push(COPY.replayAbsent);
  }
  if (crops > 0) warnings.push(COPY.cropWarning);
  if (pageRenders > 0) warnings.push(COPY.pageRenderWarning);
  const notices = options.notices;
  if (notices !== undefined) {
    if (notices.requiredContextAssetIds.length > 0) {
      warnings.push(
        `${notices.requiredContextAssetIds.length} image(s) retained because retained readings were produced from them.`,
      );
    }
    if (notices.missingAssetIds.length > 0) {
      warnings.push(
        `${notices.missingAssetIds.length} asset(s) had no usable bytes and were omitted — this export is evidence-only.`,
      );
    }
    if (notices.requestedSourceMissing) {
      warnings.push(
        "The requested original PDF bytes are unavailable — this export is evidence-only.",
      );
    }
    if (notices.unlinkedOccurrenceIds.length > 0) {
      warnings.push(
        `${notices.unlinkedOccurrenceIds.length} reading(s) reference a missing raster and keep no image link.`,
      );
    }
  }
  warnings.push(...assetLimitWarnings);
  if (jsonBytes > IMPORT_LIMITS.maxJsonBytes) {
    warnings.push(
      `JSON payload exceeds limit (${jsonBytes} bytes vs cap ${IMPORT_LIMITS.maxJsonBytes} bytes).`,
    );
  }
  if (report.assets.length > IMPORT_LIMITS.maxAssets) {
    warnings.push(
      `Asset count exceeds limit (${report.assets.length} assets vs cap ${IMPORT_LIMITS.maxAssets}).`,
    );
  }
  if (decodedTotal > IMPORT_LIMITS.maxAssetTotalBytes) {
    warnings.push(
      `Total decoded asset size exceeds limit (${decodedTotal} bytes vs cap ${IMPORT_LIMITS.maxAssetTotalBytes} bytes).`,
    );
  }
  const withinLimits =
    jsonBytes <= IMPORT_LIMITS.maxJsonBytes &&
    report.assets.length <= IMPORT_LIMITS.maxAssets &&
    decodedTotal <= IMPORT_LIMITS.maxAssetTotalBytes &&
    !assetBytesExceeded &&
    !pngPixelsExceeded &&
    !pngEdgeExceeded;
  return {
    mode: exp.mode,
    scope: exp.scope,
    replay: exp.replay,
    reportId: report.report_id,
    documentSha256: report.document.sha256,
    included: [...exp.included],
    omissions: [...exp.omissions],
    counts: {
      findings: report.findings.length,
      occurrences: report.occurrences.length,
      producedOccurrences: produced,
      retainedOccurrences: retained,
      checks: report.checks.length,
      checksCompleted: report.checks.filter((c) => c.status === "completed").length,
      readers: report.readers.length,
      pagesKept: report.pages.length,
      pagesSelected: report.plan.selected_pages.length,
      pageCount: report.document.page_count,
      regions: report.plan.regions.length,
      transforms: report.transforms.length,
      crops,
      pageRenders,
      annotations: report.annotations.length,
    },
    bytes: {
      jsonBytes,
      htmlBytes:
        options.html === undefined || options.html === null
          ? null
          : new TextEncoder().encode(options.html).length,
      decodedAssetBytes: decodedTotal,
      encodedAssetChars: encodedTotal,
      assets,
    },
    limits: {
      jsonBytes: IMPORT_LIMITS.maxJsonBytes,
      decodedAssetBytes: IMPORT_LIMITS.maxAssetTotalBytes,
      assetCount: IMPORT_LIMITS.maxAssets,
      pngPixels: IMPORT_LIMITS.maxPngPixels,
    },
    withinLimits,
    sourcePdfIncluded: report.document.source_asset_id !== null,
    filenameIncluded: report.document.display_name !== null,
    annotationsIncluded: report.annotations.length > 0,
    warnings,
  };
}

/** Convenience: canonical JSON text for the exact previewed payload. */
export { serializeReportJson };
