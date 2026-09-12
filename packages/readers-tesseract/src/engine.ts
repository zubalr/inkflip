/**
 * Injected OCR engine seam (T10).
 *
 * `@inkflip/readers-tesseract` declares no runtime dependency on
 * tesseract.js: the resolved package is an `apps/web` dependency
 * frozen in bun.lock by T02, and the adapter receives the concrete
 * module (`import Tesseract from 'tesseract.js'`) from its caller.
 * This keeps the contract-honest wiring — `createWorker(
 * [{ code:'eng', data:<verified bytes> }], OEM.LSTM_ONLY, { workerPath,
 * corePath, langPath, gzip:false, workerBlobURL:false,
 * cacheMethod:'none', signal, logger })` — inside the adapter while
 * the library itself stays an app-owned dependency.
 *
 * The worker options below are the entire reason the adapter exists:
 * explicit same-origin staged paths and `workerBlobURL:false` so no
 * default CDN URL (jsdelivr worker/core/lang fallbacks baked into
 * tesseract.js defaults) can ever be constructed.
 */

/** Subset of tesseract.js LoggerMessage the adapter emits upstream. */
export interface EngineProgress {
  /** Engine stage label, e.g. 'loading tesseract core'. */
  readonly status: string;
  /** 0..1 within the stage; may be absent/indeterminate upstream. */
  readonly progress: number;
  /**
   * The adapter's own job id for recognize-scoped progress (the
   * `j_<check>_<attempt>` value posted with the job); init-stage
   * progress carries upstream's internal job ids. Used by the reader
   * to drop events belonging to superseded operations.
   */
  readonly userJobId?: string | null;
}

/** The recognize() result page shape used by the adapter. */
export interface EngineRecognizePage {
  readonly text: string | null;
  /** Raw GetJSONText hierarchy: blocks[].paragraphs[].lines[].words[]. */
  readonly blocks: EngineBlock[] | null;
  readonly confidence: number | null;
  /** Engine-reported identities (enum names as strings). */
  readonly psm: string | null;
  readonly oem: string | null;
  readonly version: string | null;
  readonly rotateRadians?: number | null;
}

export interface EngineBlock {
  readonly paragraphs?: EngineParagraph[] | null;
  readonly text?: string;
  readonly confidence?: number;
  readonly bbox?: EngineBBox;
  readonly blocktype?: string;
}
export interface EngineParagraph {
  readonly lines?: EngineLine[] | null;
  readonly text?: string;
  readonly confidence?: number;
  readonly bbox?: EngineBBox;
}
export interface EngineLine {
  readonly words?: EngineWord[] | null;
  readonly text?: string;
  readonly confidence?: number;
  readonly bbox?: EngineBBox;
  readonly baseline?: { x0: number; y0: number; x1: number; y1: number };
}
export interface EngineWord {
  readonly text?: string;
  readonly confidence?: number;
  readonly bbox?: EngineBBox;
  readonly font_name?: string;
  readonly symbols?: unknown;
  readonly choices?: unknown;
}
export interface EngineBBox {
  readonly x0: number;
  readonly y0: number;
  readonly x1: number;
  readonly y1: number;
}

/** The tesseract.js Worker surface the adapter uses. */
export interface TesseractEngineWorker {
  /**
   * The input port accepts PREPARED `Uint8Array` PNG bytes only. The
   * adapter materializes the crop blob via `arrayBuffer()` inside the
   * operation deadline before calling — never pass a URL/string/Blob/
   * canvas: upstream's `loadImage` would take an asynchronous loader
   * path (fetch/FileReader) that sits outside the operation's
   * deadline/cancellation scope.
   */
  recognize(
    image: Uint8Array,
    options: Record<string, unknown>,
    output: Record<string, boolean>,
    jobId?: string,
  ): Promise<{ jobId: string; data: EngineRecognizePage }>;
  terminate(jobId?: string): Promise<unknown>;
}

/**
 * The tesseract.js v7 `Lang` object payload (`{ code, data }`).
 *
 * On the pinned+patched 7.0.0 worker this shape delivers the verified
 * model bytes directly: `loadLanguage` writes `data` verbatim as
 * `${code}.traineddata` into the worker filesystem (object payloads
 * have no fetch branch), and the pdf-q38-patched `initialize` job
 * maps each payload to `code` for the Init() language name. With
 * `cacheMethod:'none'` the worker never touches the shared idb-keyval
 * cache at all — the adapter-verified bytes ARE the engine input, so
 * no same-origin cache write can ever change what Init() consumes.
 */
export interface EngineLangPayload {
  /** Engine language code, e.g. 'eng' — also the Init() lang name. */
  readonly code: string;
  /**
   * The SHA-256-verified traineddata bytes, snapshotted by
   * `createEngineWorker` — the actual engine input.
   */
  readonly data: Uint8Array;
}

/**
 * Structural match for the tesseract.js module namespace. The
 * concrete module from apps/web's locked dependency satisfies this;
 * tests inject the real staged build.
 */
