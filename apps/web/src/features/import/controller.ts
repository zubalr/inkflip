/**
 * ImportController (T22) — orchestrates one offered `.inkflip.json`
 * through the file lifecycle: candidate → validating_file →
 * loading_metadata → selecting. The reopened report *is* the
 * workspace document — its recorded document identity (sha256,
 * page_count) becomes the workspace document identity.
 *
 * Ordering guarantees that carry the invariants:
 *
 * - I07 generation-first replacement: a new report offer while a
 *   report/document/run is live calls `host.requestClear("replace")`,
 *   which increments the generation BEFORE any owned resource is
 *   released — the imported report and any attached source bytes are
 *   released under the new generation, and every stale event is
 *   rejected by construction.
 * - I09/I10 the candidate is checked by declared size before any byte
 *   is read; all parsing/bounds/schema/hash/asset verification happens
 *   inside the engine's `openReport` (the T24 gate). Nothing fetches,
 *   executes, selects a reader, or mounts markup.
 * - Source association is explicit: a locally chosen PDF binds only
 *   when its bytes verify against the recorded document identity.
 * - Comparison needs two explicitly, locally selected report files —
 *   ids or URLs are never input; compare selection never clears the
 *   open workspace (it is a read-only gate plus verdict).
 *
 * The controller never touches the DOM, never fetches and never mutates
 * the candidate. Its collaborators are the structural `ImportHost`
 * (RunCoordinator) and `ImportEngine` (packages/reports/import) injected
 * by the composition.
 */
import type {
  ComparisonReadinessLike,
  ImportEngine,
  ImportFailureLike,
  ImportHost,
  ImportOutcomeLike,
  ImportedReportLike,
  InstalledReaderLike,
  ReaderAvailabilityLike,
  ReplayViewLike,
  ReportCandidate,
  ReportViewLike,
  SourceCheckLike,
} from "./types";

/** Diagnostic event stream — lets tests observe ordering without mocks. */
export type ImportEvent =
  | { readonly type: "clear"; readonly generation: number; readonly next: "idle" | "replace" }
  | { readonly type: "teardown"; readonly generation: number; readonly label: string }
  | { readonly type: "rejected"; readonly generation: number; readonly failure: ImportFailureLike }
  | {
      readonly type: "imported";
      readonly generation: number;
      readonly view: ReportViewLike;
      readonly replay: ReplayViewLike;
    }
  | {
      readonly type: "source_attached";
      readonly generation: number;
      readonly sha256: string;
      readonly replay: ReplayViewLike;
    }
  | { readonly type: "source_rejected"; readonly generation: number; readonly detail: string }
  | {
      readonly type: "compare_side";
      readonly generation: number;
      readonly side: "left" | "right";
      readonly ok: boolean;
      readonly failure: ImportFailureLike | null;
    }
  | {
      readonly type: "compare_ready";
      readonly generation: number;
      readonly readiness: ComparisonReadinessLike;
      readonly leftId: string;
      readonly rightId: string;
    };

export interface ImportControllerOptions {
  readonly host: ImportHost;
  readonly engine: ImportEngine;
  /** Host-installed reader allowlist — never report-supplied. */
  readonly installedReaders: () => readonly InstalledReaderLike[];
  readonly onEvent?: (event: ImportEvent) => void;
}

/** The live reopened report plus its display projections. */
export interface OpenedImport {
  readonly imported: ImportedReportLike;
  readonly view: ReportViewLike;
  readonly replay: ReplayViewLike;
}

export interface CompareSide {
  readonly imported: ImportedReportLike;
  readonly view: ReportViewLike;
}

export interface CompareState {
  readonly left: CompareSide | null;
  readonly right: CompareSide | null;
  readonly leftFailure: ImportFailureLike | null;
  readonly rightFailure: ImportFailureLike | null;
  readonly readiness: ComparisonReadinessLike | null;
}

const BUSY_FAILURE: ImportFailureLike = {
  kind: "invalid",
  code: "BUSY",
  detail: "import:busy",
  version: null,
};

