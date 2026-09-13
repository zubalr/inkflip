/**
 * Native-text extraction: `getTextContent({disableNormalization:true,
 * includeMarkedContent:true})` -> canonical occurrences.
 *
 * Preservation rules (READER_ADAPTER_CONTRACT.md):
 * - TextItems stay in emitted order; `ordinal` is the 0-based index among
 *   text items and `raw_text` is the API string, never injected or
 *   normalized here. The contract-normalized view is computed by the
 *   shared `normalize()` (scalar-whitespace-v1) exactly as the schema
 *   validator requires; it never alters `raw_text`.
 * - Marked-content records are counted, never emitted as occurrences.
 * - Geometry is always `estimated`: the item transform (user units) maps
 *   through the page's canonical C from packages/geometry; the extent
 *   comes from item width/height and font ascent/descent. A degenerate
 *   extent becomes `page_only`/`null` rather than an invented area (I04).
 * - Occurrence ids are hash identities over
 *   (run_key, reader, page, ordinal, locator) — equal strings at distinct
 *   positions are distinct occurrences (I02, F11 duplicates genus).
 */
import { normalize, occurrenceId } from '../../contracts/src/index.ts';
import type {
  CheckResult,
  Occurrence,
  Point,
} from '../../contracts/src/index.ts';
import {
  apply,
  makeGeometry,
  pageToCanonical,
  polygonBounds,
} from '../../geometry/src/index.ts';
import type { AdapterConfig } from './config.ts';
import type { DocumentHandle, HandlePage } from './document.ts';
import {
  CANCEL_REASON,
  ReaderError,
  classifyError,
  resourceLimitReason,
} from './errors.ts';
import {
  asReadableStreamAsyncIterable,
  hasNativeReadableStreamAsyncIterator,
  isReadableStreamTypeError,
} from './streams.ts';
import {
  isPdfJsTextItem,
  type PdfJsTextItem,
  type PdfJsTextStyle,
} from './types.ts';

export interface TextJobContext {
  /** Contract run identity; required to mint occurrence ids. */
  runKey: string;
  /** Emitted raw item order also serves the reading-order reading. */
  locatorTag?: string;
}

export interface TextExtractionDetail {
  /** Text items seen (== produced occurrences). */
  textItems: number;
  /** Marked-content records seen, by type (never occurrences). */
  markedContent: Record<string, number>;
  /** Document /Lang if declared. */
  lang: string | null;
  /** Occurrences whose extent was degenerate (page_only). */
  degenerateExtents: number;
}

export interface TextExtraction {
  occurrences: number;
  retainedIds: string[];
  detail: TextExtractionDetail;
  /**
   * True when cancellation stopped the walk early; emitted occurrences so
   * far stay retained (a cancelled check keeps its produced evidence).
   */
  cancelled: boolean;
}

const ITEM_LIMITATIONS = [
  'extent estimated from pdf.js TextItem transform, width/height and font ascent/descent; not a glyph-paint or per-character provenance',
];

const EPS = 1e-9;

async function collectTextContentStream(
  stream:
    | ReadableStream<{ items?: unknown[]; styles?: Record<string, unknown>; lang?: string | null }>
    | AsyncIterable<{ items?: unknown[]; styles?: Record<string, unknown>; lang?: string | null }>,
): Promise<{
  items: unknown[];
  styles: Record<string, PdfJsTextStyle>;
  lang: string | null;
}> {
  const textContent = {
    items: [] as unknown[],
    styles: Object.create(null) as Record<string, PdfJsTextStyle>,
    lang: null as string | null,
  };
  for await (const value of asReadableStreamAsyncIterable(stream)) {
    textContent.lang ??= value.lang ?? null;
    Object.assign(textContent.styles, value.styles ?? {});
    textContent.items.push(...(value.items ?? []));
  }
  return textContent;
}

