/**
 * Scalar-level text distance for region-match-v1.
 *
 * Levenshtein over Unicode scalar values (code points — a supplementary
 * character is one element) normalized by the longer length. Edits that
 * touch a "material" scalar — decimal digits (Nd), currency symbols
 * (Sc), math signs (Sm, including U+2212) and dash punctuation (Pd,
 * including hyphen-minus) — are never cheap: a differing substitution
 * involving one costs as much as delete+insert, so amounts, signs and
 * negation-adjacent punctuation cannot be edited away to manufacture a
 * low distance (I03, F15).
 */

import { isMaterialScalar } from '../normalization/index.ts';

/** Substitution cost for a differing pair: 2 when material is involved. */
function substitutionCost(a: string, b: string): number {
  if (a === b) return 0;
  return isMaterialScalar(a) || isMaterialScalar(b) ? 2 : 1;
}

/**
 * Raw (unnormalized) scalar Levenshtein between two code-point arrays.
 * Standard two-row dynamic program, O(a.length x b.length) bounded by
 * the caller's span-size cap.
 */
export function scalarLevenshtein(
  a: readonly string[],
  b: readonly string[],
): number {
  const n = a.length;
  const m = b.length;
  if (n === 0) return m;
  if (m === 0) return n;
  let prev = new Array<number>(m + 1);
  let cur = new Array<number>(m + 1);
  for (let j = 0; j <= m; j++) prev[j] = j;
  for (let i = 1; i <= n; i++) {
    cur[0] = i;
    const ai = a[i - 1]!;
    for (let j = 1; j <= m; j++) {
      const bj = b[j - 1]!;
      const sub = prev[j - 1]! + substitutionCost(ai, bj);
      const del = prev[j]! + 1;
      const ins = cur[j - 1]! + 1;
      cur[j] = Math.min(sub, del, ins);
    }
    [prev, cur] = [cur, prev];
  }
  return prev[m]!;
}

/**
 * region-match-v1 text distance: scalar Levenshtein of the two strings
 * normalized by the longer scalar length, clamped to [0, 1]. Two empty
 * strings have distance 0; a material substitution can legitimately
 * return a value above what plain Levenshtein would give but never
 * above 1.
 */
export function normalizedTextDistance(a: string, b: string): number {
  const as = [...a];
  const bs = [...b];
  const longest = Math.max(as.length, bs.length);
  if (longest === 0) return 0;
  const d = scalarLevenshtein(as, bs) / longest;
  return d > 1 ? 1 : d;
}
