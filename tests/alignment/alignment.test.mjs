// TEST-12 — region-match-v1 bounded conservative alignment.
//
// Verifies packages/compare/alignment against the semantics frozen in
// planning/architecture/ALIGNMENT_AND_FINDINGS.md: geometry-first
// candidate construction, bounded non-crossing assignment with
// split/merge provenance, duplicate occurrence preservation, order
// difference reporting and abstention on ambiguity. Score components are
// algorithm diagnostics, never probabilities (I06).
//
// Fixture dimensions exercised: F11 (repeated identical values keep
// separate occurrences/candidates), F12 (changed column emission order),
// F13 (ligature/combining sequences), F14 (Arabic/CJK/emoji), F15 (OCR
// material ambiguity — digit/sign/negation differences are not cheap).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ContractError } from '../../packages/contracts/src/index.ts';
import { normalizeText } from '../../packages/compare/normalization/index.ts';
import {
  REGION_MATCH_V1,
  SCORE_SEMANTICS,
  alignPage,
  normalizedTextDistance,
} from '../../packages/compare/alignment/index.ts';

// --- helpers ---------------------------------------------------------------

const polygonFor = (box) =>
  box === null
    ? null
    : [
        [box[0], box[1]],
        [box[2], box[1]],
        [box[2], box[3]],
        [box[0], box[3]],
      ];

const geometry = (box, precision = 'exact') => ({
  precision,
  space: 'canonical_page',
  polygon: polygonFor(box),
  transform_ids: [],
  basis: 'test geometry',
});

const occ = (id, ordinal, text, box, precision = 'exact', page = 0) => ({
  id,
  page_index: page,
  ordinal,
  normalized_text: normalizeText(text).text,
  geometry: geometry(box, precision),
});

const statusById = (list) => {
  const m = new Map();
  for (const x of list) m.set(x.occurrence_id, x.status);
  return m;
};

// --- acceptance: geometry-first one-to-one matching -------------------------

test('identical text and geometry produce a unique one_to_one match', () => {
  const res = alignPage(
    [occ('l0', 0, 'Total', [0, 0, 30, 10])],
    [occ('r0', 0, 'Total', [0, 0, 30, 10])],
  );
  assert.equal(res.algorithm, 'region-match-v1');
  assert.equal(res.score_semantics, 'algorithm_diagnostics_not_probability');
  assert.equal(res.matches.length, 1);
  const m = res.matches[0];
  assert.deepEqual(m.left_occurrence_ids, ['l0']);
  assert.deepEqual(m.right_occurrence_ids, ['r0']);
  assert.equal(m.provenance, 'one_to_one');
  assert.ok(m.margin >= REGION_MATCH_V1.minMargin);
  assert.ok(m.components.cost <= REGION_MATCH_V1.acceptCost);
  assert.equal(statusById(res.left).get('l0'), 'unique');
  assert.equal(statusById(res.right).get('r0'), 'unique');
});

test('differing text is allowed; material edits stay expensive', () => {
  // F15: '0' vs 'O' is a material substitution — never a cheap edit.
  const plain = 1 / '$1,000.00'.length;
  const material = normalizedTextDistance('$1,000.00', '$1,O00.00');
  assert.equal(material, 2 / '$1,000.00'.length);
  assert.ok(material > plain);
  // Negation difference is visible in the diagnostic components.
  assert.equal(normalizedTextDistance('not paid', 'paid'), 0.5);
  const res = alignPage(
    [
      occ('l0', 0, '$1,000.00', [0, 0, 80, 10]),
      occ('l1', 1, 'not paid', [0, 20, 60, 30]),
    ],
    [
      occ('r0', 0, '$1,O00.00', [0, 0, 80, 10]),
      occ('r1', 1, 'paid', [0, 20, 60, 30]),
    ],
  );
  assert.equal(res.matches.length, 2);
  const amount = res.matches.find((m) => m.left_occurrence_ids[0] === 'l0');
  assert.ok(amount.components.text_distance > 0);
  const neg = res.matches.find((m) => m.left_occurrence_ids[0] === 'l1');
  assert.equal(neg.components.text_distance, 0.5);
});

// --- acceptance: four repeated equal values remain four occurrences ---------

