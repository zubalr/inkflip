/**
 * Public inspection session (pdf-3g8) — the composition the shipped app
 * actually runs: local File → open/selection → real reader run →
 * findings/report → viewer → selected export → strict reopen.
 *
 * Everything observable flows through the T11 RunCoordinator: file
 * lifecycle, generation-first replace/cancel, run state and retained
 * occurrences are the coordinator's own bookkeeping — the UI only ever
 * renders `snapshot()` plus the sealed report. Reader results enter the
 * record exclusively as schema-valid `WorkerMessage`s admitted by
 * `receive()`; nothing here mutates coordinator state directly.
 *
 * Executors per capability:
 * - `native_text` / `render` → the pinned pdf.js adapter (T09)
 * - `ocr` → the staged Tesseract reader (T10), lazily opened during
 *   `preparing_assets`; rasters come from the named render reader
 * - `alignment` → `alignPage` (region-match-v1) computed in-page over
 *   the retained occurrences of the page's text/OCR checks
 *
 * Honesty rules: no occurrence or finding is ever fabricated here —
 * capped OCR coverage, failed/unsupported/cancelled checks and one-sided
 * readings all land in the sealed report as explicit evidence.
 */
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.mjs?url";
import * as tesseract from "tesseract.js";
import {
  MessageFactory,
  RunCoordinator,
  RUNTIME_LIMITS,
  TransferLedger,
  deriveRunKey,
} from "../../../../../packages/runtime/src/index";
import type { CoordinatorIntent } from "../../../../../packages/runtime/src/index";
import type {
  CheckPlan,
  CheckResult,
  Occurrence,
  Page,
  Plan,
  Reader,
  Report,
  Transform,
} from "../../../../../packages/contracts/src/index.ts";
import { createPdfJsReader } from "../../../../../packages/readers-pdfjs/src/index";
import type {
  DocumentHandle,
  PdfJsApi,
  PdfJsReaderAdapter,
} from "../../../../../packages/readers-pdfjs/src/index";
import {
  DEFAULT_OCR_BUDGET,
  OCR_PSM,
  TesseractOcrReader,
  buildReader,
  ocrReaderId,
} from "../../../../../packages/readers-tesseract/src/index";
import type {
  OcrHandle,
  OcrSelection,
  PageRaster,
  TesseractEngineModule,
} from "../../../../../packages/readers-tesseract/src/index";
import { buildPage } from "../../../../../packages/geometry/src/index.ts";
import { alignPage } from "../../../../../packages/compare/alignment/index.ts";
import type { AlignmentResult } from "../../../../../packages/compare/alignment/index.ts";
import type { OpenedDocumentInfo } from "../open/types";
import type { OpenProfile } from "../open/limits";
import type { ContractRegion } from "../selection/region";
import type { RegionRaster } from "../selection/RegionEditor";
import type { PlanOutcome } from "../open/OpenWorkspace";
import { displaySize } from "../selection/region";
import { OCR_ASSET_HASHES, OCR_CORE_BUILD, OCR_ENGINE_VERSION, OCR_MODEL, OCR_PATHS } from "./assets";
import { assembleReport } from "./report";
import { createExportEngine, createImportEngine, installedReaders } from "./engines";
import type { ExportEngine } from "../export/types";
import type { ImportEngine } from "../import/types";
import { OpenController } from "../open/controller";
import { ImportController } from "../import/controller";
import type { ReportViewLike, ReplayViewLike } from "../import/types";

/** Bounded preview edge for the region editor (CSS px == raster px). */
const PREVIEW_EDGE_PX = 720;
/** OCR raster target scale (px/pt ≈ 144 dpi) before the pixel cap clamps. */
const OCR_RASTER_SCALE = 2.0;
/** Whole-run wall budget surfaced on the contract plan. */
const RUN_BUDGET_MS = 120_000;

export interface InspectionState {
  readonly fileState: string;
  readonly generation: number;
  readonly doc: OpenedDocumentInfo | null;
  readonly report: Report | null;
  readonly reportSource: "run" | "import" | null;
  readonly error: { readonly message: string; readonly detail: string | null } | null;
  readonly notice: string | null;
  readonly run: ReturnType<RunCoordinator["snapshot"]>["run"];
  readonly occurrences: readonly Occurrence[];
  readonly importedView: ReportViewLike | null;
  readonly importedReplay: ReplayViewLike | null;
  readonly sourceAttached: boolean;
}

export class InspectionSession {
  readonly coordinator: RunCoordinator;
  readonly adapter: PdfJsReaderAdapter;
  readonly openController: OpenController;
  readonly importController: ImportController;
  readonly importEngine: ImportEngine;
  readonly exportEngine: ExportEngine;
  readonly profile: OpenProfile;

  private readonly listeners = new Set<() => void>();
  private doc: OpenedDocumentInfo | null = null;
  private contractPages: Page[] = [];
  private sourceBytes: Uint8Array | null = null;
  private error: InspectionState["error"] = null;
  private notice: string | null = null;

  private report: Report | null = null;
  private reportSource: "run" | "import" | null = null;
  private importedView: ReportViewLike | null = null;
  private importedReplay: ReplayViewLike | null = null;
  private sourceAttached = false;

