/**
 * Browser OCR reader adapter over tesseract.js (T10).
 *
 * Implements the READER_ADAPTER_CONTRACT operation set:
 *
 *   describe() -> ReaderManifest
 *   open(document digest, generation) -> bounded handle (one reusable
 *     initialized model per active profile; file replacement
 *     terminates it via close())
 *   plan(handle, selections) -> CheckPlan[]
 *   extract(handle, check, emitChunk, cancellation) -> CheckResult
 *   close(handle)
 *
 * Rasters come from the *named render reader* through the injected
 * `RasterSource` — this adapter never rasterizes itself (the OCR check
 * depends on the render check, RUNTIME_LIFECYCLE). The engine module
 * is likewise injected (see engine.ts); every worker is configured
 * with explicit staged same-origin worker/core/lang paths,
 * `gzip:false` and `workerBlobURL:false`, so no default CDN URL can
 * ever be constructed.
 *
 * Failure honesty (RUNTIME_LIFECYCLE): initialization/model failures
 * are terminal `failed` results with distinct reasons — never
 * conflated with `unreadable_pixels`, which is the informational
 * outcome of a *completed* recognition that found no usable text.
 * One transient retry (fresh worker) applies to init/worker crashes
 * only, inside the remaining run budget.
 */
import type {
  CheckPlan,
  CheckResult,
  Occurrence,
  Reader,
  ReaderManifest,
  Region,
  Transform,
} from '../../contracts/src/index.ts';
import type { BuiltPage } from '../../geometry/src/index.ts';
import {
  createEngineWorker,
  OCR_PSM,
  type EnginePaths,
  type OcrPsm,
  type TesseractEngineModule,
  type TesseractEngineWorker,
} from './engine.ts';
import {
  classifyError,
  OcrError,
  OCR_REASON,
  requireOcr,
  type OcrReason,
} from './errors.ts';
import {
  ModelAssetManager,
  type ModelIdentity,
  type ModelPreparation,
  type ModelState,
} from './model-cache.ts';
import {
  planCrop,
  type CropPlan,
  type OcrRegionInput,
  type PageRasterInfo,
} from './crop.ts';
import {
  buildManifest,
  buildReader,
  ocrReaderId,
  type ReaderIdentityInput,
} from './identity.ts';
import {
  LOW_CONFIDENCE_BELOW,
  mapEngineBlocks,
  meanWordConfidence,
} from './occurrences.ts';

/** Bounded per-run OCR budget (planning/config/settings.json). */
export interface OcrBudget {
  /** Max pixels entering the engine for one crop (4_000_000). */
  readonly maxRasterPixels: number;
  /** Max cumulative OCR pixels per run (20_000_000). */
  readonly maxRunOcrPixels: number;
  /** Max edge length of an OCR input (8192). */
  readonly maxRasterEdge: number;
  /** Per-page produced-occurrence cap (20_000). */
  readonly maxOccurrencesPerPage: number;
  /** Per-run produced-occurrence cap (100_000). */
  readonly maxOccurrencesPerRun: number;
  /** Per-run raw-text byte cap (8_388_608). */
  readonly maxRawTextBytesPerRun: number;
  /** Per-check wall deadline (30_000). */
  readonly checkTimeoutMs: number;
  /** Automatic transient retries (1). */
  readonly maxRetries: number;
}

export const DEFAULT_OCR_BUDGET: OcrBudget = {
  maxRasterPixels: 4_000_000,
  maxRunOcrPixels: 20_000_000,
  maxRasterEdge: 8192,
  maxOccurrencesPerPage: 20_000,
  maxOccurrencesPerRun: 100_000,
  maxRawTextBytesPerRun: 8_388_608,
  checkTimeoutMs: 30_000,
  maxRetries: 1,
};

/** A produced page raster from the named render reader. */
export interface PageRaster extends PageRasterInfo {
  /** Canvas-bearing pixels (canvas/ImageBitmap/ImageData). */
  readonly image: unknown;
  /** Contract page + canonical transform built by the renderer. */
  readonly built: BuiltPage;
}

