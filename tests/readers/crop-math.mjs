/**
 * T10 — planCrop arithmetic-level checks (no browser, no OCR engine).
 *
 * Run: node --test tests/readers/crop-math.mjs
 *
 * The spec-suite invariant under test (tests/readers/tesseract.spec.ts
 * 'bounded raster/edge/pixel counts enforced and recorded'):
 *
 *   outWidthPx === floor(cropWidthPx * resizeK)   (and same for height)
 *
 * plus: the ocr_resize Transform record stores the SAME factor
 * (matrix[0] === resizeK), caps still hold, edge-cap behavior is
 * unchanged, and a downscaled plan always records 'downsampled'.
 *
 * Regression history: planCrop previously recorded
 * resizeK = round6(min(outW/cropW, outH/cropH)), which lies below the
 * feasible interval [max(outW/cropW, outH/cropH),
 * min((outW+1)/cropW, (outH+1)/cropH)) whenever the per-axis realized
 * ratios differ — e.g. raster 4896x6336 recorded 0.359059 but
 * floor(4896*0.359059)=1757 while the realized output was 1758.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { planCrop } from '../../packages/readers-tesseract/src/crop.ts';

// Minimal Page — planCrop reads index/rotation/canonical_size_pt; the
// full-page path never touches the region polygon machinery.
const PAGE = {
  index: 0,
  media_box: [0, 0, 612, 792],
  crop_box: [0, 0, 612, 792],
  effective_view_box: [0, 0, 612, 792],
  box_source: 'crop-math test',
  user_unit: 1,
  rotation: 0,
  canonical_size_pt: [612, 792],
  raw_to_canonical_transform_id: 't_cropmath',
  limitations: [],
};

const CAPS = { maxRasterPixels: 4_000_000, maxRasterEdge: 8192 };

function raster(widthPx, heightPx, scalePxPerPt = 8) {
  return {
    rasterId: `ras_${widthPx}x${heightPx}`,
    renderReaderId: 'crop-math-render',
    scalePxPerPt,
    widthPx,
    heightPx,
  };
}

function plan(widthPx, heightPx, bounds = CAPS, opts = {}) {
  return planCrop({
    page: PAGE,
    raster: raster(widthPx, heightPx, opts.scale ?? 8),
    checkId: 'cropmath',
    region: opts.region ?? null,
    bounds,
    ...(opts.padMinPx !== undefined ? { padMinPx: opts.padMinPx } : {}),
    ...(opts.padHeightRatio !== undefined
      ? { padHeightRatio: opts.padHeightRatio }
      : {}),
  });
}

/** Every invariant the recorded resize must satisfy. */
function assertRecordedResize(plan, bounds, ctx) {
  const resize = plan.transforms.find((t) => t.operation === 'ocr_resize');
  assert.ok(resize, `${ctx}: ocr_resize transform present`);
  // Same realized factor in the plan field and the transform record.
  assert.equal(
    resize.matrix[0],
    plan.resizeK,
    `${ctx}: recorded matrix k === resizeK`,
  );
  if (plan.resizeK < 1) {
    // floor-realizes the recorded output on BOTH axes.
    assert.equal(
      Math.floor(plan.cropWidthPx * plan.resizeK),
      plan.outWidthPx,
      `${ctx}: floor(cropW*resizeK) === outWidthPx`,
    );
    assert.equal(
      Math.floor(plan.cropHeightPx * plan.resizeK),
      plan.outHeightPx,
      `${ctx}: floor(cropH*resizeK) === outHeightPx`,
    );
    assert.ok(
      plan.outWidthPx * plan.outHeightPx <= bounds.maxRasterPixels &&
        Math.max(plan.outWidthPx, plan.outHeightPx) <= bounds.maxRasterEdge,
      `${ctx}: realized output inside caps`,
    );
    assert.ok(
      plan.limitations.join(' ').includes('downsampled'),
      `${ctx}: downsampled limitation recorded`,
    );
    assert.ok(resize.matrix[0] < 1, `${ctx}: ocr_resize matrix < 1`);
  } else {
    assert.equal(plan.resizeK, 1, `${ctx}: unscaled factor is exactly 1`);
    assert.equal(plan.outWidthPx, plan.cropWidthPx, `${ctx}: outW = cropW`);
    assert.equal(plan.outHeightPx, plan.cropHeightPx, `${ctx}: outH = cropH`);
  }
}

test('spec case: 4896x6336 raster over 4M-pixel cap reproduces exactly', () => {
  const p = plan(4896, 6336);
  assert.equal(p.outWidthPx, 1758);
  assert.equal(p.outHeightPx, 2275);
  assertRecordedResize(p, CAPS, '4896x6336');
  // The recorded factor is inside the feasible interval.
  const lo = Math.max(p.outWidthPx / p.cropWidthPx, p.outHeightPx / p.cropHeightPx);
  const hi = Math.min(
    (p.outWidthPx + 1) / p.cropWidthPx,
    (p.outHeightPx + 1) / p.cropHeightPx,
  );
  assert.ok(p.resizeK >= lo && p.resizeK < hi, 'resizeK inside interval');
});

