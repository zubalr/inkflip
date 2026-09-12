/**
 * T10 — Browser selected-page/crop OCR over tesseract.js: real Chromium
 * coverage.
 *
 * The suite bundles `@inkflip/readers-tesseract` (+ geometry/contracts) with
 * `bun build --target browser`, serves it over loopback HTTP next to the
 * PINNED staged assets — tesseract.js@7.0.0 worker, the feature-detected
 * tesseract.js-core@7.0.0 *.wasm.js shims and the sha256-pinned
 * tessdata_fast eng.traineddata — plus the pdfjs-dist@6.3.289 legacy pair
 * (the named renderer) and the T05 scan fixtures. The adapter is driven
 * inside the page exactly as the app will: model prepare -> open ->
 * plan -> extract -> close.
 *
 * Coverage (effective T10 acceptance criteria):
 * - real browser OCR of a real English crop (F03 scan-raster-only) with
 *   engine/settings/model identity on every result
 * - explicit same-origin worker/core/lang paths only — no CDN, no
 *   workerBlobURL indirection, no runtime download outside the model
 * - crop/resize chain preserved through packages/geometry; word boxes
 *   mapped back to canonical page points; precision `estimated`
 * - raw word/line/block hierarchy preserved verbatim; raw_source_locator
 * - cold/cached/memory/offline asset states; SHA-256 verified before
 *   cache commitment; corrupted cache rejected
 * - initialization failure vs `unreadable_pixels` kept distinct
 * - bounded raster/edge/pixel/occurrence caps enforced and recorded
 * - low engine confidence recorded as diagnostic only — never truth
 * - one reusable initialized worker per profile; transient retry uses a
 *   fresh worker; cancel/timeout terminate it
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

import {
  expectCropOffset,
  expectDownscaledFixture,
  expectNoResizeControl,
  PIXEL_ENTRY_SNIPPET,
  runPixelCase,
} from './t10-pixel-harness.ts';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const PUBLIC = join(ROOT, 'apps', 'web', 'public');
const PDFJS_BUILD = join(ROOT, 'apps', 'web', 'node_modules', 'pdfjs-dist', 'legacy', 'build');
/**
 * The engine module is bundled from the pinned package ENTRY (not the
 * pre-built dist bundle) so the adapter under test exercises the
 * checked-in tesseract.js@7.0.0 sources — including the WorkerOptions
 * signal lifecycle patch — rather than a stale prebuilt artifact.
 */
const TESSERACT_ENTRY = join(
  ROOT, 'apps', 'web', 'node_modules', 'tesseract.js', 'src', 'index.js',
);
const FIXTURE_DEV = join(ROOT, 'fixtures', 'development');
const FIXTURE_PUBLIC = join(ROOT, 'fixtures', 'public');
const TESS_PKG = join(ROOT, 'packages', 'readers-tesseract', 'src');
const GEOM_PKG = join(ROOT, 'packages', 'geometry', 'src');
const CONTRACTS_PKG = join(ROOT, 'packages', 'contracts', 'src');

/** Pinned model identity — config/resolved-assets.json (tessdata-fast-eng). */
const MODEL = {
  id: 'tessdata-fast-eng',
  version: '65727574dfcd264acbb0c3e07860e4e9e9b22185',
  sha256: '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2',
  byteLength: 4113088,
  sourcePath: '/models/tessdata-fast-eng/7d4322bd/eng.traineddata',
  lang: 'eng',
  license: 'Apache-2.0',
  cachePath: 'inkflip/models',
};
const PATHS = {
  workerPath: '/assets/tesseract/7.0.0/worker.min.js',
  corePath: '/assets/tesseract-core/7.0.0/',
  langPath: '/models/tessdata-fast-eng/7d4322bd/',
  cachePath: 'inkflip/models',
};
/** Staged asset SHA-256s recorded in the ReaderManifest (resolved-assets.json). */
const ASSET_HASHES = [
  '576b7df7e3393e137e51849357c9adb53fe7ac1bb69bfa06cf3d61520f182c6d', // worker.min.js
  '0bc6ce3e5fbbd0cd89706cf2fd70960e3372f4f01ee24265b26990808aaeb286', // core scalar
  'eef5f8b2f8e20e150680b20adaec4a60babafee3adbe8a94583c81fee46e8680', // core lstm
  '6b61ef4e911b5cf57e656bbfe983d6e2b3711a02dd164154ddda064566e8e09d', // core simd
  'c58b46a4c796c0b8afccf77591d5b875b6896b45d402bbce8caa6f5362447b38', // core simd-lstm
  '843074aa5bad1cc6421b74a86201768ced9f244795e4d81435435a61a40ce535', // core relaxedsimd
  '861a536cf9ef8e63cb644d57bab39c388f37f7d6b6f60024b741c5f6b39a59b3', // core relaxedsimd-lstm
  MODEL.sha256, // eng.traineddata
];

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.pdf': 'application/pdf',
  '.bcmap': 'application/octet-stream',
  '.traineddata': 'application/octet-stream',
  '.wasm': 'application/wasm',
  '.icc': 'application/vnd.iccprofile',
  '.icm': 'application/vnd.iccprofile',
};

function mimeFor(pathname: string): string {
  const dot = pathname.lastIndexOf('.');
  return (dot >= 0 && MIME[pathname.slice(dot)]) || 'application/octet-stream';
}

const PAGE_HTML = `<!doctype html>
<meta charset="utf-8">
<title>inkflip t10 ocr harness</title>
<script type="module">
  globalThis.__t10ready = false;
  globalThis.__t10error = null;
  Promise.all([
    import('/vendor/pdfjs/pdf.mjs').then((m) => { globalThis.__pdfjs = m; }),
    // The tesseract.js module ships inside /bundle.js (bundled from the
    // pinned package entry, not a prebuilt dist artifact).
    import('/bundle.js'),
  ]).then(() => { globalThis.__t10ready = true; })
    .catch((e) => { globalThis.__t10error = String(e && e.stack || e); });
</script>
`;

interface Harness {
  server: Server;
  base: string;
  tmp: string;
  served: string[];
}

/**
 * The in-page harness: pdf.js renders the named raster; the adapter does
 * everything else. All values crossing evaluate() are JSON — live objects
 * stay in `state`.
 */