export type RasterSource = (pageIndex: number) => Promise<PageRaster>;

/** One planned OCR selection (page, region or single-line region). */
export interface OcrSelection {
  readonly pageIndex: number;
  readonly purpose: 'page' | 'region' | 'line';
  readonly region?: OcrRegionInput | null;
}

/** Cancellation surface: AbortSignal or a polling predicate. */
export interface OcrCancellation {
  readonly isCancelled: () => boolean;
}

export function cancellationOf(
  source: AbortSignal | OcrCancellation | (() => boolean) | undefined,
): OcrCancellation {
  if (source === undefined) return { isCancelled: () => false };
  if (typeof source === 'function') return { isCancelled: source };
  if (source instanceof AbortSignal) {
    return { isCancelled: () => source.aborted };
  }
  return source;
}

/** Producer-side bounded chunk emitter (<=256 occurrences each). */
export type EmitChunk = (
  checkId: string,
  occurrences: readonly Occurrence[],
) => void;
export const MAX_CHUNK_OCCURRENCES = 256;

/** Engine/model identity carried on every check output (I13). */
export interface OcrEngineIdentity {
  readonly name: 'tesseract.js';
  /** npm package version (frozen manifest). */
  readonly packageVersion: string;
  /** Engine-reported tesseract version from the recognize result. */
  readonly reportedVersion: string | null;
  /** Engine-reported OEM enum name. */
  readonly oem: string | null;
  /** Engine-reported PSM enum name actually used for the check. */
  readonly psmReported: string | null;
  /** Adapter implementation version. */
  readonly adapterVersion: '1.0.0';
}

export interface OcrCheckOutput {
  readonly check: CheckResult;
  /** The exact configured `Reader` identity used for this check. */
  readonly reader: Reader;
  readonly engine: OcrEngineIdentity;
  readonly model: {
    readonly id: string;
    readonly version: string;
    readonly sha256: string;
    readonly state: ModelState;
    readonly provenance: 'memory' | 'cache' | 'network' | null;
  };
  readonly raster: PageRasterInfo;
  readonly crop: {
    readonly cropX: number;
    readonly cropY: number;
    readonly cropWidthPx: number;
    readonly cropHeightPx: number;
    readonly regionPx: readonly [number, number, number, number] | null;
    readonly paddingPx: number;
    readonly resizeK: number;
    readonly outWidthPx: number;
    readonly outHeightPx: number;
    readonly ocrId: string;
  };
  /**
   * Verbatim engine output — raw text plus the word/line/block
   * hierarchy as returned by the recognizer, never normalized.
   */
  readonly raw: { readonly text: string | null; readonly blocks: unknown };
  readonly occurrences: Occurrence[];
  readonly transforms: Transform[];
  readonly diagnostics: {
    readonly meanConfidence: number | null;
    readonly lowConfidenceIds: string[];
    readonly wordCount: number;
    readonly emptyWords: number;
    readonly pixelsOcr: number;
    readonly runOcrPixelsTotal: number;
    readonly downscaled: boolean;
    readonly durationMs: number;
    readonly workerInitCount: number;
    readonly attempt: number;
  };
  readonly limitations: string[];
}

export interface OcrHandle {
  readonly id: string;
  readonly documentSha256: string;
  readonly generation: number;
  readonly openedAt: number;
  readonly model: ModelPreparation;
}

export interface OcrReaderHooks {
  readonly onProgress?: (event: {
    readonly checkId: string | null;
    readonly status: string;
    readonly progress: number;
  }) => void;
  readonly onModelState?: (state: ModelState) => void;
  readonly onError?: (detail: string) => void;
  readonly fetchImpl?: typeof fetch;
  readonly idbFactory?: IDBFactory | null;
  readonly online?: () => boolean;
  readonly now?: () => number;
}

