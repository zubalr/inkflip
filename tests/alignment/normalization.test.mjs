// TEST-12 — scalar-whitespace-v1 normalization and reversible raw maps.
//
// Verifies packages/compare/normalization against the semantics frozen in
// planning/architecture/ALIGNMENT_AND_FINDINGS.md and the contract's
// normalize() output: every non-whitespace Unicode scalar is preserved
// exactly; each maximal White_Space run collapses to one U+0020; leading
// and trailing runs are retained as that single space; nothing is
// casefolded, compatibility-normalized, expanded or erased. All indices
// are Unicode scalar indices, never UTF-16 code units.
//
// Fixture dimensions exercised: F13 (ligatures, combining sequences),
// F14 (Arabic, CJK, supplementary scalars), F15 (OCR material ambiguity —
// digits, currency, signs, negation and punctuation can never be
// normalized away).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ContractError } from '../../packages/contracts/src/index.ts';
import {
  NORMALIZATION_VERSION,
  checkNormalizedView,
  isCombiningMark,
  isMaterialScalar,
  isWhitespaceScalar,
  normalizeText,
  normalizedRangeToRaw,
  normalizedToRawEnd,
  normalizedToRawStart,
  rawRangeToNormalized,
  rawSlice,
  rawSliceForNormalizedRange,
  rawToNormalized,
} from '../../packages/compare/normalization/index.ts';

test('empty raw text produces an empty view and empty map', () => {
  const view = normalizeText('');
  assert.equal(view.raw, '');
  assert.equal(view.text, '');
  assert.equal(view.rawScalars.length, 0);
  assert.equal(view.scalars.length, 0);
  assert.equal(view.map.length, 0);
  checkNormalizedView(view);
});

test('non-whitespace string is a single identity segment', () => {
  const view = normalizeText('Total:$1,000.00');
  assert.equal(view.text, 'Total:$1,000.00');
  assert.equal(view.map.length, 1);
  assert.equal(view.map[0].operation, 'identity');
  assert.equal(view.map[0].raw_start, 0);
  assert.equal(view.map[0].raw_end, view.rawScalars.length);
  checkNormalizedView(view);
});

test('each maximal whitespace run collapses to one U+0020, edges kept', () => {
  const view = normalizeText('  a\t\tb \u00a0 c  ');
  // '  ' -> ' ', 'a', '\t\t' -> ' ', 'b', ' NBSP ' -> ' ', 'c', '  ' -> ' '
  assert.equal(view.text, ' a b c ');
  const ops = view.map.map((s) => s.operation);
  assert.deepEqual(ops, [
    'whitespace',
    'identity',
    'whitespace',
    'identity',
    'whitespace',
    'identity',
    'whitespace',
  ]);
  // Leading run: normalized space at index 0 covers raw [0,2).
  assert.equal(normalizedToRawStart(view, 0), 0);
  assert.equal(normalizedToRawEnd(view, 0), 2);
  // The collapsed space between 'a' and 'b' covers the full '\t\t' run.
  assert.equal(normalizedToRawStart(view, 2), 3);
  assert.equal(normalizedToRawEnd(view, 2), 5);
  checkNormalizedView(view);
});

test('a whitespace-only string collapses to one space', () => {
  const view = normalizeText(' \t\u00a0 ');
  assert.equal(view.text, ' ');
  assert.equal(view.map.length, 1);
  assert.equal(view.map[0].operation, 'whitespace');
  checkNormalizedView(view);
});

test('zero-width space and BOM are NOT White_Space and survive', () => {
  const view = normalizeText('x​y\ufeffz');
  assert.equal(view.text, 'x​y\ufeffz');
  assert.equal(view.scalars.length, 5);
  checkNormalizedView(view);
});

test('digits, currency, signs and punctuation are never erased', () => {
  for (const raw of [
    '1,000',
    '1000',
    '100',
    '-100',
    '−100',
    '$1,000.50',
    '+42.0',
    '€9.99',
    '(100)',
    'paid',
    'not paid',
  ]) {
    const view = normalizeText(raw);
    const stripped = raw.replace(/\s+/gu, '');
    assert.equal(view.text.replace(/ /gu, ''), stripped, raw);
    checkNormalizedView(view);
  }
  // The values named by the spec stay distinct after normalization.
  const values = ['1,000', '1000', '100', '-100', 'not paid', 'paid'];
  const seen = new Set(values.map((v) => normalizeText(v).text));
  assert.equal(seen.size, values.length);
});

test('combining marks survive as separate scalars', () => {
  const raw = 'café'; // 'cafe' + U+0301 combining acute
  const view = normalizeText(raw);
  assert.equal(view.text, raw);
  assert.equal(view.scalars.length, 5);
  assert.ok(isCombiningMark(view.scalars[4]));
  checkNormalizedView(view);
});

test('ligatures are preserved, never expanded', () => {
  const view = normalizeText('ﬁle ﬃle');
  assert.equal(view.text, 'ﬁle ﬃle');
  assert.equal(view.scalars[0], 'ﬁ');
  assert.equal(view.scalars[4], 'ﬃ');
  checkNormalizedView(view);
});

