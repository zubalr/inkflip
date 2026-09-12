/**
 * T10 reproduction: planCrop records an ocr_resize factor that must
 * reproduce the realized integer output under floor() on BOTH axes and
 * must equal the factor stored in the ocr_resize Transform record
 * (spec assertion: outWidthPx === floor(cropWidthPx * resizeK)).
 *
 * Run: node artifacts/tasks/T10/repro-planCrop.mjs
 * Exit 0 = recorded factor reproduces realized output on every case.
 * Exit 1 = defect reproduced (recorded-vs-realized mismatch printed).
 */
import { planCrop } from '../../../packages/readers-tesseract/src/crop.ts';

// Minimal Page — planCrop reads index/rotation/canonical_size_pt only;
// region:null cases never touch the polygon path. F03 scan page.
const page = {
  index: 0,
  media_box: [0, 0, 612, 792],
  crop_box: [0, 0, 612, 792],
  effective_view_box: [0, 0, 612, 792],
  box_source: 'repro',
  user_unit: 1,
  rotation: 0,
  canonical_size_pt: [612, 792],
  raw_to_canonical_transform_id: 't_repro',
  limitations: [],
};

const CAPS = { maxRasterPixels: 4_000_000, maxRasterEdge: 8192 };

function raster(widthPx, heightPx, scalePxPerPt = 8) {
  return {
    rasterId: `ras_${widthPx}x${heightPx}`,
    renderReaderId: 'repro-render',
    scalePxPerPt,
    widthPx,
    heightPx,
  };
}

const cases = [
  {
    name: 'spec case: F03 raster 4896x6336 over 4M-pixel cap',
    raster: raster(4896, 6336),
    region: null,
    bounds: CAPS,
  },
  {
    name: 'edge cap: 9000x120 (spec synthetic_edge)',
    raster: raster(9000, 120),
    region: null,
    bounds: CAPS,
  },
  {
    name: 'pixel cap asymmetric: 8000x999',
    raster: raster(8000, 999),
    region: null,
    bounds: CAPS,
  },
  {
    name: 'extreme edge cap: 50000x100',
    raster: raster(50000, 100),
    region: null,
    bounds: CAPS,
  },
  {
    name: 'control symmetric ratios: 8000x1000',
    raster: raster(8000, 1000),
    region: null,
    bounds: CAPS,
  },
  {
    // Region path: polygon [200,200]-[600,400] raster px after scale 2,
    // pad max(8, 20) = 20 -> crop 440x240; tight 50k cap forces downscale.
    name: 'region+padded crop, tight pixel cap (440x240 over 50k)',
    raster: raster(1224, 1584, 2),
    region: {
      id: 'reg_repro',
      polygon: [
        [100, 100],
        [300, 100],
        [300, 200],
        [100, 200],
      ],
      label: 'repro region',
    },
    bounds: { maxRasterPixels: 50_000, maxRasterEdge: 8192 },
  },
];

let failures = 0;
for (const c of cases) {
  const plan = planCrop({
    page,
    raster: c.raster,
    checkId: 'repro',
    region: c.region,
    bounds: c.bounds,
  });
  const wReal = Math.floor(plan.cropWidthPx * plan.resizeK);
  const hReal = Math.floor(plan.cropHeightPx * plan.resizeK);
  const resize = plan.transforms.find((t) => t.operation === 'ocr_resize');
  const matrixK = resize ? resize.matrix[0] : null;
  const okW = wReal === plan.outWidthPx;
  const okH = hReal === plan.outHeightPx;
  const okRec = matrixK === plan.resizeK;
  const okCaps =
    plan.outWidthPx * plan.outHeightPx <= c.bounds.maxRasterPixels &&
    Math.max(plan.outWidthPx, plan.outHeightPx) <= c.bounds.maxRasterEdge;
  const ok = okW && okH && okRec && okCaps;
  if (!ok) failures += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${c.name}`);
  console.log(
    `     crop ${plan.cropWidthPx}x${plan.cropHeightPx} -> out ${plan.outWidthPx}x${plan.outHeightPx}` +
      ` resizeK=${plan.resizeK} matrix[0]=${matrixK}`,
  );
  console.log(
    `     floor(cropW*resizeK)=${wReal} (${okW ? '==' : '!='} ${plan.outWidthPx})` +
      `  floor(cropH*resizeK)=${hReal} (${okH ? '==' : '!='} ${plan.outHeightPx})` +
      `  record==resizeK:${okRec} caps:${okCaps}`,
  );
}
console.log(failures === 0 ? 'ALL OK' : `${failures} case(s) misrecorded`);
process.exit(failures === 0 ? 0 : 1);