export interface OcrReaderConfig {
  readonly engine: TesseractEngineModule;
  /** npm package version string, e.g. '7.0.0'. */
  readonly engineVersion: string;
  /** Feature-detected core build label for the Reader.build record. */
  readonly coreBuild?: string;
  readonly model: ModelIdentity;
  readonly paths: EnginePaths;
  /**
   * SHA-256 digests (hex) of the staged assets this reader may load —
   * worker script, every feature-detected core variant, and the
   * traineddata — recorded verbatim in the ReaderManifest's
   * `asset_hashes` (I13).
   */
  readonly assetHashes: readonly string[];
  readonly profile: 'desktop' | 'mobile';
  readonly runKey: string;
  readonly rasterSource: RasterSource;
  readonly budget?: Partial<OcrBudget>;
  readonly hooks?: OcrReaderHooks;
}

const VALID_CHECK_ID = /^[a-z][a-z0-9_-]{0,95}$/;

/** Draw the crop region of a produced raster into a PNG Blob. */
async function cropToBlob(
  raster: PageRaster,
  plan: CropPlan,
): Promise<Blob> {
  const useOffscreen = typeof OffscreenCanvas !== 'undefined';
  const makeCanvas = (w: number, h: number): {
    canvas: OffscreenCanvas | HTMLCanvasElement;
    ctx: OffscreenCanvasRenderingContext2D | CanvasRenderingContext2D;
  } => {
    if (useOffscreen) {
      const canvas = new OffscreenCanvas(w, h);
      const ctx = canvas.getContext('2d');
      requireOcr(ctx !== null, OCR_REASON.RENDER_ERROR, 'no 2d context');
      return { canvas, ctx };
    }
    requireOcr(
      typeof document !== 'undefined',
      OCR_REASON.RENDER_ERROR,
      'no canvas implementation available',
    );
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    requireOcr(ctx !== null, OCR_REASON.RENDER_ERROR, 'no 2d context');
    return { canvas, ctx };
  };

  const { canvas, ctx } = makeCanvas(plan.outWidthPx, plan.outHeightPx);
  const image = raster.image;
  if (image instanceof ImageData) {
    const src = makeCanvas(image.width, image.height);
    src.ctx.putImageData(image, 0, 0);
    ctx.drawImage(
      src.canvas,
      plan.cropX,
      plan.cropY,
      plan.cropWidthPx,
      plan.cropHeightPx,
      0,
      0,
      plan.outWidthPx,
      plan.outHeightPx,
    );
  } else {
    ctx.drawImage(
      image as CanvasImageSource,
      plan.cropX,
      plan.cropY,
      plan.cropWidthPx,
      plan.cropHeightPx,
      0,
      0,
      plan.outWidthPx,
      plan.outHeightPx,
    );
  }
  if (useOffscreen) {
    return (canvas as OffscreenCanvas).convertToBlob({ type: 'image/png' });
  }
  const dom = canvas as HTMLCanvasElement;
  return new Promise((resolve, reject) => {
    dom.toBlob(
      (b) =>
        b === null
          ? reject(new OcrError(OCR_REASON.RENDER_ERROR, 'toBlob failed'))
          : resolve(b),
      'image/png',
    );
  });
}

/**
 * The browser OCR adapter. One instance serves one active profile on
 * one document generation; `close()` releases the worker (file
 * replacement always closes first).
 */
export class TesseractOcrReader {
  private readonly cfg: OcrReaderConfig;
  private readonly budget: OcrBudget;
  private readonly modelManager: ModelAssetManager;
  private worker: TesseractEngineWorker | null = null;
  private handle: OcrHandle | null = null;
  private closed = false;
  private workerInitCount = 0;
  private runOcrPixels = 0;
  private runOccurrences = 0;
  private runRawTextBytes = 0;
  private readonly selections = new Map<string, OcrSelection>();
  private readonly regionById = new Map<string, OcrRegionInput>();