test('four repeated equal values remain four occurrences (F11)', () => {
  const res = alignPage(
    [0, 1, 2, 3].map((i) => occ(`l${i}`, i, '100', [i * 60, 0, 30 + i * 60, 10])),
    [0, 1, 2, 3].map((i) => occ(`r${i}`, i, '100', [i * 60, 0, 30 + i * 60, 10])),
  );
  // No dedupe: four occurrences on each side, each with its own outcome.
  assert.equal(res.left.length, 4);
  assert.equal(res.right.length, 4);
  for (const s of res.left) assert.equal(s.status, 'unique');
  for (const s of res.right) assert.equal(s.status, 'unique');
  // Four distinct one_to_one matches — never a shared first-match.
  assert.equal(res.matches.length, 4);
  const leftIds = res.matches.map((m) => m.left_occurrence_ids[0]);
  const rightIds = res.matches.map((m) => m.right_occurrence_ids[0]);
  assert.deepEqual([...leftIds].sort(), ['l0', 'l1', 'l2', 'l3']);
  assert.deepEqual([...rightIds].sort(), ['r0', 'r1', 'r2', 'r3']);
  for (const m of res.matches) assert.equal(m.provenance, 'one_to_one');
});

test('a missing duplicate stays unmatched, never absorbed', () => {
  const res = alignPage(
    [0, 1, 2, 3].map((i) => occ(`l${i}`, i, '100', [i * 60, 0, 30 + i * 60, 10])),
    [0, 1, 3].map((i) => occ(`r${i}`, i, '100', [i * 60, 0, 30 + i * 60, 10])),
  );
  assert.equal(statusById(res.left).get('l2'), 'unmatched');
  assert.equal(res.matches.length, 3);
});

// --- acceptance: ambiguous ties abstain -------------------------------------

test('ambiguous ties abstain with every candidate accessible', () => {
  // Five identical readings at identical positions: order alone cannot
  // settle which left maps to which right — the margin must fail.
  const res = alignPage(
    [0, 1, 2, 3, 4].map((i) => occ(`l${i}`, i, 'x', [15, 0, 25, 10])),
    [0, 1, 2, 3, 4].map((i) => occ(`r${i}`, i, 'x', [15, 0, 25, 10])),
  );
  assert.equal(res.matches.length, 0);
  assert.ok(res.ambiguous.length > 0);
  for (const a of res.ambiguous) {
    assert.equal(a.reason, 'tie');
    assert.ok(a.margin < REGION_MATCH_V1.minMargin);
    // Every evaluated candidate pairing stays accessible.
    assert.ok(a.candidates.length >= 2);
    for (const c of a.candidates) {
      assert.ok(c.components.cost !== undefined);
    }
  }
  for (const s of [...res.left, ...res.right]) {
    assert.equal(s.status, 'ambiguous');
  }
});

test('weak agreements abstain rather than guess', () => {
  // One left reading vs a right line it cannot convincingly cover.
  const res = alignPage(
    [occ('l0', 0, 'x', [21, 0, 31, 10])],
    [
      occ('r0', 0, 'x', [9, 0, 19, 10]),
      occ('r1', 1, 'x', [33, 0, 43, 10]),
      occ('r2', 2, 'y', [45, 0, 55, 10]),
      occ('r3', 3, 'z', [57, 0, 67, 10]),
    ],
  );
  assert.equal(res.matches.length, 0);
  assert.ok(res.ambiguous.length >= 1);
  assert.equal(statusById(res.left).get('l0'), 'ambiguous');
  // No first-match-wins: competing candidates remain listed.
  const all = res.ambiguous.flatMap((a) => a.candidates);
  assert.ok(all.length >= 2);
});

test('emission-order inversions abstain as order_conflict', () => {
  // Two left lines bridged into one run; right emits them reversed.
  const res = alignPage(
    [
      occ('l0', 0, 'cat', [0, 0, 20, 10]),
      occ('l1', 1, 'dog', [0, 20, 20, 30]),
      occ('l2', 2, 'bridge', [25, 0, 45, 30]),
    ],
    [
      occ('r0', 0, 'dog', [0, 20, 20, 30]),
      occ('r1', 1, 'cat', [0, 0, 20, 10]),
    ],
  );
  assert.ok(res.ambiguous.some((a) => a.reason === 'order_conflict'));
});

// --- acceptance: page-only inputs never become exact highlights -------------