test('no case folding: case is carried through unchanged', () => {
  const view = normalizeText('ABC ß İ');
  assert.equal(view.text, 'ABC ß İ');
  checkNormalizedView(view);
});

test('supplementary scalars are one element; indices are scalar indices', () => {
  const raw = 'a 😀 b';
  const view = normalizeText(raw);
  assert.equal(view.rawScalars.length, 5);
  assert.equal(raw.length, 6); // surrogate pair is two UTF-16 units
  assert.equal(view.scalars[2], '😀');
  // Scalar index 2 of the normalized text maps to raw scalar index 2 —
  // not to UTF-16 offset 4.
  assert.equal(normalizedToRawStart(view, 2), 2);
  assert.equal(rawSlice(view, 2, 3), '😀');
  checkNormalizedView(view);
});

test('Arabic, CJK and emoji pass through unchanged', () => {
  for (const raw of ['مرحبا', '你好世界', '😀🎉', 'שלום']) {
    const view = normalizeText(raw);
    assert.equal(view.text, raw);
    checkNormalizedView(view);
  }
});

test('scalar material classes identify digits, currency, signs, dashes', () => {
  for (const ch of ['0', '9', '٤', '$', '€', '+', '−', '-']) {
    assert.ok(isMaterialScalar(ch), `expected material: ${ch}`);
  }
  assert.ok(!isMaterialScalar('a'));
  assert.ok(!isMaterialScalar(' '));
  assert.ok(isWhitespaceScalar(' '));
  assert.ok(isWhitespaceScalar(' '));
  assert.ok(!isWhitespaceScalar('x'));
});

test('maps are reversible: normalized ranges recover raw text', () => {
  const raw = '  Total:\t$1,000.00   ';
  const view = normalizeText(raw);
  // normalized text: ' Total: $1,000.00 '
  assert.equal(view.text, ' Total: $1,000.00 ');
  // Every normalized index maps inside raw bounds; identity characters
  // map pointwise, whitespace collapses map to the whole run.
  for (let i = 0; i < view.scalars.length; i++) {
    const [rs, re] = normalizedRangeToRaw(view, i, i + 1);
    const seg = view.map.find(
      (s) => i >= s.normalized_start && i < s.normalized_end,
    );
    if (seg.operation === 'whitespace') {
      assert.equal(rs, seg.raw_start);
      assert.equal(re, seg.raw_end);
    } else {
      const off = i - seg.normalized_start;
      assert.equal(rs, seg.raw_start + off);
      assert.equal(re, seg.raw_start + off + 1);
    }
  }
  // The normalized token '$1,000.00' maps back to its raw run.
  const start = view.text.indexOf('$1,000.00');
  const slice = rawSliceForNormalizedRange(
    view,
    start,
    start + '$1,000.00'.length,
  );
  assert.equal(slice, '$1,000.00');
  // A normalized range covering the collapsed tab returns the raw tab.
  const tabAt = view.text.indexOf(': ') + 1;
  assert.equal(rawSliceForNormalizedRange(view, tabAt, tabAt + 1), '\t');
  checkNormalizedView(view);
});

test('raw ranges map forward to normalized ranges', () => {
  const view = normalizeText('a  b');
  // raw: 'a'(0), ' '(1), ' '(2), 'b'(3); normalized: 'a b'
  assert.deepEqual(rawRangeToNormalized(view, 0, 1), [0, 1]);
  assert.deepEqual(rawRangeToNormalized(view, 1, 3), [1, 2]);
  assert.deepEqual(rawRangeToNormalized(view, 3, 4), [2, 3]);
  assert.equal(rawToNormalized(view, 2), 1); // second ws scalar -> same space
  assert.equal(rawToNormalized(view, 4), 3); // end-of-raw maps to end
  checkNormalizedView(view);
});

test('integrity check rejects tampered maps', () => {
  const view = normalizeText('a b');
  // Identity segment containing whitespace is impossible.
  const bad = {
    ...view,
    map: [
      {
        raw_start: 0,
        raw_end: 3,
        normalized_start: 0,
        normalized_end: 3,
        operation: 'identity',
      },
    ],
  };
  assert.throws(() => checkNormalizedView(bad), ContractError);
  // Non-contiguous coverage.
  const bad2 = {
    ...view,
    map: [
      {
        raw_start: 0,
        raw_end: 1,
        normalized_start: 0,
        normalized_end: 1,
        operation: 'identity',
      },
    ],
  };
  assert.throws(() => checkNormalizedView(bad2), ContractError);
});

test('out-of-range indices raise ContractError', () => {
  const view = normalizeText('ab');
  assert.throws(() => normalizedToRawStart(view, 3), ContractError);
  assert.throws(() => rawToNormalized(view, 3), ContractError);
  assert.throws(() => normalizedRangeToRaw(view, 2, 1), ContractError);
});

test('version identifier is the contract algorithm id', () => {
  assert.equal(NORMALIZATION_VERSION, 'scalar-whitespace-v1');
});
