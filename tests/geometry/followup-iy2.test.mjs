import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  boxPolygon, checkedInverse, clipToView, ContractError, identity,
  inversePairError, makeTransform, mapPoint, pointInPolygon,
} from '../../packages/geometry/src/index.ts';

const transform = (extent) => makeTransform({
  id: 't_extent', pageIndex: 0, fromSpace: 'a', toSpace: 'b',
  matrix: identity(), operation: 'viewport', precision: 'exact',
  source: 'extent regression', extent,
});
const geometryError = (code) => (error) =>
  error instanceof ContractError && error.code === code;

for (const [name, box] of Object.entries({
  left: [-10, 10, 0, 20], right: [100, 10, 110, 20],
  top: [10, -10, 20, 0], bottom: [10, 80, 20, 90],
  corner: [100, 80, 110, 90],
})) {
  test(`zero-area ${name} contact is outside and preserves source`, () => {
    const polygon = boxPolygon(box);
    const before = structuredClone(polygon);
    assert.deepEqual(clipToView(polygon, [100, 80]), {
      status: 'outside', clipped: null, source: before, fullyVisible: false,
    });
    assert.deepEqual(polygon, before);
  });
}

test('clipping keeps positive overlap and rejects invalid view sizes', () => {
  assert.equal(clipToView(boxPolygon([0, 0, 100, 80]), [100, 80]).status, 'inside');
  assert.equal(clipToView(boxPolygon([99, 10, 110, 20]), [100, 80]).status, 'partial');
  assert.equal(clipToView(boxPolygon([101, 10, 110, 20]), [100, 80]).status, 'outside');
  assert.equal(clipToView([], [100, 80]).clipped, null);
  for (const size of [[0, 80], [-1, 80], [100, NaN], [Infinity, 80]]) {
    assert.throws(() => clipToView(boxPolygon([0, 0, 1, 1]), size), geometryError('GEOMETRY'));
  }
});

for (const [name, run] of Object.entries({
  inversePairError: (extent) => inversePairError(identity(), identity(), extent),
  checkedInverse: (extent) => checkedInverse(identity(), extent),
  makeTransform: transform,
})) {
  test(`${name} rejects an explicit empty extent`, () => {
    assert.throws(() => run([]), geometryError('TRANSFORM'));
  });
  test(`${name} rejects malformed probe points`, () => {
    for (const point of [[0], [0, 1, 2], ['0', 0]]) {
      assert.throws(() => run([point]), geometryError('TYPE'));
    }
    for (const point of [[NaN, 0], [0, Infinity]]) {
      assert.throws(() => run([point]), geometryError('NONFINITE'));
    }
  });
}

test('usable extents and omitted default keep valid inverse contracts', () => {
  assert.deepEqual(transform(undefined).inverse, identity());
  assert.deepEqual(transform([[0, 0]]).inverse, identity());
  assert.deepEqual(checkedInverse([2, 0, 0, 4, 8, 12], [[0, 0], [100, 80]]),
    [0.5, -0, -0, 0.25, -4, -3]);
  assert.equal(inversePairError(identity(), [1, 0, 0, 1, 1, 0], [[0, 0]]), 1);
  assert.throws(() => checkedInverse([0, 0, 0, 0, 0, 0], [[0, 0]]), geometryError('TRANSFORM'));
});

test('mapPoint applies noncommuting matrices right to left without mutating input', () => {
  const point = [2, 3];
  assert.deepEqual(mapPoint(point, [1, 0, 0, 1, 10, -5], [2, 0, 0, 4, 0, 0]), [14, 7]);
  assert.deepEqual(mapPoint(point), point);
  assert.notEqual(mapPoint(point), point);
  assert.deepEqual(point, [2, 3]);
});

test('pointInPolygon uses polygon shape, winding, and explicit edge tolerance', () => {
  const triangle = [[0, 0], [10, 0], [0, 10]];
  for (const polygon of [triangle, [...triangle].reverse()]) {
    assert.equal(pointInPolygon([2, 2], polygon), true);
    assert.equal(pointInPolygon([8, 8], polygon), false);
    assert.equal(pointInPolygon([5, 5], polygon, 0.01), true);
    assert.equal(pointInPolygon([-0.005, 2], polygon, 0.01), true);
    assert.equal(pointInPolygon([-0.02, 2], polygon, 0.01), false);
    assert.equal(pointInPolygon([0, 0], polygon, 0.01), true);
  }
  assert.equal(pointInPolygon([0, 0], []), false);
});