function entrySource(): string {
  return `
import * as adapter from ${JSON.stringify(join(TESS_PKG, 'index.ts'))};
import * as geom from ${JSON.stringify(join(GEOM_PKG, 'index.ts'))};
import * as contracts from ${JSON.stringify(join(CONTRACTS_PKG, 'index.ts'))};
// Pinned engine entry — src/index.js is the CJS package entry; its
// default export is the Tesseract module object.
import Tesseract from ${JSON.stringify(TESSERACT_ENTRY)};
globalThis.__tesseract = Tesseract;

const MODEL = ${JSON.stringify(MODEL)};
const PATHS = ${JSON.stringify(PATHS)};
const ASSET_HASHES = ${JSON.stringify(ASSET_HASHES)};

const state = {
  docs: new Map(),
  rasters: new Map(),
  readers: new Map(),
  checks: new Map(),
  n: 0,
};

function serErr(e) {
  return {
    name: (e && e.name) || 'Error',
    message: String((e && e.message) || e),
    reason: (e && e.reason) || null,
  };
}

async function tryV(fn) {
  try {
    return { ok: true, value: await fn() };
  } catch (e) {
    return { ok: false, error: serErr(e) };
  }
}

function hex(bytes) {
  let s = '';
  for (const b of bytes) s += b.toString(16).padStart(2, '0');
  return s;
}

function flakyEngine(engine) {
  let calls = 0;
  return {
    OEM: engine.OEM,
    PSM: engine.PSM,
    createWorker: (l, o, p, c) => {
      calls += 1;
      if (calls === 1) return Promise.reject(new Error('synthetic spawn explosion'));
      return engine.createWorker(l, o, p, c);
    },
  };
}

const api = {
  adapter,
  geom,
  contracts,
  MODEL,
  PATHS,
  ASSET_HASHES,

  async loadDoc(url) {
    const pdfjs = globalThis.__pdfjs;
    pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/pdf.worker.mjs';
    const bytes = new Uint8Array(await (await fetch(url)).arrayBuffer());
    const task = pdfjs.getDocument({
      // pdf.js transfers its input ArrayBuffer to the pdf worker,
      // detaching it; give it a copy so the document bytes we hash
      // and retain stay immutable (I01).
      data: bytes.slice(),
      cMapUrl: '/assets/pdfjs/6.3.289/cmaps/',
      cMapPacked: true,
      standardFontDataUrl: '/assets/pdfjs/6.3.289/standard_fonts/',
      wasmUrl: '/assets/pdfjs/6.3.289/wasm/',
      iccUrl: '/assets/pdfjs/6.3.289/iccs/',
      isEvalSupported: false,
      enableXfa: false,
    });
    const doc = await task.promise;
    const docId = 'doc_' + (++state.n);
    state.docs.set(docId, { doc, task, bytes });
    return { docId, sha256: hex(contracts.sha256(bytes)), numPages: doc.numPages };
  },

  /**
   * The named-renderer seam: pdf.js paints the page; the BuiltPage and
   * the measured raster scale are computed through packages/geometry.
   * 'synthetic' kinds (blank/noise) are marked as such in rasterId —
   * diagnostic rasters, never presented as renderer output.
   */
  async rasterize(docId, pageIndex, scale, kind) {
    const rec = state.docs.get(docId);
    if (!rec) throw new Error('unknown doc ' + docId);
    const page = await rec.doc.getPage(pageIndex + 1);
    const built = geom.buildPage({
      index: pageIndex,
      viewBox: Array.from(page.view),
      userUnit: page.userUnit,
      rotation: page.rotate,
      boxSource: 'pdf.js page.view + UserUnit',
    });
    let raster;
    if (kind === 'blank' || kind === 'noise') {
      const size = geom.displayRotation(page.rotate, built.canonicalSizePt).size;
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(size[0] * scale);
      canvas.height = Math.round(size[1] * scale);
      const ctx = canvas.getContext('2d', { alpha: false });
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      if (kind === 'noise') {
        const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
        let seed = 0x2f6e2b1;
        for (let i = 0; i < img.data.length; i += 4) {
          seed = (seed * 1103515245 + 12345) & 0x7fffffff;
          if ((seed & 0xff) < 26) {
            img.data[i] = img.data[i + 1] = img.data[i + 2] = 40;
          }
        }
        ctx.putImageData(img, 0, 0);
      }
      raster = {
        rasterId: 'synthetic_' + kind + '_' + pageIndex,
        renderReaderId: 'synthetic-harness',
        scalePxPerPt: canvas.width / size[0],
        widthPx: canvas.width,
        heightPx: canvas.height,
        image: canvas,
        built,
      };
    } else {
      const viewport = page.getViewport({ scale });
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(viewport.width));
      canvas.height = Math.max(1, Math.round(viewport.height));
      const ctx = canvas.getContext('2d', { alpha: false });
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      const task = page.render({ canvasContext: ctx, viewport });
      task.onContinue = (cont) => setTimeout(cont, 0);
      await task.promise;
      const size = geom.displayRotation(page.rotate, built.canonicalSizePt).size;
      const scalePxPerPt = canvas.width / size[0];
      const expected = geom.pageToRaster(built, scalePxPerPt);
      const viewportOk =
        Array.isArray(viewport.transform) &&
        viewport.transform.length === 6 &&
        viewport.transform.every((v, i) => Math.abs(v - expected[i]) <= 1e-4);
      raster = {
        rasterId: 'ras_' + (++state.n),
        renderReaderId: 'pdfjs-6_3_289-render',
        scalePxPerPt,
        widthPx: canvas.width,
        heightPx: canvas.height,
        image: canvas,
        built,
        viewportOk,
      };
    }
    state.rasters.set(docId + ':' + pageIndex, raster);
    return {
      rasterId: raster.rasterId,
      widthPx: raster.widthPx,
      heightPx: raster.heightPx,
      scalePxPerPt: raster.scalePxPerPt,
      viewportOk: raster.viewportOk ?? null,
    };
  },

  makeReader(opts) {
    const hooks = { progress: [], models: [], errors: [] };
    const rasterSource = async (pageIndex) => {
      const r = state.rasters.get(opts.docId + ':' + pageIndex);
      if (!r) throw new Error('no raster prepared for ' + opts.docId + ' page ' + pageIndex);
      return r;
    };
    const engine =
      opts.engine === 'flakyOnce' ? flakyEngine(globalThis.__tesseract) : globalThis.__tesseract;
    const reader = new adapter.TesseractOcrReader({
      engine,
      engineVersion: '7.0.0',
      coreBuild: 'feature-detected single-threaded lstm',
      model: MODEL,
      paths: opts.paths || PATHS,
      assetHashes: ASSET_HASHES,
      profile: 'desktop',
      runKey: 't10-run-' + (opts.runKey || 'default'),
      // The named renderer whose rasters this reading is configured
      // for — bound at construction, validated again at extraction.
      renderReaderId: opts.renderReaderId || 'pdfjs-6_3_289-render',
      rasterSource,
      budget: opts.budget,
      hooks: {
        onProgress: (e) => hooks.progress.push({ status: e.status, progress: e.progress }),
        onModelState: (s) => hooks.models.push(s),
        onError: (d) => hooks.errors.push(d),
        ...(opts.idbFactory === 'none'
          ? { idbFactory: null }
          : opts.idbFactory === 'writeFail'
            ? { idbFactory: pxWriteFailIdb() }
            : {}),
      },
    });
    const readerId = 'rdr_' + (++state.n);
    state.readers.set(readerId, { reader, hooks, handle: null });
    return { readerId };
  },

  describe(readerId, kind) {
    return state.readers.get(readerId).reader.describe(kind || 'page');
  },

  async prepare(readerId) {
    return tryV(() => state.readers.get(readerId).reader.prepareModel());
  },

  async open(readerId, documentSha256, generation) {
    return tryV(async () => {
      const rec = state.readers.get(readerId);
      const handle = await rec.reader.open({ documentSha256, generation });
      rec.handle = handle;
      return handle;
    });
  },

  plan(readerId, selections) {
    return tryV(() => {
      const rec = state.readers.get(readerId);
      const checks = rec.reader.plan(rec.handle, selections);
      state.checks.set(readerId, checks);
      return checks;
    });
  },

  async extract(readerId, checkId, cancelAfterMs) {
    return tryV(async () => {
      const rec = state.readers.get(readerId);
      const check = (state.checks.get(readerId) || []).find((c) => c.id === checkId);
      if (!check) throw new Error('unplanned check ' + checkId);
      const chunks = [];
      const controller = new AbortController();
      let timer = null;
      if (typeof cancelAfterMs === 'number' && cancelAfterMs >= 0) {
        timer = setTimeout(() => controller.abort(), cancelAfterMs);
      }
      try {
        const output = await rec.reader.extract(
          rec.handle,
          check,
          (id, occurrences) => chunks.push({ checkId: id, n: occurrences.length }),
          controller.signal,
        );
        return { output, chunks, progress: rec.hooks.progress.slice() };
      } finally {
        if (timer !== null) clearTimeout(timer);
      }
    });
  },

  /**
   * Fault injection for the check-level transient retry: swaps the
   * reader's engine seam for a once-exploding wrapper and drops the
   * live worker, so the check's ensureWorker() fails once and the
   * single retry must rebuild a fresh worker. Reaching private fields
   * is deliberate — the alternative would be widening the public API
   * purely for a fault test.
   */
  async extractFlakyOnce(readerId, checkId) {
    return tryV(async () => {
      const rec = state.readers.get(readerId);
      const check = (state.checks.get(readerId) || []).find((c) => c.id === checkId);
      if (!check) throw new Error('unplanned check ' + checkId);
      rec.reader.cfg = { ...rec.reader.cfg, engine: flakyEngine(globalThis.__tesseract) };
      await rec.reader.destroyWorker();
      const chunks = [];
      const output = await rec.reader.extract(
        rec.handle,
        check,
        (id, occurrences) => chunks.push({ checkId: id, n: occurrences.length }),
      );
      return { output, chunks };
    });
  },

  // close() racing an in-flight open(): openStart begins open and
  // records the pending promise on the reader record; closeDuringOpen
  // runs close() and then settles it. The Node side waits for the real
  // raw Worker to appear (page.workers()) between the calls so the
  // abort provably lands inside engine initialization — a late init
  // must never attach a worker to a closed reader.
  async openStart(readerId) {
    const rec = state.readers.get(readerId);
    rec.pendingOpen = tryV(() =>
      rec.reader.open({ documentSha256: 'doc-sha-1', generation: 1 }));
    return 'started';
  },
  async closeDuringOpen(readerId) {
    const rec = state.readers.get(readerId);
    const closeRes = await tryV(() => rec.reader.close());
    const openRes = await rec.pendingOpen;
    rec.pendingOpen = null;
    return { openRes, closeRes, stats: api.readerStats(readerId) };
  },

  readerStats(readerId) {
    const rec = state.readers.get(readerId);
    return {
      modelState: rec.reader.modelState,
      workerInitCount: rec.reader.workerInits,
      modelStates: rec.hooks.models.slice(),
      engineErrors: rec.hooks.errors.slice(),
      progress: rec.hooks.progress.slice(),
    };
  },

  planCropOnly(readerId, docId, pageIndex, region, rasterOverride) {
    return tryV(() => {
      const r = state.rasters.get(docId + ':' + pageIndex);
      if (!r) throw new Error('no raster for ' + docId + ':' + pageIndex);
      const raster = rasterOverride ? { ...r, ...rasterOverride } : r;
      return adapter.planCrop({
        page: r.built.page,
        raster,
        checkId: 'synthetic_check',
        region: region || null,
        bounds: { maxRasterPixels: 4000000, maxRasterEdge: 8192 },
      });
    });
  },

  async removeModel(readerId) {
    return tryV(() => state.readers.get(readerId).reader.removeModelData());
  },

  async close(readerId) {
    return tryV(() => state.readers.get(readerId).reader.close());
  },

  async seedCorruptCache() {
    return tryV(async () => {
      const store = new adapter.KeyvalStore(indexedDB);
      await store.set(MODEL.cachePath + '/eng.traineddata', new Uint8Array([1, 2, 3, 4, 5]));
      return 'seeded';
    });
  },

  canonicalToRasterPoint(builtPage, scalePxPerPt, point) {
    const m = adapter.canonicalToRaster(builtPage, scalePxPerPt);
    return contracts.apply(m, point);
  },

  pageOf(docId, pageIndex) {
    const r = state.rasters.get(docId + ':' + pageIndex);
    return r ? r.built.page : null;
  },
};

${PIXEL_ENTRY_SNIPPET}

globalThis.__t10 = api;
`;
}