test('page_only and unknown precision never enter regional matching', () => {
  const res = alignPage(
    [
      occ('lp', 0, 'Total 100', null, 'page_only'),
      occ('lu', 1, 'Total 100', null, 'unknown'),
      occ('l0', 2, 'other', [0, 20, 30, 30]),
    ],
    [
      occ('r0', 0, 'Total 100', [0, 0, 50, 10]),
      occ('r1', 1, 'other', [0, 20, 30, 30]),
    ],
  );
  const left = statusById(res.left);
  const right = statusById(res.right);
  // Identical text cannot rescue missing geometry (I04/I11).
  assert.equal(left.get('lp'), 'page_level');
  assert.equal(left.get('lu'), 'page_level');
  assert.equal(right.get('r0'), 'unmatched');
  assert.ok(res.page_level.left_occurrence_ids.includes('lp'));
  assert.ok(res.page_level.left_occurrence_ids.includes('lu'));
  // The real regional pair still matches normally.
  assert.equal(left.get('l0'), 'unique');
  assert.equal(right.get('r1'), 'unique');
  assert.equal(res.matches.length, 1);
});

test('degenerate polygons are page-level, never fabricated', () => {
  const res = alignPage(
    [occ('l0', 0, 'x', [0, 0, 0, 0])], // zero-area polygon
    [occ('r0', 0, 'x', [0, 0, 10, 10])],
  );
  assert.equal(statusById(res.left).get('l0'), 'page_level');
  assert.equal(res.diagnostics.degenerate_geometry.left, 1);
  assert.equal(res.matches.length, 0);
});

// --- split/merge provenance --------------------------------------------------

test('one left reading merged from two right fragments (F11 split/merge)', () => {
  const res = alignPage(
    [occ('l0', 0, 'New York', [0, 0, 60, 10])],
    [occ('r0', 0, 'New', [0, 0, 28, 10]), occ('r1', 1, 'York', [30, 0, 58, 10])],
  );
  assert.equal(res.matches.length, 1);
  const m = res.matches[0];
  assert.equal(m.provenance, 'one_to_many');
  assert.deepEqual(m.left_occurrence_ids, ['l0']);
  assert.deepEqual(m.right_occurrence_ids, ['r0', 'r1']);
});

// --- order differences (F12) -------------------------------------------------

test('changed column emission order is reported, not judged (F12)', () => {
  const res = alignPage(
    [
      occ('la0', 0, 'A1', [0, 0, 30, 10]),
      occ('la1', 1, 'A2', [0, 20, 30, 30]),
      occ('lb0', 2, 'B1', [200, 0, 230, 10]),
      occ('lb1', 3, 'B2', [200, 20, 230, 30]),
    ],
    [
      // Right reader emits column B first.
      occ('rb0', 0, 'B1', [200, 0, 230, 10]),
      occ('rb1', 1, 'B2', [200, 20, 230, 30]),
      occ('ra0', 2, 'A1', [0, 0, 30, 10]),
      occ('ra1', 3, 'A2', [0, 20, 30, 30]),
    ],
  );
  // All readings still match uniquely — order is reported alongside.
  assert.equal(res.matches.length, 4);
  assert.ok(res.order_differences.length >= 2);
  for (const d of res.order_differences) {
    assert.equal(d.kind, 'emission_order_differs');
    assert.ok(d.match_index < res.matches.length);
  }
  assert.equal(res.diagnostics.order_inversions, res.order_differences.length);
});

// --- ligatures, combining marks, native Unicode (F13/F14) --------------------

test('ligature and combining sequences keep raw values and still align (F13)', () => {
  const res = alignPage(
    [occ('l0', 0, 'ﬁle', [0, 0, 40, 10]), occ('l1', 1, 'café', [0, 20, 50, 30])],
    [occ('r0', 0, 'file', [0, 0, 40, 10]), occ('r1', 1, 'café', [0, 20, 50, 30])],
  );
  assert.equal(res.matches.length, 2);
  // The ligature difference is measured, never erased.
  const lig = res.matches.find((m) => m.left_occurrence_ids[0] === 'l0');
  assert.ok(lig.components.text_distance > 0);
});

test('Arabic, CJK and emoji occurrences align uniquely (F14)', () => {
  const res = alignPage(
    [
      occ('l0', 0, 'مرحبا', [0, 0, 60, 10]),
      occ('l1', 1, '你好', [0, 20, 40, 30]),
      occ('l2', 2, '😀', [0, 40, 20, 50]),
    ],
    [
      occ('r0', 0, 'مرحبا', [0, 0, 60, 10]),
      occ('r1', 1, '你好', [0, 20, 40, 30]),
      occ('r2', 2, '😀', [0, 40, 20, 50]),
    ],
  );
  assert.equal(res.matches.length, 3);
  for (const m of res.matches) assert.equal(m.provenance, 'one_to_one');
});

// --- region scope -------------------------------------------------------------

