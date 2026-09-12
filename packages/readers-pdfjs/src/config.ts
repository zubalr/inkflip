/**
 * Adapter configuration and safety limits.
 *
 * The caller injects the pinned pdf.js module plus the same-origin URLs of
 * the staged runtime assets (T02 `config/resolved-assets.json`). Defaults
 * mirror the browser profile in `planning/config/settings.json`; they are
 * safety bounds, never performance tuning.
 */
import type { PdfJsApi } from './types.ts';

export interface AdapterLimits {
  /** Max source bytes accepted by open() (settings: 20 MiB). */
  maxFileBytes: number;
  /** Max pages per document (settings: 1000). */
  maxPages: number;
  /** Render pixel cap per raster (settings: 4_000_000). */
  maxRasterPixels: number;
  /** Render edge cap in pixels (settings: 8192). */
  maxRasterEdge: number;
  /** getDocument deadline (settings: parse_timeout_ms 10_000). */
  parseTimeoutMs: number;
  /** Per-render deadline (settings: render_timeout_ms 10_000). */
  renderTimeoutMs: number;
  /** Occurrences per emitted chunk (schema/settings: 256). */
  chunkOccurrences: number;
  /** Per-check produced-occurrence cap (settings: 20_000 per page). */
  maxOccurrencesPerCheck: number;
  /** Items processed before yielding to the event loop. */
  yieldEveryItems: number;
}

export const DEFAULT_LIMITS: AdapterLimits = {
  maxFileBytes: 20_971_520,
  maxPages: 1_000,
  maxRasterPixels: 4_000_000,
  maxRasterEdge: 8_192,
  parseTimeoutMs: 10_000,
  renderTimeoutMs: 10_000,
  chunkOccurrences: 256,
  maxOccurrencesPerCheck: 20_000,
  yieldEveryItems: 512,
};

export interface AdapterConfig {
  /** Injected pinned pdf.js legacy module (e.g. pdfjs-dist/legacy/build/pdf.mjs). */
  pdfjs: PdfJsApi;
  /** Same-origin URL of the pinned paired worker (pdf.worker.mjs). */
  workerSrc: string;
  /** Same-origin staged asset directories (each with trailing slash). */
  cMapUrl?: string;
  standardFontDataUrl?: string;
  wasmUrl?: string;
  iccUrl?: string;
  /** Engine name for reader identity (default "pdf.js"). */
  engineName?: string;
  /** Distribution label recorded as Reader.build. */
  buildLabel?: string;
  /** pdf.js verbosity level (default library WARNINGS). */
  verbosity?: number;
  /** Document used to create canvases; defaults to globalThis.document. */
  ownerDocument?: {
    createElement(tag: 'canvas'): {
      width: number;
      height: number;
      getContext(
        kind: '2d',
        options?: Record<string, unknown>,
      ): {
        canvas: unknown;
        getImageData(
          x: number,
          y: number,
          w: number,
          h: number,
        ): { data: Uint8ClampedArray; width: number; height: number };
      } | null;
    };
  };
  limits: AdapterLimits;
}

export interface AdapterConfigInput {
  pdfjs: PdfJsApi;
  workerSrc: string;
  cMapUrl?: string;
  standardFontDataUrl?: string;
  wasmUrl?: string;
  iccUrl?: string;
  engineName?: string;
  buildLabel?: string;
  verbosity?: number;
  ownerDocument?: AdapterConfig['ownerDocument'];
  limits?: Partial<AdapterLimits>;
}

export function resolveConfig(input: AdapterConfigInput): AdapterConfig {
  if (typeof input.workerSrc !== 'string' || input.workerSrc.length === 0) {
    throw new Error('workerSrc (pinned paired worker URL) is required');
  }
  const limits = { ...DEFAULT_LIMITS, ...(input.limits ?? {}) };
  const config: AdapterConfig = {
    pdfjs: input.pdfjs,
    workerSrc: input.workerSrc,
    limits,
  };
  if (input.cMapUrl !== undefined) config.cMapUrl = input.cMapUrl;
  if (input.standardFontDataUrl !== undefined) {
    config.standardFontDataUrl = input.standardFontDataUrl;
  }
  if (input.wasmUrl !== undefined) config.wasmUrl = input.wasmUrl;
  if (input.iccUrl !== undefined) config.iccUrl = input.iccUrl;
  if (input.engineName !== undefined) config.engineName = input.engineName;
  if (input.buildLabel !== undefined) config.buildLabel = input.buildLabel;
  if (input.verbosity !== undefined) config.verbosity = input.verbosity;
  if (input.ownerDocument !== undefined) {
    config.ownerDocument = input.ownerDocument;
  }
  return config;
}
