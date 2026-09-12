/**
 * Shared types for the import feature (T22).
 *
 * The feature is deliberately structural about its collaborators —
 * mirrors `state/store.ts` (`StoreHost`) and `features/open/types.ts`:
 * the app tsconfig cannot resolve cross-package `.ts` specifiers, so
 * `ImportEngine`/`ImportHost` describe the `packages/reports/import` and
 * `RunCoordinator` surfaces, and the concrete wiring lives in
 * `mount.tsx`.
 */

/** Minimal File/Blob surface the import controller needs. */
export interface ReportCandidate {
  /** Local label only — never an identity, never leaves the browser. */
  readonly name: string;
  readonly size: number;
  /** Full bytes — requested only after the declared-size pre-check. */
  arrayBuffer(): Promise<ArrayBuffer>;
}

/** Failure classes surfaced to the user (mirrors ImportFailure). */
export type ImportFailureKind = "not_a_report" | "unsupported_version" | "too_large" | "invalid";

export interface ImportFailureLike {
  readonly kind: ImportFailureKind | string;
  readonly code: string;
  readonly detail: string;
  readonly version: string | null;
}

/** Where the original document bytes stand for replay. */
export interface SourceStateLike {
  readonly kind: "embedded" | "required" | "not_applicable" | string;
  readonly assetId?: string;
  readonly byteLength?: number;
}

/** Producer-declared export disclosure, shown verbatim. */
export interface ScopeLike {
  readonly mode: string;
  readonly scope: string;
  readonly replay: string;
  readonly included: readonly string[];
  readonly omissions: readonly string[];
}

export interface ReaderViewLike {
  readonly id: string;
  readonly name: string;
  readonly version: string;
  readonly method: string;
  readonly environment: string;
  readonly label: string;
  readonly installed: boolean;
}

export interface OccurrenceViewLike {
  readonly id: string;
  readonly readerId: string;
  readonly readerLabel: string;
  readonly pageIndex: number;
  readonly rawText: string;
  readonly normalizedText: string;
  readonly geometryPrecision: string;
  readonly limitations: readonly string[];
}

export interface FindingViewLike {
  readonly id: string;
  readonly kind: string;
  readonly title: string;
  readonly explanation: string;
  readonly pageIndex: number;
  readonly alignment: string;
  readonly priority: string;
  readonly basis: string;
  readonly limitations: readonly string[];
  readonly occurrences: readonly OccurrenceViewLike[];
}

export interface AnnotationViewLike {
  readonly id: string;
  readonly findingId: string | null;
  readonly pageIndex: number;
  readonly text: string;
  readonly authorLabel: string | null;
}

export interface AssetViewLike {
  readonly id: string;
  readonly purpose: string;
  readonly pageIndex: number | null;
  readonly mediaType: string;
  readonly byteLength: number;
  /** `data:image/png;base64,…` from the sanitized re-encode, or null. */
  readonly dataUrl: string | null;
  readonly width: number | null;
  readonly height: number | null;
}

export interface CoverageViewLike {
  readonly checks: number;
  readonly checksCompleted: number;
  readonly checksUnsupported: number;
  readonly checksFailed: number;
  readonly producedOccurrences: number;
  readonly retainedOccurrences: number;
  readonly pagesSelected: number;
  readonly pageCount: number;
}

export interface ReportViewLike {
  readonly reportId: string;
  readonly title: string;
  readonly filenameIncluded: boolean;
  readonly document: {
    readonly sha256: string;
    readonly byteLength: number;
    readonly pageCount: number;
    readonly displayName: string | null;
  };
  readonly scope: ScopeLike;
  readonly coverage: CoverageViewLike;
  readonly readers: readonly ReaderViewLike[];
  readonly findings: readonly FindingViewLike[];
  readonly annotations: readonly AnnotationViewLike[];
  readonly assets: readonly AssetViewLike[];
  readonly limitations: readonly string[];
}

export interface ReplayViewLike {
  readonly source: "embedded" | "attached" | "missing" | "not_applicable" | string;
  readonly readersMissing: readonly string[];
  readonly readersInstalled: readonly string[];
  readonly ready: boolean;
}

/** The gate-validated report plus derived state (opaque to the UI). */
export interface ImportedReportLike {
  readonly report: unknown;
  readonly source: SourceStateLike;
  readonly scope: ScopeLike;
}

export type ImportOutcomeLike =
  | { readonly ok: true; readonly imported: ImportedReportLike }
  | { readonly ok: false; readonly failure: ImportFailureLike };

export type ComparisonReadinessLike =
  | { readonly status: "ready"; readonly documentSha256: string }
  | { readonly status: "same_report" }
  | { readonly status: "incomparable"; readonly reason: string };

export type SourceCheckLike =
  | { readonly ok: true; readonly sha256: string; readonly byteLength: number }
  | { readonly ok: false; readonly kind: string; readonly detail: string };

/** Host-installed reader allowlist entry (never report-supplied). */
export interface InstalledReaderLike {
  readonly id: string;
  readonly name: string;
  readonly version: string;
}

export interface ReaderAvailabilityLike {
  readonly available: readonly { readonly id: string }[];
  readonly missing: readonly { readonly id: string }[];
}

/**
 * The import domain engine — satisfied member-for-member by
 * `packages/reports/import`. Every untrusted byte crosses `openReport`
 * (the T24 gate); nothing else in the feature parses report bytes.
 */
export interface ImportEngine {
  /** Declared-size pre-check bound, mirroring the gate's JSON limit. */
  readonly maxJsonBytes: number;
  openReport(data: Uint8Array): ImportOutcomeLike;
  readerAvailability(
    report: unknown,
    installed: readonly InstalledReaderLike[],
  ): ReaderAvailabilityLike;
  reportView(imported: ImportedReportLike, availability: ReaderAvailabilityLike): ReportViewLike;
  replayView(
    imported: ImportedReportLike,
    availability: ReaderAvailabilityLike,
    sourceAttached: boolean,
  ): ReplayViewLike;
  verifySource(report: unknown, bytes: Uint8Array): SourceCheckLike;
  prepareComparison(left: unknown, right: unknown): ComparisonReadinessLike;
}

/**
 * Lifecycle host — the file-state half of `RunCoordinator`
 * (validating_file → loading_metadata → selecting, plus
 * generation-first clear/replace). Structurally identical to
 * `OpenHost` in features/open — the import reopen uses the same
 * lifecycle so a stale generation can never mutate the open report.
 */
export interface ImportHost {
  readonly fileState: string;
  readonly currentGeneration: number;
  openFile(): void;
  fileValidated(): void;
  metadataLoaded(document: { sha256: string; page_count: number }): void;
  requestClear(next?: "idle" | "replace"): unknown;
  own(resource: unknown, label?: string, teardown?: () => unknown): void;
}