export interface TesseractEngineModule {
  createWorker(
    langs: string | readonly string[] | readonly EngineLangPayload[],
    oem: number,
    options: Record<string, unknown>,
    config?: unknown,
  ): Promise<TesseractEngineWorker>;
  readonly OEM: { readonly LSTM_ONLY: number };
  readonly PSM: Record<string, string>;
}

/** Explicit same-origin worker configuration (no defaults). */
export interface EnginePaths {
  /** e.g. `/assets/tesseract/7.0.0/worker.min.js`. */
  readonly workerPath: string;
  /** e.g. `/assets/tesseract-core/7.0.0/` (feature-detected dir). */
  readonly corePath: string;
  /** e.g. `/models/tessdata-fast-eng/7d4322bd/`. */
  readonly langPath: string;
  /**
   * tesseract.js `cachePath` prefix for the traineddata cache key the
   * adapter pre-seeds with verified bytes (default 'inkflip/models').
   */
  readonly cachePath: string;
}

export interface CreateEngineWorkerInput {
  readonly engine: TesseractEngineModule;
  readonly lang: string;
  readonly paths: EnginePaths;
  /**
   * The adapter-verified traineddata bytes (SHA-256 checked against
   * the frozen manifest at preparation). A snapshot copy is handed to
   * the engine — it is the only model channel the worker uses.
   */
  readonly modelBytes: Uint8Array;
  /**
   * Concrete-lifetime abort for THIS worker. The pdf-ebz-patched
   * tesseract.js@7.0.0 `WorkerOptions.signal`: observed before spawn
   * and for the worker's whole life — aborting synchronously
   * terminates the real raw worker and rejects pending
   * readiness/jobs with `signal.reason`.
   */
  readonly signal?: AbortSignal;
  /** Bounded stage/progress reporter — stage codes only. */
  readonly onProgress?: (event: EngineProgress) => void;
  /** Raw engine errors for local diagnostics (path-stripped). */
  readonly onError?: (detail: string) => void;
}

/**
 * `createWorker([{code, data}], OEM.LSTM_ONLY, options)` with the
 * contract's explicit local configuration:
 *
 * - `workerPath`/`corePath`/`langPath` point at staged same-origin
 *   assets — never the baked-in jsdelivr defaults;
 * - `gzip:false` — the staged eng.traineddata is uncompressed;
 * - `workerBlobURL:false` — the worker script loads from its real
 *   same-origin URL, not an opaque blob indirection;
 * - `langs` is the v7 `Lang` payload `[{code, data}]` — NOT a
 *   language string. A SNAPSHOT of `input.modelBytes` is placed in
 *   `data`: the patched worker writes those bytes verbatim to
 *   `./eng.traineddata` (object payloads have no fetch branch) and
 *   the q38-patched `initialize` job sends `code` as the Init
 *   language name. The engine input is exactly the adapter-verified
 *   payload — not a shared cache slot another writer could race.
 * - `cacheMethod:'none'` — the worker performs no cache read or
 *   write; the adapter's own verified cache (model-cache.ts) is a
 *   warm-start store for future preparations only.
 * - `signal` (pdf-ebz patched `WorkerOptions.signal`) owns this
 *   worker's concrete lifetime: abort hard-terminates the raw worker
 *   and rejects readiness/pending jobs even mid-initialization.
 * - `logger` forwards only bounded stage/progress codes.
 */
export function createEngineWorker(
  input: CreateEngineWorkerInput,
): Promise<TesseractEngineWorker> {
  const { engine, lang, paths } = input;
  // Snapshot: later mutation of the adapter's in-memory copy can never
  // alter the bytes already committed to this engine boundary.
  const langs: readonly EngineLangPayload[] = [
    { code: lang, data: input.modelBytes.slice() },
  ];
  return engine.createWorker(langs, engine.OEM.LSTM_ONLY, {
    workerPath: paths.workerPath,
    corePath: paths.corePath,
    langPath: paths.langPath,
    cachePath: paths.cachePath,
    gzip: false,
    workerBlobURL: false,
    cacheMethod: 'none',
    ...(input.signal !== undefined ? { signal: input.signal } : {}),
    logger: (m: { status?: unknown; progress?: unknown; userJobId?: unknown }) => {
      if (typeof m?.status === 'string' && typeof m?.progress === 'number') {
        input.onProgress?.({
          status: m.status,
          progress: m.progress,
          userJobId: typeof m.userJobId === 'string' ? m.userJobId : null,
        });
      }
    },
    errorHandler: (detail: unknown) => {
      input.onError?.(
        typeof detail === 'string' ? detail : String(detail ?? 'engine error'),
      );
    },
  });
}

/** Engine PSM enum values for the two supported check kinds. */
export const OCR_PSM = {
  /** Full selected page — PSM 6 (single uniform block). */
  PAGE: '6',
  /** Deliberately single-line user region — PSM 7. */
  SINGLE_LINE: '7',
} as const;
export type OcrPsm = (typeof OCR_PSM)[keyof typeof OCR_PSM];
