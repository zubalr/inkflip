/**
 * T10 — Browser pixel regression for the recorded OCR resize factor.
 *
 * LIGHT suite: bundles `@inkflip/readers-tesseract` (+ geometry/contracts)
 * with `bun build --target browser` and drives the REAL adapter inside
 * Chromium — plan -> raster -> planCrop -> cropToBlob -> engine boundary —
 * but the engine seam is a stub worker that captures the produced PNG
 * blob and returns an empty completed hierarchy. NO tesseract.js module,
 * worker, core wasm, or traineddata is loaded anywhere in this file.
 *
 * Why pixels: the recorded `ocr_resize` factor must be the factor the
 * renderer actually draws. The crop canvas is integer-sized
 * (floor(crop*k) x floor(crop*k)) but drawImage's destination is the
 * fractional crop*k x crop*k — the same scale the transform records —
 * so the sub-pixel right/bottom remainder is clipped and reported via
 * `ocr_resize_clipped` / CropPlan.resizeClipPx.
 *
 * The 49x80 fixture (columns x<42 black, x>=42 red, fully opaque) with a
 * 50-px cap plans k=0.1125 -> 5x9 output. Under the recorded-factor draw,
 * output pixel (4,4)'s center maps back to source x=40 (black). Under
 * the old integer-stretch draw (dest 5x9 => x-scale 5/49) the same pixel
 * samples source x≈44.1 — red. The decoded bytes therefore prove which
 * geometry the canvas really applied.
 *
 * Covers both production source branches of cropToBlob:
 *   - image instanceof ImageData (putImageData into a staging canvas)
 *   - image as CanvasImageSource (direct drawImage)
 * plus a no-resize control and a nonzero crop-origin case.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const TESS_PKG = join(ROOT, 'packages', 'readers-tesseract', 'src');
const GEOM_PKG = join(ROOT, 'packages', 'geometry', 'src');
const CONTRACTS_PKG = join(ROOT, 'packages', 'contracts', 'src');

const PAGE_HTML = `<!doctype html>
<meta charset="utf-8">
<title>inkflip t10 crop-pixel harness</title>
<script type="module">
  globalThis.__pxready = false;
  globalThis.__pxerror = null;
  import('/bundle.js')
    .then(() => { globalThis.__pxready = true; })
    .catch((e) => { globalThis.__pxerror = String(e && e.stack || e); });
</script>
`;

interface Harness {
  server: Server;
  base: string;
  tmp: string;
  served: string[];
}

/**
 * The in-page harness. A stub TesseractEngineModule satisfies the
 * adapter's injected-engine seam; its worker captures the exact PNG
 * Blob produced by cropToBlob, which is then decoded back to pixels
 * with createImageBitmap so assertions run on real browser output —
 * never on draw-call arguments.
 */