  constructor(config: OcrReaderConfig) {
    this.cfg = config;
    this.budget = { ...DEFAULT_OCR_BUDGET, ...(config.budget ?? {}) };
    this.modelManager = new ModelAssetManager(config.model, {
      onState: (s) => config.hooks?.onModelState?.(s),
      ...(config.hooks?.fetchImpl !== undefined
        ? { fetchImpl: config.hooks.fetchImpl }
        : {}),
      ...(config.hooks?.idbFactory !== undefined
        ? { idbFactory: config.hooks.idbFactory }
        : {}),
      ...(config.hooks?.online !== undefined
        ? { online: config.hooks.online }
        : {}),
    });
  }

  private now(): number {
    return this.cfg.hooks?.now?.() ?? Date.now();
  }

  /** Model/asset state machine (distinct honest states). */
  get modelState(): ModelState {
    return this.modelManager.currentState;
  }

  /** Number of engine workers initialized in this handle's life. */
  get workerInits(): number {
    return this.workerInitCount;
  }

  /**
   * `describe()` — ReaderManifest for the page-profile reading.
   * The line-profile manifest is `describe('line')`.
   */
  describe(kind: 'page' | 'line' = 'page'): ReaderManifest {
    const reader = this.readerFor(kind === 'line' ? OCR_PSM.SINGLE_LINE : OCR_PSM.PAGE);
    return buildManifest(reader, this.cfg.assetHashes);
  }

  /**
   * Explicit model preparation (cold/download/cache/memory states).
   * Idempotent: verified in-memory bytes are reused without a
   * network or cache round-trip. Initialization failure surfaces
   * here — never as a fabricated page result.
   */
  async prepareModel(): Promise<ModelPreparation> {
    requireOcr(!this.closed, OCR_REASON.UNSUPPORTED, 'reader is closed');
    return (await this.modelManager.prepare()).preparation;
  }

  /**
   * "Remove downloaded OCR data": drops the persisted traineddata
   * cache slot and in-memory bytes. Static model caching may survive
   * Clear — removal is an explicit action only.
   */
  async removeModelData(): Promise<void> {
    await this.modelManager.remove();
  }

  private readerFor(psm: OcrPsm, raster?: PageRasterInfo): Reader {
    const input: ReaderIdentityInput = {
      engineVersion: this.cfg.engineVersion,
      coreBuild: this.cfg.coreBuild ?? 'lstm',
      model: this.cfg.model,
      renderReaderId: raster?.renderReaderId ?? 'unbound',
      rasterDpi: Math.round((raster?.scalePxPerPt ?? 0) * 72),
      psm,
      profile: this.cfg.profile,
      limitations: [],
    };
    return buildReader(input);
  }

  /** Contract CheckPlan reader id for one selection purpose. */
  private planReaderId(purpose: OcrSelection['purpose']): string {
    const psm = purpose === 'line' ? OCR_PSM.SINGLE_LINE : OCR_PSM.PAGE;
    return ocrReaderId({
      profile: this.cfg.profile,
      psm,
      renderReaderId: 'pending',
    });
  }

  /**
   * `open()` — prepare the verified model and initialize the single
   * reusable engine worker for this handle. Initialization failure is
   * a terminal state of the *handle*, never a fabricated reading.
   */
  async open(input: {
    readonly documentSha256: string;
    readonly generation: number;
  }): Promise<OcrHandle> {
    requireOcr(!this.closed, OCR_REASON.UNSUPPORTED, 'reader is closed');
    const prepared = await this.modelManager.prepare();
    const handle: OcrHandle = {
      id: `ocrh_${input.generation}_${Math.floor(this.now())}`,
      documentSha256: input.documentSha256,
      generation: input.generation,
      openedAt: this.now(),
      model: prepared.preparation,
    };
    this.handle = handle;
    // A new run gets a fresh budget and plan set; a healthy worker
    // from the previous run may be reused (same-generation reuse is
    // allowed; file replacement terminates it via close()).
    this.runOcrPixels = 0;
    this.runOccurrences = 0;
    this.runRawTextBytes = 0;
    this.selections.clear();
    this.regionById.clear();
    await this.ensureWorker();
    return handle;
  }