  private ocrReader: TesseractOcrReader | null = null;
  private ocrHandle: OcrHandle | null = null;
  private ocrSelections = new Map<string, OcrSelection>();
  private rasters = new Map<
    number,
    PageRaster & { generation: number; documentSha256: string }
  >();

  private plansById = new Map<string, CheckPlan>();
  private regionsById = new Map<string, ContractRegion>();
  private alignments = new Map<string, AlignmentResult>();
  private runReaders = new Map<string, Reader>();
  private transforms = new Map<string, Transform>();
  private pageTransforms: Transform[] = [];
  private jobSignals = new Map<string, AbortController>();
  private runGeneration = 0;
  private runKey = "";
  private cancelPending = false;
  private selectedPages: number[] = [];
  private selectedRegions: ContractRegion[] = [];
  private ocrPagesCount = 0;
  private ocrNote: string | null = null;
  private runStartedAt = "";
  private runStartPerf = 0;
  private openedAt = "";
  private assembledForGeneration = -1;
  private pumping = false;

  constructor(profile: OpenProfile) {
    this.profile = profile;
    this.adapter = createPdfJsReader({
      pdfjs: pdfjs as unknown as PdfJsApi,
      workerSrc: workerUrl,
      cMapUrl: "/assets/pdfjs/6.3.289/cmaps/",
      standardFontDataUrl: "/assets/pdfjs/6.3.289/standard_fonts/",
      wasmUrl: "/assets/pdfjs/6.3.289/wasm/",
      iccUrl: "/assets/pdfjs/6.3.289/iccs/",
    });
    this.coordinator = new RunCoordinator({
      schedule: (fn, ms) => setTimeout(fn, ms),
      unschedule: (handle) => clearTimeout(handle as number),
    });
    this.importEngine = createImportEngine();
    this.exportEngine = createExportEngine();
    this.openController = new OpenController({
      host: this.coordinator,
      adapter: this.adapter,
      profile,
      onEvent: (event) => this.onOpenEvent(event),
    });
    this.importController = new ImportController({
      host: this.coordinator,
      engine: this.importEngine,
      installedReaders: () => installedReaders(this.adapter, this.installedOcrReaders()),
      onEvent: (event) => this.onImportEvent(event),
    });
    this.coordinator.subscribe(() => this.onCoordinatorChange());
  }