function entrySource(): string {
  return `
import * as adapter from ${JSON.stringify(join(TESS_PKG, 'index.ts'))};
import * as geom from ${JSON.stringify(join(GEOM_PKG, 'index.ts'))};
import * as contracts from ${JSON.stringify(join(CONTRACTS_PKG, 'index.ts'))};

const state = { n: 0 };

function hex(bytes) {
  let s = '';
  for (const b of bytes) s += b.toString(16).padStart(2, '0');
  return s;
}

// Honest stub model: real bytes, real sha256, declared in the model
// identity so prepare() verifies what it fetched — but nothing OCR-
// shaped is ever loaded (fetchImpl serves these bytes only).
const STUB_MODEL_BYTES = new Uint8Array(256);
for (let i = 0; i < STUB_MODEL_BYTES.length; i++) {
  STUB_MODEL_BYTES[i] = (i * 31 + 7) & 0xff;
}
const MODEL = {
  id: 'stub-ocr-model',
  version: '0',
  sha256: hex(contracts.sha256(STUB_MODEL_BYTES)),
  byteLength: STUB_MODEL_BYTES.length,
  sourcePath: '/stub/eng.traineddata',
  lang: 'eng',
  license: 'Apache-2.0',
  cachePath: 'inkflip/stub',
};
const PATHS = {
  workerPath: '/stub/worker.js',
  corePath: '/stub/core/',
  langPath: '/stub/lang/',
  cachePath: 'inkflip/stub',
};

// 49x80 RGBA, fully opaque: columns x<42 black, x>=42 red.
const FIXTURE_W = 49;
const FIXTURE_H = 80;
const SEAM_X = 42;

function fixtureImageData() {
  const d = new Uint8ClampedArray(FIXTURE_W * FIXTURE_H * 4);
  for (let y = 0; y < FIXTURE_H; y++) {
    for (let x = 0; x < FIXTURE_W; x++) {
      const i = (y * FIXTURE_W + x) * 4;
      const red = x >= SEAM_X;
      d[i] = red ? 255 : 0;
      d[i + 1] = 0;
      d[i + 2] = 0;
      d[i + 3] = 255;
    }
  }
  return new ImageData(d, FIXTURE_W, FIXTURE_H);
}

function fixtureCanvas() {
  const c = document.createElement('canvas');
  c.width = FIXTURE_W;
  c.height = FIXTURE_H;
  c.getContext('2d').putImageData(fixtureImageData(), 0, 0);
  return c;
}

// The engine boundary stub: capture the produced image, complete with
// an empty blocks hierarchy (honest unreadable_pixels, never a fake
// recognition). No worker/core/model is constructed.
function stubEngine(captured) {
  return {
    OEM: { LSTM_ONLY: 1 },
    PSM: { SINGLE_BLOCK: '6', SINGLE_LINE: '7' },
    createWorker: (langs, oem, options) => {
      captured.workerOptions = options;
      return Promise.resolve({
        recognize: (image, options2, output, jobId) => {
          captured.image = image;
          captured.recognizeOptions = options2;
          captured.output = output;
          return Promise.resolve({
            jobId: jobId || 'j_stub',
            data: {
              text: null,
              blocks: [],
              confidence: null,
              psm: '6',
              oem: 'LSTM_ONLY',
              version: 'stub',
            },
          });
        },
        terminate: () => Promise.resolve(),
      });
    },
  };
}

async function decodePng(blob) {
  const bmp = await createImageBitmap(blob);
  const oc = new OffscreenCanvas(bmp.width, bmp.height);
  const cx = oc.getContext('2d');
  cx.drawImage(bmp, 0, 0);
  const d = cx.getImageData(0, 0, bmp.width, bmp.height);
  return {
    width: bmp.width,
    height: bmp.height,
    data: Array.from(d.data),
  };
}

const api = {
  adapter,
  geom,
  contracts,

  /**
   * Drive the real adapter end to end with the stub engine. Returns
   * JSON-safe output plus the decoded PNG pixels captured at the
   * engine boundary. unmapPt (optional) is an output-pixel point
   * mapped back to canonical space through the recorded chain.
   */
  async runCase(input, unmapPt) {
    const captured = {};
    const built = geom.buildPage({
      index: 0,
      viewBox: [0, 0, FIXTURE_W, FIXTURE_H],
      userUnit: 1,
      rotation: 0,
      boxSource: 'synthetic 49x80 fixture; UserUnit 1; /Rotate 0',
    });
    const image = input.branch === 'imagedata'
      ? fixtureImageData()
      : fixtureCanvas();
    const raster = {
      rasterId: 'px_' + input.branch + '_' + (++state.n),
      renderReaderId: 'synthetic-fixture',
      scalePxPerPt: 1,
      widthPx: FIXTURE_W,
      heightPx: FIXTURE_H,
      image,
      built,
    };
    const reader = new adapter.TesseractOcrReader({
      engine: stubEngine(captured),
      engineVersion: '0.0.0-stub',
      coreBuild: 'stub',
      model: MODEL,
      paths: PATHS,
      assetHashes: [],
      profile: 'desktop',
      runKey: 't10-pixels',
      rasterSource: () => Promise.resolve(raster),
      budget: input.budget,
      imageSmoothingEnabled: input.smoothing,
      hooks: {
        fetchImpl: () =>
          Promise.resolve(new Response(STUB_MODEL_BYTES.slice())),
        idbFactory: null,
        online: () => true,
      },
    });
    const docSha = hex(contracts.sha256(new Uint8Array([49, 80, 4, 255])));
    const handle = await reader.open({ documentSha256: docSha, generation: 1 });
    const sel = {
      pageIndex: 0,
      purpose: input.region ? 'region' : 'page',
      ...(input.region ? { region: input.region } : {}),
    };
    const checks = reader.plan(handle, [sel]);
    const check = checks[0];
    const out = await reader.extract(handle, check, () => {});

    let decoded = null;
    let imageClass = 'other';
    if (captured.image instanceof Blob) {
      imageClass = 'Blob:' + captured.image.type;
      decoded = await decodePng(captured.image);
    } else if (captured.image !== undefined) {
      imageClass = String(
        captured.image && captured.image.constructor
          ? captured.image.constructor.name
          : typeof captured.image,
      );
    }

    const ocrResize = out.transforms.find((t) => t.operation === 'ocr_resize');
    const cropT = out.transforms.find((t) => t.operation === 'crop_translation');
    const rasterS = out.transforms.find((t) => t.operation === 'raster_scale');
    // Inverse-map an output-pixel center back to canonical space through
    // the recorded chain (k=1 paths too): raster = ocr/k + crop origin.
    const k = out.crop.resizeK;
    const inv = geom.ocrToCanonical(
      built,
      raster.scalePxPerPt,
      [out.crop.cropX, out.crop.cropY],
      [k, k],
    );
    const unmapped = unmapPt ? geom.apply(inv, unmapPt) : null;

    await reader.close(handle);
    return {
      status: out.check.status,
      reason: out.check.reason,
      crop: out.crop,
      limitations: out.limitations,
      ocrResizeMatrix: ocrResize ? ocrResize.matrix : null,
      ocrResizeInverse: ocrResize ? ocrResize.inverse : null,
      cropTranslateMatrix: cropT ? cropT.matrix : null,
      rasterScaleMatrix: rasterS ? rasterS.matrix : null,
      transformOps: out.transforms.map((t) => t.operation),
      imageClass,
      decoded,
      diagnostics: out.diagnostics,
      unmapped,
    };
  },
};

globalThis.__px = api;
`;
}