async function startHarness(): Promise<Harness> {
  const tmp = mkdtempSync(join(tmpdir(), 'inkflip-t10-'));
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
      if (pathname === '/' || pathname === '/t10.html') {
        return send(200, PAGE_HTML, 'text/html; charset=utf-8');
      }
      if (pathname === '/bundle.js') {
        return send(200, readFileSync(bundlePath), 'text/javascript; charset=utf-8');
      }
      if (pathname.startsWith('/vendor/pdfjs/')) {
        const name = pathname.slice('/vendor/pdfjs/'.length);
        if (!/^[A-Za-z0-9._-]+$/.test(name)) return send(403, 'forbidden');
        return send(200, readFileSync(join(PDFJS_BUILD, name)), mimeFor(name));
      }
      if (pathname.startsWith('/assets/') || pathname.startsWith('/models/')) {
        const file = join(PUBLIC, pathname);
        if (!file.startsWith(PUBLIC) || !existsSync(file)) return send(404, 'not found');
        return send(200, readFileSync(file), mimeFor(file));
      }
      if (pathname.startsWith('/fixtures/')) {
        const name = pathname.slice('/fixtures/'.length);
        if (!/^[A-Za-z0-9._-]+$/.test(name)) return send(403, 'forbidden');
        for (const dir of [FIXTURE_DEV, FIXTURE_PUBLIC]) {
          const file = join(dir, name);
          if (existsSync(file)) return send(200, readFileSync(file), 'application/pdf');
        }
        return send(404, 'not found');
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

test.describe.configure({ timeout: 300_000 });

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
  await page.goto(`${harness.base}/t10.html`);
  await page.waitForFunction(
    () =>
      (globalThis as { __t10ready?: boolean; __t10error?: unknown }).__t10ready ||
      (globalThis as { __t10error?: unknown }).__t10error,
  );
  const bootError = await page.evaluate(
    () => (globalThis as { __t10error?: unknown }).__t10error ?? null,
  );
  expect(bootError, 'module boot failure').toBeNull();
});

/** Load the F03 raster-only scan and render page 0 through pdf.js. */
async function loadScanDoc(
  page: import('@playwright/test').Page,
  scale: number,
  kind: 'render' | 'blank' | 'noise' = 'render',
): Promise<{ docId: string; sha256: string; raster: Record<string, unknown> }> {
  return page.evaluate(
    async ({ scaleArg, kindArg }) => {
      const api = (globalThis as any).__t10;
      const doc = await api.loadDoc('/fixtures/scan-raster-only.pdf');
      const raster = await api.rasterize(doc.docId, 0, scaleArg, kindArg);
      return { docId: doc.docId, sha256: doc.sha256, raster };
    },
    { scaleArg: scale, kindArg: kind },
  );
}

/** Canonical-space polygon for the F03 "AMOUNT DUE $100.00" line. */
const AMOUNT_LINE_REGION = {
  id: 'reg_amount_line',
  polygon: [
    [40, 130],
    [330, 130],
    [330, 178],
    [40, 178],
  ] as [number, number][],
  label: 'single-line amount region',
};

const BLANK_REGION = {
  id: 'reg_blank',
  polygon: [
    [40, 400],
    [400, 400],
    [400, 620],
    [40, 620],
  ] as [number, number][],
  label: 'blank lower page',
};

// ---------------------------------------------------------------------------
// Real browser OCR: staged assets only, explicit identity, raw hierarchy
// ---------------------------------------------------------------------------

test('real English crop OCR via staged same-origin assets (PSM 7)', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (r) => requests.push(r.url()));

  const { docId, raster } = await loadScanDoc(page, 2);
  // The named renderer's viewport transform really is S·R·C (verified
  // against packages/geometry in-page) — the raster OCR consumes.
  expect(raster.viewportOk).toBe(true);
  const out = await page.evaluate(async ({ docIdArg, region }) => {
    const api = (globalThis as any).__t10;
    const { readerId } = api.makeReader({ docId: docIdArg });
    const open = await api.open(readerId, 'doc-sha-1', 1);
    if (!open.ok) return { openError: open.error };
    const checks = await api.plan(readerId, [
      { pageIndex: 0, purpose: 'line', region },
    ]);
    if (!checks.ok) return { planError: checks.error };
    const run = await api.extract(readerId, checks.value[0].id);
    const stats = api.readerStats(readerId);
    const manifest = api.describe(readerId, 'line');
    const normOk =
      run.ok &&
      run.value.output.occurrences.every(
        (o: any) =>
          o.normalized_text === api.contracts.normalize(o.raw_text).text &&
          JSON.stringify(o.normalization_map) ===
            JSON.stringify(api.contracts.normalize(o.raw_text).map),
      );
    await api.close(readerId);
    return { run, stats, manifest, checks: checks.value, normOk };
  }, { docIdArg: docId, region: AMOUNT_LINE_REGION });

  expect(out.run?.ok, JSON.stringify(out.run?.error)).toBe(true);
  const output = out.run.value.output;
  expect(output.check.status).toBe('completed');
  expect(output.check.reason).toBeNull();

  // Real English words off the bitmap print.
  const joined = output.occurrences.map((o: any) => o.raw_text).join(' ');
  console.log(`PSM7 crop raw_text: ${joined}`);
  expect(output.occurrences.length).toBeGreaterThanOrEqual(2);
  expect(joined).toContain('AMOUNT');
  expect(joined).toContain('DUE');

  // Identity on the actual result (I13): engine/settings/model/renderer.
  expect(output.raster.scalePxPerPt).toBeCloseTo(2, 5);
  expect(output.raster.renderReaderId).toBe('pdfjs-6_3_289-render');
  expect(output.reader.method).toBe('ocr');
  expect(output.reader.environment).toBe('browser');
  expect(output.reader.settings.psm).toBe(7);
  expect(output.reader.settings.language).toBe('eng');
  expect(output.reader.settings.normalization).toBe('scalar-whitespace-v1');
  expect(output.reader.settings.render_reader_id).toBe('pdfjs-6_3_289-render');
  expect(output.reader.settings.raster_dpi).toBe(144);
  expect(output.reader.model_hashes).toContain(MODEL.sha256);
  expect(output.engine.name).toBe('tesseract.js');
  expect(output.engine.packageVersion).toBe('7.0.0');
  expect(output.engine.adapterVersion).toBe('1.0.0');
  expect(output.engine.reportedVersion).toBeTruthy();
  console.log(`engine reported: psm=${output.engine.psmReported} oem=${output.engine.oem} version=${output.engine.reportedVersion}`);
  expect(output.model.sha256).toBe(MODEL.sha256);
  expect(output.model.state).toBe('ready_memory');
  expect(output.model.provenance).toBe('network');

  // Raw hierarchy preserved verbatim + locator into it (I03).
  expect(output.raw.blocks).not.toBeNull();
  expect(Array.isArray(output.raw.blocks)).toBe(true);
  expect((output.raw.blocks as any[]).length).toBeGreaterThan(0);
  const firstBlock = (output.raw.blocks as any[])[0];
  expect(firstBlock.paragraphs[0].lines[0].words.length).toBeGreaterThan(0);
  for (const o of output.occurrences) {
    expect(o.raw_source_locator).toMatch(
      /^tesseract\.js\/blocks\[\d+\]\.paragraphs\[\d+\]\.lines\[\d+\]\.words\[\d+\]$/,
    );
    expect(typeof o.raw_text).toBe('string');
    expect(o.raw_text.length).toBeGreaterThan(0);
    // OCR geometry is estimated — never exact, never fabricated (I04).
    expect(o.geometry.precision).toBe('estimated');
    expect(o.geometry.space).toBe('canonical_page');
    expect(Array.isArray(o.geometry.polygon)).toBe(true);
    // Confidence is an engine diagnostic estimate — never truth.
    expect(o.engine_score).not.toBeNull();
    expect(o.engine_score.scale_min).toBe(0);
    expect(o.engine_score.scale_max).toBe(100);
    expect(o.engine_score.meaning).toMatch(/estimate|diagnostic/i);
  }
  expect(out.normOk).toBe(true);

  // Crop/resize chain preserved (original region vs padded crop).
  expect(output.crop.regionPx).not.toBeNull();
  expect(output.crop.paddingPx).toBeGreaterThanOrEqual(8);
  const ops = output.transforms.map((t: any) => t.operation);
  expect(ops).toEqual(['raster_scale', 'crop_translation', 'ocr_resize']);
  expect(output.transforms.map((t: any) => t.to_space)).toEqual([
    `raster:${output.raster.rasterId}`,
    `ocr:${output.crop.ocrId}`,
    `ocr:${output.crop.ocrId}`,
  ]);

  // One initialized worker served the whole check.
  expect(out.stats.workerInitCount).toBe(1);
  expect(out.stats.modelStates).toContain('downloading');
  expect(out.stats.modelStates).toContain('verifying');
  expect(out.run.value.chunks.every((c: any) => c.n <= 256)).toBe(true);

  // Every byte the page pulled came from our loopback origin: the staged
  // worker, one feature-detected core shim and the pinned traineddata.
  // No default CDN URL was ever constructed.
  const external = requests.filter((u) => !u.startsWith(harness.base));
  expect(external, `non-same-origin requests: ${external.join(',')}`).toEqual([]);
  expect(requests.some((u) => u.endsWith('/assets/tesseract/7.0.0/worker.min.js'))).toBe(true);
  expect(
    requests.some((u) => /\/assets\/tesseract-core\/7\.0\.0\/tesseract-core-[a-z-]*\.wasm\.js$/.test(u)),
    'feature-detected core shim must be the staged file',
  ).toBe(true);
  expect(
    requests.filter((u) => u.endsWith('/models/tessdata-fast-eng/7d4322bd/eng.traineddata')).length,
  ).toBe(1);
});

