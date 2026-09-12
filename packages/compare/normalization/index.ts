/**
 * @inkflip/compare/normalization — scalar-whitespace-v1 normalized views.
 *
 * Implements the comparison-aid half of T12: the normalized view of a raw
 * reading plus the REVERSIBLE scalar-index map between the two. The raw
 * string is never modified, dropped or re-ordered (I03); normalization
 * only collapses each maximal Unicode White_Space run into one U+0020 and
 * keeps leading/trailing whitespace as that single space.
 *
 * The collapse itself is `normalize` from `@inkflip/contracts` — the same
 * function the report validator uses to recompute `normalized_text` and
 * `normalization_map`, so views produced here are byte-for-byte the
 * contract views. This module adds what the contract deliberately does
 * not: index conversion in both directions, raw-slice recovery and an
 * integrity check over the segment map.
 *
 * Index units are Unicode scalar values (code points), matching the
 * contract and the Python port — NOT UTF-16 code units. A supplementary
 * character such as U+1F4B8 is ONE scalar here but two `string.length`
 * units; converting to UTF-16 selection offsets is a UI-adapter concern
 * and does not happen in this package.
 *
 * What this module never does (per ALIGNMENT_AND_FINDINGS.md): no
 * casefold, no NFKC/NFKD, no ligature expansion, no combining-mark
 * removal, no punctuation removal and no minus-sign collapse. "1,000",
 * "1000", "100", "-100", "not paid" and "paid" stay different values.
 */

import {
  ContractError,
  WS,
  normalize,
  require,
} from '../../contracts/src/index.ts';
import type { RawMap } from '../../contracts/src/index.ts';

export const NORMALIZATION_VERSION = 'scalar-whitespace-v1';

/**
 * A raw reading plus its scalar-whitespace-v1 normalized view and the
 * segment map between them. `raw`/`text` are the strings; `rawScalars`
 * and `scalars` are the same strings as code-point arrays — every index
 * in `map` and every index accepted by the helpers below is a scalar
 * index into those arrays, not a UTF-16 offset.
 */
export interface NormalizedView {
  /** The unmodified API-returned string. */
  readonly raw: string;
  /** `raw` as an array of Unicode scalar values. */
  readonly rawScalars: readonly string[];
  /** The normalized comparison text (one U+0020 per whitespace run). */
  readonly text: string;
  /** `text` as an array of Unicode scalar values. */
  readonly scalars: readonly string[];
  /**
   * Contract `RawMap` segments, in raw order, covering `[0, raw]`
   * contiguously. `identity` segments copy scalars unchanged;
   * `whitespace` segments collapse a nonempty White_Space run to one
   * U+0020 — a many-to-one map that stays inspectable.
   */
  readonly map: readonly RawMap[];
}

/**
 * Build the normalized view of a raw reading. Empty raw text produces an
 * empty normalized view with an empty map; a string without whitespace
 * produces a single identity segment.
 */
export function normalizeText(raw: string): NormalizedView {
  require(typeof raw === 'string', 'TYPE', 'raw text must be a string');
  const { text, map } = normalize(raw);
  return {
    raw,
    rawScalars: [...raw],
    text,
    scalars: [...text],
    map,
  };
}

/**
 * Structural integrity check over a normalized view: the map must cover
 * the raw and normalized strings contiguously, identity segments must
 * reproduce their raw scalars exactly (and may not contain whitespace),
 * whitespace segments must collapse a nonempty all-whitespace run to
 * exactly one U+0020, and the normalized text may contain no whitespace
 * scalar other than those single spaces (so normalized spaces are never
 * adjacent). Throws ContractError 'NORMALIZATION' on any violation.
 */