async function startHarness(): Promise<Harness> {
  const tmp = mkdtempSync(join(tmpdir(), 'inkflip-t10px-'));
  const entry = join(tmp, 'entry.mjs');
  const bundlePath = join(tmp, 'bundle.js');
  writeFileSync(entry, entrySource());
  execFileSync(
    'bun',
    ['build', '--target', 'browser', '--format', 'esm', '--outfile', bundlePath, entry],
    { cwd: ROOT, stdio: 'pipe' },
  );

  const served: string[] = [];
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? '/', 'http://127.0.0.1');
    const pathname = decodeURIComponent(url.pathname);
    served.push(`${req.method} ${pathname}`);
    const send = (status: number, body: Buffer | string, type = 'application/octet-stream') => {
      res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store' });
      res.end(body);
    };
    try {
      if (pathname === '/' || pathname === '/px.html') {
        return send(200, PAGE_HTML, 'text/html; charset=utf-8');
      }
      if (pathname === '/bundle.js') {
        return send(200, readFileSync(bundlePath), 'text/javascript; charset=utf-8');
      }
      return send(404, 'not found');
    } catch (error) {
      return send(500, String(error));
    }
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (address === null || typeof address !== 'object') throw new Error('harness bind failed');
  return { server, base: `http://127.0.0.1:${address.port}`, tmp, served };
}

let harness: Harness;

test.describe.configure({ timeout: 120_000 });

test.beforeAll(async () => {
  harness = await startHarness();
});

test.afterAll(() => {
  harness.server.close();
  rmSync(harness.tmp, { recursive: true, force: true });
});

test.beforeEach(async ({ page }) => {
  page.on('pageerror', (error) => {
    console.log(`[pageerror] ${error}`);
  });
  await page.goto(`${harness.base}/px.html`);
  await page.waitForFunction(
    () =>
      (globalThis as { __pxready?: boolean; __pxerror?: unknown }).__pxready ||
      (globalThis as { __pxerror?: unknown }).__pxerror,
  );
  const bootError = await page.evaluate(
    () => (globalThis as { __pxerror?: unknown }).__pxerror ?? null,
  );
  expect(bootError, 'module boot failure').toBeNull();
});

/** Decode helper: RGBA at pixel (x,y) of a decoded image record. */
function px(
  decoded: { width: number; data: number[] },
  x: number,
  y: number,
): number[] {
  const i = (y * decoded.width + x) * 4;
  return decoded.data.slice(i, i + 4);
}

const BLACK = [0, 0, 0, 255];
const RED = [255, 0, 0, 255];