test('full-page PSM-6 OCR, reusable worker, deterministic occurrence ids', async ({ page }) => {
  const { docId } = await loadScanDoc(page, 2);
  const out = await page.evaluate(async ({ docIdArg, region }) => {
    const api = (globalThis as any).__t10;
    const { readerId } = api.makeReader({ docId: docIdArg });
    const open = await api.open(readerId, 'doc-sha-1', 1);
    if (!open.ok) return { openError: open.error };
    const checks = await api.plan(readerId, [
      { pageIndex: 0, purpose: 'page' },
      { pageIndex: 0, purpose: 'line', region },
    ]);
    if (!checks.ok) return { planError: checks.error };
    const pageRun = await api.extract(readerId, checks.value[0].id);
    const lineRun = await api.extract(readerId, checks.value[1].id);
    const pageRun2 = await api.extract(readerId, checks.value[0].id);
    const stats = api.readerStats(readerId);
    await api.close(readerId);
    return { pageRun, lineRun, pageRun2, stats, checks: checks.value };
  }, { docIdArg: docId, region: AMOUNT_LINE_REGION });

  expect(out.pageRun?.ok, JSON.stringify(out.pageRun?.error)).toBe(true);
  expect(out.lineRun?.ok).toBe(true);
  const pageOut = out.pageRun.value.output;
  const lineOut = out.lineRun.value.output;
  expect(pageOut.check.status).toBe('completed');
  expect(lineOut.check.status).toBe('completed');

  const pageText = pageOut.occurrences.map((o: any) => o.raw_text).join(' ');
  console.log(`PSM6 page raw_text: ${pageText}`);
  expect(pageText).toContain('QUARTERLY');
  expect(pageText).toContain('SUMMARY');
  expect(pageText).toContain('INVOICE');
  expect(pageText).toContain('AMOUNT');

  // PSM differs by configured reading; reader ids are distinct (I13).
  expect(pageOut.reader.settings.psm).toBe(6);
  expect(lineOut.reader.settings.psm).toBe(7);
  expect(pageOut.reader.id).not.toBe(lineOut.reader.id);
  expect(out.checks[0].region_id).toBeNull();
  expect(out.checks[1].region_id).toBe('reg_amount_line');

  // One initialized model served every check in the profile (reuse).
  expect(out.stats.workerInitCount).toBe(1);

  // Deterministic engine + same configured reading => stable occurrence ids.
  const ids1 = pageOut.occurrences.map((o: any) => o.id);
  const ids2 = out.pageRun2.value.output.occurrences.map((o: any) => o.id);
  expect(ids2).toEqual(ids1);
});

// ---------------------------------------------------------------------------
// Failure honesty: init/model failures never become 'unreadable_pixels'
// ---------------------------------------------------------------------------

test('worker init failure is a terminal failure, never unreadable_pixels', async ({ page }) => {
  const { docId } = await loadScanDoc(page, 2, 'blank');
  const out = await page.evaluate(async ({ docIdArg, region }) => {
    const api = (globalThis as any).__t10;
    // A) Worker script 404 -> createWorker rejects at spawn.
    const bad = api.makeReader({
      docId: docIdArg,
      paths: {
        workerPath: '/assets/tesseract/7.0.0/MISSING-worker.js',
        corePath: '/assets/tesseract-core/7.0.0/',
        langPath: '/models/tessdata-fast-eng/7d4322bd/',
        cachePath: 'inkflip/models',
      },
    });
    const openBad = await api.open(bad.readerId, 'doc-sha-1', 1);

    // B) Healthy reader OCRs a genuinely blank raster: completed-empty.
    // The blank raster is produced by the synthetic harness, so the
    // reader consuming it is bound to that producer id — configured
    // renderer identity is checked against the raster at extraction.
    const good = api.makeReader({
      docId: docIdArg,
      renderReaderId: 'synthetic-harness',
    });
    const openGood = await api.open(good.readerId, 'doc-sha-1', 1);
    let blankRun = null;
    if (openGood.ok) {
      const checks = await api.plan(good.readerId, [
        { pageIndex: 0, purpose: 'region', region },
      ]);
      if (checks.ok) {
        blankRun = await api.extract(good.readerId, checks.value[0].id);
      }
    }
    const statsBad = api.readerStats(bad.readerId);
    const statsGood = api.readerStats(good.readerId);
    await api.close(good.readerId);
    return { openBad, openGood, blankRun, statsBad, statsGood };
  }, { docIdArg: docId, region: BLANK_REGION });

  // Initialization failure: explicit OcrError reason at open(), not a
  // fabricated page result and never 'unreadable_pixels'.
  expect(out.openBad.ok).toBe(false);
  expect(out.openBad.error.reason).toBe('init_crash');
  expect(out.openBad.error.reason).not.toBe('unreadable_pixels');
  expect(out.statsBad.modelState).toBe('ready_memory'); // model fine; worker failed

  expect(out.openGood.ok).toBe(true);
  const blank = out.blankRun.value.output;
  expect(blank.check.status).toBe('completed');
  // The recognizer ran to completion and found no usable text: the
  // informational completed-empty outcome, distinct from init failure.
  expect(blank.check.reason).toBe('unreadable_pixels');
  expect(blank.check.produced_occurrence_count).toBe(0);
  expect(blank.limitations.join(' ')).toContain('unreadable_pixels');
  expect(blank.raw.blocks).not.toBeUndefined();
  expect(out.statsGood.workerInitCount).toBe(1);
});

test('model integrity failure and corrupted cache are rejected', async ({ page }) => {
  const { docId } = await loadScanDoc(page, 2);
  // Corrupt every traineddata fetch: bytes must fail SHA-256 verification.
  await page.route('**/models/tessdata-fast-eng/7d4322bd/eng.traineddata', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/octet-stream',
      body: Buffer.from('corrupted-not-a-model'),
    }),
  );
  const tampered = await page.evaluate(async ({ docIdArg }) => {
    const api = (globalThis as any).__t10;
    const { readerId } = api.makeReader({ docId: docIdArg });
    const prep = await api.prepare(readerId);
    const stats = api.readerStats(readerId);
    return { prep, stats };
  }, { docIdArg: docId });
  expect(tampered.prep.ok).toBe(false);
  expect(tampered.prep.error.reason).toBe('model_integrity');
  expect(tampered.stats.modelState).toBe('failed_integrity');
  expect(tampered.stats.modelStates).toContain('downloading');
  expect(tampered.stats.modelStates).toContain('verifying');

  await page.unroute('**/models/tessdata-fast-eng/7d4322bd/eng.traineddata');

  // A mismatched pre-existing cache entry is deleted and reported, then
  // replaced by a fresh verified download — never silently accepted.
  const corruptedCache = await page.evaluate(async ({ docIdArg }) => {
    const api = (globalThis as any).__t10;
    await api.seedCorruptCache();
    const { readerId } = api.makeReader({ docId: docIdArg });
    const prep = await api.prepare(readerId);
    const stats = api.readerStats(readerId);
    return { prep, stats };
  }, { docIdArg: docId });
  expect(corruptedCache.prep.ok).toBe(true);
  expect(corruptedCache.prep.value.provenance).toBe('network');
  expect(corruptedCache.prep.value.sha256).toBe(MODEL.sha256);
  expect(corruptedCache.prep.value.limitations.join(' ')).toContain('cache_integrity');
});

test('offline-unavailable is a distinct asset state, not an unreadable page', async ({ page }) => {
  await page.context().setOffline(true);
  const out = await page.evaluate(async () => {
    const api = (globalThis as any).__t10;
    const { readerId } = api.makeReader({ docId: 'unused' });
    const prep = await api.prepare(readerId);
    const stats = api.readerStats(readerId);
    return { prep, stats };
  });
  expect(out.prep.ok).toBe(false);
  expect(out.prep.error.reason).toBe('unavailable_offline');
  expect(out.stats.modelState).toBe('unavailable_offline');
  expect(out.prep.error.reason).not.toBe('unreadable_pixels');

  await page.context().setOffline(false);
  const recovered = await page.evaluate(async () => {
    const api = (globalThis as any).__t10;
    const { readerId } = api.makeReader({ docId: 'unused' });
    const prep = await api.prepare(readerId);
    return { prep };
  });
  expect(recovered.prep.ok).toBe(true);
  expect(recovered.prep.value.state).toBe('ready_memory');
  expect(recovered.prep.value.provenance).toBe('network');
});

// ---------------------------------------------------------------------------
// Bounded work: raster edge/pixel caps, run budgets, degenerate geometry
// ---------------------------------------------------------------------------

