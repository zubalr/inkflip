/**
 * Engine bindings for the public inspection session (pdf-3g8).
 *
 * Thin adapters from the feature's structural `ImportEngine` /
 * `ExportEngine` interfaces onto the production report packages — the
 * same bindings the preview mounts use. Untrusted bytes only ever cross
 * `openReport` (the T24 gate); exports only ever go through the T16
 * projection/serialization pipeline.
 */
import type { Reader, Report } from "../../../../../packages/contracts/src/index.ts";
import {
  IMPORT_JSON_LIMIT,
  openReport,
  prepareComparison,
  readerAvailability,
  replayView,
  reportViewModel,
  verifySourceCandidate,
} from "../../../../../packages/reports/import/index.ts";
import type {
  ImportedReport,
  ReaderAvailability,
} from "../../../../../packages/reports/import/index.ts";
import {
  buildExportPreview,
  exportFileName,
  projectReport,
  renderReportHtml,
  serializeReportJson,
} from "../../../../../packages/reports/export/index.ts";
import type { ExportEngine } from "../export/types";
import type { ImportEngine } from "../import/types";

/** Host-installed reader allowlist — every runnable identity. */
export function installedReaders(
  adapter: {
    readers: { text: Reader; render: Reader };
    ocrReader?: Reader | null;
  },
  ocrReaders: readonly Reader[] = [],
): Reader[] {
  const list: Reader[] = [adapter.readers.text, adapter.readers.render];
  if (adapter.ocrReader) list.push(adapter.ocrReader);
  // The Tesseract reader is lazily constructed but always installable
  // here (bundled engine, staged+hash-verified model assets) — declare
  // its deterministic identities so replay readiness is honest.
  for (const r of ocrReaders) {
    if (!list.some((x) => x.id === r.id)) list.push(r);
  }
  return list;
}

export function createImportEngine(): ImportEngine {
  return {
    maxJsonBytes: IMPORT_JSON_LIMIT,
    openReport: (data: Uint8Array) => openReport(data),
    readerAvailability: (report, list) =>
      readerAvailability(report as Report, list),
    reportView: (imported, availability) =>
      reportViewModel(
        imported as ImportedReport,
        availability as ReaderAvailability,
      ),
    replayView: (imported, availability, attached) =>
      replayView(
        imported as ImportedReport,
        availability as ReaderAvailability,
        attached,
      ),
    verifySource: (report, bytes) =>
      verifySourceCandidate(report as Report, bytes),
    prepareComparison: (left, right) =>
      prepareComparison(left as Report, right as Report),
  };
}

export function createExportEngine(): ExportEngine {
  return {
    project: (source, request) =>
      projectReport(source as Report, request as never) as never,
    preview: (report, options) =>
      buildExportPreview(report as Report, options as never) as never,
    serializeJson: (report) => serializeReportJson(report as Report),
    renderHtml: (report) => renderReportHtml(report as Report),
    fileName: (report, format) => exportFileName(report as Report, format),
  };
}
