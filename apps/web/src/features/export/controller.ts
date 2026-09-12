/**
 * Export flow controller (T16).
 *
 * Holds the inclusion options the user asked for, re-runs the projection
 * through the injected engine whenever they change, and derives the
 * preview from the *projected* report — the preview can never describe a
 * different payload than the downloads (I09; the preview is generated
 * from the final projected object, not checkbox state).
 *
 * Privacy defaults are enforced here: source PDF, filename and notes are
 * off until the user turns them on. When source opt-in is requested the
 * actual original bytes are pulled from the injected provider; absent or
 * mismatched bytes keep the export evidence-only — the controller never
 * fabricates a replayable bundle.
 */
import type {
  ExportAvailability,
  ExportEngine,
  ExportOutput,
  ExportPreviewLike,
  ExportRequestLike,
  ProjectionLike,
  ProjectionNoticesLike,
} from "./types";

export interface ExportControllerOptions {
  /** Returns the original PDF bytes on explicit opt-in, or null. */
  readonly sourcePdfBytes?: () => Uint8Array | null;
  /** Initial request overrides (defaults are the privacy profile). */
  readonly request?: ExportRequestLike;
}

export interface ExportControllerState {
  readonly request: ExportRequestLike;
  readonly availability: ExportAvailability;
  readonly preview: ExportPreviewLike | null;
  readonly notices: ProjectionNoticesLike | null;
  /** Last projection error code/message, or null when healthy. */
  readonly error: string | null;
  /** True when the user asked for source PDF but no usable bytes exist. */
  readonly sourceUnavailable: boolean;
}

const DEFAULT_REQUEST: ExportRequestLike = {
  scope: "selection",
  findings: "all",
  occurrences: "cited",
  crops: "all",
  pageRenders: "none",
  annotations: false,
  filename: false,
  sourcePdf: null,
};

export class ExportController {
  private readonly engine: ExportEngine;
  private readonly source: unknown;
  private readonly sourcePdfBytes: (() => Uint8Array | null) | undefined;
  private request: ExportRequestLike;
  private projection: ProjectionLike | null = null;
  private error: string | null = null;
  private sourceUnavailable = false;
  private readonly availability: ExportAvailability;

  constructor(engine: ExportEngine, source: unknown, options: ExportControllerOptions = {}) {
    this.engine = engine;
    this.source = source;
    this.sourcePdfBytes = options.sourcePdfBytes;
    this.request = { ...DEFAULT_REQUEST, ...options.request };
    this.availability = probeAvailability(source);
    this.recompute();
  }

  get state(): ExportControllerState {
    return {
      request: this.request,
      availability: this.availability,
      preview:
        this.projection === null
          ? null
          : this.engine.preview(this.projection.report, {
              notices: this.projection.notices,
            }),
      notices: this.projection?.notices ?? null,
      error: this.error,
      sourceUnavailable: this.sourceUnavailable,
    };
  }

  /** Merge inclusion options and recompute projection + preview. */
  setOption(patch: Partial<ExportRequestLike>): ExportControllerState {
    this.request = { ...this.request, ...patch };
    this.recompute();
    return this.state;
  }

  /** User intent for the source-PDF opt-in; bytes are pulled lazily. */
  setSourcePdfWanted(wanted: boolean): ExportControllerState {
    this.request = { ...this.request, sourcePdf: wanted ? "carry" : null };
    this.recompute();
    return this.state;
  }

  /** Canonical JSON download payload for the current projection. */
  jsonOutput(): ExportOutput {
    const report = this.requireReport();
    return {
      name: this.engine.fileName(report, "json"),
      text: this.engine.serializeJson(report),
    };
  }

  /** Script-free HTML download payload for the current projection. */
  htmlOutput(): ExportOutput {
    const report = this.requireReport();
    return {
      name: this.engine.fileName(report, "html"),
      text: this.engine.renderHtml(report),
    };
  }

  private requireReport(): unknown {
    if (this.projection === null) {
      throw new Error(this.error ?? "No export projection available");
    }
    return this.projection.report;
  }

  private recompute(): void {
    this.sourceUnavailable = false;
    const request = { ...this.request };
    if (request.sourcePdf === "carry") {
      // 'carry' only valid for re-exports of already-embedded sources;
      // fresh exports pull actual bytes from the provider.
      const bytes = this.sourcePdfBytes?.() ?? null;
      if (bytes === null) {
        if (this.availability.hasSourcePdf) {
          request.sourcePdf = "carry";
        } else {
          // Missing bytes stay missing: evidence-only, never replayable.
          request.sourcePdf = null;
          this.sourceUnavailable = true;
        }
      } else {
        request.sourcePdf = bytes;
      }
    }
    try {
      this.projection = this.engine.project(this.source, request);
      this.error = null;
    } catch (exc) {
      this.projection = null;
      this.error = exc instanceof Error ? exc.message : String(exc);
    }
  }
}

/** Inspect the recorded run for optional categories the UI can offer. */
export function probeAvailability(source: unknown): ExportAvailability {
  const report = source as {
    assets?: { purpose?: string }[];
    document?: { source_asset_id?: string | null; display_name?: string | null };
    annotations?: unknown[];
  } | null;
  const assets = Array.isArray(report?.assets) ? report.assets : [];
  return {
    hasSourcePdf:
      report?.document?.source_asset_id !== null && report?.document?.source_asset_id !== undefined,
    hasFilename:
      report?.document?.display_name !== null && report?.document?.display_name !== undefined,
    hasAnnotations: Array.isArray(report?.annotations) && report.annotations.length > 0,
    hasPageRenders: assets.some((a) => a?.purpose === "page_render"),
    hasCrops: assets.some((a) => a?.purpose === "crop"),
  };
}