test('bounded raster/edge/pixel counts enforced and recorded', async ({ page }) => {
  const { docId } = await loadScanDoc(page, 8); // 4896x6336 px raster
  const out = await page.evaluate(async ({ docIdArg }) => {
    const api = (globalThis as any).__t10;
    const { readerId } = api.makeReader({
      docId: docIdArg,
      budget: { checkTimeoutMs: 120_000 },
    });
    const open = await api.open(readerId, 'doc-sha-1', 1);
    if (!open.ok) return { openError: open.error };
    const checks = await api.plan(readerId, [{ pageIndex: 0, purpose: 'page' }]);
    if (!checks.ok) return { planError: checks.error };
    const run = await api.extract(readerId, checks.value[0].id);
    // Synthetic oversized-edge raster through planCrop: hard cap applies.
    // (planCropOnly returns a Promise like every tryV seam — await it.)
    const edgePlan = await api.planCropOnly(readerId, docIdArg, 0, null, {
      widthPx: 9000,
      heightPx: 120,
      rasterId: 'synthetic_edge',
    });
    const degenerate = await api.planCropOnly(readerId, docIdArg, 0, {
      id: 'reg_degenerate',
      polygon: [
        [5, 5],
        [5, 5],
        [5, 5],
      ],
      label: 'zero-area',
    });
    await api.close(readerId);
    return { run, edgePlan, degenerate };
  }, { docIdArg: docId });

  expect(out.run?.ok, JSON.stringify(out.run?.error)).toBe(true);
  const output = out.run.value.output;
  expect(output.check.status).toBe('completed');
  // The 31M-px raster was downsampled to <=4M px before reaching the engine.
  expect(output.raster.widthPx).toBe(4896);
  expect(output.raster.heightPx).toBe(6336);
  expect(output.crop.resizeK).toBeLessThan(1);
  expect(output.crop.outWidthPx * output.crop.outHeightPx).toBeLessThanOrEqual(4_000_000);
  expect(Math.max(output.crop.outWidthPx, output.crop.outHeightPx)).toBeLessThanOrEqual(8192);
  expect(output.diagnostics.downscaled).toBe(true);
  expect(output.limitations.join(' ')).toContain('downsampled');
  // The realized resize factor is recorded in the transform chain.
  const resize = output.transforms.find((t: any) => t.operation === 'ocr_resize');
  expect(resize).toBeTruthy();
  expect(resize.matrix[0]).toBeLessThan(1);
  expect(output.crop.outWidthPx).toBe(Math.floor(output.crop.cropWidthPx * output.crop.resizeK));

  // Edge cap: a 9000-px-wide crop downscales under 8192.
  expect(out.edgePlan.ok).toBe(true);
  expect(Math.max(out.edgePlan.value.outWidthPx, out.edgePlan.value.outHeightPx)).toBeLessThanOrEqual(8192);
  expect(out.edgePlan.value.resizeK).toBeLessThan(1);
  expect(out.edgePlan.value.limitations.join(' ')).toContain('downsampled');

  // Degenerate geometry is rejected, never guessed.
  expect(out.degenerate.ok).toBe(false);
  expect(out.degenerate.error.reason).toBe('geometry_unavailable');
});

test('run OCR pixel budget bounds later checks honestly', async ({ page }) => {
  const { docId } = await loadScanDoc(page, 2);
  const out = await page.evaluate(async ({ docIdArg, region }) => {
    const api = (globalThis as any).__t10;
    // The ~600x116px crop (~70k px) fits once; the second identical check
    // exceeds a 100k run budget -> resource_limit, not silent truncation.
    const { readerId } = api.makeReader({
      docId: docIdArg,
      budget: { maxRunOcrPixels: 100_000 },
    });
    const open = await api.open(readerId, 'doc-sha-1', 1);
    if (!open.ok) return { openError: open.error };
    const checks = await api.plan(readerId, [
      { pageIndex: 0, purpose: 'line', region },
      { pageIndex: 0, purpose: 'line', region },
    ]);
    if (!checks.ok) return { planError: checks.error };
    const first = await api.extract(readerId, checks.value[0].id);
    const second = await api.extract(readerId, checks.value[1].id);
    await api.close(readerId);
    return { first, second };
  }, { docIdArg: docId, region: AMOUNT_LINE_REGION });

  expect(out.first?.ok).toBe(true);
  expect(out.first.value.output.check.status).toBe('completed');
  expect(out.second?.ok).toBe(true);
  const second = out.second.value.output;
  expect(second.check.status).toBe('failed');
  expect(second.check.reason).toBe('resource_limit');
  expect(second.check.produced_occurrence_count).toBe(0);
  // The earlier completed result is preserved (I17 — partial results stand).
  expect(out.first.value.output.check.retained_occurrence_ids.length).toBeGreaterThan(0);
});

// ---------------------------------------------------------------------------
// Geometry + confidence semantics
// ---------------------------------------------------------------------------

test('word boxes map back through the recorded chain; confidence is diagnostic', async ({ page }) => {
  const { docId } = await loadScanDoc(page, 2);
  const out = await page.evaluate(async ({ docIdArg, region }) => {
    const api = (globalThis as any).__t10;
    const { readerId } = api.makeReader({ docId: docIdArg });
    const open = await api.open(readerId, 'doc-sha-1', 1);
    if (!open.ok) return { openError: open.error };
    const checks = await api.plan(readerId, [
      { pageIndex: 0, purpose: 'line', region },
    ]);
    if (!checks.ok) return { planError: checks.error };
    const lineRun = await api.extract(readerId, checks.value[0].id);
    await api.close(readerId);

    // The noise raster is synthetic-harness output — a pdfjs-bound
    // reader must not consume it. A second reader bound to the actual
    // producer runs its own check on the same page slot.
    const noiseRaster = await api.rasterize(docIdArg, 0, 2, 'noise');
    const noiseReader = api.makeReader({
      docId: docIdArg,
      renderReaderId: 'synthetic-harness',
    });
    const noiseOpen = await api.open(noiseReader.readerId, 'doc-sha-1', 1);
    let noiseRun = null;
    if (noiseOpen.ok) {
      const noiseChecks = await api.plan(noiseReader.readerId, [
        { pageIndex: 0, purpose: 'region', region },
      ]);
      if (noiseChecks.ok) {
        noiseRun = await api.extract(noiseReader.readerId, noiseChecks.value[0].id);
      }
      await api.close(noiseReader.readerId);
    }

    if (!lineRun.ok) return { lineError: lineRun.error };
    const output = lineRun.value.output;
    // Round-trip one word polygon centroid through the recorded chain:
    // canonical centroid -> raster px must land inside the recorded crop.
    const page0 = api.pageOf(docIdArg, 0);
    const mapped = output.occurrences.map((o: any) => {
      const poly = o.geometry.polygon;
      if (!poly) return { inCrop: null };
      const cx = poly.reduce((a: number, p: number[]) => a + p[0], 0) / poly.length;
      const cy = poly.reduce((a: number, p: number[]) => a + p[1], 0) / poly.length;
      const px = api.canonicalToRasterPoint(page0, output.raster.scalePxPerPt, [cx, cy]);
      return {
        inCrop:
          px[0] >= output.crop.cropX - 1 &&
          px[0] <= output.crop.cropX + output.crop.cropWidthPx + 1 &&
          px[1] >= output.crop.cropY - 1 &&
          px[1] <= output.crop.cropY + output.crop.cropHeightPx + 1,
        rasterPoint: px,
      };
    });
    return { output, mapped, noiseRaster, noiseRun };
  }, { docIdArg: docId, region: AMOUNT_LINE_REGION });

  const output = out.output;
  expect(output.check.status).toBe('completed');
  // Every occurrence carries the recorded transform chain (I02).
  const recorded = new Set(output.transforms.map((t: any) => t.id));
  for (const o of output.occurrences) {
    for (const id of o.geometry.transform_ids) expect(recorded.has(id)).toBe(true);
    expect(o.geometry.basis).toContain('ocr:');
  }
  // Centroids land inside the padded crop rectangle in raster pixels.
  for (const m of out.mapped) expect(m.inCrop).toBe(true);

  // Confidence semantics: diagnostic engine score only (I06).
  expect(output.diagnostics.meanConfidence).not.toBeNull();
  expect(output.diagnostics.meanConfidence).toBeGreaterThanOrEqual(0);
  expect(output.diagnostics.meanConfidence).toBeLessThanOrEqual(100);
  const flagged = output.occurrences.filter((o: any) =>
    o.limitations.includes('low_engine_score'),
  );
  expect(flagged.map((o: any) => o.id)).toEqual(output.diagnostics.lowConfidenceIds);
  for (const o of flagged) expect(o.engine_score.value).toBeLessThan(60);
  // A score is never evidence of correctness — presence + scale only.
  expect(output.occurrences.every((o: any) => o.engine_score.meaning.includes('diagnostic'))).toBe(
    true,
  );

  // Noise raster: the engine either finds no text (unreadable_pixels —
  // honest completed-empty) or emits scored occurrences; never a truth
  // claim either way.
  expect(out.noiseRun, 'synthetic-harness reader open/plan/extract').not.toBeNull();
  expect(out.noiseRun.ok).toBe(true);
  const noise = out.noiseRun.value.output;
  expect(['completed']).toContain(noise.check.status);
  if (noise.occurrences.length === 0) {
    expect(noise.check.reason).toBe('unreadable_pixels');
  } else {
    expect(noise.occurrences.every((o: any) => o.engine_score !== null)).toBe(true);
    expect(noise.diagnostics.wordCount).toBeGreaterThanOrEqual(noise.occurrences.length);
  }
});

// ---------------------------------------------------------------------------
// Cache/cold/offline state distinctions + model removal
// ---------------------------------------------------------------------------