/** Shared assertions for the 49x80 -> 5x9 downscale case. */
function expectDownscaledFixture(out: {
  status: string;
  reason: string | null;
  imageClass: string;
  decoded: { width: number; height: number; data: number[] } | null;
  crop: {
    cropX: number;
    cropY: number;
    cropWidthPx: number;
    cropHeightPx: number;
    resizeK: number;
    resizeClipPx: readonly [number, number];
    outWidthPx: number;
    outHeightPx: number;
    regionPx: readonly number[] | null;
    paddingPx: number;
  };
  limitations: string[];
  ocrResizeMatrix: number[] | null;
  diagnostics: { downscaled: boolean; pixelsOcr: number };
  unmapped: number[];
}): void {
  expect(out.status).toBe('completed');
  expect(out.reason).toBe('unreadable_pixels');
  // The engine boundary received a real encoded PNG blob.
  expect(out.imageClass).toBe('Blob:image/png');
  expect(out.decoded).not.toBeNull();
  const decoded = out.decoded!;
  expect(decoded.width).toBe(5);
  expect(decoded.height).toBe(9);

  // Plan/record identity: recorded factor is the rendered factor.
  expect(out.crop.cropX).toBe(0);
  expect(out.crop.cropY).toBe(0);
  expect(out.crop.cropWidthPx).toBe(49);
  expect(out.crop.cropHeightPx).toBe(80);
  expect(out.crop.resizeK).toBe(0.1125);
  expect(out.crop.outWidthPx).toBe(5);
  expect(out.crop.outHeightPx).toBe(9);
  expect(out.diagnostics.downscaled).toBe(true);
  expect(out.diagnostics.pixelsOcr).toBe(45);
  expect(out.ocrResizeMatrix).not.toBeNull();
  expect(out.ocrResizeMatrix![0]).toBe(0.1125);
  expect(out.ocrResizeMatrix![3]).toBe(0.1125);

  // Fractional-destination clipping: 49*0.1125=5.5125 -> right 0.5125;
  // 80*0.1125=9 exactly -> bottom 0. Decision is on the actual
  // difference, not on storage-rounded values.
  expect(Math.abs(out.crop.resizeClipPx[0] - 0.5125)).toBeLessThan(1e-9);
  expect(out.crop.resizeClipPx[1]).toBe(0);
  expect(out.limitations.join(' ')).toContain('ocr_resize_clipped');
  expect(out.limitations.join(' ')).toContain('downsampled');

  // Decoded bytes: every output pixel samples source x<=40 — the red
  // seam at x>=42 is unreachable under k=0.1125, so the whole image is
  // opaque black. The old integer-stretch draw (x-scale 5/49) would
  // sample x≈44.1 for column 4 — red — so this byte check catches it.
  for (let y = 0; y < decoded.height; y++) {
    for (let x = 0; x < decoded.width; x++) {
      expect(px(decoded, x, y), `pixel (${x},${y})`).toEqual(BLACK);
    }
  }

  // Inverse mapping of output pixel (4,4)'s center lands inside source
  // pixel [40,41) x [40,41) — inside the black region, before the seam.
  expect(out.unmapped[0]).toBeGreaterThanOrEqual(39.999999);
  expect(out.unmapped[0]).toBeLessThan(41);
  expect(out.unmapped[1]).toBeGreaterThanOrEqual(39.999999);
  expect(out.unmapped[1]).toBeLessThan(41);
}

test('recorded resize factor drives actual rendering (ImageData source branch)', async ({
  page,
}) => {
  const out = await page.evaluate(() =>
    (
      globalThis as {
        __px: {
          runCase: (
            i: unknown,
            pt?: number[],
          ) => Promise<Record<string, never>>;
        };
      }
    ).__px.runCase(
      {
        branch: 'imagedata',
        smoothing: false,
        budget: { maxRasterPixels: 50, maxRasterEdge: 8192 },
      },
      [4.5, 4.5],
    ),
  );
  expectDownscaledFixture(
    out as Parameters<typeof expectDownscaledFixture>[0],
  );
});

test('recorded resize factor drives actual rendering (CanvasImageSource branch)', async ({
  page,
}) => {
  const out = await page.evaluate(() =>
    (
      globalThis as {
        __px: {
          runCase: (
            i: unknown,
            pt?: number[],
          ) => Promise<Record<string, never>>;
        };
      }
    ).__px.runCase(
      {
        branch: 'canvas',
        smoothing: false,
        budget: { maxRasterPixels: 50, maxRasterEdge: 8192 },
      },
      [4.5, 4.5],
    ),
  );
  expectDownscaledFixture(
    out as Parameters<typeof expectDownscaledFixture>[0],
  );
});

