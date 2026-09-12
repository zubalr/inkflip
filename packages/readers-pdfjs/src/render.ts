/**
 * Bounded, yieldable page rendering with deterministic release.
 *
 * - Scale is clamped by the pixel/edge caps; a clamped render records the
 *   actual scale and a downsampling limitation, never a silent change.
 * - `RenderTask.onContinue` is scheduled on a macrotask so long operator
 *   lists yield to the event loop instead of monopolizing the frame.
 * - Cancellation calls `RenderTask.cancel`, awaits the resulting
   * RenderingCancelledException, then releases the canvas (w/h -> 0) —
 *   the task and its canvas are never left half-alive.
 * - The canvas is always adapter-owned and always released; the caller
 *   receives extracted ImageData plus the transform records that bound
 *   the raster (display rotation + raster scale through packages/geometry).
 * - Static annotation appearances only (AnnotationMode.ENABLE). Forms,
 *   XFA, annotation actions, links and attachments are never activated.
 */
import type { Transform } from '../../contracts/src/index.ts';
import {
  compose,
  displayTransformRecord,
  pageToDisplay,
  rasterScale,
  rasterTransformRecord,
} from '../../geometry/src/index.ts';
import type { AdapterConfig } from './config.ts';
import type { DocumentHandle, HandlePage } from './document.ts';
import {
  CANCEL_REASON,
  ReaderError,
  TIMEOUT_REASON,
  classifyError,
  renderErrorReason,
  resourceLimitReason,
} from './errors.ts';
import type { PdfJsRenderTask } from './types.ts';

export interface RenderedRaster {
  /** Raster identity, e.g. `r_p0_1`. */
  rasterId: string;
  widthPx: number;
  heightPx: number;
  /** Actual pixels per physical point used (after clamping). */
  scalePxPerPt: number;
  /** RGBA pixels, row-major, length widthPx*heightPx*4. */
  imageData: Uint8ClampedArray;
  /** pdf.js viewport transform actually used (validated against S·R·C). */
  viewportTransform: number[];
  /** Whether the used viewport matched the canonical composition. */
  viewportVerified: boolean;
  /** display_rotation + raster_scale records for this raster. */
  transforms: Transform[];
  limitations: string[];
}

interface CanvasLike {
  width: number;
  height: number;
  getContext(
    kind: '2d',
    options?: Record<string, unknown>,
  ): {
    getImageData(
      x: number,
      y: number,
      w: number,
      h: number,
    ): { data: Uint8ClampedArray; width: number; height: number };
  } | null;
}

const VIEWPORT_TOLERANCE = 1e-6;

function releaseCanvas(canvas: CanvasLike | null): void {
  if (canvas === null) return;
  canvas.width = 0;
  canvas.height = 0;
}

function defaultOwnerDocument(): NonNullable<AdapterConfig['ownerDocument']> {
  const doc = (globalThis as { document?: unknown }).document;
  if (doc === undefined || doc === null) {
    throw new ReaderError(
      'unsupported',
      'unsupported:no DOM canvas available; supply config.ownerDocument',
    );
  }
  return doc as NonNullable<AdapterConfig['ownerDocument']>;
}

/**
 * Render one page to a bounded canvas and return extracted pixels.
 * `signal` aborts via `RenderTask.cancel`; `deadlineMs` defaults to the
 * configured render timeout. Exactly one of raster/throw results.
 */
