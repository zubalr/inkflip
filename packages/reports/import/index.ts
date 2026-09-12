/**
 * @inkflip/reports/import — strict local report import domain layer.
 *
 * Every untrusted `.inkflip.json` input enters through `openReport`,
 * which delegates all parsing/bounds/schema/hash/asset verification to
 * the T24 gate (`../validation/import_gate.ts`) and never reimplements
 * them. The modules here only add what the reopen flow needs on top:
 * failure classification, explicit local source verification, reader
 * availability against a host allowlist, two-file comparison readiness,
 * and inert display view models. No module performs I/O, fetches,
 * executes, or interprets report strings as code, commands, paths, or
 * URLs.
 */

export { IMPORT_JSON_LIMIT, openReport } from "./open.ts";
export type { ImportedReport, ImportOutcome, ScopeDisclosure, SourceState } from "./open.ts";

export { classifyImportFailure } from "./errors.ts";
export type { ImportFailure, ImportFailureKind } from "./errors.ts";

export { verifySourceCandidate } from "./source.ts";
export type { SourceCheck } from "./source.ts";

export { readerAvailability, readerLabel } from "./readers.ts";
export type { InstalledReader, ReaderAvailability } from "./readers.ts";

export { prepareComparison } from "./compare.ts";
export type { ComparisonReadiness } from "./compare.ts";

export { replayView, reportViewModel } from "./view.ts";
export type {
  AnnotationView,
  AssetView,
  CoverageView,
  FindingView,
  OccurrenceView,
  ReaderView,
  ReplayView,
  ReportView,
} from "./view.ts";