test('edge cap 9000x120 records an exactly-reproducing factor', () => {
  const p = plan(9000, 120);
  // Realized output at the edge cap — the recorded factor reproduces it.
  assert.equal(p.outWidthPx, 8192);
  assert.equal(p.outHeightPx, 109);
  assertRecordedResize(p, CAPS, '9000x120');
});

test('asymmetric pixel cap 8000x999', () => {
  assertRecordedResize(plan(8000, 999), CAPS, '8000x999');
});

test('extreme edge cap 50000x100', () => {
  const p = plan(50000, 100);
  assertRecordedResize(p, CAPS, '50000x100');
});

test('region+padded crop under a tight pixel cap', () => {
  // Canonical rect [100,100]-[300,200] at 2px/pt -> [200,200]-[600,400]
  // raster px; pad = max(8, ceil(200*0.1)) = 20 -> crop 440x240.
  const region = {
    id: 'reg_tight',
    polygon: [
      [100, 100],
      [300, 100],
      [300, 200],
      [100, 200],
    ],
    label: 'tight-cap region',
  };
  const bounds = { maxRasterPixels: 50_000, maxRasterEdge: 8192 };
  const p = planCrop({
    page: PAGE,
    raster: raster(1224, 1584, 2),
    checkId: 'cropmath',
    region,
    bounds,
  });
  assert.equal(p.cropWidthPx, 440);
  assert.equal(p.cropHeightPx, 240);
  assert.equal(p.paddingPx, 20);
  assertRecordedResize(p, bounds, 'region 440x240/50k');
});

test('sub-precision interval: lower-edge candidate yields 43x21 within cap', () => {
  // crop 8192x4000 with a 903-px cap realizes k≈0.0052495 -> ideal
  // 43x20; the feasible interval [0.005249023,0.00525) holds NO multiple
  // of 1e-6, so no representable factor keeps the ideal size. The
  // lower-edge candidate 0.00525 (ceil of the interval's lower bound)
  // floor-derives 43x21 = 903 px — legitimately larger than the ideal
  // height, exactly at the pixel cap, still floor-exact and recorded.
  const bounds = { maxRasterPixels: 903, maxRasterEdge: 8192 };
  const p = plan(8192, 4000, bounds);
  assertRecordedResize(p, bounds, '8192x4000/903');
  assert.equal(p.outWidthPx * p.outHeightPx <= 903, true);
});

test('no downscale needed: factor is exactly 1, output equals crop', () => {
  const p = plan(1200, 900);
  assertRecordedResize(p, CAPS, '1200x900');
});

test('degenerate region polygon is rejected, never guessed', () => {
  assert.throws(
    () =>
      plan(4896, 6336, CAPS, {
        region: {
          id: 'reg_degenerate',
          polygon: [
            [5, 5],
            [5, 5],
            [5, 5],
          ],
          label: 'zero-area',
        },
      }),
    /degenerate raster bounds|no usable polygon/,
  );
});

test('region clipped to raster records the clip', () => {
  // Region beyond the raster's top-left corner: padding clipped to 0,0.
  const region = {
    id: 'reg_corner',
    polygon: [
      [-5, -5],
      [30, -5],
      [30, 30],
      [-5, 30],
    ],
    label: 'corner',
  };
  const p = plan(1200, 900, CAPS, { region, scale: 2 });
  assert.equal(p.cropX, 0);
  assert.equal(p.cropY, 0);
  assert.ok(p.limitations.join(' ').includes('crop_padding_clipped'));
});

// --- deterministic fuzz: realistic + adversarial dims ----------------

/** mulberry32 — fixed seed, no flakiness. */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