async function getTextContentCompat(page: {
  getTextContent: HandlePage['proxy']['getTextContent'];
  streamTextContent?: (params: {
    includeMarkedContent?: boolean;
    disableNormalization?: boolean;
  }) =>
    | ReadableStream<{ items?: unknown[]; styles?: Record<string, unknown>; lang?: string | null }>
    | AsyncIterable<{ items?: unknown[]; styles?: Record<string, unknown>; lang?: string | null }>;
}): Promise<{
  items: unknown[];
  styles: Record<string, PdfJsTextStyle>;
  lang: string | null;
}> {
  const params = { includeMarkedContent: true, disableNormalization: true };
  const canIterateNatively = hasNativeReadableStreamAsyncIterator();
  if (canIterateNatively) {
    try {
      return await page.getTextContent(params);
    } catch (error) {
      if (!isReadableStreamTypeError(error) || typeof page.streamTextContent !== 'function') {
        throw error;
      }
      return collectTextContentStream(page.streamTextContent(params));
    }
  }
  if (typeof page.streamTextContent === 'function') {
    return collectTextContentStream(page.streamTextContent(params));
  }
  return await page.getTextContent(params);
}

function itemQuadCanonical(
  item: PdfJsTextItem,
  style: PdfJsTextStyle | undefined,
  canonicalMatrix: ReturnType<typeof pageToCanonical>,
): { polygon: Point[] | null; limitations: string[] } {
  const t = item.transform;
  const limitations: string[] = [];
  if (
    !Array.isArray(t) ||
    t.length !== 6 ||
    !t.every((v) => typeof v === 'number' && Number.isFinite(v))
  ) {
    return {
      polygon: null,
      limitations: ['TextItem transform absent or non-finite; no extent claimed'],
    };
  }
  const ax = Math.hypot(t[0]!, t[1]!);
  const ay = Math.hypot(t[2]!, t[3]!);
  // Item-space width: user-space advance re-expressed in text-space units.
  const wItem = ax > EPS ? item.width / ax : 0;
  // Thickness in item-space y units: ascent/descent are em ratios and the
  // transform's y column is exactly fontSize long, so em ratios apply
  // directly. Missing style falls back to the font-size unit square.
  const ascent =
    style && typeof style.ascent === 'number' && Number.isFinite(style.ascent)
      ? style.ascent
      : 1;
  const descent =
    style && typeof style.descent === 'number' && Number.isFinite(style.descent)
      ? style.descent
      : 0;
  if (ax <= EPS || ay <= EPS || wItem <= 0 || ascent <= descent) {
    return {
      polygon: null,
      limitations: [
        'degenerate TextItem extent (zero advance or thickness); position retained at item anchor only',
      ],
    };
  }
  const quadUser: Point[] = [
    apply(t, [0, descent]),
    apply(t, [wItem, descent]),
    apply(t, [wItem, ascent]),
    apply(t, [0, ascent]),
  ];
  const quadCanonical = quadUser.map((p) => apply(canonicalMatrix, p));
  if (style?.vertical === true) {
    limitations.push(
      'vertical font: extent estimated along the item axes; advance direction approximate',
    );
  }
  return { polygon: quadCanonical, limitations };
}

function isAborted(signal: AbortSignal | undefined): boolean {
  return signal?.aborted === true;
}

/**
 * Run a native_text (or reading_order) extraction on one page.
 * `emitChunk` is awaited per chunk (<=256 occurrences), which is the
 * adapter's backpressure hook; the wire-level two-unacknowledged window
 * is owned by the runtime ChunkSender, not reimplemented here.
 */
