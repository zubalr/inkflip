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
  /** Findings present on the source report, for the selection picker. */
  readonly findingChoices: readonly FindingChoice[];
  /** Thumbnails of the crops the current projection will carry (T23). */
  readonly cropPreviews: readonly CropPreview[];
  /**
   * Notes excluded because their finding was deselected (engine prunes
   * annotations to kept findings — contract-required). Disclosed
   * separately so a note never disappears silently (review F2).
   */
  readonly notesExcludedWithFindings: number;
}

export interface FindingChoice {
  readonly id: string;
  /** 1-based document-order number — the stable "Finding N" the report
   *  and the compare table use. */
  readonly number: number;
  readonly title: string;
  readonly pageIndex: number;
  /** First named reading's raw text, truncated — distinguishes findings
   *  whose titles read identically. */
  readonly snippet: string | null;
}

export interface CropPreview {
  readonly id: string;
  readonly pageIndex: number;
  readonly dataUrl: string;
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
  private readonly findingChoices: readonly FindingChoice[];
  /** Sealed report identity — lets the panel preserve user choices across
   *  same-report source rebuilds (e.g. notes edited) while a genuinely
   *  different report still resets to privacy defaults. */
  readonly sourceReportId: string | null;

  constructor(engine: ExportEngine, source: unknown, options: ExportControllerOptions = {}) {
    this.engine = engine;
    this.source = source;
    this.sourcePdfBytes = options.sourcePdfBytes;
    this.request = { ...DEFAULT_REQUEST, ...options.request };
    this.availability = probeAvailability(source);
    this.findingChoices = probeFindingChoices(source);
    this.sourceReportId = probeReportId(source);
    this.recompute();
  }

  /**
   * Re-apply a previous request against this controller's source,
   * sanitized to what the source actually offers. Used when the panel's
   * source identity changed but the sealed report did not (notes edited,
   * parent re-render) — without this the projection silently reverted to
   * "all findings" and could ship evidence the user had deselected.
   */
  restoreRequest(prev: ExportRequestLike): ExportControllerState {
    const next: Partial<ExportRequestLike> = { ...prev };
    if (Array.isArray(next.findings)) {
      const known = new Set(this.findingChoices.map((f) => f.id));
      const ids = next.findings.filter((id) => known.has(id));
      next.findings = ids.length === this.findingChoices.length ? "all" : ids;
    }
    if (next.annotations === true && !this.availability.hasAnnotations) {
      next.annotations = false;
    }
    if (next.filename === true && !this.availability.hasFilename) {
      next.filename = false;
    }
    if (next.pageRenders === "all" && !this.availability.hasPageRenders) {
      next.pageRenders = "none";
    }
    this.request = { ...this.request, ...next };
    this.recompute();
    return this.state;
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
      findingChoices: this.findingChoices,
      cropPreviews: this.cropPreviews(),
      notesExcludedWithFindings: this.notesExcludedWithFindings(),
    };
  }

  /**
   * Restrict the export to an explicit finding subset (T23 multi-finding
   * selection). `"all"` restores the default full-evidence projection; an
   * empty array exports zero findings — the projection still discloses the
   * omitted evidence honestly rather than pretending nothing existed.
   */
  setFindingSelection(ids: "all" | readonly string[]): ExportControllerState {
    this.request = { ...this.request, findings: ids === "all" ? "all" : [...ids] };
    this.recompute();
    return this.state;
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
      // 'carry' reuses already-embedded sources when present;
      // fresh exports pull actual bytes from the provider.
      const bytes = this.sourcePdfBytes?.() ?? null;
      if (bytes !== null) {
        request.sourcePdf = bytes;
      } else {
        // Keep 'carry' so engine.project records requestedSourceMissing if embedded bytes are absent,
        // preserving the distinction between 'not requested' and 'requested but unavailable'.
        request.sourcePdf = "carry";
        if (!this.availability.hasSourcePdf) {
          this.sourceUnavailable = true;
        }
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

  /**
   * Crop thumbnails for the preview pane, decoded from the *projected*
   * report — what the user sees is exactly what the download contains.
   */
  private cropPreviews(): readonly CropPreview[] {
    if (this.projection === null) return [];
    const assets = (this.projection.report as { assets?: readonly {
      id?: string; purpose?: string; media_type?: string; data_base64?: string; page_index?: number;
    }[] }).assets ?? [];
    const out: CropPreview[] = [];
    for (const a of assets) {
      if (a?.purpose !== "crop" || typeof a.data_base64 !== "string") continue;
      out.push({
        id: String(a.id),
        pageIndex: typeof a.page_index === "number" ? a.page_index : -1,
        dataUrl: `data:${a.media_type ?? "image/png"};base64,${a.data_base64}`,
      });
    }
    return out;
  }

  /**
   * Source annotations dropped because the finding they annotate was
   * deselected. Only counted when notes inclusion is on — when notes are
   * off the wholesale "Notes excluded." line already discloses them.
   */
  private notesExcludedWithFindings(): number {
    if (this.projection === null || this.request.annotations !== true) return 0;
    const kept = new Set(
      ((this.projection.report as { findings?: readonly { id?: string }[] }).findings ?? [])
        .map((f) => f.id),
    );
    const sourceAnnotations =
      (this.source as { annotations?: readonly { finding_id?: string | null }[] }).annotations ?? [];
    return sourceAnnotations.filter(
      (a) => typeof a?.finding_id === "string" && !kept.has(a.finding_id),
    ).length;
  }
}

/** Sealed report identity of the source, or null for non-report inputs. */
export function probeReportId(source: unknown): string | null {
  const id = (source as { report_id?: unknown } | null)?.report_id;
  return typeof id === "string" ? id : null;
}

/** Findings on the source report, in document order. */
export function probeFindingChoices(source: unknown): readonly FindingChoice[] {
  const report = source as {
    findings?: readonly {
      id?: string;
      title?: string;
      page_index?: number;
      occurrence_ids?: readonly string[];
    }[];
    occurrences?: readonly { id?: string; raw_text?: string }[];
  } | null;
  const findings = report?.findings;
  if (!Array.isArray(findings)) return [];
  const textById = new Map<string, string>();
  for (const occ of report?.occurrences ?? []) {
    if (typeof occ?.id === "string" && typeof occ.raw_text === "string") {
      textById.set(occ.id, occ.raw_text);
    }
  }
  const out: FindingChoice[] = [];
  for (const f of findings) {
    if (typeof f?.id !== "string") continue;
    let snippet: string | null = null;
    for (const occId of f.occurrence_ids ?? []) {
      const text = textById.get(occId);
      if (text !== undefined) {
        snippet = text.length > 48 ? `${text.slice(0, 48)}…` : text;
        break;
      }
    }
    out.push({
      id: f.id,
      number: out.length + 1,
      title: typeof f.title === "string" ? f.title : f.id,
      pageIndex: typeof f.page_index === "number" ? f.page_index : -1,
      snippet,
    });
  }
  return out;
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
