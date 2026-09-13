/**
 * @inkflip/readers-pdfjs — PDF.js rendering/text reader adapter (T09).
 *
 * Uses the PINNED paired pdf.js legacy main/worker injected by the caller
 * (T02 stages `pdfjs-dist@6.3.289`; never resolved or downloaded here).
 * Documented `getTextContent`/`getViewport`/`render`/`RenderTask.cancel`
 * only; TextItems keep emitted order, ordinals, transforms and raw API
 * strings. Canonical geometry, rotation and UserUnit go exclusively
 * through `@inkflip/geometry` (T04). Rendering is bounded, yields via
 * `onContinue`, and cancellation releases the task and canvas. PDF
 * actions, links, attachments, forms, XFA and scripting are never
 * activated. Capability limits are reported honestly — there is no
 * occurrence-level glyph-paint provenance on this boundary.
 */
export { createPdfJsReader, ADAPTER_VERSION } from './adapter.ts';
export type {
  Cancellation,
  ExtractJob,
  ExtractOutcome,
  PdfJsApi,
  PdfJsReaderAdapter,
  PlanSelection,
} from './adapter.ts';
export type {
  AdapterConfig,
  AdapterConfigInput,
  AdapterLimits,
} from './config.ts';
export { DEFAULT_LIMITS } from './config.ts';
export type {
  DocumentHandle,
  HandlePage,
} from './document.ts';
export { hexSha256 } from './document.ts';
export {
  CANCEL_REASON,
  ENCRYPTED_REASON,
  ReaderError,
  TIMEOUT_REASON,
  classifyError,
} from './errors.ts';
export type { AdapterFailure } from './errors.ts';
export { buildManifest, buildReaders } from './manifest.ts';
export type { ReaderIdentity } from './manifest.ts';
export type { RenderedRaster } from './render.ts';
export type { TextExtraction, TextExtractionDetail } from './text.ts';
export { canonicalBounds } from './text.ts';
export {
  ensureReadableStreamAsyncIterator,
  isReadableStreamTypeError,
} from './streams.ts';
export type {
  PdfJsContentItem,
  PdfJsDocument,
  PdfJsLoadingTask,
  PdfJsMarkedContent,
  PdfJsPage,
  PdfJsRenderTask,
  PdfJsTextContent,
  PdfJsTextItem,
  PdfJsTextStyle,
  PdfJsViewport,
} from './types.ts';
export { isPdfJsTextItem } from './types.ts';