export async function extractText(
  config: AdapterConfig,
  handle: DocumentHandle,
  page: HandlePage,
  checkId: string,
  readerId: string,
  job: TextJobContext,
  emitChunk: (chunk: Occurrence[]) => unknown,
  signal: AbortSignal | undefined,
): Promise<TextExtraction> {
  let content;
  try {
    content = await getTextContentCompat(page.proxy);
  } catch (error) {
    throw classifyError(error);
  }
  if (isAborted(signal)) {
    throw new ReaderError('cancelled', CANCEL_REASON);
  }
  const canonicalMatrix = pageToCanonical(page.built);
  const canonicalId = page.built.canonical.id;
  const locatorTag = job.locatorTag ?? 'text';
  const detail: TextExtractionDetail = {
    textItems: 0,
    markedContent: {},
    lang: content.lang ?? null,
    degenerateExtents: 0,
  };
  const retainedIds: string[] = [];
  let chunk: Occurrence[] = [];
  let ordinal = 0;

  const flush = async (): Promise<void> => {
    if (chunk.length === 0) return;
    const out = chunk;
    chunk = [];
    await emitChunk(out);
  };

  let cancelled = false;
  for (const raw of content.items) {
    if (isAborted(signal)) {
      cancelled = true;
      break;
    }
    if (!isPdfJsTextItem(raw)) {
      const type =
        typeof raw === 'object' && raw !== null && 'type' in raw
          ? String((raw as { type?: unknown }).type)
          : 'unknown';
      detail.markedContent[type] = (detail.markedContent[type] ?? 0) + 1;
      continue;
    }
    const item = raw;
    detail.textItems += 1;
    const style = content.styles[item.fontName];
    const { polygon, limitations } = itemQuadCanonical(
      item,
      style,
      canonicalMatrix,
    );
    const locator = `pdfjs:getTextContent:p${page.built.page.index}:${locatorTag}${ordinal}`;
    const normalized = normalize(item.str);
    const occurrenceLimitations = [
      ...ITEM_LIMITATIONS,
      ...limitations,
      ...([...item.str].length > 1
        ? [
            'multi-character TextItem: no per-character advance boxes; the whole measured item is the extent',
          ]
        : []),
      ...(page.viewportVerified
        ? []
        : ['page viewport transform unverified; precise overlay disabled']),
    ];
    let geometry;
    if (polygon === null) {
      detail.degenerateExtents += 1;
      geometry = makeGeometry({
        precision: 'page_only',
        polygon: null,
        transformIds: [canonicalId],
        basis:
          'pdf.js getTextContent item anchor present but extent degenerate or absent; no area polygon claimed',
      });
    } else {
      geometry = makeGeometry({
        precision: 'estimated',
        polygon,
        transformIds: [canonicalId],
        basis:
          'pdf.js getTextContent TextItem transform+width/height with font ascent/descent, mapped through the page raw_to_canonical transform',
      });
    }
    const occurrence: Occurrence = {
      id: occurrenceId(
        job.runKey,
        readerId,
        page.built.page.index,
        ordinal,
        locator,
      ),
      reader_id: readerId,
      page_index: page.built.page.index,
      ordinal,
      raw_text: item.str,
      normalized_text: normalized.text,
      normalization_map: normalized.map,
      geometry,
      engine_score: null,
      source_asset_id: null,
      raw_source_locator: locator,
      limitations: occurrenceLimitations,
    };
    retainedIds.push(occurrence.id);
    chunk.push(occurrence);
    if (retainedIds.length > config.limits.maxOccurrencesPerCheck) {
      throw new ReaderError(
        'resource_limit',
        resourceLimitReason('per-check occurrence cap exceeded'),
      );
    }
    if (chunk.length >= config.limits.chunkOccurrences) await flush();
    ordinal += 1;
    if (ordinal % config.limits.yieldEveryItems === 0) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  }
  await flush();
  return {
    occurrences: retainedIds.length,
    retainedIds,
    detail,
    cancelled,
  };
}

/** Convenience: did an extraction complete with zero text items? */
export function completedEmpty(result: CheckResult): boolean {
  return result.status === 'completed' && result.produced_occurrence_count === 0;
}

/** Bounding box of a canonical polygon (for tests/diagnostics). */
export function canonicalBounds(occurrence: Occurrence): number[] | null {
  if (occurrence.geometry.polygon === null) return null;
  const b = polygonBounds(occurrence.geometry.polygon);
  return [...b];
}
