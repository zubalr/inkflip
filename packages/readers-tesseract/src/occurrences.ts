/**
 * Engine blocks → contract Occurrences (T10).
 *
 * The recognizer's word/line/block hierarchy is kept RAW — the
 * verbatim `blocks` JSON travels in the check output's `raw` field and
 * each word occurrence points into it via `raw_source_locator`
 * (`tesseract.js/blocks[b].paragraphs[p].lines[l].words[w]`). Nothing
 * here normalizes engine text into a claim: `raw_text` is the exact
 * API-returned string (I03), `normalized_text` is only the
 * schema-required scalar-whitespace-v1 view with its reversible map.
 *
 * Geometry precision is always `estimated` (COORDINATES.md: an OCR box
 * is an estimated pixel interpretation), never `exact` — and never
 * `page_only`/`unknown`, because the engine supplied a real box (I04).
 * `engine_score` is the recognizer's own 0–100 confidence, labeled as
 * a diagnostic estimate — never asserted as ground truth (I06).
 */
import {
  normalize,
  occurrenceId,
} from '../../contracts/src/index.ts';
import type {
  EngineScore,
  Geometry,
  Matrix,
  Occurrence,
  Point,
} from '../../contracts/src/index.ts';
import {
  apply,
  ocrToCanonical,
  round6,
  type BuiltPage,
} from '../../geometry/src/index.ts';
import type {
  EngineBlock,
  EngineLine,
  EngineWord,
} from './engine.ts';
import { OCR_REASON, requireOcr } from './errors.ts';
import type { CropPlan } from './crop.ts';

/** Recognizer score scale (tesseract word confidence). */
export const ENGINE_SCORE_MIN = 0;
export const ENGINE_SCORE_MAX = 100;
/** Words below this are flagged low-confidence (diagnostic only). */
export const LOW_CONFIDENCE_BELOW = 60;
export const ENGINE_SCORE_MEANING =
  'tesseract word confidence (0-100); recognizer estimate for ' +
  'diagnostics — never asserted as ground truth';

export interface MapBlocksInput {
  readonly built: BuiltPage;
  readonly plan: CropPlan;
  readonly blocks: readonly EngineBlock[];
  readonly readerId: string;
  readonly runKey: string;
  readonly pageIndex: number;
  /** Per-page produced-occurrence cap (default 20_000). */
  readonly maxOccurrences?: number;
}

export interface MappedBlocks {
  readonly occurrences: Occurrence[];
  /** ids of occurrences flagged `low_engine_score` (diagnostic). */
  readonly lowConfidenceIds: string[];
  /** Word count actually walked in the engine hierarchy. */
  readonly wordCount: number;
  /** Engine words with empty text (no occurrence emitted). */
  readonly emptyWords: number;
}

function bboxPolygonCanonical(
  word: EngineWord,
  ocr2canon: Matrix,
): Point[] | null {
  const b = word.bbox;
  if (
    b === undefined ||
    ![b.x0, b.y0, b.x1, b.y1].every(Number.isFinite) ||
    !(b.x1 > b.x0 && b.y1 > b.y0)
  ) {
    return null;
  }
  // Perimeter order TL,TR,BR,BL — a TL,TR,BL,BR ordering would be a
  // self-crossing bow-tie whose shoelace area is zero, which the
  // contract validator rightly rejects as degenerate geometry.
  const corners: Point[] = [
    [b.x0, b.y0],
    [b.x1, b.y0],
    [b.x1, b.y1],
    [b.x0, b.y1],
  ];
  return corners.map((p) => {
    const [x, y] = apply(ocr2canon, p);
    return [round6(x), round6(y)];
  });
}

/**
 * Flatten the engine hierarchy into word-level contract occurrences,
 * preserving emitted order and the verbatim hierarchy positions.
 * Throws `resource_limit` past the occurrence cap — a bounded-output
 * failure, not a silent truncation (I05).
 */
