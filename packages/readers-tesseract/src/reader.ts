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
  Transform,
} from '../../contracts/src/index.ts';
import type { BuiltPage } from '../../geometry/src/index.ts';
import {
  createEngineWorker,
  OCR_PSM,
  type EnginePaths,
  type EngineProgress,
  type EngineRecognizePage,
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
  /** Per-run raw-text byte cap (8_388_608) — UTF-8 bytes. */
  readonly maxRawTextBytesPerRun: number;
  /**
   * One absolute wall deadline covering the WHOLE check operation —
   * raster acquisition, crop/encode, engine init (if needed) and
   * recognize including the single transient retry (30_000). A retry
   * only ever receives the time remaining.
   */
  readonly checkTimeoutMs: number;
  /**
   * Bounded lifetime for `open()` — model preparation plus eager
   * worker initialization (30_000).
   */
  readonly openTimeoutMs: number;
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
  openTimeoutMs: 30_000,
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
    /** Fractional-destination clipping, output px [right, bottom]. */
    readonly resizeClipPx: readonly [number, number];
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
   * Reader id of the named render reader this OCR reading consumes.
   * Required and validated up front (`^[a-z0-9_-]{1,60}$`): it is bound
   * into describe()/plan()/output/occurrence identity BEFORE any
   * CheckPlan is finalized, so the immutable plan never carries a
   * pending placeholder. Every raster supplied by `rasterSource` must
   * carry this exact `renderReaderId` — a mismatch is a typed
   * `render_error`, not a silently re-identified reading.
   */
  readonly renderReaderId: string;
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
/**
 * A configured render reader id must already be in reader-id
 * namespace form — the same alphabet `ocrReaderId` emits — so the
 * bound identity is faithful and the composed reader id stays under
 * the 96-char id limit untruncated.
 */
const VALID_RENDER_READER_ID = /^[a-z0-9_-]{1,60}$/;

/** UTF-8 byte accounting for the raw-text run budget. */
const utf8 = new TextEncoder();

/**
 * One operation's absolute deadline + cancellation scope. `handle` is
 * set once the handle being opened exists (open()); every guarded
 * await checks cancellation, the absolute deadline, reader closure,
 * operation supersession and handle validity.
 */
interface OpScope {
  readonly op: number;
  readonly deadlineAt: number;
  readonly cancel: OcrCancellation;
  handle: OcrHandle | null;
}

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
  // Canvas image smoothing stays at the production default (true);
  // there is deliberately no public knob — the recorded resize factor
  // is the real drawn factor under the browser's own smoothing.
  const image = raster.image;
  // The recorded ocr_resize factor IS the real destination scale: the
  // source crop is drawn to crop*resizeK x crop*resizeK output pixels
  // (fractional) on the integer canvas, which clips the sub-pixel
  // right/bottom remainder — the same mapping the transform records.
  const destW = plan.cropWidthPx * plan.resizeK;
  const destH = plan.cropHeightPx * plan.resizeK;
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
      destW,
      destH,
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
      destW,
      destH,
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
  /** Concrete-lifetime controller for `this.worker` (engine signal). */
  private workerCtl: AbortController | null = null;
  /** A worker init in flight — joined, never overlapped. */
  private workerInit: Promise<TesseractEngineWorker> | null = null;
  /**
   * Concrete-lifetime controller for the in-flight init. Reachable
   * from destroyWorker() so close()/deadline aborts the real raw
   * worker even before install — the signal covers the worker's
   * entire life, including constructor readiness.
   */
  private workerInitCtl: AbortController | null = null;
  private handle: OcrHandle | null = null;
  private closed = false;
  /** Monotonic current-operation token; a newer op supersedes older. */
  private opSeq = 0;
  /** Engine jobId -> owning op, for progress attribution. */
  private readonly jobOps = new Map<string, number>();
  private workerInitCount = 0;
  private runOcrPixels = 0;
  private runOccurrences = 0;
  private runRawTextBytes = 0;
  private readonly selections = new Map<string, OcrSelection>();
  private readonly regionById = new Map<string, OcrRegionInput>();

  constructor(config: OcrReaderConfig) {
    this.cfg = config;
    this.budget = { ...DEFAULT_OCR_BUDGET, ...config.budget };
    requireOcr(
      VALID_RENDER_READER_ID.test(config.renderReaderId),
      OCR_REASON.UNSUPPORTED,
      `renderReaderId must match ${VALID_RENDER_READER_ID} ` +
        `(got ${JSON.stringify(config.renderReaderId)})`,
    );
    requireOcr(
      config.paths.cachePath === config.model.cachePath,
      OCR_REASON.UNSUPPORTED,
      'paths.cachePath and model.cachePath must agree: the engine ' +
        'consumes the adapter-verified cache slot by construction ' +
        `(${JSON.stringify(config.paths.cachePath)} != ` +
        `${JSON.stringify(config.model.cachePath)})`,
    );
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
   * here — never as a fabricated page result. Bounded by
   * `openTimeoutMs` like every async step this reader owns.
   */
  async prepareModel(): Promise<ModelPreparation> {
    requireOcr(!this.closed, OCR_REASON.UNSUPPORTED, 'reader is closed');
    const scope: OpScope = {
      op: this.opSeq,
      deadlineAt: this.now() + this.budget.openTimeoutMs,
      cancel: cancellationOf(undefined),
      handle: null,
    };
    return (
      await this.withDeadline(this.modelManager.prepare(), scope)
    ).preparation;
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
      // The configured render reader id is bound at construction —
      // never a pending placeholder and never rewritten per call.
      renderReaderId: this.cfg.renderReaderId,
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
      renderReaderId: this.cfg.renderReaderId,
    });
  }

  /**
   * `open()` — prepare the verified model and initialize the single
   * reusable engine worker for this handle, under one bounded
   * cancellation lifetime (`openTimeoutMs`): model preparation and
   * eager worker init share the deadline and the caller's
   * cancellation. Initialization failure is a terminal state of the
   * *handle*, never a fabricated reading.
   */
  async open(input: {
    readonly documentSha256: string;
    readonly generation: number;
    readonly cancellation?: AbortSignal | OcrCancellation | (() => boolean);
  }): Promise<OcrHandle> {
    requireOcr(!this.closed, OCR_REASON.UNSUPPORTED, 'reader is closed');
    const op = ++this.opSeq;
    const scope: OpScope = {
      op,
      deadlineAt: this.now() + this.budget.openTimeoutMs,
      cancel: cancellationOf(input.cancellation),
      handle: null,
    };
    try {
      const prepared = await this.withDeadline(
        this.modelManager.prepare(),
        scope,
      );
      this.guard(scope);
      const handle: OcrHandle = {
        id: `ocrh_${input.generation}_${Math.floor(this.now())}`,
        documentSha256: input.documentSha256,
        generation: input.generation,
        openedAt: this.now(),
        model: prepared.preparation,
      };
      // Install before worker init so staleness guards can see it.
      this.handle = handle;
      scope.handle = handle;
      // A new run gets a fresh budget and plan set; a healthy worker
      // from the previous run may be reused (same-generation reuse is
      // allowed; file replacement terminates it via close()).
      this.runOcrPixels = 0;
      this.runOccurrences = 0;
      this.runRawTextBytes = 0;
      this.selections.clear();
      this.regionById.clear();
      await this.ensureWorker(scope);
      this.guard(scope);
      return handle;
    } catch (error) {
      const { reason, detail } = classifyError(error, OCR_REASON.INIT_CRASH);
      // The failed open must not leave a half-usable handle or worker.
      this.handle = null;
      await this.destroyWorker();
      throw new OcrError(reason, `OCR open: ${detail}`);
    }
  }

  /**
   * Terminal-status guard: throws a typed reason once the operation
   * is cancelled, past its absolute deadline, superseded by a newer
   * operation, or detached from the live handle. Called after every
   * awaited step and before installing workers, starting recognition,
   * publishing progress, changing accounting, or emitting.
   */
  private guard(scope: OpScope): void {
    if (scope.cancel.isCancelled()) {
      throw new OcrError(OCR_REASON.USER_CANCEL, 'cancelled');
    }
    if (this.now() >= scope.deadlineAt) {
      throw new OcrError(OCR_REASON.TIMEOUT, 'operation deadline reached');
    }
    if (this.closed) {
      throw new OcrError(OCR_REASON.USER_CANCEL, 'reader closed');
    }
    if (this.opSeq !== scope.op) {
      throw new OcrError(OCR_REASON.USER_CANCEL, 'operation superseded');
    }
    if (scope.handle !== null && this.handle?.id !== scope.handle.id) {
      throw new OcrError(OCR_REASON.USER_CANCEL, 'handle superseded');
    }
  }

  /** Milliseconds left on the operation's absolute deadline. */
  private remaining(scope: OpScope): number {
    return scope.deadlineAt - this.now();
  }

  /**
   * Race one external await against the operation's absolute deadline
   * and cancellation poll. The work promise keeps its handlers
   * registered after losing, so a late settlement is consumed — never
   * an unhandled rejection — while its result is dropped by the
   * caller's next guard.
   */
  private async withDeadline<T>(
    work: Promise<T>,
    scope: OpScope,
  ): Promise<T> {
    this.guard(scope);
    const ms = this.remaining(scope);
    let timer: ReturnType<typeof setTimeout> | undefined;
    let poll: ReturnType<typeof setInterval> | undefined;
    try {
      return await new Promise<T>((resolve, reject) => {
        timer = setTimeout(
          () =>
            reject(
              new OcrError(
                OCR_REASON.TIMEOUT,
                `operation deadline ${scope.deadlineAt}`,
              ),
            ),
          ms,
        );
        poll = setInterval(() => {
          if (scope.cancel.isCancelled()) {
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

  /**
   * Worker-level progress is published only while its owning
   * operation is still current: recognize progress carries our jobId
   * (jobOps), init progress belongs to the op that created the
   * worker; events from superseded ops or a closed reader are
   * dropped.
   */
  private forwardProgress(e: EngineProgress, creatingOp: number): void {
    if (this.closed) return;
    const jobOp = typeof e.userJobId === 'string'
      ? this.jobOps.get(e.userJobId)
      : undefined;
    const owner = jobOp ?? creatingOp;
    if (owner !== this.opSeq) return;
    this.cfg.hooks?.onProgress?.({
      checkId: null,
      status: e.status,
      progress: e.progress,
    });
  }

  /** One reusable initialized model per active profile. */
  private async ensureWorker(scope: OpScope): Promise<TesseractEngineWorker> {
    if (this.worker !== null) return this.worker;
    this.guard(scope);
    if (this.workerInit !== null) {
      // An init already owns this slot — join it rather than start an
      // overlapping initialization.
      const joined = await this.withDeadline(this.workerInit, scope);
      this.guard(scope);
      return joined;
    }
    const ctl = new AbortController();
    const creatingOp = scope.op;
    this.workerInitCtl = ctl;
    const init = (async (): Promise<TesseractEngineWorker> => {
      // Engine-boundary gate first: the worker-readable cache slot
      // must already hold the verified payload — the engine's only
      // model channel — before any worker exists.
      await this.withDeadline(this.modelManager.prepareForEngine(), scope);
      return createEngineWorker({
        engine: this.cfg.engine,
        lang: this.cfg.model.lang,
        paths: this.cfg.paths,
        signal: ctl.signal,
        onProgress: (e) => this.forwardProgress(e, creatingOp),
        onError: (d) => this.cfg.hooks?.onError?.(d),
      });
    })();
    this.workerInit = init;
    try {
      const worker = await this.withDeadline(init, scope);
      // Reject the stale install: if this op was superseded, closed or
      // re-deadlined while the worker was initializing, the fresh
      // worker is terminated by the catch below instead of installed.
      this.guard(scope);
      requireOcr(
        this.worker === null,
        OCR_REASON.WORKER_CRASH,
        'worker slot occupied during init',
      );
      this.worker = worker;
      this.workerCtl = ctl;
      this.workerInit = null;
      this.workerInitCtl = null;
      this.workerInitCount++;
      return worker;
    } catch (error) {
      if (this.workerInit === init) this.workerInit = null;
      if (this.workerInitCtl === ctl) this.workerInitCtl = null;
      const { reason, detail } = classifyError(error, OCR_REASON.INIT_CRASH);
      if (!ctl.signal.aborted) {
        ctl.abort(error instanceof OcrError ? error : new OcrError(reason, detail));
      }
      // Own the init promise to settlement: a late success terminates
      // its own worker (never a newer one); a late rejection is
      // consumed here.
      init.then(
        (late) => {
          void late.terminate();
        },
        () => {},
      );
      throw new OcrError(reason, `OCR worker init: ${detail}`);
    }
  }

  private async destroyWorker(): Promise<void> {
    const w = this.worker;
    const ctl = this.workerCtl;
    const init = this.workerInit;
    const initCtl = this.workerInitCtl;
    // Invalidate admission before cleanup settles.
    this.worker = null;
    this.workerCtl = null;
    this.workerInit = null;
    this.workerInitCtl = null;
    // Abort the concrete lifetimes FIRST — an in-flight init's raw
    // worker is hard-terminated by the patched engine even before the
    // promise settles; an installed worker's signal does the same.
    if (initCtl !== null && !initCtl.signal.aborted) {
      initCtl.abort(
        new OcrError(OCR_REASON.WORKER_CRASH, 'worker terminated'),
      );
    }
    if (ctl !== null && !ctl.signal.aborted) {
      ctl.abort(
        new OcrError(OCR_REASON.WORKER_CRASH, 'worker terminated'),
      );
    }
    if (init !== null) {
      // A still-pending init resolves late at best — its worker must
      // terminate itself without touching a newer one; rejections are
      // consumed so nothing escapes unhandled.
      init.then(
        (late) => {
          void late.terminate();
        },
        () => {},
      );
    }
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
    const op = ++this.opSeq;
    const started = this.now();
    // ONE absolute deadline scopes the whole operation: raster
    // acquisition, crop encode, engine init, recognize, and the single
    // transient retry all draw from it — a retry receives only the
    // remaining budget, never a fresh full timeout.
    const scope: OpScope = {
      op,
      deadlineAt: started + this.budget.checkTimeoutMs,
      cancel,
      handle,
    };
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
        resizeClipPx: [0, 0],
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
          emitChunk, scope, started, attempt);
      } catch (error) {
        const { reason, detail } = classifyError(error, OCR_REASON.WORKER_CRASH);
        if (reason === OCR_REASON.TIMEOUT || reason === OCR_REASON.USER_CANCEL) {
          await this.destroyWorker();
          return fail(reason);
        }
        const transient = reason === OCR_REASON.INIT_CRASH ||
          reason === OCR_REASON.WORKER_CRASH;
        // A retry runs only inside the operation's remaining time.
        if (
          transient && attempt < this.budget.maxRetries &&
          this.remaining(scope) > 0
        ) {
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
    scope: OpScope,
    started: number,
    attempt: number,
  ): Promise<OcrCheckOutput> {
    requireOcr(
      this.handle !== null && this.handle.id === handle.id,
      OCR_REASON.UNSUPPORTED,
      'extract() requires this reader’s current handle',
    );
    this.guard(scope);
    // 1) Raster from the named render reader (render dependency) —
    //    bounded by the operation's absolute deadline; a stalled
    //    source returns on the deadline instead of parking forever.
    let raster: PageRaster;
    try {
      raster = await this.withDeadline(
        this.cfg.rasterSource(check.page_index),
        scope,
      );
    } catch (error) {
      if (error instanceof OcrError) throw error;
      throw new OcrError(
        OCR_REASON.RENDER_ERROR,
        `raster source failed for page ${check.page_index}: ` +
          `${error instanceof Error ? error.message : String(error)}`,
      );
    }
    this.guard(scope);
    requireOcr(
      raster.built.page.index === check.page_index,
      OCR_REASON.RENDER_ERROR,
      'raster source returned the wrong page',
    );
    // The produced raster must come from the render reader this
    // reading was configured for — anything else is a different
    // provenance and never silently re-identified.
    requireOcr(
      raster.renderReaderId === this.cfg.renderReaderId,
      OCR_REASON.RENDER_ERROR,
      `raster supplied by ${JSON.stringify(raster.renderReaderId)} ` +
        `but this reading is configured for ` +
        `${JSON.stringify(this.cfg.renderReaderId)}`,
    );

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
    this.guard(scope);
    this.runOcrPixels += pixelsOcr;

    // 4) Crop to owned PNG bytes (no external image URLs, ever). The
    //    blob encode and byte materialization are asynchronous stalls
    //    — both stay inside the operation's deadline. The engine
    //    input port accepts prepared Uint8Array bytes only.
    const blob = await this.withDeadline(cropToBlob(raster, plan), scope);
    this.guard(scope);
    const imageBytes = new Uint8Array(
      await this.withDeadline(blob.arrayBuffer(), scope),
    );
    this.guard(scope);
    // The produced PNG is bounded by the same raster pixel caps —
    // 4 bytes/px worst case plus container slack.
    const maxPngBytes = pixelsOcr * 4 + 65_536;
    requireOcr(
      imageBytes.byteLength <= maxPngBytes,
      OCR_REASON.RESOURCE_LIMIT,
      `encoded OCR input ${imageBytes.byteLength} exceeds bound ` +
        `${maxPngBytes} for ${pixelsOcr} px`,
    );

    // 5) Recognize with the recorded PSM under the same deadline.
    const worker = await this.ensureWorker(scope);
    this.guard(scope);
    const jobId = `j_${check.id}_${attempt}`;
    this.jobOps.set(jobId, scope.op);
    let result: { jobId: string; data: EngineRecognizePage };
    try {
      result = await this.withDeadline(
        worker.recognize(
          imageBytes,
          { tessedit_pageseg_mode: psm },
          { text: true, blocks: true },
          jobId,
        ),
        scope,
      );
    } finally {
      this.jobOps.delete(jobId);
    }
    this.guard(scope);
    const data = result.data;

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
        renderReaderId: this.cfg.renderReaderId,
      }),
      runKey: this.cfg.runKey,
      pageIndex: check.page_index,
      maxOccurrences: this.budget.maxOccurrencesPerPage,
    });
    const rawText = typeof data.text === 'string' ? data.text : null;
    // The raw-text run cap counts UTF-8 BYTES (TextEncoder), never
    // UTF-16 units — a multibyte string costs more than .length.
    const rawBytes = rawText === null ? 0 : utf8.encode(rawText).byteLength;
    this.guard(scope);
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

    // 8) Bounded emission — terminal-status guard before each chunk.
    for (let i = 0; i < mapped.occurrences.length; i += MAX_CHUNK_OCCURRENCES) {
      this.guard(scope);
      emitChunk(check.id, mapped.occurrences.slice(i, i + MAX_CHUNK_OCCURRENCES));
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
        resizeClipPx: plan.resizeClipPx,
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

  /** `close()` — terminate the worker and release the handle. */
  async close(handle?: OcrHandle): Promise<void> {
    if (handle !== undefined && this.handle?.id !== handle.id) {
      return; // a stale handle cannot close a newer generation's worker
    }
    // Invalidate admission before cleanup: any in-flight open/extract
    // continuation observes terminal status (closed + superseded op +
    // detached handle) before worker teardown settles.
    this.closed = true;
    this.opSeq++;
    this.handle = null;
    await this.destroyWorker();
  }
}