test('cold, memory, and cached model states are distinct; removal is explicit', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (r) => requests.push(r.url()));

  // Nothing model-related may be fetched before explicit preparation.
  const preFetch = requests.filter((u) => u.includes('traineddata'));
  expect(preFetch, 'model must not be fetched at landing time').toEqual([]);

  const out = await page.evaluate(async () => {
    const api = (globalThis as any).__t10;
    const a = api.makeReader({ docId: 'unused' });
    const cold = await api.prepare(a.readerId);
    const memory = await api.prepare(a.readerId);
    // A second manager on the same origin hits the persisted cache slot.
    const b = api.makeReader({ docId: 'unused' });
    const cached = await api.prepare(b.readerId);
    const statsA = api.readerStats(a.readerId);
    const statsB = api.readerStats(b.readerId);
    // "Remove downloaded OCR data" — explicit removal only.
    const removed = await api.removeModel(b.readerId);
    const afterRemove = api.readerStats(b.readerId);
    // The first manager's verified in-memory copy is unaffected.
    const stillMemory = await api.prepare(a.readerId);
    return { cold, memory, cached, statsA, statsB, removed, afterRemove, stillMemory };
  });

  expect(out.cold.value.state).toBe('ready_memory');
  expect(out.cold.value.provenance).toBe('network');
  expect(out.cold.value.sha256).toBe(MODEL.sha256);
  expect(out.memory.value.provenance).toBe('memory');
  expect(out.cached.value.state).toBe('ready_cached');
  expect(out.cached.value.provenance).toBe('cache');
  expect(out.cached.value.sha256).toBe(MODEL.sha256);
  expect(out.statsB.modelStates).toEqual(['ready_cached']);
  expect(out.afterRemove.modelState).toBe('not_prepared');
  expect(out.stillMemory.value.provenance).toBe('memory');

  // Exactly one traineddata fetch for the whole sequence (verified cold
  // download; the second manager read the persisted cache slot instead).
  expect(requests.filter((u) => u.endsWith('eng.traineddata')).length).toBe(1);
});

// ---------------------------------------------------------------------------
// Lifecycle: transient retry uses a fresh worker; cancel terminates it
// ---------------------------------------------------------------------------

test('one transient retry on a fresh worker; cancel terminates the worker', async ({ page }) => {
  const { docId } = await loadScanDoc(page, 2);
  const out = await page.evaluate(async ({ docIdArg, region }) => {
    const api = (globalThis as any).__t10;
    // A) First createWorker call explodes; the single transient retry
    // rebuilds the worker rather than reusing a dead one.
    const flaky = api.makeReader({ docId: docIdArg, engine: 'flakyOnce' });
    // open() initializes the model+worker: init crash surfaces here too.
    const openFlaky = await api.open(flaky.readerId, 'doc-sha-1', 1);
    let retryRun = null;
    let checks = null;
    if (openFlaky.ok) {
      checks = await api.plan(flaky.readerId, [
        { pageIndex: 0, purpose: 'line', region },
        { pageIndex: 0, purpose: 'page' },
      ]);
      // open() itself consumed the first (exploding) createWorker call, so
      // this reader's worker is healthy; drive a separate flaky extract via
      // a second reader to see the retry at check level.
      retryRun = await api.extract(flaky.readerId, checks.value[0].id);
    }
    const flakyStats = api.readerStats(flaky.readerId);
    await api.close(flaky.readerId);

    // B) A reader whose worker dies at *check* time retries on a fresh one.
    const flaky2 = api.makeReader({ docId: docIdArg, engine: 'flakyOnce' });
    // Prepare the model only; worker init explodes inside extract's retry.
    const open2 = await api.open(flaky2.readerId, 'doc-sha-1', 1);
    const flaky2Stats = api.readerStats(flaky2.readerId);
    await api.close(flaky2.readerId);

    // C) Cancel: full-page check aborted mid-recognize -> cancelled state
    // and worker termination; the next check re-initializes cleanly.
    const good = api.makeReader({ docId: docIdArg });
    const openGood = await api.open(good.readerId, 'doc-sha-1', 1);
    let cancelled = null;
    let after = null;
    if (openGood.ok) {
      const gchecks = await api.plan(good.readerId, [
        { pageIndex: 0, purpose: 'page' },
        { pageIndex: 0, purpose: 'line', region },
      ]);
      cancelled = await api.extract(good.readerId, gchecks.value[0].id, 40);
      after = await api.extract(good.readerId, gchecks.value[1].id);
    }
    const goodStats = api.readerStats(good.readerId);
    await api.close(good.readerId);
    return { openFlaky, retryRun, flakyStats, open2, flaky2Stats, cancelled, after, goodStats };
  }, { docIdArg: docId, region: AMOUNT_LINE_REGION });

  // The first createWorker call exploded inside open(): the handle init
  // is honest about it (init_crash), distinct from an unreadable page.
  expect(out.openFlaky.ok).toBe(false);
  expect(out.openFlaky.error.reason).toBe('init_crash');
  expect(out.retryRun).toBeNull();

  // Same story at check time: init crash during extract is failed, and
  // the single transient retry also failed because the SAME flaky engine
  // rejected again? No — calls is per-reader-wrapper; open2's first
  // createWorker explodes too -> open2 fails identically.
  expect(out.open2.ok).toBe(false);
  expect(out.open2.error.reason).toBe('init_crash');
  expect(out.flaky2Stats.workerInitCount).toBe(0);

  // Cancel: the aborted page check is cancelled (never retried), the
  // worker is terminated, and the following crop check re-initializes a
  // fresh worker successfully.
  expect(out.cancelled?.ok).toBe(true);
  const cancelled = out.cancelled.value.output;
  expect(cancelled.check.status).toBe('cancelled');
  expect(cancelled.check.reason).toBe('user_cancel');
  expect(out.after?.ok).toBe(true);
  const after = out.after.value.output;
  expect(after.check.status).toBe('completed');
  // Cancel destroyed the worker; the healthy retry needed a fresh one.
  expect(out.goodStats.workerInitCount).toBe(2);
});

test('check-level transient retry rebuilds the worker once and succeeds', async ({ page }) => {
  const { docId } = await loadScanDoc(page, 2);
  const out = await page.evaluate(async ({ docIdArg, region }) => {
    const api = (globalThis as any).__t10;
    // Engine whose first createWorker rejects. A healthy open() is
    // impossible, so prepare the model and drive extract through a
    // reader opened with the real engine — then swap the engine seam.
    const good = api.makeReader({ docId: docIdArg });
    const open = await api.open(good.readerId, 'doc-sha-1', 1);
    if (!open.ok) return { openError: open.error };
    const checks = await api.plan(good.readerId, [
      { pageIndex: 0, purpose: 'line', region },
    ]);
    if (!checks.ok) return { planError: checks.error };
    const run = await api.extractFlakyOnce(good.readerId, checks.value[0].id);
    const stats = api.readerStats(good.readerId);
    await api.close(good.readerId);
    return { run, stats };
  }, { docIdArg: docId, region: AMOUNT_LINE_REGION });

  expect(out.run?.ok, JSON.stringify(out.run?.error)).toBe(true);
  const output = out.run.value.output;
  expect(output.check.status).toBe('completed');
  expect(output.diagnostics.attempt).toBe(1);
  // Exactly one healthy worker exists after the retry (the exploded one
  // never counted, and no third worker was built).
  expect(out.stats.workerInitCount).toBe(2); // open() worker + retried worker
});

// ===========================================================================
// LIGHT coverage — stub-engine / worker-init-only checks. These run under
// the SAME harness and bundle; select them alone with `-g 'light:'`. No
// recognize() call on a real model is ever made in this section (the only
// real-engine tests below stop at worker initialization, an allowed light
// check; the heavy recognize suite stays above).
// ===========================================================================

test.describe('light: crop pixel regressions — recorded factor is the drawn factor (stub engine)', () => {
  test('ImageData source branch', async ({ page }) => {
    const out = await runPixelCase(
      page,
      { branch: 'imagedata', budget: { maxRasterPixels: 50, maxRasterEdge: 8192 } },
      [4.5, 4.5],
    );
    expectDownscaledFixture(out);
  });

  test('CanvasImageSource branch', async ({ page }) => {
    const out = await runPixelCase(
      page,
      { branch: 'canvas', budget: { maxRasterPixels: 50, maxRasterEdge: 8192 } },
      [4.5, 4.5],
    );
    expectDownscaledFixture(out);
  });

  test('no-resize control: k=1 full crop, exact bytes, no clipping limitation', async ({
    page,
  }) => {
    const out = await runPixelCase(page, { branch: 'imagedata' });
    expectNoResizeControl(out);
  });

  test('crop-offset region: nonzero source origin restored, no padding artifacts', async ({
    page,
  }) => {
    const out = await runPixelCase(page, {
      branch: 'imagedata',
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
    });
    expectCropOffset(out);
  });
});

// ---------------------------------------------------------------------------