  /** One reusable initialized model per active profile. */
  private async ensureWorker(): Promise<TesseractEngineWorker> {
    if (this.worker !== null) return this.worker;
    try {
      this.worker = await createEngineWorker({
        engine: this.cfg.engine,
        lang: this.cfg.model.lang,
        paths: this.cfg.paths,
        onProgress: (e) =>
          this.cfg.hooks?.onProgress?.({
            checkId: null,
            status: e.status,
            progress: e.progress,
          }),
        onError: (d) => this.cfg.hooks?.onError?.(d),
      });
      this.workerInitCount++;
      return this.worker;
    } catch (error) {
      const { reason, detail } = classifyError(error, OCR_REASON.INIT_CRASH);
      throw new OcrError(reason, `OCR worker init: ${detail}`);
    }
  }

  private async destroyWorker(): Promise<void> {
    const w = this.worker;
    this.worker = null;
    if (w !== null) {
      try {
        await w.terminate();
      } catch {
        // Termination is best-effort; the worker is gone either way.
      }
    }
  }

  /** `pages()` — supported geometry metadata comes from the renderer. */
  pages(): { supported: true; note: string } {
    return {
      supported: true,
      note: 'OCR consumes rasters produced by the named render reader',
    };
  }

  /**
   * `plan()` — one OCR CheckPlan per explicit selection. `line`
   * selections get the PSM-7 reader identity; page/region get PSM-6.
   */
  plan(
    handle: OcrHandle,
    selections: readonly OcrSelection[],
  ): CheckPlan[] {
    requireOcr(
      this.handle !== null && this.handle.id === handle.id,
      OCR_REASON.UNSUPPORTED,
      'plan() requires this reader’s open handle',
    );
    const checks: CheckPlan[] = [];
    for (const [i, sel] of selections.entries()) {
      requireOcr(
        Number.isInteger(sel.pageIndex) && sel.pageIndex >= 0,
        OCR_REASON.GEOMETRY_UNAVAILABLE,
        'selection pageIndex must be a nonnegative integer',
      );
      const id = `ocr_${sel.pageIndex}_${i}`;
      requireOcr(VALID_CHECK_ID.test(id), OCR_REASON.UNSUPPORTED, `bad check id ${id}`);
      if (sel.region !== undefined && sel.region !== null) {
        this.regionById.set(sel.region.id, sel.region);
      }
      this.selections.set(id, sel);
      checks.push({
        id,
        page_index: sel.pageIndex,
        reader_ids: [this.planReaderId(sel.purpose)],
        capability: 'ocr',
        region_id: sel.region?.id ?? null,
      });
    }
    return checks;
  }

  /** Resolve the selection + psm for a planned check. */
  private selectionFor(check: CheckPlan): {
    selection: OcrSelection;
    psm: OcrPsm;
    region: OcrRegionInput | null;
  } {
    const selection = this.selections.get(check.id) ?? {
      pageIndex: check.page_index,
      purpose: check.region_id === null ? 'page' : 'region',
      region: null,
    };
    const psm: OcrPsm = selection.purpose === 'line'
      ? OCR_PSM.SINGLE_LINE
      : OCR_PSM.PAGE;
    let region: OcrRegionInput | null = selection.region ?? null;
    if (region === null && check.region_id !== null) {
      region = this.regionById.get(check.region_id) ?? null;
      requireOcr(
        region !== null,
        OCR_REASON.GEOMETRY_UNAVAILABLE,
        `region ${check.region_id} was not registered in plan()`,
      );
    }
    return { selection, psm, region };
  }