export function checkNormalizedView(view: NormalizedView): void {
  const rawLen = view.rawScalars.length;
  const normLen = view.scalars.length;
  require(
    view.rawScalars.join('') === view.raw,
    'NORMALIZATION',
    'raw scalar table disagrees with raw text',
  );
  require(
    view.scalars.join('') === view.text,
    'NORMALIZATION',
    'normalized scalar table disagrees with normalized text',
  );
  if (rawLen === 0) {
    require(
      normLen === 0 && view.map.length === 0,
      'NORMALIZATION',
      'empty raw text must have empty view and map',
    );
    return;
  }
  let rawPos = 0;
  let normPos = 0;
  let prevWhitespace = false;
  for (const [segIndex, seg] of view.map.entries()) {
    require(
      seg.raw_start === rawPos && seg.raw_end > seg.raw_start,
      'NORMALIZATION',
      `map segment ${segIndex} does not cover raw text contiguously`,
    );
    require(
      seg.normalized_start === normPos && seg.normalized_end > normPos,
      'NORMALIZATION',
      `map segment ${segIndex} does not cover normalized text contiguously`,
    );
    const rawSlice = view.rawScalars.slice(seg.raw_start, seg.raw_end);
    const normSlice = view.scalars.slice(
      seg.normalized_start,
      seg.normalized_end,
    );
    if (seg.operation === 'identity') {
      require(
        seg.raw_end - seg.raw_start ===
          seg.normalized_end - seg.normalized_start,
        'NORMALIZATION',
        `identity segment ${segIndex} changes scalar count`,
      );
      require(
        rawSlice.every((ch, i) => ch === normSlice[i]),
        'NORMALIZATION',
        `identity segment ${segIndex} alters a scalar`,
      );
      require(
        rawSlice.every((ch) => !WS.has(ch)),
        'NORMALIZATION',
        `identity segment ${segIndex} contains whitespace`,
      );
      prevWhitespace = false;
    } else if (seg.operation === 'whitespace') {
      require(
        seg.normalized_end - seg.normalized_start === 1 &&
          normSlice[0] === ' ',
        'NORMALIZATION',
        `whitespace segment ${segIndex} must emit exactly one U+0020`,
      );
      require(
        rawSlice.every((ch) => WS.has(ch)),
        'NORMALIZATION',
        `whitespace segment ${segIndex} erases a non-whitespace scalar`,
      );
      require(
        !prevWhitespace,
        'NORMALIZATION',
        `adjacent whitespace segments ${segIndex} are not a maximal run`,
      );
      prevWhitespace = true;
    } else {
      throw new ContractError(
        'NORMALIZATION',
        `unknown map operation ${String(seg.operation)}`,
      );
    }
    rawPos = seg.raw_end;
    normPos = seg.normalized_end;
  }
  require(
    rawPos === rawLen && normPos === normLen,
    'NORMALIZATION',
    'map does not cover the whole strings',
  );
}

// ---------------------------------------------------------------------------
// Reversible index conversion
// ---------------------------------------------------------------------------

function segmentAtNormalized(view: NormalizedView, index: number): RawMap {
  // Segments cover [0, scalars.length) contiguously in order; binary
  // search the (sorted) normalized_start column.
  let lo = 0;
  let hi = view.map.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const seg = view.map[mid]!;
    if (index < seg.normalized_start) hi = mid - 1;
    else if (index >= seg.normalized_end) lo = mid + 1;
    else return seg;
  }
  throw new ContractError(
    'NORMALIZATION',
    `normalized index ${index} outside [0, ${view.scalars.length})`,
  );
}

function segmentAtRaw(view: NormalizedView, index: number): RawMap {
  let lo = 0;
  let hi = view.map.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const seg = view.map[mid]!;
    if (index < seg.raw_start) hi = mid - 1;
    else if (index >= seg.raw_end) lo = mid + 1;
    else return seg;
  }
  throw new ContractError(
    'NORMALIZATION',
    `raw index ${index} outside [0, ${view.rawScalars.length})`,
  );
}

function checkIndex(value: number, size: number, what: string): void {
  require(
    Number.isInteger(value) && value >= 0 && value <= size,
    'NORMALIZATION',
    `${what} index ${value} outside [0, ${size}]`,
  );
}

/**
 * Raw scalar offset of the FIRST raw scalar that produced normalized
 * character `index` — for a whitespace-collapse this is the start of the
 * run. `index === scalars.length` maps to `rawScalars.length`, so
 * half-open ranges work.
 */
export function normalizedToRawStart(
  view: NormalizedView,
  index: number,
): number {
  checkIndex(index, view.scalars.length, 'normalized');
  if (index === view.scalars.length) return view.rawScalars.length;
  const seg = segmentAtNormalized(view, index);
  if (seg.operation === 'whitespace') return seg.raw_start;
  return seg.raw_start + (index - seg.normalized_start);
}

/**
 * Raw scalar offset AFTER the last raw scalar that produced normalized
 * character `index` — for a whitespace-collapse this is the end of the
 * whole run. `index === scalars.length` maps to `rawScalars.length`.
 */