  /**
   * The OCR reader identities this build can actually construct — both
   * PSM profiles bound to the live render reader. Deterministic, same
   * values `startRun` plans with, so imported reports that name them
   * resolve as installed.
   */
  private installedOcrReaders(): Reader[] {
    return [OCR_PSM.PAGE, OCR_PSM.SINGLE_LINE].map((psm) =>
      buildReader({
        engineVersion: OCR_ENGINE_VERSION,
        coreBuild: OCR_CORE_BUILD,
        model: OCR_MODEL,
        renderReaderId: this.adapter.readers.render.id,
        rasterDpi: 0,
        psm,
        profile: this.profile.id,
        limitations: [],
      }),
    );
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(): void {
    for (const listener of this.listeners) listener();
  }

  getState(): InspectionState {
    const snap = this.coordinator.snapshot();
    return {
      fileState: snap.fileState,
      generation: snap.generation,
      doc: this.doc,
      report: this.report,
      reportSource: this.reportSource,
      error: this.error,
      notice: this.notice ?? this.ocrNote,
      run: snap.run,
      occurrences: snap.occurrences,
      importedView: this.importedView,
      importedReplay: this.importedReplay,
      sourceAttached: this.sourceAttached,
    };
  }

  /**
   * One intake for every offered file: `.inkflip.json`/`.json` goes to
   * the strict report gate; anything else is validated as a PDF. The
   * controllers own generation-first replace semantics.
   */
  async offerFile(candidate: { name: string; type: string; size: number; slice: (a: number, b: number) => { arrayBuffer(): Promise<ArrayBuffer> }; arrayBuffer(): Promise<ArrayBuffer> }): Promise<void> {
    this.error = null;
    const isJson =
      candidate.name.endsWith(".json") ||
      candidate.name.endsWith(".inkflip.json") ||
      candidate.type === "application/json";
    if (isJson) {
      const outcome = await this.importController.offer(candidate);
      if (!outcome.ok) {
        this.error = { message: failureMessage(outcome.failure), detail: outcome.failure.detail };
        this.emit();
      }
      return;
    }
    const outcome = await this.openController.offer(candidate);
    if (!outcome.ok) {
      this.error = { message: outcome.error.message, detail: outcome.error.detail ?? null };
      this.emit();
      return;
    }
    // Retain the original bytes locally for the explicit export
    // source-inclusion opt-in — read once, identity-verified against the
    // document the controller actually opened (a superseding offer must
    // never inherit stale bytes).
    try {
      const bytes = new Uint8Array(await candidate.arrayBuffer());
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      const hex = [...new Uint8Array(digest)]
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
      if (hex === this.doc?.sha256) {
        this.sourceBytes = bytes;
      }
    } catch {
      this.sourceBytes = null;
    }
  }

  /** Explicit local source PDF for replay on an open imported report. */
  async attachSource(candidate: { name: string; size: number; arrayBuffer(): Promise<ArrayBuffer> }): Promise<void> {
    const result = await this.importController.offerSource(candidate);
    if (!result.ok) {
      this.error = { message: "The selected file does not match this report's recorded document.", detail: result.detail };
      this.emit();
      return;
    }
    // The controller hash-verified the candidate against the report's
    // recorded document — retain it so the export source opt-in can
    // include the file the user just attached. The sourceAttached flag
    // (set by the controller's source_attached event) binds this write
    // to the import that verified it.
    try {
      const bytes = new Uint8Array(await candidate.arrayBuffer());
      if (this.sourceAttached) this.sourceBytes = bytes;
    } catch {
      this.sourceBytes = null;
    }
  }

  /**
   * OpenWorkspace's startRun prop: freeze the plan, start the
   * coordinator run, then execute dispatched jobs to settlement. The
   * PlanOutcome is returned synchronously; job execution proceeds
   * asynchronously through `pump()`.
   */
  startRun = (
    handle: unknown,
    pages: readonly number[],
    regions: ReadonlyMap<number, ContractRegion>,
    options?: { readonly ocrConsent?: boolean },
  ): PlanOutcome => {
    const doc = this.doc;
    if (!doc) throw new Error("no document");
    this.selectedPages = [...pages].sort((a, b) => a - b);
    this.selectedRegions = [...regions.values()];
    this.regionsById = new Map(this.selectedRegions.map((r) => [r.id, r]));
    this.plansById = new Map();
    this.alignments = new Map();
    this.runReaders = new Map();
    this.transforms = new Map();
    this.rasters = new Map();
    this.ocrSelections = new Map();
    this.ocrReader = null;
    this.ocrHandle = null;
    this.cancelPending = false;
    this.notice = null;
    this.ocrNote = null;
    this.assembledForGeneration = -1;

    // OCR eligibility: user-drawn region pages first, then the rest of
    // the selection, bounded by the profile cap — narrowing is recorded
    // on the report, never silent (the AGY cap semantics). A mobile
    // profile additionally requires explicit consent before the model
    // load is planned at all.
    const ocrAllowed = options?.ocrConsent !== false;
    const withRegion = this.selectedPages.filter((p) => regions.has(p));
    const withoutRegion = this.selectedPages.filter((p) => !regions.has(p));
    const ocrPages = ocrAllowed
      ? [...withRegion, ...withoutRegion].slice(
          0,
          this.profile.maxOcrPagesPerRun,
        )
      : [];
    this.ocrPagesCount = ocrPages.length;
    this.ocrNote = !ocrAllowed
      ? "OCR checks were not run — consent was not given on this device. Native text checks still ran on every selected page."
      : ocrPages.length < this.selectedPages.length
        ? `OCR coverage limited to ${ocrPages.length} of ${this.selectedPages.length} selected page(s) by the ${this.profile.id} profile; text-layer checks still ran on every selected page.`
        : null;

    const checks: CheckPlan[] = [];
    const textPlans = this.adapter.plan(handle as DocumentHandle, {
      pages: this.selectedPages,
      capabilities: ["native_text"],
    });
    const renderPlans =
      ocrPages.length === 0
        ? []
        : this.adapter.plan(handle as DocumentHandle, {
            pages: ocrPages,
            capabilities: ["render"],
          });
    checks.push(...textPlans, ...renderPlans);

    // OCR CheckPlans mirror the reader's own deterministic ids — the
    // reader's `plan()` output is verified against these exact ids once
    // the model handle opens during preparing_assets.
    const ocrSelections: OcrSelection[] = ocrPages.map((pageIndex) => {
      const region = regions.get(pageIndex);
      return {
        pageIndex,
        purpose: region === undefined ? "page" : "region",
        region:
          region === undefined
            ? null
            : {
                id: region.id,
                polygon: region.geometry.polygon,
                label: region.label,
              },
      };
    });
    const ocrPlans: CheckPlan[] = ocrSelections.map((sel, i) => ({
      id: `ocr_${sel.pageIndex}_${i}`,
      page_index: sel.pageIndex,
      reader_ids: [
        ocrReaderId({
          profile: this.profile.id,
          psm: sel.purpose === "line" ? OCR_PSM.SINGLE_LINE : OCR_PSM.PAGE,
          renderReaderId: this.adapter.readers.render.id,
        }),
      ],
      capability: "ocr",
      region_id: sel.region?.id ?? null,
    }));
    ocrSelections.forEach((sel, i) => {
      this.ocrSelections.set(`ocr_${sel.pageIndex}_${i}`, sel);
    });
    checks.push(...ocrPlans);

    const textReaderId = this.adapter.readers.text.id;
    const ocrReaderIdByPage = new Map<number, string>();
    for (const sel of ocrSelections) {
      ocrReaderIdByPage.set(
        sel.pageIndex,
        ocrReaderId({
          profile: this.profile.id,
          psm: sel.purpose === "line" ? OCR_PSM.SINGLE_LINE : OCR_PSM.PAGE,
          renderReaderId: this.adapter.readers.render.id,
        }),
      );
    }
    for (const page of this.selectedPages) {
      // An alignment check names the readings it compares — the text
      // layer always, plus the OCR reader when the page is OCR-checked.
      const compared = [textReaderId];
      const ocrId = ocrReaderIdByPage.get(page);
      if (ocrId !== undefined) compared.push(ocrId);
      checks.push({
        id: `chk_p${page}_alignment`,
        page_index: page,
        reader_ids: compared,
        capability: "alignment",
        region_id: regions.get(page)?.id ?? null,
      });
    }
    for (const check of checks) this.plansById.set(check.id, check);

    const readers: Reader[] = [this.adapter.readers.text, this.adapter.readers.render];
    if (ocrPages.length > 0) {
      const planned = buildReader({
        engineVersion: OCR_ENGINE_VERSION,
        coreBuild: OCR_CORE_BUILD,
        model: OCR_MODEL,
        renderReaderId: this.adapter.readers.render.id,
        rasterDpi: 0,
        psm: OCR_PSM.PAGE,
        profile: this.profile.id,
        limitations: [],
      });
      readers.push(planned);
      // Declare the planned reader immediately — if model preparation then
      // fails, the report still names the reader its checks referenced
      // (a successful extract later replaces this descriptor with the
      // actual one carrying raster dpi/limitations).
      this.runReaders.set(planned.id, planned);
    }
    this.runKey = deriveRunKey(doc.sha256, readers, {
      checks: checks.map((c) => c.id),
    });
    this.runStartedAt = new Date().toISOString();
    this.runStartPerf = performance.now();
    this.coordinator.startRun({
      runKey: this.runKey,
      checks,
      selectedPagesTotal: this.selectedPages.length,
      budgetMs: RUN_BUDGET_MS,
      needsAssets: ocrPages.length > 0,
    });
    this.runGeneration = this.coordinator.currentGeneration;

    let dispatched: { jobId: string; checkId: string; capability: string }[] = [];
    if (ocrPages.length > 0) {
      // needsAssets holds the coordinator in preparing_assets — nothing
      // dispatches until assetsReady releases it in prepareOcrAssets.
      void this.prepareOcrAssets(handle as DocumentHandle, ocrSelections);
    } else {
      dispatched = this.drainOnce();
      this.pump();
    }

    const snapshot = this.coordinator.snapshot();
    return {
      checks: checks.map((c) => ({
        id: c.id,
        page_index: c.page_index,
        capability: c.capability,
        region_id: c.region_id,
      })),
      dispatched,
      selectedPagesTotal: snapshot.run?.selectedPagesTotal ?? this.selectedPages.length,
    };
  };

  /**
   * preparing_assets → running: open the OCR reader, verify its real
   * `plan()` output matches the pre-planned check ids (a mismatch fails
   * the OCR checks honestly — a silently renamed plan would be a lie),
   * then release the coordinator into `running`.
   */
  private async prepareOcrAssets(
    handle: DocumentHandle,
    selections: readonly OcrSelection[],
  ): Promise<void> {
    const generation = this.runGeneration;
    const stale = () => this.coordinator.currentGeneration !== generation;
    try {
      const reader = new TesseractOcrReader({
        engine: tesseract as unknown as TesseractEngineModule,
        engineVersion: OCR_ENGINE_VERSION,
        coreBuild: OCR_CORE_BUILD,
        model: OCR_MODEL,
        paths: OCR_PATHS,
        assetHashes: OCR_ASSET_HASHES,
        profile: this.profile.id,
        runKey: this.runKey,
        renderReaderId: this.adapter.readers.render.id,
        rasterSource: (pageIndex) => this.ocrRaster(handle, pageIndex),
      });
      if (stale()) return;
      const ocrHandle = await reader.open({
        documentSha256: this.doc?.sha256 ?? "",
        generation,
      });
      if (stale()) {
        await reader.close().catch(() => undefined);
        return;
      }
      const planned = reader.plan(ocrHandle, selections);
      const mismatch = planned.some(
        (c, i) =>
          c.id !== `ocr_${selections[i]?.pageIndex}_${i}` ||
          !this.plansById.has(c.id),
      );
      this.ocrReader = reader;
      this.ocrHandle = ocrHandle;
      this.coordinator.ownRunResource(reader, "ocr-reader", () => reader.close());
      if (mismatch) {
        this.notice = "OCR plan identity mismatch — OCR checks will report failure.";
      }
    } catch (error) {
      // Model/worker preparation failed: OCR checks still dispatch and
      // report `failed`/`model_missing` honestly — never a silent stall.
      // Guarded by generation: a stale prep must never clobber the
      // reader a superseding run may have just assigned.
      if (!stale()) {
        this.ocrReader = null;
        this.ocrHandle = null;
        this.notice = `OCR model could not be prepared: ${error instanceof Error ? error.message.slice(0, 140) : "unavailable"}. OCR checks are recorded as failed.`;
      }
    }
    if (stale()) return;
    if (this.coordinator.fileState === "preparing_assets") {
      this.coordinator.assetsReady();
      if (this.cancelPending) {
        this.cancelPending = false;
        this.coordinator.requestCancel();
      }
    }
    this.pump();
  }

  /** Render one page for OCR — reuses the run's render-check raster. */
  private async ocrRaster(
    handle: DocumentHandle,
    pageIndex: number,
  ): Promise<PageRaster> {
    const generation = this.runGeneration;
    const cached = this.rasters.get(pageIndex);
    if (
      cached &&
      cached.generation === generation &&
      cached.documentSha256 === (this.doc?.sha256 ?? "")
    ) {
      return cached;
    }
    const out = await this.adapter.extract(
      handle,
      {
        id: `ras_src_p${pageIndex}`,
        page_index: pageIndex,
        reader_ids: [this.adapter.readers.render.id],
        capability: "render",
        region_id: null,
      },
      () => undefined,
      {},
      {
        runKey: this.runKey,
        renderScalePxPerPt: OCR_RASTER_SCALE,
        rasterIndex: pageIndex,
      },
    );
    const raster = out.raster;
    if (!raster) {
      throw new Error(out.result.reason ?? "render failed");
    }
    const page = this.contractPages[pageIndex];
    if (!page) throw new Error(`page ${pageIndex} metadata missing`);
    const image = new ImageData(
      new Uint8ClampedArray(raster.imageData),
      raster.widthPx,
      raster.heightPx,
    );
    const pageRaster: PageRaster = {
      rasterId: raster.rasterId,
      renderReaderId: this.adapter.readers.render.id,
      scalePxPerPt: raster.scalePxPerPt,
      widthPx: raster.widthPx,
      heightPx: raster.heightPx,
      image,
      built: buildPage({
        index: page.index,
        mediaBox: page.media_box,
        cropBox: page.crop_box,
        viewBox: page.effective_view_box,
        userUnit: page.user_unit,
        rotation: page.rotation,
        boxSource: page.box_source,
        transformId: page.raw_to_canonical_transform_id,
        limitations: page.limitations,
      }),
    };
    if (
      this.coordinator.currentGeneration === generation &&
      this.runGeneration === generation
    ) {
      this.rasters.set(pageIndex, {
        generation,
        documentSha256: this.doc?.sha256 ?? "",
        ...pageRaster,
      });
    }
    return pageRaster;
  }

  /** Region-editor preview raster through the real render path. */
  renderPageRaster = async (
    handle: unknown,
    pageIndex: number,
  ): Promise<RegionRaster> => {
    const page = this.doc?.pages[pageIndex];
    if (!page) throw new Error(`page ${pageIndex + 1} has no metadata`);
    const [dispW, dispH] = displaySize(page);
    const requested = PREVIEW_EDGE_PX / Math.max(dispW, dispH);
    const checks = this.adapter.plan(handle as DocumentHandle, {
      pages: [pageIndex],
      capabilities: ["render"],
    });
    const check = checks[0];
    if (!check) throw new Error("render check was not planned");
    const outcome = await this.adapter.extract(
      handle as DocumentHandle,
      check,
      () => undefined,
      {},
      { renderScalePxPerPt: requested },
    );
    const raster = outcome.raster;
    if (!raster) throw new Error(outcome.result.reason ?? "render failed");
    return {
      widthPx: raster.widthPx,
      heightPx: raster.heightPx,
      scalePxPerPt: raster.scalePxPerPt,
      imageData: raster.imageData,
      limitations: raster.limitations,
    };
  };

  /**
   * Instrumented observation: render the live committed document at a
   * requested scale that exceeds pixel/edge caps and record the clamp.
   */
  probeRasterBounds = async (
    handle: unknown,
    requestedScalePxPerPt = 20,
  ): Promise<{
    widthPx: number;
    heightPx: number;
    requestedScalePxPerPt: number;
    usedScalePxPerPt: number;
    limitations: readonly string[];
    status: string;
    reason: string | null;
  }> => {
    const checks = this.adapter.plan(handle as DocumentHandle, {
      pages: [0],
      capabilities: ["render"],
    });
    const check = checks[0];
    if (!check) throw new Error("render check was not planned");
    const outcome = await this.adapter.extract(
      handle as DocumentHandle,
      check,
      () => undefined,
      {},
      { renderScalePxPerPt: requestedScalePxPerPt },
    );
    const raster = outcome.raster;
    return {
      widthPx: raster?.widthPx ?? 0,
      heightPx: raster?.heightPx ?? 0,
      requestedScalePxPerPt,
      usedScalePxPerPt: raster?.scalePxPerPt ?? 0,
      limitations: raster?.limitations ?? [],
      status: outcome.result.status,
      reason: outcome.result.reason,
    };
  };

  /**
   * Instrumented observation of the bundled TransferLedger: two claims
   * succeed, the third is raster_cap, release recovers a slot.
   */
  probeLiveRasterCap(): {
    first: "ok" | "raster_cap" | "foreign";
    second: "ok" | "raster_cap" | "foreign";
    third: "ok" | "raster_cap" | "foreign";
    liveAfterTwo: number;
    liveAfterRelease: number;
    recovered: "ok" | "raster_cap" | "foreign";
    cap: number;
  } {
    const ledger = new TransferLedger();
    const first = ledger.claim("raster_rgba", "probe_a");
    const second = ledger.claim("raster_rgba", "probe_b");
    const third = ledger.claim("raster_rgba", "probe_c");
    const liveAfterTwo = ledger.liveRasters;
    ledger.release("probe_a");
    const liveAfterRelease = ledger.liveRasters;
    const recovered = ledger.claim("raster_rgba", "probe_c");
    return {
      first,
      second,
      third,
      liveAfterTwo,
      liveAfterRelease,
      recovered,
      cap: RUNTIME_LIMITS.maxLiveRasters,
    };
  }

  observeResources(): ReturnType<RunCoordinator["resourceObservation"]> {
    return this.coordinator.resourceObservation();
  }

  cancelRun(): void {
    if (this.coordinator.fileState === "running") {
      this.coordinator.requestCancel();
      this.pump();
    } else if (this.coordinator.fileState === "preparing_assets") {
      // The coordinator only admits cancel from `running` — remember the
      // intent and cancel the instant assetsReady releases the run.
      this.cancelPending = true;
      this.emit();
    }
  }

  /** Terminal run → selecting for an explicit re-run on the same file. */
  newRun(): void {
    this.report = null;
    this.reportSource = null;
    this.coordinator.prepareNewRun();
    this.emit();
  }

  close(): void {
    this.report = null;
    this.reportSource = null;
    this.importedView = null;
    this.importedReplay = null;
    this.doc = null;
    this.error = null;
    this.notice = null;
    this.ocrNote = null;
    this.sourceAttached = false;
    if (this.coordinator.fileState !== "idle") {
      this.openController.clear();
    }
    this.emit();
  }

  /** Original bytes for the explicit export opt-in (file-scoped). */
  sourcePdfBytes = (): Uint8Array | null => this.sourceBytes;

  // -----------------------------------------------------------------
  // coordinator event wiring
  // -----------------------------------------------------------------

  private onOpenEvent(event: { type: string; [k: string]: unknown }): void {
    if (event.type === "metadata") {
      this.doc = event.document as OpenedDocumentInfo;
      this.error = null;
      this.notice = null;
      this.ocrNote = null;
      this.openedAt = new Date().toISOString();
      // Full contract pages for the report + geometry: the same adapter
      // read the controller performed, kept for the run.
      const handle = this.openController.currentHandle;
      if (handle !== null) {
        void this.adapter
          .pages(handle as DocumentHandle)
          .then((meta) => {
            if (this.openController.currentHandle === handle) {
              this.contractPages = [...meta.pages];
              this.pageTransforms = [...meta.transforms];
            }
          })
          .catch(() => undefined);
      }
    } else if (event.type === "clear") {
      this.doc = null;
      this.report = null;
      this.reportSource = null;
      this.importedView = null;
      this.importedReplay = null;
      this.contractPages = [];
      this.pageTransforms = [];
      this.sourceBytes = null;
      this.sourceAttached = false;
    }
    this.emit();
  }

  private onImportEvent(event: { type: string; [k: string]: unknown }): void {
    if (event.type === "imported") {
      const opened = this.importController.currentImport;
      if (opened) {
        this.importedView = opened.view as ReportViewLike;
        this.importedReplay = opened.replay as ReplayViewLike;
        this.report = opened.imported.report as Report;
        this.reportSource = "import";
        this.doc = null;
        // The import path bypasses the open controller's 'clear' event —
        // the previous document's retained bytes and page metadata must
        // end at the replacement boundary with it.
        this.sourceBytes = null;
        this.contractPages = [];
        this.pageTransforms = [];
        this.error = null;
        this.notice = null;
        this.ocrNote = null;
      }
    } else if (event.type === "source_attached") {
      this.sourceAttached = true;
      const opened = this.importController.currentImport;
      if (opened) this.importedReplay = opened.replay as ReplayViewLike;
      this.error = null;
    } else if (event.type === "source_rejected") {
      this.error = {
        message: "The selected file does not match this report's recorded document.",
        detail: String(event.detail ?? ""),
      };
    } else if (event.type === "rejected") {
      const failure = event.failure as { message?: string; kind?: string; detail?: string };
      this.error = {
        message: failureMessage(failure),
        detail: failure.detail ?? null,
      };
    } else if (event.type === "clear") {
      this.report = null;
      this.reportSource = null;
      this.importedView = null;
      this.importedReplay = null;
      this.sourceBytes = null;
      this.contractPages = [];
      this.pageTransforms = [];
      this.sourceAttached = false;
    }
    this.emit();
  }

  private onCoordinatorChange(): void {
    const state = this.coordinator.fileState;
    // Coordinator-internal transitions (deadline timeouts, dependency
    // cascades, clear intents) also push outbox intents — drain on every
    // notify so terminate/dispatch work actually executes.
    if (state === "running" || state === "preparing_assets") this.pump();
    if (
      (state === "complete" || state === "partial" || state === "failed") &&
      this.assembledForGeneration !== this.coordinator.currentGeneration
    ) {
      this.assembledForGeneration = this.coordinator.currentGeneration;
      this.assembleRunReport(state);
    }
    this.emit();
  }

  // -----------------------------------------------------------------
  // job execution: outbox intents -> real readers -> inbound messages
  // -----------------------------------------------------------------

  /** Execute one outbox intent; returns the dispatch job when it is one. */
  private executeIntent(intent: CoordinatorIntent): {
    jobId: string;
    checkId: string;
    capability: string;
  } | null {
    if (intent.type === "dispatch" && intent.checkId !== null) {
      const job = {
        jobId: intent.jobId,
        checkId: intent.checkId,
        capability: intent.capability ?? "",
      };
      void this.executeJob(intent.jobId, intent.checkId);
      return job;
    }
    if (intent.type === "terminate") {
      this.jobSignals.get(intent.jobId)?.abort();
    }
    // 'ack' is recorded by drainOutbox itself; 'message' intents are
    // coordinator→worker control (cancel) already covered by terminate.
    return null;
  }

  /**
   * Drain the outbox once: execute every dispatch, honour terminates.
   * Returns the jobs dispatched so callers can show real dispatch
   * evidence in the plan panel.
   */
  private drainOnce(): { jobId: string; checkId: string; capability: string }[] {
    const dispatched: { jobId: string; checkId: string; capability: string }[] = [];
    for (const intent of this.coordinator.drainOutbox()) {
      const job = this.executeIntent(intent);
      if (job !== null) dispatched.push(job);
    }
    return dispatched;
  }

  private pump(): void {
    if (this.pumping) return;
    this.pumping = true;
    try {
      for (;;) {
        const intents = this.coordinator.drainOutbox();
        if (intents.length === 0) return;
        for (const intent of intents) this.executeIntent(intent);
      }
    } finally {
      this.pumping = false;
    }
  }

  private feed(msg: unknown): void {
    this.coordinator.receive(msg);
    // Draining after every admitted message delivers the ack that frees
    // the sender's bounded window and surfaces newly-runnable dependents.
    this.pump();
  }

  private async executeJob(jobId: string, checkId: string): Promise<void> {
    const check = this.plansById.get(checkId);
    if (!check) return;
    const generation = this.runGeneration;
    const mf = new MessageFactory({
      generation,
      documentSha256: this.doc?.sha256 ?? "",
      runKey: this.runKey,
      jobId,
    });
    const ac = new AbortController();
    this.jobSignals.set(jobId, ac);
    const stale = () => this.coordinator.currentGeneration !== generation;
    const feedChunks = (occs: readonly Occurrence[]): void => {
      for (let i = 0; i < occs.length; i += 256) {
        this.feed(mf.chunk(check.id, [...occs.slice(i, i + 256)]));
      }
    };
    try {
      let result: CheckResult;
      if (check.capability === "ocr") {
        result = await this.runOcrCheck(check, feedChunks, ac.signal, stale);
      } else if (check.capability === "alignment") {
        result = this.runAlignmentCheck(check, ac, stale);
      } else {
        const handle = this.openController.currentHandle;
        if (handle === null || stale()) {
          result = {
            id: check.id,
            status: "cancelled",
            reason: "user_cancel",
            produced_occurrence_count: 0,
            retained_occurrence_ids: [],
          };
        } else {
          const outcome = await this.adapter.extract(
            handle as DocumentHandle,
            check,
            (occs) => {
              if (!stale()) feedChunks(occs);
            },
            { signal: ac.signal },
            {
              runKey: this.runKey,
              renderScalePxPerPt:
                check.capability === "render" ? OCR_RASTER_SCALE : undefined,
              rasterIndex: check.page_index,
            },
          );
          result = outcome.result;
          if (outcome.raster && check.capability === "render" && !stale()) {
            for (const t of outcome.raster.transforms ?? []) {
              this.transforms.set(t.id, t);
            }
            // Cache for the dependent OCR check's raster source — bound
            // to this run's generation and document so a late-settling
            // render can never feed stale pixels to a later run.
            const page = this.contractPages[check.page_index];
            if (page) {
              const image = new ImageData(
                new Uint8ClampedArray(outcome.raster.imageData),
                outcome.raster.widthPx,
                outcome.raster.heightPx,
              );
              this.rasters.set(check.page_index, {
                generation,
                documentSha256: this.doc?.sha256 ?? "",
                rasterId: outcome.raster.rasterId,
                renderReaderId: this.adapter.readers.render.id,
                scalePxPerPt: outcome.raster.scalePxPerPt,
                widthPx: outcome.raster.widthPx,
                heightPx: outcome.raster.heightPx,
                image,
                built: buildPage({
                  index: page.index,
                  mediaBox: page.media_box,
                  cropBox: page.crop_box,
                  viewBox: page.effective_view_box,
                  userUnit: page.user_unit,
                  rotation: page.rotation,
                  boxSource: page.box_source,
                  transformId: page.raw_to_canonical_transform_id,
                  limitations: page.limitations,
                }),
              });
            }
          }
        }
      }
      if (stale()) return;
      this.feed(mf.checkTerminal(check.id, result.status, result.reason));
    } catch (error) {
      if (stale()) return;
      if (ac.signal.aborted) {
        this.feed(mf.checkTerminal(check.id, "cancelled", "user_cancel"));
      } else {
        const reason =
          error instanceof Error ? error.message.slice(0, 120) : "executor_error";
        this.feed(mf.checkTerminal(check.id, "failed", reason));
      }
    } finally {
      this.jobSignals.delete(jobId);
      if (!stale()) this.pump();
    }
  }

  private async runOcrCheck(
    check: CheckPlan,
    feedChunks: (occs: readonly Occurrence[]) => void,
    signal: AbortSignal,
    stale: () => boolean,
  ): Promise<CheckResult> {
    const reader = this.ocrReader;
    const handle = this.ocrHandle;
    if (reader === null || handle === null) {
      return {
        id: check.id,
        status: "failed",
        reason: "model_missing:ocr reader was not prepared for this run",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      };
    }
    const output = await reader.extract(
      handle,
      check,
      (_id, occs) => {
        if (stale()) return;
        feedChunks(occs);
      },
      signal,
    );
    if (stale()) return { id: check.id, status: "cancelled", reason: "user_cancel", produced_occurrence_count: 0, retained_occurrence_ids: [] };
    this.runReaders.set(output.reader.id, output.reader);
    for (const t of output.transforms ?? []) {
      this.transforms.set(t.id, t);
    }
    return output.check;
  }

  private runAlignmentCheck(
    check: CheckPlan,
    ac: AbortController,
    stale: () => boolean,
  ): CheckResult {
    const snapshot = this.coordinator.snapshot();
    const retained = new Map(snapshot.occurrences.map((o) => [o.id, o]));
    const view = snapshot.run?.checks ?? [];
    const textCheck = view.find(
      (c) => c.pageIndex === check.page_index && c.capability === "native_text",
    );
    const ocrCheck = view.find(
      (c) => c.pageIndex === check.page_index && c.capability === "ocr",
    );
    const left = (textCheck?.retainedOccurrenceIds ?? [])
      .map((id) => retained.get(id))
      .filter((o): o is Occurrence => o !== undefined);
    const right = (ocrCheck?.retainedOccurrenceIds ?? [])
      .map((id) => retained.get(id))
      .filter((o): o is Occurrence => o !== undefined);
    if (ac.signal.aborted || stale()) {
      return {
        id: check.id,
        status: "cancelled",
        reason: "user_cancel",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      };
    }
    const region = this.regionsById.get(check.region_id ?? "");
    const result = alignPage(left, right, {
      page_index: check.page_index,
      region:
        region?.geometry.polygon != null
          ? { polygon: region.geometry.polygon }
          : null,
    });
    this.alignments.set(check.id, result);
    return {
      id: check.id,
      status: "completed",
      reason: null,
      produced_occurrence_count: 0,
      retained_occurrence_ids: [],
    };
  }

  // -----------------------------------------------------------------
  // settle → sealed report
  // -----------------------------------------------------------------

  private assembleRunReport(runStatus: string): void {
    const doc = this.doc;
    const snap = this.coordinator.snapshot();
    if (doc === null || snap.run === null) return;
    try {
      const checks = this.coordinator.settledCheckResults();
      const readers: Reader[] = [
        this.adapter.readers.text,
        this.adapter.readers.render,
        ...this.runReaders.values(),
      ];
      const plan: Plan = {
        version: "1.0.0",
        selected_pages: [...this.selectedPages],
        regions: this.selectedRegions.map((r) => ({
          id: r.id,
          page_index: r.page_index,
          geometry: { ...r.geometry, polygon: r.geometry.polygon === null ? null : [...r.geometry.polygon] },
          label: r.label,
        })),
        checks: [...this.plansById.values()],
        normalization_version: "scalar-whitespace-v1",
        alignment_version: "region-match-v1",
        profile: this.profile.id,
        budget: {
          max_raster_pixels: this.profile.maxRasterPixels,
          max_run_ocr_pixels: DEFAULT_OCR_BUDGET.maxRunOcrPixels,
          timeout_ms: RUN_BUDGET_MS,
          max_retries: DEFAULT_OCR_BUDGET.maxRetries,
        },
      };
      this.report = assembleReport({
        fileName: doc.label,
        openedAtIso: this.openedAt,
        runStartedAtIso: this.runStartedAt,
        durationMs: performance.now() - this.runStartPerf,
        document: {
          sha256: doc.sha256,
          byte_length: doc.byteLength,
          page_count: doc.pageCount,
        },
        plan,
        selectedPages: this.selectedPages,
        regions: this.selectedRegions,
        readers,
        checks,
        occurrences: [...snap.occurrences],
        alignments: this.alignments,
        runKey: this.runKey,
        runStatus: runStatus as Report["execution"]["status"],
        pages: this.contractPages,
        transforms: [...this.pageTransforms, ...this.transforms.values()],
        environment:
          typeof navigator === "undefined"
            ? "browser"
            : navigator.userAgent,
        maxOcrPagesPerRun: this.profile.maxOcrPagesPerRun,
        ocrCoverageNote: this.ocrNote,
      });
      this.reportSource = "run";
      this.importedView = null;
      this.importedReplay = null;
      this.error = null;
    } catch (error) {
      this.report = null;
      this.reportSource = null;
      this.error = {
        message: "The inspection run finished but its report could not be assembled.",
        detail: error instanceof Error ? error.message.slice(0, 200) : "assembly_error",
      };
    }
  }
}

function failureMessage(failure: { kind?: string; detail?: string }): string {
  switch (failure.kind) {
    case "not_a_report":
      return "That file is not an Inkflip report.";
    case "unsupported_version":
      return "This report version is not supported by this build.";
    case "too_large":
      return "That file is too large to open here.";
    default:
      return "Could not open that file.";
  }
}