test('floor-equality fuzz over realistic and adversarial dims', () => {
  const rasters = [];
  // Realistic: letter/A4/legal pages at common render DPIs.
  for (const [pw, ph] of [
    [612, 792],
    [595, 842],
    [612, 1008],
  ]) {
    for (const dpi of [72, 96, 144, 150, 200, 300, 450, 600]) {
      const s = dpi / 72;
      rasters.push([Math.round(pw * s), Math.round(ph * s), s]);
    }
  }
  // Adversarial edges: caps, just over/under, extreme aspect ratios.
  rasters.push(
    [4896, 6336, 8],
    [9000, 120, 8],
    [50000, 100, 8],
    [8192, 8192, 8],
    [8193, 100, 8],
    [8191, 8191, 8],
    [12000, 7000, 8],
    [4000, 4000, 8],
    [6324, 4914, 8],
    [2, 2, 1],
    [1, 1, 1],
    [7, 5, 1],
  );
  const boundsSet = [
    CAPS,
    { maxRasterPixels: 1_000_000, maxRasterEdge: 4096 },
    { maxRasterPixels: 250_000, maxRasterEdge: 2048 },
    { maxRasterPixels: 50_000, maxRasterEdge: 8192 },
    { maxRasterPixels: 903, maxRasterEdge: 8192 },
    { maxRasterPixels: 4_000_000, maxRasterEdge: 1024 },
  ];
  let checked = 0;
  let downscaled = 0;
  for (const [w, h, s] of rasters) {
    for (const b of boundsSet) {
      const p = planCrop({
        page: PAGE,
        raster: raster(w, h, s),
        checkId: 'fuzz',
        region: null,
        bounds: b,
      });
      assertRecordedResize(p, b, `raster ${w}x${h} caps ${b.maxRasterPixels}/${b.maxRasterEdge}`);
      checked += 1;
      if (p.resizeK < 1) downscaled += 1;
    }
  }
  assert.ok(checked > 100, `fuzz covered ${checked} plans`);
  assert.ok(downscaled > 50, `fuzz covered ${downscaled} downscales`);
});

test('floor-equality fuzz over seeded regions on a fixed page', () => {
  const rand = rng(0x10c0de);
  const boundsSet = [
    CAPS,
    { maxRasterPixels: 250_000, maxRasterEdge: 2048 },
    { maxRasterPixels: 50_000, maxRasterEdge: 8192 },
  ];
  let checked = 0;
  let downscaled = 0;
  for (let i = 0; i < 200; i += 1) {
    const x = rand() * 600;
    const y = rand() * 780;
    const w = 1 + rand() * 200;
    const h = 1 + rand() * 120;
    const region = {
      id: `reg_fuzz_${i}`,
      polygon: [
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h],
      ],
      label: 'fuzz',
    };
    const b = boundsSet[i % boundsSet.length];
    const p = planCrop({
      page: PAGE,
      raster: raster(4896, 6336, 8),
      checkId: `fuzz_${i}`,
      region,
      bounds: b,
    });
    assertRecordedResize(p, b, `region ${i} -> crop ${p.cropWidthPx}x${p.cropHeightPx}`);
    checked += 1;
    if (p.resizeK < 1) downscaled += 1;
  }
  assert.equal(checked, 200);
  assert.ok(downscaled > 20, `region fuzz covered ${downscaled} downscales`);
});

test('fractional-destination clipping is recorded in output px', () => {
  // 4896x6336 @4M -> k=0.359069, realized 1758x2275; the drawn
  // destination is 1758.001824x2275.061184 -> clips 0.001824 right and
  // 0.061184 bottom output px (each in [0,1)).
  const p = plan(4896, 6336);
  assert.equal(p.resizeK, 0.359069);
  const [clipR, clipB] = p.resizeClipPx;
  assert.ok(Math.abs(clipR - 0.001824) < 1e-9, `right clip ${clipR}`);
  assert.ok(Math.abs(clipB - 0.061184) < 1e-9, `bottom clip ${clipB}`);
  assert.ok(clipR >= 0 && clipR < 1 && clipB >= 0 && clipB < 1);
  assert.ok(p.limitations.join(' ').includes('ocr_resize_clipped'));
  // Consistency: clip amounts equal frac(crop * resizeK) by definition.
  assert.equal(p.cropWidthPx * p.resizeK - p.outWidthPx, clipR);
  assert.equal(p.cropHeightPx * p.resizeK - p.outHeightPx, clipB);

  // Mixed edge: right destination is exactly 8192 (clip 0) while the
  // bottom clips 0.384 — the limitation fires on the bottom amount.
  const exact = plan(50000, 100); // k=0.16384: 50000*k=8192 exactly
  assert.equal(exact.resizeClipPx[0], 0);
  assert.ok(Math.abs(exact.resizeClipPx[1] - 0.384) < 1e-9);
  assert.ok(exact.limitations.join(' ').includes('ocr_resize_clipped'));

  // No downscale -> [0,0] and no clipping limitation.
  const none = plan(1200, 900);
  assert.deepEqual(none.resizeClipPx, [0, 0]);
  assert.ok(!none.limitations.join(' ').includes('ocr_resize_clipped'));
});

test('transform chain shape is preserved', () => {
  const p = plan(4896, 6336);
  assert.deepEqual(
    p.transforms.map((t) => t.operation),
    ['raster_scale', 'crop_translation', 'ocr_resize'],
  );
  assert.equal(p.transforms[1].to_space, `ocr:${p.ocrId}`);
  assert.equal(p.transforms[2].to_space, `ocr:${p.ocrId}`);
});
