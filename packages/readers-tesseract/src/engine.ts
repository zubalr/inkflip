/**
 * Injected OCR engine seam (T10).
 *
 * `@inkflip/readers-tesseract` declares no runtime dependency on
 * tesseract.js: the resolved package is an `apps/web` dependency
 * frozen in bun.lock by T02, and the adapter receives the concrete
 * module (`import Tesseract from 'tesseract.js'`) from its caller.
 * This keeps the contract-honest wiring — `createWorker(
 * [{ code:'eng', data:'eng' }], OEM.LSTM_ONLY, { workerPath, corePath,
 * langPath, gzip:false, workerBlobURL:false, cacheMethod:'readOnly',
 * logger })` — inside the adapter while the library itself stays an
 * app-owned dependency.
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
  recognize(
    image: unknown,
    options: Record<string, unknown>,
    output: Record<string, boolean>,
    jobId?: string,
  ): Promise<{ jobId: string; data: EngineRecognizePage }>;
  terminate(jobId?: string): Promise<unknown>;
}

/**
 * The tesseract.js v7 `Lang` object payload (`{ code, data }`).
 *
 * On the pinned 7.0.0 worker this shape has one non-obvious contract
 * (verified against `src/worker-script/index.js` empirically):
 * `loadLanguage` uses `code` for the traineddata file name and reads
 * `data` ONLY on a cache miss, while `initialize` maps each payload to
 * `payload.data` as the Init() language name. Supplying real bytes in
 * `data` is therefore misinterpreted as a language name and fails
 * initialization — the adapter passes `data === code` and delivers the
 * verified traineddata bytes through the pre-seeded cache slot (see
 * `createEngineWorker`).
 */
export interface EngineLangPayload {
  /** Engine language code, e.g. 'eng' — also the Init() lang name. */
  readonly code: string;
  /**
   * Cache-miss fallback content consumed by upstream `loadLanguage`.
   * Must equal `code` on pinned 7.0.0: a miss writes these bytes as
   * `${code}.traineddata`, so the language code itself is a 3-byte
   * poison payload that fails Init() honestly — a miss can never
   * silently become an unverified model download.
   */
  readonly data: string;
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
  /** Bounded stage/progress reporter — stage codes only. */
  readonly onProgress?: (event: EngineProgress) => void;
  /** Raw engine errors for local diagnostics (path-stripped). */
  readonly onError?: (detail: string) => void;
}

/**
 * `createWorker(lang, OEM.LSTM_ONLY, options)` with the contract's
 * explicit local configuration:
 *
 * - `workerPath`/`corePath`/`langPath` point at staged same-origin
 *   assets — never the baked-in jsdelivr defaults;
 * - `gzip:false` — the staged eng.traineddata is uncompressed;
 * - `workerBlobURL:false` — the worker script loads from its real
 *   same-origin URL, not an opaque blob indirection;
 * - `cacheMethod:'readOnly'` — the engine only *reads* the traineddata
 *   cache slot the adapter pre-seeded with SHA-256-verified bytes, so
 *   unverified bytes can never enter the model;
 * - `logger` forwards only bounded stage/progress codes.
 */
export function createEngineWorker(
  input: CreateEngineWorkerInput,
): Promise<TesseractEngineWorker> {
  const { engine, lang, paths } = input;
  return engine.createWorker(lang, engine.OEM.LSTM_ONLY, {
    workerPath: paths.workerPath,
    corePath: paths.corePath,
    langPath: paths.langPath,
    cachePath: paths.cachePath,
    gzip: false,
    workerBlobURL: false,
    cacheMethod: 'readOnly',
    logger: (m: { status?: unknown; progress?: unknown }) => {
      if (typeof m?.status === 'string' && typeof m?.progress === 'number') {
        input.onProgress?.({ status: m.status, progress: m.progress });
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