function tooLargeFailure(detail: string): ImportFailureLike {
  return { kind: "too_large", code: "SIZE", detail, version: null };
}

function invalidFailure(code: string, detail: string): ImportFailureLike {
  return { kind: "invalid", code, detail, version: null };
}

export class ImportController {
  private readonly host: ImportHost;
  private readonly engine: ImportEngine;
  private readonly installedReaders: () => readonly InstalledReaderLike[];
  private readonly listeners = new Set<(event: ImportEvent) => void>();

  private busy = false;
  private current: OpenedImport | null = null;
  private sourceAttached = false;
  private compareLeft: CompareSide | null = null;
  private compareRight: CompareSide | null = null;
  private compareLeftFailure: ImportFailureLike | null = null;
  private compareRightFailure: ImportFailureLike | null = null;
  private compareReadiness: ComparisonReadinessLike | null = null;

  constructor(options: ImportControllerOptions) {
    this.host = options.host;
    this.engine = options.engine;
    this.installedReaders = options.installedReaders;
    if (options.onEvent) this.listeners.add(options.onEvent);
  }

  private emit(event: ImportEvent): void {
    // Set iteration tolerates a listener unsubscribing itself mid-emit.
    for (const listener of this.listeners) listener(event);
  }

  subscribe(listener: (event: ImportEvent) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  get currentImport(): OpenedImport | null {
    return this.current;
  }

  get compareState(): CompareState {
    return {
      left: this.compareLeft,
      right: this.compareRight,
      leftFailure: this.compareLeftFailure,
      rightFailure: this.compareRightFailure,
      readiness: this.compareReadiness,
    };
  }

  private availability(report: unknown): ReaderAvailabilityLike {
    return this.engine.readerAvailability(report, this.installedReaders());
  }

  /**
   * Offer one report candidate. When a report/document/run is live the
   * generation increments first (`requestClear("replace")`) and owned
   * teardown runs under the new generation — a stale event can never
   * reach the reopened report (I07).
   */
  async offer(candidate: ReportCandidate): Promise<ImportOutcomeLike> {
    if (this.busy) {
      return { ok: false, failure: BUSY_FAILURE };
    }
    this.busy = true;
    try {
      const failClosed = (failure: ImportFailureLike, mutateLifecycle: boolean): ImportOutcomeLike => {
        this.emit({
          type: "rejected",
          generation: this.host.currentGeneration,
          failure,
        });
        if (mutateLifecycle) {
          this.host.requestClear("idle");
        }
        return { ok: false, failure };
      };

      // Cheap declared-size gate and full validation happen BEFORE any
      // workspace replacement so a refused import cannot wipe a different
      // valid session.
      if (!Number.isFinite(candidate.size) || candidate.size > this.engine.maxJsonBytes) {
        return failClosed(tooLargeFailure("import:declared-size"), false);
      }
      let bytes: Uint8Array;
      try {
        bytes = new Uint8Array(await candidate.arrayBuffer());
      } catch {
        return failClosed(invalidFailure("BYTES", "import:unreadable"), false);
      }

      const outcome = this.engine.openReport(bytes);
      if (!outcome.ok) {
        return failClosed(outcome.failure, false);
      }

      const state = this.host.fileState;
      if (state === "idle") {
        this.host.openFile();
      } else if (state === "validating_file") {
        // Already in the sniff phase: proceed.
      } else if (state === "clearing") {
        return { ok: false, failure: BUSY_FAILURE };
      } else {
        // selecting/running/terminal states: generation-first replacement
        // only after the candidate has been proven to be a report.
        this.emit({
          type: "clear",
          generation: this.host.currentGeneration,
          next: "replace",
        });
        this.host.requestClear("replace");
      }

      const imported = outcome.imported;
      const report = imported.report as {
        document: { sha256: string; page_count: number };
      };
      this.host.fileValidated();
      this.host.metadataLoaded({
        sha256: report.document.sha256,
        page_count: report.document.page_count,
      });

      const availability = this.availability(imported.report);
      const view = this.engine.reportView(imported, availability);
      const replay = this.engine.replayView(imported, availability, false);
      this.sourceAttached = false;
      this.current = { imported, view, replay };
      // File-scoped ownership: the imported evidence is released by
      // clear/replace — and the teardown observes the NEW generation.
      this.host.own(imported, "imported-report", () => {
        this.emit({
          type: "teardown",
          generation: this.host.currentGeneration,
          label: "imported-report",
        });
        if (this.current?.imported === imported) {
          this.current = null;
          this.sourceAttached = false;
        }
      });
      this.emit({
        type: "imported",
        generation: this.host.currentGeneration,
        view,
        replay,
      });
      return outcome;
    } catch (error) {
      const failure = invalidFailure(
        "INTERNAL",
        error instanceof Error ? error.message.slice(0, 160) : "unexpected",
      );
      this.emit({
        type: "rejected",
        generation: this.host.currentGeneration,
        failure,
      });
      try {
        this.host.requestClear("idle");
      } catch {
        // Already idle/clearing — nothing more to release here.
      }
      return { ok: false, failure };
    } finally {
      this.busy = false;
    }
  }

  /**
   * Offer an explicit local source PDF for replay. Only meaningful for
   * an open evidence report whose original bytes are missing; the bytes
   * must verify against the recorded document identity or nothing is
   * attached and replay stays blocked (I09).
   *
   * The byte read is bound to the exact opened report and generation it
   * started under: a replace or clear that lands while the read is in
   * flight supersedes it, and the verified bytes are dropped rather
   * than attached to a different report or a cleared workspace (I07 —
   * the same generation discipline `offer` applies to itself). The
   * newer action always wins; the stale read never emits — a read that
   * fails after supersession drops its `source_rejected` the same way.
   */
  async offerSource(
    candidate: ReportCandidate,
  ): Promise<
    SourceCheckLike | { readonly ok: false; readonly kind: string; readonly detail: string }
  > {
    if (this.busy) {
      return { ok: false, kind: "busy", detail: "source:busy" };
    }
    const current = this.current;
    if (current === null) {
      return { ok: false, kind: "no_report", detail: "source:no-report-open" };
    }
    if (current.imported.source.kind !== "required") {
      return {
        ok: false,
        kind: "not_required",
        detail: "source:not-required",
      };
    }
    // Cheap reject on declared size before reading any byte.
    if (candidate.size !== current.view.document.byteLength) {
      const detail = "source:length-mismatch";
      this.emit({
        type: "source_rejected",
        generation: this.host.currentGeneration,
        detail,
      });
      return { ok: false, kind: "source_mismatch", detail };
    }
    // Bind the pending read to this exact report at this generation.
    const generation = this.host.currentGeneration;
    let bytes: Uint8Array;
    try {
      bytes = new Uint8Array(await candidate.arrayBuffer());
    } catch {
      // The same binding as the success path: a read superseded while
      // in flight (replace/clear landed first) drops its failure too —
      // the report it was offered for is gone, so the rejection can
      // never render on the newer generation's report.
      if (this.current !== current || this.host.currentGeneration !== generation) {
        return { ok: false, kind: "superseded", detail: "source:superseded" };
      }
      const detail = "source:unreadable";
      this.emit({
        type: "source_rejected",
        generation: this.host.currentGeneration,
        detail,
      });
      return { ok: false, kind: "source_mismatch", detail };
    }
    // The read outlived the report it was offered for — replace or
    // clear already won. Drop the bytes: no attach, no ownership, no
    // event under the new generation.
    if (this.current !== current || this.host.currentGeneration !== generation) {
      return { ok: false, kind: "superseded", detail: "source:superseded" };
    }
    const check = this.engine.verifySource(current.imported.report, bytes);
    if (!check.ok) {
      if (this.current !== current || this.host.currentGeneration !== generation) {
        return { ok: false, kind: "superseded", detail: "source:superseded" };
      }
      this.emit({
        type: "source_rejected",
        generation: this.host.currentGeneration,
        detail: check.detail,
      });
      return check;
    }
    // Re-check after hashing: a replace that landed during verify must
    // not attach or overwrite the newer report with the stale current.
    if (this.current !== current || this.host.currentGeneration !== generation) {
      return { ok: false, kind: "superseded", detail: "source:superseded" };
    }
    this.sourceAttached = true;
    this.host.own(bytes, "source-bytes", () => {
      this.emit({
        type: "teardown",
        generation: this.host.currentGeneration,
        label: "source-bytes",
      });
      this.sourceAttached = false;
    });
    const availability = this.availability(current.imported.report);
    const replay = this.engine.replayView(current.imported, availability, true);
    this.current = { ...current, replay };
    this.emit({
      type: "source_attached",
      generation: this.host.currentGeneration,
      sha256: check.sha256,
      replay,
    });
    return {
      ...check,
      bytes,
      generation: this.host.currentGeneration,
      documentSha256: check.sha256,
    };
  }

  /**
   * Offer one side of a comparison — an explicitly, locally selected
   * report file. Compare selection never touches the workspace
   * lifecycle: it gates the bytes and records the side; the verdict
   * appears once both sides validate.
   */
  async offerCompareSide(
    side: "left" | "right",
    candidate: ReportCandidate,
  ): Promise<ImportOutcomeLike> {
    if (this.busy) {
      return { ok: false, failure: BUSY_FAILURE };
    }
    this.busy = true;
    try {
      const fail = (failure: ImportFailureLike): ImportOutcomeLike => {
        if (side === "left") {
          this.compareLeft = null;
          this.compareLeftFailure = failure;
        } else {
          this.compareRight = null;
          this.compareRightFailure = failure;
        }
        this.compareReadiness = null;
        this.emit({
          type: "compare_side",
          generation: this.host.currentGeneration,
          side,
          ok: false,
          failure,
        });
        return { ok: false, failure };
      };

      if (!Number.isFinite(candidate.size) || candidate.size > this.engine.maxJsonBytes) {
        return fail(tooLargeFailure("import:declared-size"));
      }
      let bytes: Uint8Array;
      try {
        bytes = new Uint8Array(await candidate.arrayBuffer());
      } catch {
        return fail(invalidFailure("BYTES", "import:unreadable"));
      }
      const outcome = this.engine.openReport(bytes);
      if (!outcome.ok) {
        return fail(outcome.failure);
      }
      const availability = this.availability(outcome.imported.report);
      const view = this.engine.reportView(outcome.imported, availability);
      const sideState: CompareSide = { imported: outcome.imported, view };
      if (side === "left") {
        this.compareLeft = sideState;
        this.compareLeftFailure = null;
      } else {
        this.compareRight = sideState;
        this.compareRightFailure = null;
      }
      this.emit({
        type: "compare_side",
        generation: this.host.currentGeneration,
        side,
        ok: true,
        failure: null,
      });
      if (this.compareLeft !== null && this.compareRight !== null) {
        this.compareReadiness = this.engine.prepareComparison(
          this.compareLeft.imported.report,
          this.compareRight.imported.report,
        );
        this.emit({
          type: "compare_ready",
          generation: this.host.currentGeneration,
          readiness: this.compareReadiness,
          leftId: this.compareLeft.view.reportId,
          rightId: this.compareRight.view.reportId,
        });
      }
      return outcome;
    } finally {
      this.busy = false;
    }
  }

  /** Clear the workspace back to idle (generation increments first). */
  clear(): void {
    this.current = null;
    this.sourceAttached = false;
    if (this.host.fileState !== "idle") {
      this.emit({
        type: "clear",
        generation: this.host.currentGeneration,
        next: "idle",
      });
      this.host.requestClear("idle");
    }
  }
}
