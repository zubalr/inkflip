/**
 * Structural typing of the pinned pdf.js surface the adapter consumes.
 *
 * The adapter never imports `pdfjs-dist`: the caller injects the pinned,
 * paired legacy build (`pdfjs-dist/legacy/build/pdf.mjs` plus its matching
 * `pdf.worker.mjs`, staged by T02). Typing only the surface we actually use
 * keeps the adapter honest about what the selected API exposes — notably,
 * original MediaBox/CropBox are *not* available here (`page.view` is the
 * effective view only), and there is no occurrence-level glyph-paint or
 * rendering-mode oracle on this boundary.
 */

/** Minimal shape of the injected `pdfjs-dist` legacy module. */
export interface PdfJsApi {
  /** Actual library version string (e.g. "6.3.289"). */
  readonly version: string;
  /** Global worker configuration; only `workerSrc` is set by the adapter. */
  readonly GlobalWorkerOptions: {
    workerSrc?: string;
    workerPort?: unknown;
  };
  /** Annotation rendering modes (ENABLE = static appearance streams only). */
  readonly AnnotationMode: {
    readonly DISABLE: number;
    readonly ENABLE: number;
    readonly ENABLE_FORMS: number;
    readonly ENABLE_STORAGE: number;
  };
  readonly getDocument: (src: Record<string, unknown>) => PdfJsLoadingTask;
}

export interface PdfJsLoadingTask {
  readonly promise: Promise<PdfJsDocument>;
  /** Destroys the document and this task's own worker. */
  destroy(): Promise<void>;
  onProgress?: ((progress: { loaded: number; total: number }) => void) | null;
}

export interface PdfJsDocument {
  readonly numPages: number;
  getPage(pageNumber: number): Promise<PdfJsPage>;
}

export interface PdfJsViewport {
  /** user-space -> viewport transform, UserUnit already applied once. */
  readonly transform: number[];
  readonly width: number;
  readonly height: number;
}

export interface PdfJsPage {
  /** Effective view box [x0,y0,x1,y1] — NOT proof of original page boxes. */
  readonly view: number[];
  /** Page /UserUnit (>0). */
  readonly userUnit: number;
  /** Document /Rotate in degrees. */
  readonly rotate: number;
  getViewport(params: {
    scale: number;
    rotation?: number;
    offsetX?: number;
    offsetY?: number;
    dontFlip?: boolean;
  }): PdfJsViewport;
  getTextContent(params: {
    includeMarkedContent?: boolean;
    disableNormalization?: boolean;
  }): Promise<PdfJsTextContent>;
  streamTextContent?(params: {
    includeMarkedContent?: boolean;
    disableNormalization?: boolean;
  }): AsyncIterable<{
    items?: PdfJsContentItem[];
    styles?: Record<string, PdfJsTextStyle>;
    lang?: string | null;
  }>;
  render(params: Record<string, unknown>): PdfJsRenderTask;
  cleanup?(resetStats?: boolean): boolean;
}

export interface PdfJsRenderTask {
  readonly promise: Promise<unknown>;
  cancel(extraDelay?: number): void;
  /**
   * Continuation callback: when set, pdf.js calls it instead of resuming
   * directly; the adapter schedules it on a macrotask to yield.
   */
  onContinue: ((continuation: () => void) => void) | null;
}

export interface PdfJsTextStyle {
  fontFamily?: string;
  ascent?: number;
  descent?: number;
  vertical?: boolean;
}

/** A text-bearing item in `getTextContent` output. */
export interface PdfJsTextItem {
  readonly str: string;
  readonly dir: string;
  /** Text-space -> user-space matrix (user units; UserUnit NOT applied). */
  readonly transform: number[];
  /** Horizontal advance, already in user units. */
  readonly width: number;
  /** Font size in user units (nonzero for horizontal text). */
  readonly height: number;
  readonly fontName: string;
  readonly hasEOL?: boolean;
  readonly type?: undefined;
}

/** Marked-content records are structural markers, never text occurrences. */
export interface PdfJsMarkedContent {
  readonly type: string;
  readonly id?: string | null;
  readonly tag?: string | null;
}

export type PdfJsContentItem = PdfJsTextItem | PdfJsMarkedContent;

export interface PdfJsTextContent {
  items: PdfJsContentItem[];
  styles: Record<string, PdfJsTextStyle>;
  lang: string | null;
}

/** Whether a content item is a real text item (not a marked-content record). */
export function isPdfJsTextItem(item: unknown): item is PdfJsTextItem {
  return (
    typeof item === 'object' &&
    item !== null &&
    typeof (item as PdfJsTextItem).str === 'string' &&
    Array.isArray((item as PdfJsTextItem).transform)
  );
}