export async function renderPage(
  config: AdapterConfig,
  handle: DocumentHandle,
  page: HandlePage,
  requestedScale: number,
  rasterIndex: number,
  signal: AbortSignal | undefined,
  deadlineMs?: number,
): Promise<RenderedRaster> {
  const limits = config.limits;
  if (
    typeof requestedScale !== 'number' ||
    !Number.isFinite(requestedScale) ||
    requestedScale <= 0
  ) {
    throw new ReaderError(
      'failed',
      'render_error:requested scale must be a positive finite number',
    );
  }
  const [wPt, hPt] = page.built.canonicalSizePt;
  const displaySize =
    page.built.page.rotation === 90 || page.built.page.rotation === 270
      ? [hPt, wPt]
      : [wPt, hPt];
  const maxScale = Math.min(
    limits.maxRasterEdge / displaySize[0]!,
    limits.maxRasterEdge / displaySize[1]!,
    Math.sqrt(limits.maxRasterPixels / (displaySize[0]! * displaySize[1]!)),
  );
  if (!(maxScale > 0) || !Number.isFinite(maxScale)) {
    throw new ReaderError(
      'resource_limit',
      resourceLimitReason('page cannot be rasterized within pixel caps'),
    );
  }
  const limitations: string[] = [];
  let scale = requestedScale;
  if (scale > maxScale) {
    scale = maxScale;
    limitations.push(
      `render downsampled to ${scale} px/pt by raster caps (requested ${requestedScale}); actual scale recorded`,
    );
  }

  const viewport = page.proxy.getViewport({ scale });
  const expected = compose(
    rasterScale(scale),
    pageToDisplay(page.built),
  );
  const viewportVerified =
    page.viewportVerified &&
    Array.isArray(viewport.transform) &&
    viewport.transform.length === 6 &&
    viewport.transform.every(
      (v, i) =>
        typeof v === 'number' &&
        Number.isFinite(v) &&
        Math.abs(v - expected[i]!) <= VIEWPORT_TOLERANCE,
    );
  if (!viewportVerified) {
    limitations.push(
      'render viewport transform differs from canonical S*R*C; precise overlay anchoring disabled for this raster',
    );
  }

  const ownerDocument = config.ownerDocument ?? defaultOwnerDocument();
  const canvas = ownerDocument.createElement('canvas') as unknown as CanvasLike;
  canvas.width = Math.max(1, Math.ceil(viewport.width));
  canvas.height = Math.max(1, Math.ceil(viewport.height));
  const ctx = canvas.getContext('2d', { alpha: false });
  if (ctx === null) {
    releaseCanvas(canvas);
    throw new ReaderError(
      'failed',
      renderErrorReason('2d canvas context unavailable'),
    );
  }

  let task: PdfJsRenderTask;
  try {
    task = page.proxy.render({
      canvasContext: ctx,
      viewport,
      annotationMode: config.pdfjs.AnnotationMode.ENABLE,
    });
  } catch (error) {
    releaseCanvas(canvas);
    throw classifyError(error, true);
  }
  // Cooperative yielding between operator-list chunks (bounded rendering).
  task.onContinue = (continuation) => {
    setTimeout(continuation, 0);
  };

  const timeoutMs = deadlineMs ?? limits.renderTimeoutMs;
  const outcome = await new Promise<
    | { kind: 'done' }
    | { kind: 'cancelled' }
    | { kind: 'timeout' }
    | { kind: 'error'; error: unknown }
  >((resolve) => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const finish = (value: Parameters<typeof resolve>[0]): void => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      resolve(value);
    };
    timer = setTimeout(() => {
      try {
        task.cancel();
      } catch {
        // Task already settled; cancellation is best-effort.
      }
      finish({ kind: 'timeout' });
    }, timeoutMs);
    const onAbort = (): void => {
      try {
        task.cancel();
      } catch {
        // Task already settled; cancellation is best-effort.
      }
      finish({ kind: 'cancelled' });
    };
    if (signal) {
      if (signal.aborted) {
        onAbort();
      } else {
        signal.addEventListener('abort', onAbort, { once: true });
      }
    }
    task.promise.then(
      () => finish({ kind: 'done' }),
      (error: unknown) => {
        const name =
          typeof error === 'object' && error !== null
            ? String((error as { name?: unknown }).name ?? '')
            : '';
        finish(
          name === 'RenderingCancelledException'
            ? signal?.aborted
              ? { kind: 'cancelled' }
              : { kind: 'timeout' }
            : { kind: 'error', error },
        );
      },
    );
  });

  if (outcome.kind !== 'done') {
    releaseCanvas(canvas);
    if (outcome.kind === 'cancelled') {
      throw new ReaderError('cancelled', CANCEL_REASON);
    }
    if (outcome.kind === 'timeout') {
      throw new ReaderError('timeout', TIMEOUT_REASON);
    }
    throw classifyError(outcome.error, true);
  }

  let image: { data: Uint8ClampedArray; width: number; height: number };
  try {
    image = ctx.getImageData(0, 0, canvas.width, canvas.height);
  } catch (error) {
    releaseCanvas(canvas);
    throw classifyError(error, true);
  } finally {
    releaseCanvas(canvas);
  }
  // Belt and braces: the released canvas must stay released.
  releaseCanvas(canvas);

  const rasterId = `r_p${page.built.page.index}_${rasterIndex}`;
  const transforms = [
    displayTransformRecord(page.built.page),
    rasterTransformRecord(page.built.page, scale, rasterId),
  ];
  handle.transforms.push(...transforms);
  return {
    rasterId,
    widthPx: image.width,
    heightPx: image.height,
    scalePxPerPt: scale,
    imageData: image.data,
    viewportTransform: [...viewport.transform],
    viewportVerified,
    transforms,
    limitations,
  };
}
