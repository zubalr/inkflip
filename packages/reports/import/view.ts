/**
 * `reportViewModel` — a plain-data projection of a validated report for
 * display. The UI renders these strings as inert text nodes (and `bdi`
 * for report-controlled text); nothing here is ever interpreted as
 * markup, a command, a path, or a URL.
 *
 * Asset payloads are exposed only as sanitized PNG data URLs built from
 * the gate's clean re-encode — never from stored imported bytes.
 * Non-PNG assets (e.g. the embedded source PDF) get no renderable
 * payload at all.
 */
import { encodeBase64 } from "../export/serialize.ts";
import type { ImportedReport, ScopeDisclosure } from "./open.ts";
import type { ReaderAvailability } from "./readers.ts";
import { readerLabel } from "./readers.ts";

export interface ReaderView {
  readonly id: string;
  readonly name: string;
  readonly version: string;
  readonly method: string;
  readonly environment: string;
  /** Display label — `${name} ${version}` inert text. */
  readonly label: string;
  /** True when a host-installed reader has this exact id. */
  readonly installed: boolean;
}

export interface OccurrenceView {
  readonly id: string;
  readonly readerId: string;
  readonly readerLabel: string;
  readonly pageIndex: number;
  readonly rawText: string;
  readonly normalizedText: string;
  readonly geometryPrecision: string;
  readonly limitations: readonly string[];
}

export interface FindingView {
  readonly id: string;
  readonly kind: string;
  readonly title: string;
  readonly explanation: string;
  readonly pageIndex: number;
  readonly alignment: string;
  readonly priority: string;
  readonly basis: string;
  readonly limitations: readonly string[];
  readonly occurrences: readonly OccurrenceView[];
}

export interface AnnotationView {
  readonly id: string;
  readonly findingId: string | null;
  readonly pageIndex: number;
  readonly text: string;
  readonly authorLabel: string | null;
}

export interface AssetView {
  readonly id: string;
  readonly purpose: string;
  readonly pageIndex: number | null;
  readonly mediaType: string;
  readonly byteLength: number;
  /** `data:image/png;base64,…` built from the sanitized re-encode, or null. */
  readonly dataUrl: string | null;
  readonly width: number | null;
  readonly height: number | null;
}

export interface CoverageView {
  readonly checks: number;
  readonly checksCompleted: number;
  readonly checksUnsupported: number;
  readonly checksFailed: number;
  readonly producedOccurrences: number;
  readonly retainedOccurrences: number;
  readonly pagesSelected: number;
  readonly pageCount: number;
}

export interface ReportView {
  readonly reportId: string;
  readonly title: string;
  readonly filenameIncluded: boolean;
  readonly document: {
    readonly sha256: string;
    readonly byteLength: number;
    readonly pageCount: number;
    readonly displayName: string | null;
  };
  readonly scope: ScopeDisclosure;
  readonly coverage: CoverageView;
  readonly readers: readonly ReaderView[];
  readonly findings: readonly FindingView[];
  readonly annotations: readonly AnnotationView[];
  readonly assets: readonly AssetView[];
  readonly limitations: readonly string[];
}