export function mapEngineBlocks(input: MapBlocksInput): MappedBlocks {
  const { built, plan, blocks, readerId, runKey, pageIndex } = input;
  const maxOccurrences = input.maxOccurrences ?? 20_000;
  const resize: Point = [plan.resizeK, plan.resizeK];
  const crop: Point = [plan.cropX, plan.cropY];
  // `ocrToCanonical` is C·O⁻¹ (geometry/src/page.ts): the inverse of
  // the recorded raster_scale + crop_translation + ocr_resize chain.
  const ocr2canon = ocrToCanonical(
    built,
    planScaleOf(plan),
    crop,
    resize,
  );
  const transformIds = plan.transforms.map((t) => t.id);
  const basis =
    `tesseract.js word bbox in ocr:${plan.ocrId} pixels; ` +
    `mapped ocr->canonical through transforms ${transformIds.join(',')}`;

  const occurrences: Occurrence[] = [];
  const lowConfidenceIds: string[] = [];
  let wordCount = 0;
  let emptyWords = 0;
  let ordinal = 0;

  for (const [bi, block] of blocks.entries()) {
    for (const [pi, para] of (block.paragraphs ?? []).entries()) {
      for (const [li, line] of (para.lines ?? []).entries()) {
        for (const [wi, word] of (line.words ?? []).entries()) {
          wordCount++;
          const raw = typeof word.text === 'string' ? word.text : '';
          if (raw.length === 0) {
            // An engine word with no text emits no occurrence; the
            // hierarchy position stays visible in `raw.blocks`.
            emptyWords++;
            continue;
          }
          requireOcr(
            ordinal < maxOccurrences,
            OCR_REASON.RESOURCE_LIMIT,
            `OCR produced more than ${maxOccurrences} occurrences on ` +
              `page ${pageIndex}`,
          );
          const locator =
            `tesseract.js/blocks[${bi}].paragraphs[${pi}]` +
            `.lines[${li}].words[${wi}]`;
          const norm = normalize(raw);
          const polygon = bboxPolygonCanonical(word, ocr2canon);
          const limitations: string[] = [];
          let score: EngineScore | null = null;
          if (
            typeof word.confidence === 'number' &&
            Number.isFinite(word.confidence)
          ) {
            score = {
              value: word.confidence,
              scale_min: ENGINE_SCORE_MIN,
              scale_max: ENGINE_SCORE_MAX,
              meaning: ENGINE_SCORE_MEANING,
            };
            if (word.confidence < LOW_CONFIDENCE_BELOW) {
              limitations.push('low_engine_score');
            }
          } else {
            limitations.push('engine_score_absent');
          }
          const geometry: Geometry = {
            precision: 'estimated',
            space: 'canonical_page',
            polygon,
            transform_ids: transformIds,
            basis,
          };
          if (polygon === null) {
            limitations.push('geometry_absent');
            // I04: a missing engine box is `unknown`, never guessed.
            geometry.precision = 'unknown';
            geometry.polygon = null;
          }
          occurrences.push({
            id: occurrenceId(runKey, readerId, pageIndex, ordinal, locator),
            reader_id: readerId,
            page_index: pageIndex,
            ordinal,
            raw_text: raw,
            normalized_text: norm.text,
            normalization_map: norm.map,
            geometry,
            engine_score: score,
            source_asset_id: null,
            raw_source_locator: locator,
            limitations,
          });
          if (score !== null && word.confidence! < LOW_CONFIDENCE_BELOW) {
            lowConfidenceIds.push(occurrences[occurrences.length - 1]!.id);
          }
          ordinal++;
        }
      }
    }
  }
  return { occurrences, lowConfidenceIds, wordCount, emptyWords };
}

/** Raster scale used to build the crop plan (px/pt). */
function planScaleOf(plan: CropPlan): number {
  // The raster_scale transform record carries the exact scale used.
  const raster = plan.transforms.find((t) => t.operation === 'raster_scale');
  if (raster === undefined) return 1;
  return raster.matrix[0];
}

/** Sum of engine word confidences — diagnostic only. */
export function meanWordConfidence(blocks: readonly EngineBlock[]): {
  mean: number | null;
  count: number;
} {
  let sum = 0;
  let count = 0;
  const visit = (line: EngineLine): void => {
    for (const word of line.words ?? []) {
      if (typeof word.confidence === 'number') {
        sum += word.confidence;
        count++;
      }
    }
  };
  for (const block of blocks) {
    for (const para of block.paragraphs ?? []) {
      for (const line of para.lines ?? []) visit(line);
    }
  }
  return { mean: count === 0 ? null : sum / count, count };
}