  /**
   * `extract()` — run one planned OCR check to a terminal result.
   * Emits occurrences through `emitChunk` in <=256-item chunks and
   * returns the check's honest output record. Completed-empty is a
   * completed check with reason `unreadable_pixels`, never a failure.
   */
  async extract(
    handle: OcrHandle,
    check: CheckPlan,
    emitChunk: EmitChunk,
    cancellation?: AbortSignal | OcrCancellation | (() => boolean),
  ): Promise<OcrCheckOutput> {
    const cancel = cancellationOf(cancellation);
    const started = this.now();
    const emptyShell = (psmForRecord: OcrPsm): Omit<OcrCheckOutput, 'check'> => ({
      reader: this.readerFor(psmForRecord),
      engine: {
        name: 'tesseract.js' as const,
        packageVersion: this.cfg.engineVersion,
        reportedVersion: null,
        oem: null,
        psmReported: null,
        adapterVersion: '1.0.0' as const,
      },
      model: {
        id: this.cfg.model.id,
        version: this.cfg.model.version,
        sha256: this.cfg.model.sha256,
        state: this.modelState,
        provenance: this.handle?.model.provenance ?? null,
      },
      raster: {
        rasterId: 'unproduced',
        renderReaderId: 'unbound',
        scalePxPerPt: 0,
        widthPx: 0,
        heightPx: 0,
      },
      crop: {
        cropX: 0,
        cropY: 0,
        cropWidthPx: 0,
        cropHeightPx: 0,
        regionPx: null,
        paddingPx: 0,
        resizeK: 1,
        outWidthPx: 0,
        outHeightPx: 0,
        ocrId: `ocr_${check.id}`,
      },
      raw: { text: null, blocks: null },
      occurrences: [],
      transforms: [],
      diagnostics: {
        meanConfidence: null,
        lowConfidenceIds: [],
        wordCount: 0,
        emptyWords: 0,
        pixelsOcr: 0,
        runOcrPixelsTotal: this.runOcrPixels,
        downscaled: false,
        durationMs: this.now() - started,
        workerInitCount: this.workerInitCount,
        attempt: 0,
      },
      limitations: [],
    });
    let resolved: { psm: OcrPsm; region: OcrRegionInput | null };
    try {
      resolved = this.selectionFor(check);
    } catch (error) {
      const { reason } = classifyError(error, OCR_REASON.GEOMETRY_UNAVAILABLE);
      return {
        ...emptyShell(OCR_PSM.PAGE),
        check: {
          id: check.id,
          status: 'failed',
          reason,
          produced_occurrence_count: 0,
          retained_occurrence_ids: [],
        },
      };
    }
    const { psm, region } = resolved;
    const fail = (
      reason: OcrReason,
      extra?: Partial<OcrCheckOutput>,
    ): OcrCheckOutput => ({
      ...emptyShell(psm),
      ...extra,
      check: {
        id: check.id,
        status: reason === OCR_REASON.UNSUPPORTED ? 'unsupported'
        : reason === OCR_REASON.USER_CANCEL ? 'cancelled'
        : reason === OCR_REASON.TIMEOUT ? 'timeout'
        : 'failed',
        reason,
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
    });

    if (cancel.isCancelled()) {
      return fail(OCR_REASON.USER_CANCEL);
    }

    let attempt = 0;
    for (;;) {
      try {
        return await this.extractOnce(handle, check, psm, region,
          emitChunk, cancel, started, attempt);
      } catch (error) {
        const { reason, detail } = classifyError(error, OCR_REASON.WORKER_CRASH);
        if (reason === OCR_REASON.TIMEOUT || reason === OCR_REASON.USER_CANCEL) {
          await this.destroyWorker();
          return fail(reason);
        }
        const transient = reason === OCR_REASON.INIT_CRASH ||
          reason === OCR_REASON.WORKER_CRASH;
        if (transient && attempt < this.budget.maxRetries) {
          // One transient retry, fresh worker only (RUNTIME_LIFECYCLE).
          attempt++;
          await this.destroyWorker();
          continue;
        }
        if (transient) await this.destroyWorker();
        return fail(reason, { limitations: [`engine: ${detail.slice(0, 200)}`] });
      }
    }
  }

  /** One extraction attempt (retries are fresh executions). */
  private async extractOnce(
    handle: OcrHandle,
    check: CheckPlan,
    psm: OcrPsm,
    region: OcrRegionInput | null,
    emitChunk: EmitChunk,
    cancel: OcrCancellation,
    started: number,
    attempt: number,
  ): Promise<OcrCheckOutput> {
    requireOcr(
      this.handle !== null && this.handle.id === handle.id,
      OCR_REASON.UNSUPPORTED,
      'extract() requires this reader’s current handle',
    );
    // 1) Raster from the named render reader (render dependency).
    let raster: PageRaster;
    try {
      raster = await this.cfg.rasterSource(check.page_index);
    } catch (error) {
      throw new OcrError(
        OCR_REASON.RENDER_ERROR,
        `raster source failed for page ${check.page_index}: ` +
          `${error instanceof Error ? error.message : String(error)}`,
      );
    }
    requireOcr(
      raster.built.page.index === check.page_index,
      OCR_REASON.RENDER_ERROR,
      'raster source returned the wrong page',
    );
    if (cancel.isCancelled()) {
      throw new OcrError(OCR_REASON.USER_CANCEL, 'cancelled after raster');
    }

    // 2) Crop/resize plan through the recorded geometry chain.
    const plan = planCrop({
      page: raster.built.page,
      raster,
      checkId: check.id,
      region,
      bounds: {
        maxRasterPixels: this.budget.maxRasterPixels,
        maxRasterEdge: this.budget.maxRasterEdge,
      },
    });

    // 3) Bounded run accounting before pixels reach the engine.
    const pixelsOcr = plan.outWidthPx * plan.outHeightPx;
    if (this.runOcrPixels + pixelsOcr > this.budget.maxRunOcrPixels) {
      throw new OcrError(
        OCR_REASON.RESOURCE_LIMIT,
        `run OCR pixel budget ${this.budget.maxRunOcrPixels} exceeded ` +
          `(${this.runOcrPixels}+${pixelsOcr})`,
      );
    }
    this.runOcrPixels += pixelsOcr;

    // 4) Crop to an owned PNG blob (no external image URLs, ever).
    const blob = await cropToBlob(raster, plan);

    // 5) Recognize with the recorded PSM; bounded by the check deadline.
    const worker = await this.ensureWorker();
    const result = await this.withDeadline(
      worker.recognize(
        blob,
        { tessedit_pageseg_mode: psm },
        { text: true, blocks: true },
        `j_${check.id}_${attempt}`,
      ),
      this.budget.checkTimeoutMs,
      cancel,
    );
    const data = result.data;
    if (cancel.isCancelled()) {
      throw new OcrError(OCR_REASON.USER_CANCEL, 'cancelled after recognize');
    }

    // 6) Missing blocks = capability failure, never fabricated boxes.
    requireOcr(
      data.blocks !== null && data.blocks !== undefined,
      OCR_REASON.BLOCKS_UNAVAILABLE,
      'engine returned no blocks hierarchy',
    );

    // 7) Raw hierarchy -> contract occurrences through O->canonical.
    const mapped = mapEngineBlocks({
      built: raster.built,
      plan,
      blocks: data.blocks,
      readerId: ocrReaderId({
        profile: this.cfg.profile,
        psm,
        renderReaderId: raster.renderReaderId,
      }),
      runKey: this.cfg.runKey,
      pageIndex: check.page_index,
      maxOccurrences: this.budget.maxOccurrencesPerPage,
    });
    const rawText = typeof data.text === 'string' ? data.text : null;
    const rawBytes = rawText === null ? 0 : rawText.length;
    if (
      this.runOccurrences + mapped.occurrences.length >
        this.budget.maxOccurrencesPerRun ||
      this.runRawTextBytes + rawBytes > this.budget.maxRawTextBytesPerRun
    ) {
      throw new OcrError(
        OCR_REASON.RESOURCE_LIMIT,
        'run occurrence/raw-text budget exceeded',
      );
    }
    this.runOccurrences += mapped.occurrences.length;
    this.runRawTextBytes += rawBytes;

    // 8) Bounded emission.
    for (let i = 0; i < mapped.occurrences.length; i += MAX_CHUNK_OCCURRENCES) {
      emitChunk(check.id, mapped.occurrences.slice(i, i + MAX_CHUNK_OCCURRENCES));
    }
    if (cancel.isCancelled()) {
      throw new OcrError(OCR_REASON.USER_CANCEL, 'cancelled after emit');
    }

    const ids = mapped.occurrences.map((o) => o.id);
    const confidence = meanWordConfidence(data.blocks);
    const completedEmpty = mapped.occurrences.length === 0;
    const limitations = [...plan.limitations];
    if (completedEmpty) {
      limitations.push(
        'unreadable_pixels: engine completed but produced no words',
      );
    }
    const reader = this.readerFor(psm, raster);
    const checkResult: CheckResult = {
      id: check.id,
      status: 'completed',
      // completed-empty is honest `unreadable_pixels` evidence, not a
      // failure and never a retry candidate.
      reason: completedEmpty ? OCR_REASON.UNREADABLE_PIXELS : null,
      produced_occurrence_count: mapped.occurrences.length,
      retained_occurrence_ids: ids,
    };
    return {
      check: checkResult,
      reader,
      engine: {
        name: 'tesseract.js',
        packageVersion: this.cfg.engineVersion,
        reportedVersion: data.version ?? null,
        oem: data.oem ?? null,
        psmReported: data.psm ?? null,
        adapterVersion: '1.0.0',
      },
      model: {
        id: this.cfg.model.id,
        version: this.cfg.model.version,
        sha256: this.cfg.model.sha256,
        state: this.modelState,
        provenance: this.handle?.model.provenance ?? null,
      },
      raster: {
        rasterId: raster.rasterId,
        renderReaderId: raster.renderReaderId,
        scalePxPerPt: raster.scalePxPerPt,
        widthPx: raster.widthPx,
        heightPx: raster.heightPx,
      },
      crop: {
        cropX: plan.cropX,
        cropY: plan.cropY,
        cropWidthPx: plan.cropWidthPx,
        cropHeightPx: plan.cropHeightPx,
        regionPx: plan.regionPx,
        paddingPx: plan.paddingPx,
        resizeK: plan.resizeK,
        outWidthPx: plan.outWidthPx,
        outHeightPx: plan.outHeightPx,
        ocrId: plan.ocrId,
      },
      raw: { text: rawText, blocks: data.blocks },
      occurrences: mapped.occurrences,
      transforms: plan.transforms,
      diagnostics: {
        meanConfidence: confidence.mean,
        lowConfidenceIds: mapped.lowConfidenceIds,
        wordCount: mapped.wordCount,
        emptyWords: mapped.emptyWords,
        pixelsOcr,
        runOcrPixelsTotal: this.runOcrPixels,
        downscaled: plan.resizeK < 1,
        durationMs: this.now() - started,
        workerInitCount: this.workerInitCount,
        attempt,
      },
      limitations,
    };
  }

  /** Deadline + cancellation around an engine promise. */
  private async withDeadline<T>(
    work: Promise<T>,
    timeoutMs: number,
    cancel: OcrCancellation,
  ): Promise<T> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let poll: ReturnType<typeof setInterval> | undefined;
    try {
      return await new Promise<T>((resolve, reject) => {
        timer = setTimeout(
          () => reject(new OcrError(OCR_REASON.TIMEOUT, `check deadline ${timeoutMs}ms`)),
          timeoutMs,
        );
        poll = setInterval(() => {
          if (cancel.isCancelled()) {
            reject(new OcrError(OCR_REASON.USER_CANCEL, 'cancelled'));
          }
        }, 25);
        work.then(resolve, reject);
      });
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      if (poll !== undefined) clearInterval(poll);
    }
  }

  /** `close()` — terminate the worker and release the handle. */
  async close(handle?: OcrHandle): Promise<void> {
    if (handle !== undefined && this.handle?.id !== handle.id) {
      return; // a stale handle cannot close a newer generation's worker
    }
    await this.destroyWorker();
    this.handle = null;
    this.closed = true;
  }
}