export function reportViewModel(
  imported: ImportedReport,
  availability: ReaderAvailability,
): ReportView {
  const { report, audit } = imported;
  const missingIds = new Set(availability.missing.map((r) => r.id));
  const readersById = new Map(report.readers.map((r) => [r.id, r]));
  const occurrencesById = new Map(report.occurrences.map((o) => [o.id, o]));

  const readers: ReaderView[] = report.readers.map((reader) => ({
    id: reader.id,
    name: reader.name,
    version: reader.version,
    method: reader.method,
    environment: reader.environment,
    label: readerLabel(reader),
    installed: !missingIds.has(reader.id),
  }));

  const occurrenceView = (occurrenceId: string): OccurrenceView | null => {
    const occurrence = occurrencesById.get(occurrenceId);
    if (occurrence === undefined) return null;
    const reader = readersById.get(occurrence.reader_id);
    return {
      id: occurrence.id,
      readerId: occurrence.reader_id,
      readerLabel: reader !== undefined ? readerLabel(reader) : occurrence.reader_id,
      pageIndex: occurrence.page_index,
      rawText: occurrence.raw_text,
      normalizedText: occurrence.normalized_text,
      geometryPrecision: occurrence.geometry.precision,
      limitations: [...occurrence.limitations],
    };
  };

  const findings: FindingView[] = report.findings.map((finding) => ({
    id: finding.id,
    kind: finding.kind,
    title: finding.title,
    explanation: finding.explanation,
    pageIndex: finding.page_index,
    alignment: finding.alignment,
    priority: finding.priority,
    basis: finding.basis,
    limitations: [...finding.limitations],
    occurrences: finding.occurrence_ids
      .map(occurrenceView)
      .filter((o): o is OccurrenceView => o !== null),
  }));

  const annotations: AnnotationView[] = report.annotations.map((a) => ({
    id: a.id,
    findingId: a.finding_id,
    pageIndex: a.page_index,
    text: a.text,
    authorLabel: a.author_label,
  }));

  const assets: AssetView[] = report.assets.map((asset) => {
    const clean = audit.sanitizedPngs.get(asset.id);
    const isPng = asset.media_type === "image/png" && clean !== undefined;
    return {
      id: asset.id,
      purpose: asset.purpose,
      pageIndex: asset.page_index,
      mediaType: asset.media_type,
      byteLength: asset.byte_length,
      dataUrl: isPng ? `data:image/png;base64,${encodeBase64(clean.png)}` : null,
      width: isPng ? clean.width : null,
      height: isPng ? clean.height : null,
    };
  });

  const checks = report.checks;
  const coverage: CoverageView = {
    checks: checks.length,
    checksCompleted: checks.filter((c) => c.status === "completed").length,
    checksUnsupported: checks.filter((c) => c.status === "unsupported").length,
    checksFailed: checks.filter((c) => c.status === "failed" || c.status === "skipped").length,
    producedOccurrences: checks.reduce((sum, c) => sum + c.produced_occurrence_count, 0),
    retainedOccurrences: checks.reduce((sum, c) => sum + c.retained_occurrence_ids.length, 0),
    pagesSelected: report.plan.selected_pages.length,
    pageCount: report.document.page_count,
  };

  return {
    reportId: report.report_id,
    title: report.document.display_name ?? "Imported report",
    filenameIncluded: report.document.display_name !== null,
    document: {
      sha256: report.document.sha256,
      byteLength: report.document.byte_length,
      pageCount: report.document.page_count,
      displayName: report.document.display_name,
    },
    scope: imported.scope,
    coverage,
    readers,
    findings,
    annotations,
    assets,
    limitations: [...report.limitations],
  };
}

/** Replay readiness: source standing plus reader environment. */
export interface ReplayView {
  /** 'embedded' | 'attached' | 'missing' | 'not_applicable'. */
  readonly source: "embedded" | "attached" | "missing" | "not_applicable";
  /** Display labels of recorded readers with no installed match. */
  readonly readersMissing: readonly string[];
  /** Display labels of recorded readers that are installed. */
  readonly readersInstalled: readonly string[];
  /**
   * True only when the original bytes are present (embedded or
   * explicitly attached) *and* every recorded reader is installed.
   * `ready` still means "replay may proceed", not that a run happened.
   */
  readonly ready: boolean;
}

export function replayView(
  imported: ImportedReport,
  availability: ReaderAvailability,
  sourceAttached: boolean,
): ReplayView {
  const source = imported.source;
  const sourceState =
    source.kind === "embedded"
      ? "embedded"
      : source.kind === "required"
        ? sourceAttached
          ? "attached"
          : "missing"
        : "not_applicable";
  const readersMissing = availability.missing.map(readerLabel);
  const readersInstalled = availability.available.map(readerLabel);
  return {
    source: sourceState,
    readersMissing,
    readersInstalled,
    ready:
      (sourceState === "embedded" || sourceState === "attached") && readersMissing.length === 0,
  };
}