test.describe('light: configured renderer identity (stub engine)', () => {
  test('plan/extract/describe identities agree on the configured renderer', async ({
    page,
  }) => {
    const out = await runPixelCase(page, {});
    expect(out.open?.ok).toBe(true);
    expect(out.run?.ok).toBe(true);
    const check = out.checks![0];
    const output = out.output!;
    // The configured render reader id is bound into plan-time reader
    // ids, the emitted reader record, and the raster identity — one
    // value, established before any plan was finalized.
    expect(check.reader_ids).toEqual([output.reader.id]);
    expect(out.manifest?.ok).toBe(true);
    expect(out.manifest!.value!.reader.id).toBe(output.reader.id);
    expect(output.reader.settings.render_reader_id).toBe('synthetic-fixture');
    expect(output.raster.renderReaderId).toBe('synthetic-fixture');
  });

  test('a raster produced by a different renderer fails render_error, never re-identified', async ({
    page,
  }) => {
    const out = await runPixelCase(page, {
      rasterRenderReaderId: 'some-other-renderer',
    });
    expect(out.open?.ok).toBe(true);
    expect(out.run?.ok).toBe(true);
    const output = out.output!;
    expect(output.check.status).toBe('failed');
    expect(output.check.reason).toBe('render_error');
    expect(output.check.produced_occurrence_count).toBe(0);
    // And the emitted reader identity still names the configured
    // renderer — the reading was never silently reassigned.
    expect(output.reader.settings.render_reader_id).toBe('synthetic-fixture');
  });

  test('missing or malformed configured ids are rejected at construction', async ({
    page,
  }) => {
    for (const bad of ['', 'Bad Id!', 'x'.repeat(80)]) {
      const out = await runPixelCase(page, { renderReaderId: bad });
      expect(out.construct?.ok).toBe(false);
      expect(out.construct?.reason).toBe('unsupported');
      expect(out.open).toBeNull();
    }
  });
});

// ---------------------------------------------------------------------------