export function normalizedToRawEnd(
  view: NormalizedView,
  index: number,
): number {
  checkIndex(index, view.scalars.length, 'normalized');
  if (index === view.scalars.length) return view.rawScalars.length;
  const seg = segmentAtNormalized(view, index);
  if (seg.operation === 'whitespace') return seg.raw_end;
  return seg.raw_start + (index - seg.normalized_start) + 1;
}

/**
 * Map a half-open normalized range `[start, end)` to the half-open raw
 * range covering every raw scalar that fed it. A range covering one
 * collapsed space maps back to the entire whitespace run — the
 * many-to-one direction stays inspectable.
 */
export function normalizedRangeToRaw(
  view: NormalizedView,
  start: number,
  end: number,
): [number, number] {
  checkIndex(start, view.scalars.length, 'normalized start');
  checkIndex(end, view.scalars.length, 'normalized end');
  require(start <= end, 'NORMALIZATION', 'inverted normalized range');
  if (start === end) {
    const at = normalizedToRawStart(view, start);
    return [at, at];
  }
  return [
    normalizedToRawStart(view, start),
    normalizedToRawEnd(view, end - 1),
  ];
}

/**
 * Normalized scalar offset of the character produced by raw scalar
 * `index`. A raw scalar inside a whitespace run maps to the single
 * space. `index === rawScalars.length` maps to `scalars.length`.
 */
export function rawToNormalized(
  view: NormalizedView,
  index: number,
): number {
  checkIndex(index, view.rawScalars.length, 'raw');
  if (index === view.rawScalars.length) return view.scalars.length;
  const seg = segmentAtRaw(view, index);
  if (seg.operation === 'whitespace') return seg.normalized_start;
  return seg.normalized_start + (index - seg.raw_start);
}

/**
 * Map a half-open raw range `[start, end)` to the half-open normalized
 * range it produced.
 */
export function rawRangeToNormalized(
  view: NormalizedView,
  start: number,
  end: number,
): [number, number] {
  checkIndex(start, view.rawScalars.length, 'raw start');
  checkIndex(end, view.rawScalars.length, 'raw end');
  require(start <= end, 'NORMALIZATION', 'inverted raw range');
  if (start === end) {
    const at = rawToNormalized(view, start);
    return [at, at];
  }
  return [rawToNormalized(view, start), rawToNormalized(view, end - 1) + 1];
}

/** Raw scalars `[start, end)` re-joined — raw text is never rewritten. */
export function rawSlice(
  view: NormalizedView,
  start: number,
  end: number,
): string {
  checkIndex(start, view.rawScalars.length, 'raw start');
  checkIndex(end, view.rawScalars.length, 'raw end');
  require(start <= end, 'NORMALIZATION', 'inverted raw range');
  return view.rawScalars.slice(start, end).join('');
}

/**
 * The raw substring that produced normalized range `[start, end)` —
 * e.g. mapping a matched normalized span back onto the stored raw
 * reading for display.
 */
export function rawSliceForNormalizedRange(
  view: NormalizedView,
  start: number,
  end: number,
): string {
  const [rs, re] = normalizedRangeToRaw(view, start, end);
  return rawSlice(view, rs, re);
}

// ---------------------------------------------------------------------------
// Meaningful-character classification (I03 / "no cheap digit/sign edits")
// ---------------------------------------------------------------------------

/**
 * Scalars whose loss or silent substitution would change meaning:
 * decimal digits (Nd, all scripts), currency symbols (Sc), math signs
 * (Sm — including U+2212 minus) and dash punctuation (Pd — including
 * U+002D hyphen-minus). Punctuation outside Pd is preserved by the
 * identity rule anyway; these four classes are the ones the alignment
 * cost treats as expensive to edit.
 */
export const MATERIAL_SCALAR_RE = /[\p{Nd}\p{Sc}\p{Sm}\p{Pd}]/u;

/** Combining marks (M*) — must survive normalization untouched. */
export const COMBINING_MARK_RE = /\p{M}/u;

export function isMaterialScalar(ch: string): boolean {
  return MATERIAL_SCALAR_RE.test(ch);
}

export function isCombiningMark(ch: string): boolean {
  return COMBINING_MARK_RE.test(ch);
}

export function isWhitespaceScalar(ch: string): boolean {
  return WS.has(ch);
}
