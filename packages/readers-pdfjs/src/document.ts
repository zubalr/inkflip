/**
 * Document lifecycle: `open(immutable bytes, digest, generation)`,
 * `pages(handle)` and `close(handle)`.
 *
 * - Source bytes are never mutated or transferred: getDocument receives an
 *   adapter-owned copy (pdf.js takes ownership of the buffer it is given).
 * - The worker is configured only through a caller-supplied same-origin
 *   `workerSrc` naming the pinned paired worker; no URL, credentials,
 *   scripting, XFA or annotation-storage machinery is instantiated, so
 *   PDF actions/links/attachments can never be activated by this path.
 * - `close` destroys only this handle's own loading task/worker; a new
 *   generation's worker is a different instance and is unaffected.
 */
import { require, sha256 } from '../../contracts/src/index.ts';
import type { Box, Page, Transform } from '../../contracts/src/index.ts';
import {
  buildPage,
  compose,
  pageToDisplay,
  rasterScale,
  type BuiltPage,
} from '../../geometry/src/index.ts';
import {
  ReaderError,
  classifyError,
  resourceLimitReason,
  unsupportedReason,
} from './errors.ts';
import type { AdapterConfig } from './config.ts';
import type {
  PdfJsDocument,
  PdfJsLoadingTask,
  PdfJsPage,
} from './types.ts';

export function hexSha256(bytes: Uint8Array): string {
  let s = '';
  for (const b of sha256(bytes)) s += b.toString(16).padStart(2, '0');
  return s;
}

/** Per-page adapter-side record: contract page plus its pdf.js proxy. */
export interface HandlePage {
  built: BuiltPage;
  proxy: PdfJsPage;
  /**
   * Whether pdf.js' own viewport transform matched the canonical R·C at
   * scale 1 within 1e-6. A mismatch disables precise overlays only —
   * occurrences remain `estimated` as they always are.
   */
  viewportVerified: boolean;
}

export interface DocumentHandle {
  readonly digest: string;
  readonly byteLength: number;
  readonly generation: number;
  readonly task: PdfJsLoadingTask;
  readonly doc: PdfJsDocument;
  readonly pages: (HandlePage | null)[];
  /** Transforms emitted so far (canonical C per opened page). */
  readonly transforms: Transform[];
  closed: boolean;
}

function assertRotation(
  rotate: number,
): asserts rotate is Page['rotation'] {
  const r = ((rotate % 360) + 360) % 360;
  require(
    r === 0 || r === 90 || r === 180 || r === 270,
    'GEOMETRY',
    `Unsupported rotation ${rotate}`,
  );
}

function normalizeRotation(rotate: number): Page['rotation'] {
  assertRotation(rotate);
  return (((rotate % 360) + 360) % 360) as Page['rotation'];
}

const VIEWPORT_TOLERANCE = 1e-6;

/**
 * Open immutable bytes through the pinned pdf.js build. The supplied
 * digest is verified against the adapter-computed SHA-256 so a
 * mislabelled document can never acquire the wrong identity (I13).
 */
export async function openDocument(
  config: AdapterConfig,
  input: { bytes: Uint8Array; sha256: string; generation: number },
): Promise<DocumentHandle> {
  require(
    input.bytes instanceof Uint8Array && input.bytes.length > 0,
    'DOCUMENT',
    'open requires nonempty immutable bytes',
  );
  require(
    input.bytes.length <= config.limits.maxFileBytes,
    'SIZE',
    `document exceeds max_file_bytes ${config.limits.maxFileBytes}`,
  );
  const digest = hexSha256(input.bytes);
  require(
    input.sha256 === digest,
    'IDENTITY',
    'supplied document digest does not match the bytes',
  );
  // The library takes ownership of the buffer it is given; the original
  // stays immutable and untouched by construction (I01).
  const copy = input.bytes.slice();
  config.pdfjs.GlobalWorkerOptions.workerSrc = config.workerSrc;
  let task: PdfJsLoadingTask;
  try {
    task = config.pdfjs.getDocument({
      data: copy,
      // Kept for older API compatibility; pdf.js 6.x removed this option.
      // The real guarantee is structural: no scripting/sandbox/annotation
      // storage, form, XFA or link machinery is ever instantiated here.
      isEvalSupported: false,
      enableXfa: false,
      cMapUrl: config.cMapUrl,
      cMapPacked: true,
      standardFontDataUrl: config.standardFontDataUrl,
      wasmUrl: config.wasmUrl,
      iccUrl: config.iccUrl,
      useSystemFonts: false,
      canvasMaxAreaInBytes: config.limits.maxRasterPixels * 4,
      verbosity: config.verbosity,
    });
  } catch (error) {
    throw classifyError(error);
  }
  const deadline = new Promise<never>((_, reject) => {
    const t = setTimeout(
      () =>
        reject(
          new ReaderError(
            'timeout',
            'timeout:document load exceeded parse_timeout_ms',
          ),
        ),
      config.limits.parseTimeoutMs,
    );
    if (typeof t === 'object' && t !== null && 'unref' in t) {
      (t as { unref: () => void }).unref();
    }
  });
  let doc: PdfJsDocument;
  try {
    doc = await Promise.race([task.promise, deadline]);
  } catch (error) {
    await task.destroy().catch(() => undefined);
    throw classifyError(error);
  }
  require(
    doc.numPages >= 1,
    'SIZE',
    `page count ${doc.numPages} outside supported range`,
  );
  if (doc.numPages > config.limits.maxPages) {
    await task.destroy().catch(() => undefined);
    throw new ReaderError(
      'resource_limit',
      resourceLimitReason(
        `page count ${doc.numPages} exceeds max_document_pages`,
      ),
    );
  }
  return {
    digest,
    byteLength: input.bytes.length,
    generation: input.generation,
    task,
    doc,
    pages: new Array<HandlePage | null>(doc.numPages).fill(null),
    transforms: [],
    closed: false,
  };
}