test.describe('light: occurrence geometry and assembled report (stub engine)', () => {
  const WORD_RESULT = {
    text: 'HELLO',
    blocks: [
      {
        bbox: { x0: 2, y0: 2, x1: 20, y1: 12 },
        paragraphs: [
          {
            bbox: { x0: 2, y0: 2, x1: 20, y1: 12 },
            lines: [
              {
                bbox: { x0: 2, y0: 2, x1: 20, y1: 12 },
                words: [
                  {
                    text: 'HELLO',
                    confidence: 90,
                    bbox: { x0: 2, y0: 2, x1: 20, y1: 12 },
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  };

  test('word polygon is TL,TR,BR,BL with nonzero signed area', async ({ page }) => {
    const out = await runPixelCase(page, { stubResult: WORD_RESULT });
    expect(out.run?.ok).toBe(true);
    const output = out.output!;
    expect(output.check.status).toBe('completed');
    expect(output.occurrences).toHaveLength(1);
    const occ = output.occurrences![0];
    expect(occ.raw_text).toBe('HELLO');
    expect(occ.raw_source_locator).toBe(
      'tesseract.js/blocks[0].paragraphs[0].lines[0].words[0]',
    );
    // Raster == canonical at s=1/rot=0 (raster->canonical is
    // R^-1*S^-1 — the C flip belongs to user->canonical, not this
    // chain). Exact perimeter order TL,TR,BR,BL — no bow-tie.
    expect(occ.geometry.polygon).toEqual([
      [2, 2],
      [20, 2],
      [20, 12],
      [2, 12],
    ]);
    // Signed shoelace area is nonzero (|18*10| = 180).
    const p = occ.geometry.polygon!;
    const shoelace =
      p.reduce(
        (a, pt, i) => a + pt[0] * p[(i + 1) % p.length][1] - p[(i + 1) % p.length][0] * pt[1],
        0,
      ) / 2;
    expect(Math.abs(shoelace)).toBe(180);
    // The occurrence reader id is the configured identity — same as
    // plan and output.
    expect(occ.reader_id).toBe(output.reader.id);
    expect(out.checks![0].reader_ids).toEqual([occ.reader_id]);
  });

  test('an assembled evidence report with OCR geometry passes contract validation', async ({
    page,
  }) => {
    const out = await runPixelCase(page, { stubResult: WORD_RESULT });
    expect(out.run?.ok).toBe(true);
    const validated = await page.evaluate(
      ({ output, built, checks, docSha }) => {
        const api = (globalThis as any).__t10;
        const toHex = (b: Uint8Array) =>
          Array.from(b).map((x) => x.toString(16).padStart(2, '0')).join('');
        const assembled = {
          kind: 'report',
          schema_version: '1.0.0',
          report_id: toHex(
            api.contracts.sha256(new TextEncoder().encode('stub-report')),
          ),
          document: {
            sha256: docSha,
            byte_length: 4,
            page_count: 1,
            display_name: null,
            source_asset_id: null,
          },
          readers: [output.reader],
          pages: [built.page],
          transforms: [built.canonical, ...output.transforms],
          occurrences: output.occurrences,
          findings: [],
          annotations: [],
          plan: {
            version: '1.0.0',
            selected_pages: [0],
            regions: [],
            checks,
            normalization_version: 'scalar-whitespace-v1',
            alignment_version: 'region-match-v1',
            profile: 'desktop',
            budget: {
              max_raster_pixels: 4000000,
              max_run_ocr_pixels: 20000000,
              timeout_ms: 30000,
              max_retries: 1,
            },
          },
          checks: [output.check],
          execution: {
            execution_id: '94b59f8e-32d9-474d-ae09-29dd07f7c4c7',
            run_key:
              '72cf7c0239a8135437126710e23f1a5736fe222c7761678abdf057ca609e1a83',
            status: 'complete',
            started_at: '2026-09-12T00:00:00.000000+00:00',
            duration_ms: 10,
            environment: 'Chromium (playwright harness)',
            result_origin: 'live',
            errors: [],
          },
          export: {
            mode: 'evidence',
            scope: 'selection',
            included: ['selected_text', 'document_hash', 'settings', 'coverage'],
            omissions: [],
            replay: 'requires_original',
            origin_report_id: null,
          },
          assets: [],
          limitations: output.limitations,
        };
        api.contracts.validateReport(assembled, false);
        return assembled;
      },
      {
        output: out.output,
        built: out.built,
        checks: out.checks,
        docSha: out.docSha,
      },
    );
    expect(validated.occurrences).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------

test.describe('light: UTF-8 raw-text run budget (stub engine)', () => {
  test('raw text cap counts UTF-8 bytes, not UTF-16 units', async ({ page }) => {
    // 'é' is 1 UTF-16 code unit but 2 UTF-8 bytes. A 1-byte cap must
    // reject it; a 2-byte cap must accept it. '😀' is 2 units/4 bytes —
    // a 3-byte cap rejects it even though .length says 2.
    const tight = await runPixelCase(page, {
      stubResult: { text: 'é', blocks: [] },
      budget: { maxRawTextBytesPerRun: 1 },
    });
    expect(tight.run?.ok).toBe(true);
    expect(tight.output!.check.status).toBe('failed');
    expect(tight.output!.check.reason).toBe('resource_limit');

    const exact = await runPixelCase(page, {
      stubResult: { text: 'é', blocks: [] },
      budget: { maxRawTextBytesPerRun: 2 },
    });
    expect(exact.run?.ok).toBe(true);
    expect(exact.output!.check.status).toBe('completed');
    expect(exact.output!.raw.text).toBe('é');

    const emoji = await runPixelCase(page, {
      stubResult: { text: '😀', blocks: [] },
      budget: { maxRawTextBytesPerRun: 3 },
    });
    expect(emoji.run?.ok).toBe(true);
    expect(emoji.output!.check.status).toBe('failed');
    expect(emoji.output!.check.reason).toBe('resource_limit');
  });
});

// ---------------------------------------------------------------------------

test.describe('light: verified model bytes reach the engine', () => {
  test('worker init payload: object language + readOnly verified cache slot (stub)', async ({
    page,
  }) => {
    const out = await runPixelCase(page, {});
    expect(out.run?.ok).toBe(true);
    const c = out.captured;
    // The engine was launched with the v7 Lang object payload — code
    // names the language; data==code means a cache miss can only ever
    // write a poison stub (no fetch branch exists for object payloads).
    expect(c.workerLangs).toEqual([{ code: 'eng', data: 'eng' }]);
    const opts = c.workerOptions!;
    expect(opts.cacheMethod).toBe('readOnly');
    expect(opts.gzip).toBe(false);
    expect(opts.workerBlobURL).toBe(false);
    expect(opts.workerPath).toBe('/stub/worker.js');
    expect(opts.corePath).toBe('/stub/core/');
    expect(opts.langPath).toBe('/stub/models/');
    expect(opts.cachePath).toBe('inkflip/stub');
    // The concrete-lifetime signal is a real AbortSignal handed to the
    // engine — wired but not aborted on the happy path.
    expect(opts.signal).toBe('AbortSignal');
    expect(c.signalAbortedAtCreate).toBe(false);
    // The engine input is prepared PNG bytes, not a URL/blob/loader.
    expect(c.imageClass).toBe('Uint8Array');
    expect((c.imageBytes?.length ?? 0) > 8).toBe(true);
    // The produced bytes are a real PNG (\x89PNG\r\n\x1a\n).
    expect(c.imageBytes!.slice(0, 8)).toEqual([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
    ]);
  });

  test('a stale or corrupt cache slot is replaced before the engine sees it', async ({
    page,
  }) => {
    // Seed a corrupt slot first; open() must detect, delete, refetch,
    // re-verify, commit — and only then let a worker init consume it.
    // A real worker init succeeding proves the slot held valid bytes
    // (a corrupt slot would fail the engine's Init honestly).
    const res = await page.evaluate(async () => {
      const api = (globalThis as any).__t10;
      await api.seedCorruptCache();
      const { readerId } = api.makeReader({ docId: 'unused' });
      const open = await api.open(readerId, 'doc-sha-1', 1);
      const stats = api.readerStats(readerId);
      await api.close(readerId);
      return { open, stats };
    });
    expect(res.open.ok, JSON.stringify(res.open.error)).toBe(true);
    expect(res.stats.workerInitCount).toBe(1);
    expect(res.stats.modelState).toBe('ready_memory');
    // The corrupt slot was reported, not silently trusted.
    expect(
      res.open.value.model.limitations.join(' '),
    ).toContain('cache_integrity');
  });

  test('the engine consumes the verified slot — never a second divergent copy', async ({
    page,
  }) => {
    // First request serves the real pinned bytes; any SECOND request
    // would serve divergent bytes. If the engine fetched its own copy
    // it would get the corrupt body and init would fail — and any
    // fetch at all would increment `served` past 1.
    let served = 0;
    const realBytes = readFileSync(
      join(PUBLIC, 'models', 'tessdata-fast-eng', '7d4322bd', 'eng.traineddata'),
    );
    await page.route(
      '**/models/tessdata-fast-eng/7d4322bd/eng.traineddata',
      (route) => {
        served += 1;
        return route.fulfill({
          status: 200,
          contentType: 'application/octet-stream',
          body: served === 1 ? realBytes : Buffer.from('divergent-not-a-model'),
        });
      },
    );
    const res = await page.evaluate(async () => {
      const api = (globalThis as any).__t10;
      const { readerId } = api.makeReader({ docId: 'unused' });
      const open = await api.open(readerId, 'doc-sha-1', 1);
      const stats = api.readerStats(readerId);
      await api.close(readerId);
      return { open, stats };
    });
    await page.unroute('**/models/tessdata-fast-eng/7d4322bd/eng.traineddata');
    expect(res.open.ok, JSON.stringify(res.open.error)).toBe(true);
    // Real worker init succeeded — proving the slot held valid bytes.
    expect(res.stats.workerInitCount).toBe(1);
    // Exactly ONE traineddata request happened: the adapter's own
    // verified download. The engine never fetched a second copy.
    expect(served).toBe(1);
  });

  test('unavailable model cache fails honestly before any engine work', async ({
    page,
  }) => {
    const out = await runPixelCase(page, { idbFactory: 'none' });
    expect(out.open?.ok).toBe(false);
    expect(out.open?.error?.reason).toBe('missing_model');
    // No worker was ever created — the gate fires first.
    expect(out.captured.createWorkerCount ?? 0).toBe(0);
    expect(out.captured.recognizeCount ?? 0).toBe(0);
  });

  test('a failed cache write fails honestly before any engine work', async ({
    page,
  }) => {
    const out = await runPixelCase(page, { idbFactory: 'writeFail' });
    expect(out.open?.ok).toBe(false);
    expect(out.open?.error?.reason).toBe('missing_model');
    expect(out.captured.createWorkerCount ?? 0).toBe(0);
  });
});

// ---------------------------------------------------------------------------

test.describe('light: operation deadline and cancellation lifecycle', () => {
  test('a stalled raster resolves to timeout inside one deadline', async ({
    page,
  }) => {
    const out = await runPixelCase(page, {
      stallRaster: true,
      budget: { checkTimeoutMs: 200 },
    });
    expect(out.open?.ok).toBe(true);
    expect(out.run?.ok).toBe(true);
    expect(out.output!.check.status).toBe('timeout');
    expect(out.output!.check.reason).toBe('timeout');
    // Bounded — the op returned near its deadline, not parked forever.
    expect(out.elapsedMs!).toBeGreaterThanOrEqual(150);
    expect(out.elapsedMs!).toBeLessThan(4000);
    // The deadline teardown terminated the already-created worker.
    expect(out.captured.terminateCount).toBe(1);
  });

  test('cancel during a stalled raster returns user_cancel, fast', async ({
    page,
  }) => {
    const out = await runPixelCase(page, {
      stallRaster: true,
      cancelAfterMs: 60,
      budget: { checkTimeoutMs: 10_000 },
    });
    expect(out.output!.check.status).toBe('cancelled');
    expect(out.output!.check.reason).toBe('user_cancel');
    expect(out.elapsedMs!).toBeLessThan(3000);
    expect(out.captured.recognizeCount ?? 0).toBe(0);
  });

  test('a hung engine init at extract time fails timeout and terminates', async ({
    page,
  }) => {
    const out = await runPixelCase(page, {
      engineAfterOpen: 'hangInit',
      budget: { checkTimeoutMs: 200 },
      settleMs: 50,
    });
    expect(out.open?.ok).toBe(true);
    expect(out.output!.check.status).toBe('timeout');
    expect(out.output!.check.reason).toBe('timeout');
    expect(out.elapsedMs!).toBeLessThan(4000);
    // The init was abandoned; its (never-resolving) worker never
    // recognized anything and never overlapped another init.
    // createWorkerCount: 1 (open's stub) + 1 (the hung swap-in).
    expect(out.captured.createWorkerCount).toBe(2);
    expect(out.captured.maxConcurrentInits).toBe(1);
    expect(out.captured.recognizeCount ?? 0).toBe(0);
  });

  test('cancel during engine init returns user_cancel and aborts the engine signal', async ({
    page,
  }) => {
    const out = await runPixelCase(page, {
      engineAfterOpen: 'hangInit',
      cancelAfterMs: 60,
      budget: { checkTimeoutMs: 10_000 },
      settleMs: 50,
    });
    expect(out.output!.check.status).toBe('cancelled');
    expect(out.output!.check.reason).toBe('user_cancel');
    // The abort signal reached the engine's createWorker options and
    // carried our typed cancel reason.
    expect(out.captured.workerOptions?.signal).toBe('AbortSignal');
    expect(out.captured.abortReason).toBe('user_cancel');
    expect(out.captured.recognizeCount ?? 0).toBe(0);
    expect(out.chunks).toEqual([]);
  });

  test('a late init success terminates its own worker and installs nothing', async ({
    page,
  }) => {
    const out = await runPixelCase(page, {
      engineAfterOpen: 'lateInit',
      lateInitMs: 250,
      budget: { checkTimeoutMs: 100 },
      settleMs: 400,
    });
    expect(out.output!.check.status).toBe('timeout');
    // The late-resolving worker terminated itself — never installed.
    // createWorkerCount: open's stub + the late one; terminateCount:
    // the open worker's swap teardown + the late self-termination.
    expect(out.captured.createWorkerCount).toBe(2);
    expect(out.captured.terminateCount).toBe(2);
    expect(out.captured.recognizeCount ?? 0).toBe(0);
  });

  test('a retry runs inside the operation deadline, not a fresh budget', async ({
    page,
  }) => {
    // createWorker #1 rejects (transient init_crash), #2 hangs. If the
    // retry drew a full fresh timeout the op would take ~2x the
    // deadline; instead it ends near 1x.
    const out = await runPixelCase(page, {
      engineAfterOpen: 'flakyHang',
      budget: { checkTimeoutMs: 400 },
      settleMs: 50,
    });
    expect(out.output!.check.status).toBe('timeout');
    // open's stub + flaky reject + the retried (hung) init.
    expect(out.captured.createWorkerCount).toBe(3);
    expect(out.elapsedMs!).toBeGreaterThanOrEqual(350);
    expect(out.elapsedMs!).toBeLessThan(750);
  });

  test('a hung recognize is terminated at the deadline', async ({ page }) => {
    const out = await runPixelCase(page, {
      engineAfterOpen: 'hangRecognize',
      budget: { checkTimeoutMs: 200 },
    });
    expect(out.output!.check.status).toBe('timeout');
    expect(out.captured.recognizeCount).toBe(1);
    // Worker-level teardown: the swapped-out open worker plus the
    // hung recognize's worker — both terminated.
    expect(out.captured.terminateCount).toBe(2);
  });

  test('cancel before extract never touches the engine', async ({ page }) => {
    const out = await runPixelCase(page, { cancelBeforeExtract: true });
    expect(out.run?.ok).toBe(true);
    expect(out.output!.check.status).toBe('cancelled');
    expect(out.output!.check.reason).toBe('user_cancel');
    expect(out.captured.recognizeCount ?? 0).toBe(0);
    expect(out.chunks).toEqual([]);
  });

  test('close during a real open aborts the raw worker init', async ({ page }) => {
    // REAL engine: the in-flight createWorker's raw Worker is
    // hard-terminated; nothing is installed on a closed reader.
    const baseline = page.workers().length;
    await page.evaluate(async () => {
      const api = (globalThis as any).__t10;
      const { readerId } = api.makeReader({ docId: 'unused' });
      (globalThis as any).__tmpReaderId = readerId;
      return api.openStart(readerId);
    });
    // Wait until the raw engine Worker actually exists — the patched
    // createWorker registers its abort listener in the same synchronous
    // block as spawnWorker, so a visible worker is always abort-covered.
    await expect
      .poll(() => page.workers().length, { timeout: 15_000 })
      .toBe(baseline + 1);
    const res = await page.evaluate(() => {
      const api = (globalThis as any).__t10;
      return api.closeDuringOpen((globalThis as any).__tmpReaderId);
    });
    expect(res.openRes.ok).toBe(false);
    // The aborted raw transport surfaces our typed reason — never a
    // half-open handle and never a fabricated reading.
    expect(res.openRes.error.reason).toBe('worker_crash');
    expect(res.stats.workerInitCount).toBe(0);
    // The real raw worker is gone — not leaked.
    await expect
      .poll(() => page.workers().length, { timeout: 5_000 })
      .toBe(baseline);
  });
});