test('a selected region is a hard scope', () => {
  const res = alignPage(
    [
      occ('l0', 0, 'in', [10, 10, 30, 20]),
      occ('l1', 1, 'out', [300, 10, 320, 20]),
    ],
    [
      occ('r0', 0, 'in', [10, 10, 30, 20]),
      occ('r1', 1, 'out', [300, 10, 320, 20]),
    ],
    { region: { polygon: polygonFor([0, 0, 100, 100]) } },
  );
  assert.ok(res.region_scoped);
  assert.equal(statusById(res.left).get('l0'), 'unique');
  assert.equal(statusById(res.left).get('l1'), 'out_of_scope');
  assert.equal(statusById(res.right).get('r1'), 'out_of_scope');
  assert.equal(res.matches.length, 1);
});

// --- bounded matching: no unbounded quadratic ---------------------------------

test('components over 64 fragments abstain to region-level comparison', () => {
  const left = [];
  const right = [];
  for (let i = 0; i < 70; i++) {
    left.push(occ(`l${i}`, i, `x${i}`, [i * 15, 0, 10 + i * 15, 10]));
    right.push(occ(`r${i}`, i, `x${i}`, [i * 15, 0, 10 + i * 15, 10]));
  }
  const res = alignPage(left, right);
  assert.equal(res.abstentions.length, 1);
  assert.equal(res.abstentions[0].reason, 'component_too_large');
  assert.deepEqual(res.abstentions[0].fragment_counts, [70, 70]);
  for (const s of res.left) assert.equal(s.status, 'abstained');
  for (const s of res.right) assert.equal(s.status, 'abstained');
  assert.equal(res.diagnostics.blocks_abstained, 1);
});

test('work counters stay bounded: local windows, not page-quadratic', () => {
  // 20 isolated duplicate pairs far apart: 20 tiny components, each a
  // bounded solve — the total geometry gate work is a small fraction of
  // the 80x80 span pairs a whole-page pass would imply.
  const left = [];
  const right = [];
  for (let i = 0; i < 20; i++) {
    const x = i * 200;
    left.push(occ(`l${i}`, i, `v${i}`, [x, 0, x + 30, 10]));
    right.push(occ(`r${i}`, i, `v${i}`, [x, 0, x + 30, 10]));
  }
  const res = alignPage(left, right);
  assert.equal(res.matches.length, 20);
  const d = res.diagnostics;
  const wholePagePairs = d.candidate_spans.left * d.candidate_spans.right;
  assert.ok(
    d.span_gate_checks <= wholePagePairs / 4,
    `gate checks ${d.span_gate_checks} vs span pairs ${wholePagePairs}`,
  );
  // Every assignment solve ran on a grid of at most 65x65 cells.
  assert.ok(d.assignments_solved > 0);
  assert.ok(d.assignment_cells <= 65 * 65 * d.assignments_solved);
  assert.ok(d.line_link_checks > 0);
});

// --- input validation and immutability ---------------------------------------

test('duplicate occurrence ids and multi-page inputs are rejected', () => {
  assert.throws(
    () =>
      alignPage(
        [occ('a', 0, 'x', [0, 0, 10, 10]), occ('a', 1, 'x', [0, 20, 10, 30])],
        [occ('r', 0, 'x', [0, 0, 10, 10])],
      ),
    ContractError,
  );
  assert.throws(
    () =>
      alignPage(
        [occ('l0', 0, 'x', [0, 0, 10, 10], 'exact', 0)],
        [occ('r0', 0, 'x', [0, 0, 10, 10], 'exact', 1)],
      ),
    ContractError,
  );
});

test('inputs are never modified by the matcher', () => {
  const left = [occ('l0', 0, 'x  y', [0, 0, 10, 10])];
  const right = [occ('r0', 0, 'x y', [0, 0, 10, 10])];
  const before = JSON.stringify([left, right]);
  alignPage(left, right);
  assert.equal(JSON.stringify([left, right]), before);
});

test('score components are exported as diagnostics, not probability', () => {
  assert.equal(SCORE_SEMANTICS, 'algorithm_diagnostics_not_probability');
  const res = alignPage(
    [occ('l0', 0, 'a', [0, 0, 10, 10])],
    [occ('r0', 0, 'a', [0, 0, 10, 10])],
  );
  const c = res.matches[0].components;
  for (const k of ['geometry_distance', 'order_distance', 'text_distance', 'cost']) {
    assert.ok(typeof c[k] === 'number' && c[k] >= 0 && c[k] <= 1, k);
  }
});