export function requireOpen(handle: DocumentHandle): void {
  if (handle.closed) {
    throw new ReaderError('failed', 'closed:document handle is closed');
  }
}

/**
 * Contract page record plus geometry for one page, opened lazily.
 * `page.view` is the *effective* view; original MediaBox/CropBox are
 * unavailable through this API and are stored as null (never invented).
 * The canonical C comes from packages/geometry — the adapter never
 * derives coordinates itself. pdf.js' own viewport transform is then
 * validated against Scale(1)·R·C; a mismatch is recorded, not repaired.
 */
export async function handlePage(
  config: AdapterConfig,
  handle: DocumentHandle,
  pageIndex: number,
): Promise<HandlePage> {
  requireOpen(handle);
  require(
    Number.isInteger(pageIndex) && pageIndex >= 0 && pageIndex < handle.doc.numPages,
    'PAGE',
    `page index ${pageIndex} outside document`,
  );
  const cached = handle.pages[pageIndex];
  if (cached) return cached;
  let proxy: PdfJsPage;
  try {
    proxy = await handle.doc.getPage(pageIndex + 1);
  } catch (error) {
    throw classifyError(error);
  }
  const view = proxy.view;
  require(
    Array.isArray(view) &&
      view.length === 4 &&
      view.every((v) => typeof v === 'number' && Number.isFinite(v)) &&
      view[2]! > view[0]! &&
      view[3]! > view[1]!,
    'GEOMETRY',
    'pdf.js reported an invalid effective view',
  );
  let built: BuiltPage;
  try {
    built = buildPage({
      index: pageIndex,
      viewBox: view as unknown as Box,
      userUnit: proxy.userUnit,
      rotation: normalizeRotation(proxy.rotate),
      boxSource:
        'pdf.js page.view effective view; original MediaBox/CropBox unavailable via selected API',
      limitations: [
        'media_box and crop_box are null: the selected pdf.js API exposes only the effective view',
      ],
    });
  } catch (error) {
    if (error instanceof ReaderError) throw error;
    throw new ReaderError(
      'unsupported',
      unsupportedReason(
        `page geometry unavailable: ${error instanceof Error ? error.message : String(error)}`,
      ),
    );
  }
  handle.transforms.push(built.canonical);
  let viewportVerified = false;
  try {
    const expected = compose(rasterScale(1), pageToDisplay(built));
    const actual = proxy.getViewport({ scale: 1 }).transform;
    viewportVerified =
      Array.isArray(actual) &&
      actual.length === 6 &&
      actual.every(
        (v, i) =>
          typeof v === 'number' &&
          Number.isFinite(v) &&
          Math.abs(v - expected[i]!) <= VIEWPORT_TOLERANCE,
      );
  } catch {
    viewportVerified = false;
  }
  if (!viewportVerified) {
    built.page.limitations.push(
      'pdf.js viewport transform differs from canonical R*C; precise overlays disabled for this page',
    );
  }
  const record: HandlePage = { built, proxy, viewportVerified };
  handle.pages[pageIndex] = record;
  return record;
}

/** Page count plus contract metadata for every page (opens them lazily). */
export async function documentPages(
  config: AdapterConfig,
  handle: DocumentHandle,
): Promise<{ count: number; pages: Page[]; transforms: Transform[] }> {
  requireOpen(handle);
  const pages: Page[] = [];
  for (let i = 0; i < handle.doc.numPages; i++) {
    pages.push((await handlePage(config, handle, i)).built.page);
  }
  return { count: handle.doc.numPages, pages, transforms: [...handle.transforms] };
}

/** Idempotent close: destroys this handle's document and worker only. */
export async function closeDocument(handle: DocumentHandle): Promise<void> {
  if (handle.closed) return;
  handle.closed = true;
  handle.pages.fill(null);
  try {
    await handle.task.destroy();
  } catch {
    // Destroy is best-effort; the handle is already unreachable.
  }
}