test('no-resize control: k=1 full crop, exact bytes, no clipping limitation', async ({
  page,
}) => {
  const out = (await page.evaluate(() =>
    (
      globalThis as {
        __px: { runCase: (i: unknown) => Promise<Record<string, never>> };
      }
    ).__px.runCase({
      branch: 'imagedata',
      smoothing: false,
      // default caps: 49x80=3920px < 4M, edges < 8192 -> no resize
    },
    ),
  )) as {
    status: string;
    reason: string | null;
    imageClass: string;
    decoded: { width: number; height: number; data: number[] } | null;
    crop: {
      resizeK: number;
      resizeClipPx: readonly [number, number];
      outWidthPx: number;
      outHeightPx: number;
      cropX: number;
      cropY: number;
    };
    limitations: string[];
    ocrResizeMatrix: number[] | null;
    diagnostics: { downscaled: boolean };
  };
  expect(out.status).toBe('completed');
  expect(out.reason).toBe('unreadable_pixels');
  expect(out.imageClass).toBe('Blob:image/png');
  const decoded = out.decoded!;
  expect(decoded.width).toBe(49);
  expect(decoded.height).toBe(80);
  expect(out.crop.resizeK).toBe(1);
  expect(out.crop.outWidthPx).toBe(49);
  expect(out.crop.outHeightPx).toBe(80);
  expect(out.crop.resizeClipPx).toEqual([0, 0]);
  expect(out.diagnostics.downscaled).toBe(false);
  expect(out.ocrResizeMatrix![0]).toBe(1);
  expect(out.ocrResizeMatrix![3]).toBe(1);
  expect(out.limitations.join(' ')).not.toContain('ocr_resize_clipped');
  expect(out.limitations.join(' ')).not.toContain('downsampled');
  // Byte-exact identity: seam column preserved verbatim.
  expect(px(decoded, 41, 4)).toEqual(BLACK);
  expect(px(decoded, 42, 4)).toEqual(RED);
  expect(px(decoded, 48, 79)).toEqual(RED);
});

test('crop-offset region: nonzero source origin restored, no padding artifacts', async ({
  page,
}) => {
  // Region canonical polygon -> raster bounds [34,10]-[41,26] (s=1,
  // /Rotate 0); pad max(8, ceil(16*0.1))=8 -> crop (26,2)-(49,34):
  // 23x32 at origin (26,2), k=1. The red seam at source x=42 lands at
  // output x=16 — its position proves the source origin offset was
  // applied; the exact 23x32 size proves no padding leaked in.
  const out = (await page.evaluate(() =>
    (
      globalThis as {
        __px: { runCase: (i: unknown) => Promise<Record<string, never>> };
      }
    ).__px.runCase({
      branch: 'imagedata',
      smoothing: false,
      region: {
        id: 'seam-window',
        label: 'region',
        polygon: [
          [34, 10],
          [41, 10],
          [41, 26],
          [34, 26],
        ],
      },
    },
    ),
  )) as {
    status: string;
    reason: string | null;
    imageClass: string;
    decoded: { width: number; height: number; data: number[] } | null;
    crop: {
      cropX: number;
      cropY: number;
      cropWidthPx: number;
      cropHeightPx: number;
      regionPx: readonly number[] | null;
      paddingPx: number;
      resizeK: number;
      resizeClipPx: readonly [number, number];
      outWidthPx: number;
      outHeightPx: number;
    };
    limitations: string[];
  };
  expect(out.status).toBe('completed');
  expect(out.imageClass).toBe('Blob:image/png');
  const decoded = out.decoded!;
  expect(decoded.width).toBe(23);
  expect(decoded.height).toBe(32);
  expect(out.crop.cropX).toBe(26);
  expect(out.crop.cropY).toBe(2);
  expect(out.crop.cropWidthPx).toBe(23);
  expect(out.crop.cropHeightPx).toBe(32);
  expect(out.crop.paddingPx).toBe(8);
  expect(out.crop.regionPx).toEqual([34, 10, 41, 26]);
  expect(out.crop.resizeK).toBe(1);
  expect(out.crop.resizeClipPx).toEqual([0, 0]);
  expect(out.limitations.join(' ')).not.toContain('ocr_resize_clipped');
  expect(out.limitations.join(' ')).not.toContain('crop_padding_clipped');
  // Seam at output x = 42-26 = 16: left of it black, right red.
  expect(px(decoded, 0, 10)).toEqual(BLACK);
  expect(px(decoded, 15, 10)).toEqual(BLACK);
  expect(px(decoded, 16, 10)).toEqual(RED);
  expect(px(decoded, 22, 31)).toEqual(RED);
});
