/**
 * T09 — PDF.js rendering/text reader adapter: real Chromium coverage.
 *
 * The suite builds `@inkflip/readers-pdfjs` for the browser with
 * `bun build --target browser`, serves it plus the PINNED pdfjs-dist@6.3.289
 * legacy pair (`apps/web/node_modules/pdfjs-dist/legacy/build/pdf.mjs` +
 * `pdf.worker.mjs`, the frozen-lockfile install), the T02 staged runtime
 * data assets and the T05 fixture bytes over loopback HTTP, then drives the
 * adapter inside the page exactly as the app will.
 *
 * Coverage (effective T09 acceptance criteria):
 * - real mapping/clean PDFs processed through bytes (F01, F02 + controls)
 * - raw_text is never injected/normalized (exact getTextContent strings)
 * - occurrence geometry, /Rotate and /UserUnit verified through
 *   @inkflip/geometry (F07 all rotations, F08 units 0.5/1/2/10)
 * - no glyph-paint provenance claim anywhere (manifests + occurrences)
 * - render cancellation releases the task and its canvas
 * - unavailable structure checks terminate `unsupported`, never faked
 * - committed F10 mapping variants preserve raw API strings; F11 keeps four positions
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const PDFJS_BUILD = join(ROOT, 'apps', 'web', 'node_modules', 'pdfjs-dist', 'legacy', 'build');
const PDFJS_ASSETS = join(ROOT, 'apps', 'web', 'public', 'assets', 'pdfjs', '6.3.289');
const FIXTURE_PUBLIC = join(ROOT, 'fixtures', 'public');
const FIXTURE_DEV = join(ROOT, 'fixtures', 'development');
const PKG = join(ROOT, 'packages', 'readers-pdfjs', 'src');

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.pdf': 'application/pdf',
  '.bcmap': 'application/octet-stream',
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
<title>inkflip t09 adapter harness</title>
<script type="module">
  globalThis.__t09ready = false;
  globalThis.__t09error = null;
  Promise.all([
    import('/vendor/pdfjs/pdf.mjs').then((m) => { globalThis.__pdfjs = m; }),
    import('/bundle.js'),
  ]).then(() => { globalThis.__t09ready = true; })
    .catch((e) => { globalThis.__t09error = String(e && e.stack || e); });
</script>
`;

interface Harness {
  server: Server;
  base: string;
  bundlePath: string;
  tmp: string;
}

function sha256HexFile(path: string): string {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

async function startHarness(): Promise<Harness> {
  const tmp = mkdtempSync(join(tmpdir(), 'inkflip-t09-'));
  const entry = join(tmp, 'entry.mjs');
  const bundlePath = join(tmp, 'bundle.js');
  writeFileSync(
    entry,
    [
      `import * as api from ${JSON.stringify(join(PKG, 'index.ts'))};`,
      `import * as doc from ${JSON.stringify(join(PKG, 'document.ts'))};`,
      `import * as rend from ${JSON.stringify(join(PKG, 'render.ts'))};`,
      `import * as textm from ${JSON.stringify(join(PKG, 'text.ts'))};`,
      `import * as contracts from ${JSON.stringify(join(ROOT, 'packages', 'contracts', 'src', 'index.ts'))};`,
      `import * as geometry from ${JSON.stringify(join(ROOT, 'packages', 'geometry', 'src', 'index.ts'))};`,
      `globalThis.__t09 = { api, doc, rend, textm, contracts, geometry };`,
    ].join('\n'),
  );
  execFileSync('bun', ['build', '--target', 'browser', '--format', 'esm', '--outfile', bundlePath, entry], {
    cwd: ROOT,
    stdio: 'pipe',
  });

  const server = createServer((req, res) => {
    const url = new URL(req.url ?? '/', 'http://127.0.0.1');
    const pathname = decodeURIComponent(url.pathname);
    const send = (status: number, body: Buffer | string, type = 'application/octet-stream') => {
      res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store' });
      res.end(body);
    };
    try {
      if (pathname === '/' || pathname === '/t09.html') {
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
      if (pathname.startsWith('/assets/pdfjs/6.3.289/')) {
        const rel = pathname.slice('/assets/pdfjs/6.3.289/'.length);
        const file = join(PDFJS_ASSETS, rel);
        if (!file.startsWith(PDFJS_ASSETS) || !existsSync(file)) return send(404, 'not found');
        return send(200, readFileSync(file), mimeFor(file));
      }
      if (pathname.startsWith('/fixtures/')) {
        const name = pathname.slice('/fixtures/'.length);
        if (!/^[A-Za-z0-9._-]+$/.test(name)) return send(403, 'forbidden');
        for (const dir of [FIXTURE_PUBLIC, FIXTURE_DEV]) {
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
  return { server, base: `http://127.0.0.1:${address.port}`, bundlePath, tmp };
}

let harness: Harness;

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
  await page.goto(`${harness.base}/t09.html`);
  await page.waitForFunction(
    () => (globalThis as { __t09ready?: boolean; __t09error?: unknown }).__t09ready ||
      (globalThis as { __t09error?: unknown }).__t09error,
  );
  const bootError = await page.evaluate(
    () => (globalThis as { __t09error?: unknown }).__t09error ?? null,
  );
  expect(bootError, 'module boot failure').toBeNull();
});

/** In-page adapter factory options shared by every test. */
const ADAPTER_ARGS = {
  workerSrc: '/vendor/pdfjs/pdf.worker.mjs',
  cMapUrl: '/assets/pdfjs/6.3.289/cmaps/',
  standardFontDataUrl: '/assets/pdfjs/6.3.289/standard_fonts/',
  wasmUrl: '/assets/pdfjs/6.3.289/wasm/',
  iccUrl: '/assets/pdfjs/6.3.289/iccs/',
};

// ---------------------------------------------------------------------------
// Pinned-pair identity and describe()
// ---------------------------------------------------------------------------

test('pinned pair + describe() identity and honest capabilities', async ({ page }) => {
  // The installed pair really is the pinned 6.3.289 package (T02 freeze).
  const mainSha = sha256HexFile(join(PDFJS_BUILD, 'pdf.mjs'));
  const workerSha = sha256HexFile(join(PDFJS_BUILD, 'pdf.worker.mjs'));
  expect(mainSha).toMatch(/^[0-9a-f]{64}$/);
  expect(workerSha).toMatch(/^[0-9a-f]{64}$/);
  console.log(`pinned pdf.mjs sha256=${mainSha}`);
  console.log(`pinned pdf.worker.mjs sha256=${workerSha}`);

  const out = await page.evaluate(async (adapterArgs) => {
    const { api } = (globalThis as any).__t09;
    const pdfjs = (globalThis as any).__pdfjs;
    const adapter = api.createPdfJsReader({ pdfjs, ...adapterArgs });
    const { readers, manifests } = adapter.describe();
    return {
      version: pdfjs.version,
      workerSrc: pdfjs.GlobalWorkerOptions.workerSrc ?? null,
      readers,
      manifests,
    };
  }, ADAPTER_ARGS);

  expect(out.version).toBe('6.3.289');
  const [text, render] = out.readers as Array<Record<string, any>>;
  expect(text.id).toBe('pdfjs-6_3_289-text');
  expect(render.id).toBe('pdfjs-6_3_289-render');
  expect(text.method).toBe('native_text');
  expect(render.method).toBe('render');
  expect(render.settings.annotation_mode).toBe('static_appearance');
  const support = (r: any, name: string) =>
    r.capabilities.find((c: any) => c.name === name)?.support;
  expect(support(text, 'native_text')).toBe('supported');
  expect(support(text, 'reading_order')).toBe('approximate');
  expect(support(render, 'render')).toBe('supported');
  for (const cap of ['ocr', 'object_render_mode', 'crop_metadata', 'paint_overlap', 'alignment']) {
    expect(support(text, cap), `text.${cap}`).toBe('unavailable');
    expect(support(render, cap), `render.${cap}`).toBe('unavailable');
  }
  // No glyph-paint provenance claim anywhere in identity or manifest text.
  const blob = JSON.stringify(out);
  expect(blob).toContain('not a glyph-paint');
  expect(blob).not.toMatch(/exact glyph|glyph[- ]paint provenance claimed|per-glyph exact/i);
});

// ---------------------------------------------------------------------------
// F01: real bytes through open(); raw text preserved; identical raster
// ---------------------------------------------------------------------------

test('F01 mapping vs control: bytes in, raw text out, identical raster', async ({ page }) => {
  const out = await page.evaluate(async ({ adapterArgs }) => {
    const { api, contracts } = (globalThis as any).__t09;
    const pdfjs = (globalThis as any).__pdfjs;
    const adapter = api.createPdfJsReader({ pdfjs, ...adapterArgs });

    async function runFixture(name: string) {
      const bytes = new Uint8Array(await (await fetch(`/fixtures/${name}`)).arrayBuffer());
      const sha = api.hexSha256(bytes);
      const handle = await adapter.open({ bytes, sha256: sha, generation: 1 });
      const meta = await adapter.pages(handle);
      const checks = adapter.plan(handle, {
        pages: [0],
        capabilities: ['native_text', 'render'],
      });
      const chunks: any[][] = [];
      const textOutcome = await adapter.extract(
        handle,
        checks.find((c: any) => c.capability === 'native_text'),
        (chunk: any[]) => chunks.push(chunk),
      );
      const renderOutcome = await adapter.extract(
        handle,
        checks.find((c: any) => c.capability === 'render'),
        () => undefined,
        {},
        { renderScalePxPerPt: 1 },
      );
      // Independent ground truth: same pinned build, direct getTextContent.
      const task2 = pdfjs.getDocument({ data: bytes.slice(), enableXfa: false });
      const doc2 = await task2.promise;
      const page2 = await doc2.getPage(1);
      const tc = await page2.getTextContent({
        includeMarkedContent: true,
        disableNormalization: true,
      });
      const rawStrs = tc.items
        .filter((it: any) => typeof it.str === 'string')
        .map((it: any) => it.str);
      await task2.destroy();
      const occurrences = chunks.flat();
      const normOk = occurrences.every(
        (o: any) =>
          o.normalized_text === contracts.normalize(o.raw_text).text &&
          JSON.stringify(o.normalization_map) ===
            JSON.stringify(contracts.normalize(o.raw_text).map),
      );
      const r = renderOutcome.raster;
      const rasterSha = r
        ? Array.from(api.hexSha256(new Uint8Array(r.imageData.buffer))).join('')
        : null;
      const dark = r
        ? (() => {
            let minX = r.widthPx, minY = r.heightPx, maxX = -1, maxY = -1, n = 0;
            for (let y = 0; y < r.heightPx; y++) {
              for (let x = 0; x < r.widthPx; x++) {
                const i = (y * r.widthPx + x) * 4;
                if (r.imageData[i] + r.imageData[i + 1] + r.imageData[i + 2] < 384) {
                  n++;
                  if (x < minX) minX = x;
                  if (x > maxX) maxX = x;
                  if (y < minY) minY = y;
                  if (y > maxY) maxY = y;
                }
              }
            }
            return { n, minX, minY, maxX, maxY };
          })()
        : null;
      const viewportVerified = handle.pages[0]?.viewportVerified ?? null;
      await adapter.close(handle);
      return {
        sha,
        pageCount: meta.count,
        pages: meta.pages,
        textStatus: textOutcome.result.status,
        occurrences,
        rawStrs,
        normOk,
        chunkSizes: chunks.map((c) => c.length),
        renderStatus: renderOutcome.result.status,
        rasterSha,
        raster: r
          ? { widthPx: r.widthPx, heightPx: r.heightPx, scale: r.scalePxPerPt, verified: r.viewportVerified, limitations: r.limitations }
          : null,
        dark,
        viewportVerified,
        detail: textOutcome.detail,
        bytesAfter: api.hexSha256(bytes),
      };
    }
    return {
      mapping: await runFixture('mapping-amount.pdf'),
      control: await runFixture('mapping-control.pdf'),
    };
  }, { adapterArgs: ADAPTER_ARGS });

  for (const side of ['mapping', 'control'] as const) {
    const f = out[side];
    expect(f.bytesAfter, 'source bytes mutated').toBe(f.sha);
    expect(f.pageCount).toBe(1);
    expect(f.textStatus).toBe('completed');
    expect(f.renderStatus).toBe('completed');
    expect(f.viewportVerified).toBe(true);
    expect(f.raster?.verified).toBe(true);
    // Raw adapter output is exactly the pdf.js item sequence (no injection,
    // no reordering, no normalization of raw_text).
    expect(f.occurrences.map((o: any) => o.raw_text)).toEqual(f.rawStrs);
    expect(f.occurrences.map((o: any) => o.ordinal)).toEqual(
      f.rawStrs.map((_: string, i: number) => i),
    );
    expect(f.normOk).toBe(true);
    expect(f.chunkSizes.every((n: number) => n <= 256)).toBe(true);
    // Geometry is an honest estimate, never exact/glyph-paint.
    for (const o of f.occurrences) {
      expect(['estimated', 'page_only']).toContain(o.geometry.precision);
      expect(o.limitations.join(' ')).toMatch(/not a glyph-paint/);
    }
    // The painted text raster: real marks on the page.
    expect(f.dark!.n).toBeGreaterThan(500);
  }
  // "Looks right, reads wrong": identical painted rasters, different text.
  expect(out.mapping.occurrences.map((o: any) => o.raw_text)).toContain('$1,000');
  expect(out.mapping.occurrences.map((o: any) => o.raw_text)).not.toContain('$100');
  expect(out.control.occurrences.map((o: any) => o.raw_text)).toContain('$100');
  expect(out.control.occurrences.map((o: any) => o.raw_text)).not.toContain('$1,000');
  expect(out.mapping.rasterSha).toBe(out.control.rasterSha);
  expect(out.mapping.raster?.widthPx).toBe(520);
  expect(out.mapping.raster?.heightPx).toBe(400);
});

// ---------------------------------------------------------------------------
// F02: covered text — extra raw item preserved, raster matches control
// ---------------------------------------------------------------------------

test('F02 covered vs control: hidden layer kept raw, raster unaffected', async ({ page }) => {
  const out = await page.evaluate(async ({ adapterArgs }) => {
    const { api } = (globalThis as any).__t09;
    const pdfjs = (globalThis as any).__pdfjs;
    const adapter = api.createPdfJsReader({ pdfjs, ...adapterArgs });
    async function runFixture(name: string) {
      const bytes = new Uint8Array(await (await fetch(`/fixtures/${name}`)).arrayBuffer());
      const handle = await adapter.open({
        bytes,
        sha256: api.hexSha256(bytes),
        generation: 1,
      });
      const checks = adapter.plan(handle, {
        pages: [0],
        capabilities: ['native_text', 'render'],
      });
      const chunks: any[][] = [];
      const textOutcome = await adapter.extract(
        handle,
        checks.find((c: any) => c.capability === 'native_text'),
        (c: any[]) => chunks.push(c),
      );
      const renderOutcome = await adapter.extract(
        handle,
        checks.find((c: any) => c.capability === 'render'),
        () => undefined,
      );
      const r = renderOutcome.raster;
      let dark = 0;
      if (r) {
        for (let i = 0; i < r.imageData.length; i += 4) {
          if (r.imageData[i] + r.imageData[i + 1] + r.imageData[i + 2] < 384) dark++;
        }
      }
      await adapter.close(handle);
      return {
        status: textOutcome.result.status,
        texts: chunks.flat().map((o: any) => o.raw_text),
        dark,
        dims: r ? [r.widthPx, r.heightPx] : null,
      };
    }
    return {
      covered: await runFixture('covered-amount.pdf'),
      control: await runFixture('covered-control.pdf'),
    };
  }, { adapterArgs: ADAPTER_ARGS });

  expect(out.covered.status).toBe('completed');
  // The covered early string is preserved raw — the adapter does not decide
  // what paint covered; it reports what getTextContent returned.
  expect(out.covered.texts).toContain('$1,000');
  expect(out.covered.texts).toContain('$100');
  expect(out.control.texts).toContain('$100');
  expect(out.control.texts).not.toContain('$1,000');
  expect(out.covered.texts.length).toBeGreaterThan(out.control.texts.length);
  // Paint truth: both rasters show the same final marks.
  expect(out.covered.dims).toEqual(out.control.dims);
  expect(Math.abs(out.covered.dark - out.control.dark)).toBeLessThanOrEqual(8);
});

// ---------------------------------------------------------------------------
// F07: rotation + nonzero/negative origins + UserUnit 2 through geometry
// ---------------------------------------------------------------------------

test('F07 rotations and origins: page records, R*C verification, raster dims', async ({ page }) => {
  const cases = await page.evaluate(async ({ adapterArgs }) => {
    const { api, geometry } = (globalThis as any).__t09;
    const pdfjs = (globalThis as any).__pdfjs;
    const adapter = api.createPdfJsReader({ pdfjs, ...adapterArgs });
    const results: Record<string, any> = {};
    for (const name of ['geometry-0', 'geometry-90', 'geometry-180', 'geometry-270', 'geometry-control']) {
      const bytes = new Uint8Array(await (await fetch(`/fixtures/${name}.pdf`)).arrayBuffer());
      const handle = await adapter.open({
        bytes,
        sha256: api.hexSha256(bytes),
        generation: 1,
      });
      const meta = await adapter.pages(handle);
      const hp = handle.pages[0]!;
      const page = meta.pages[0]!;
      const checks = adapter.plan(handle, { pages: [0], capabilities: ['native_text', 'render'] });
      const chunks: any[][] = [];
      await adapter.extract(
        handle,
        checks.find((c: any) => c.capability === 'native_text'),
        (c: any[]) => chunks.push(c),
      );
      const renderOutcome = await adapter.extract(
        handle,
        checks.find((c: any) => c.capability === 'render'),
        () => undefined,
      );
      const r = renderOutcome.raster!;
      // Independent analytic expectation for the display transform D = R*C.
      const expectedD = geometry.pageToDisplay(hp.built);
      const pdfjsViewport = hp.proxy.getViewport({ scale: 1 }).transform;
      const dMatch = expectedD.every(
        (v: number, i: number) => Math.abs(v - pdfjsViewport[i]) <= 1e-6,
      );
      // Recompute every occurrence polygon from the raw pdf.js item through
      // the canonical C — verifies the adapter used T04 end to end.
      const tc = await hp.proxy.getTextContent({
        includeMarkedContent: true,
        disableNormalization: true,
      });
      const C = geometry.pageToCanonical(hp.built);
      const occs = chunks.flat();
      let geometryChecked = 0;
      let geometryMismatches = 0;
      for (const occ of occs) {
        if (occ.geometry.polygon === null) continue;
        const item = tc.items.filter((it: any) => typeof it.str === 'string')[occ.ordinal];
        const style = tc.styles[item.fontName] ?? {};
        const t = item.transform;
        const ax = Math.hypot(t[0], t[1]);
        const w = item.width / ax;
        const asc = style.ascent ?? 1;
        const desc = style.descent ?? 0;
        const quad = [
          geometry.apply(t, [0, desc]),
          geometry.apply(t, [w, desc]),
          geometry.apply(t, [w, asc]),
          geometry.apply(t, [0, asc]),
        ].map((p: number[]) => geometry.apply(C, p));
        const poly = occ.geometry.polygon;
        geometryChecked++;
        for (let i = 0; i < 4; i++) {
          if (Math.abs(poly[i][0] - quad[i][0]) > 1e-6 || Math.abs(poly[i][1] - quad[i][1]) > 1e-6) {
            geometryMismatches++;
            break;
          }
        }
      }
      results[name] = {
        rotation: page.rotation,
        userUnit: page.user_unit,
        view: page.effective_view_box,
        mediaBox: page.media_box,
        cropBox: page.crop_box,
        canonicalSize: page.canonical_size_pt,
        canonicalMatrix: meta.transforms.find((t: any) => t.id === page.raw_to_canonical_transform_id)?.matrix ?? null,
        viewportVerified: hp.viewportVerified,
        dMatch,
        rasterDims: [r.widthPx, r.heightPx],
        occurrenceCount: occs.length,
        geometryChecked,
        geometryMismatches,
      };
      await adapter.close(handle);
    }
    return results;
  }, { adapterArgs: ADAPTER_ARGS });

  // [20,40,500,390] view at u=2 -> C=[2,0,0,-2,-40,780], canonical 960x700.
  const rotated: Record<string, number> = {
    'geometry-0': 0,
    'geometry-90': 90,
    'geometry-180': 180,
    'geometry-270': 270,
  };
  for (const [name, rot] of Object.entries(rotated)) {
    const r = cases[name];
    expect(r.rotation, name).toBe(rot);
    expect(r.userUnit, name).toBe(2);
    expect(r.view, name).toEqual([20, 40, 500, 390]);
    expect(r.mediaBox, `${name} media_box must be null (unavailable)`).toBeNull();
    expect(r.cropBox, `${name} crop_box must be null (unavailable)`).toBeNull();
    expect(r.canonicalSize, name).toEqual([960, 700]);
    expect(r.canonicalMatrix, name).toEqual([2, 0, 0, -2, -40, 780]);
    expect(r.viewportVerified, name).toBe(true);
    expect(r.dMatch, name).toBe(true);
    expect(r.geometryMismatches, name).toBe(0);
    expect(r.geometryChecked, name).toBeGreaterThan(0);
    expect(r.occurrenceCount, name).toBeGreaterThan(0);
    const [w, h] = rot === 90 || rot === 270 ? [700, 960] : [960, 700];
    expect(r.rasterDims, name).toEqual([w, h]);
  }
  const control = cases['geometry-control'];
  expect(control.rotation).toBe(0);
  expect(control.userUnit).toBe(1);
  expect(control.view).toEqual([0, 0, 520, 400]);
  expect(control.canonicalSize).toEqual([520, 400]);
  expect(control.canonicalMatrix).toEqual([1, 0, 0, -1, 0, 400]);
  expect(control.viewportVerified).toBe(true);
  expect(control.dMatch).toBe(true);
  expect(control.rasterDims).toEqual([520, 400]);
});

// ---------------------------------------------------------------------------
// F08: UserUnit applied exactly once (0.5/1/2/10), raster fiducial check
// ---------------------------------------------------------------------------

test('F08 UserUnit values: no double scaling, fiducial square lands exactly', async ({ page }) => {
  const cases = await page.evaluate(async ({ adapterArgs }) => {
    const { api } = (globalThis as any).__t09;
    const pdfjs = (globalThis as any).__pdfjs;
    const adapter = api.createPdfJsReader({ pdfjs, ...adapterArgs });
    const results: Record<string, any> = {};
    for (const name of ['userunit-0.5', 'userunit-1', 'userunit-2', 'userunit-10']) {
      const bytes = new Uint8Array(await (await fetch(`/fixtures/${name}.pdf`)).arrayBuffer());
      const handle = await adapter.open({
        bytes,
        sha256: api.hexSha256(bytes),
        generation: 1,
      });
      const meta = await adapter.pages(handle);
      const page = meta.pages[0]!;
      const checks = adapter.plan(handle, { pages: [0], capabilities: ['render'] });
      const outcome = await adapter.extract(handle, checks[0], () => undefined);
      const r = outcome.raster!;
      // The fiducial square: user-space [372,250]-[472,350] -> display x
      // right edge at 472*u pt; find the rightmost dark pixel.
      let maxX = -1;
      for (let y = 0; y < r.heightPx; y++) {
        for (let x = r.widthPx - 1; x > maxX; x--) {
          const i = (y * r.widthPx + x) * 4;
          if (r.imageData[i] + r.imageData[i + 1] + r.imageData[i + 2] < 384) {
            maxX = x;
            break;
          }
        }
      }
      results[name] = {
        userUnit: page.user_unit,
        canonicalSize: page.canonical_size_pt,
        verified: handle.pages[0]!.viewportVerified && r.viewportVerified,
        scale: r.scalePxPerPt,
        dims: [r.widthPx, r.heightPx],
        maxDarkX: maxX,
        downsampled: r.limitations.some((l: string) => l.includes('downsampled')),
      };
      await adapter.close(handle);
    }
    return results;
  }, { adapterArgs: ADAPTER_ARGS });

  const expectedUnits: Record<string, number> = {
    'userunit-0.5': 0.5,
    'userunit-1': 1,
    'userunit-2': 2,
    'userunit-10': 10,
  };
  for (const [name, u] of Object.entries(expectedUnits)) {
    const r = cases[name];
    expect(r.userUnit, name).toBe(u);
    expect(r.canonicalSize, name).toEqual([520 * u, 400 * u]);
    expect(r.verified, `${name}: pdf.js viewport must equal R*C (single UserUnit)`).toBe(true);
    // Physical raster dims: 520u x 400u pt at the actual (possibly clamped)
    // scale; the adapter sizes its canvas with Math.ceil of the viewport.
    expect(r.dims[0], name).toBe(Math.ceil(520 * u * r.scale - 1e-9));
    expect(r.dims[1], name).toBe(Math.ceil(400 * u * r.scale - 1e-9));
    expect(r.dims[0] * r.dims[1], `${name} must stay within 4 MP after integer canvas sizing`).toBeLessThanOrEqual(4_000_000);
    // Fiducial square right edge: 372+100=472 user units -> 472u display pt.
    // If UserUnit were applied twice the mark would sit at ~472u^2*scale'.
    const expectedX = 472 * u * r.scale;
    expect(Math.abs(r.maxDarkX - expectedX), name).toBeLessThanOrEqual(Math.max(3, u * r.scale));
  }
  expect(cases['userunit-10'].downsampled, 'u=10 exceeds the 4Mpx cap and must record it').toBe(true);
  expect(cases['userunit-0.5'].downsampled).toBe(false);
});

// ---------------------------------------------------------------------------
// Cancellation: render task + canvas released; text mid-walk cancel
// ---------------------------------------------------------------------------

test('render cancellation releases task and canvas; later renders unaffected', async ({ page }) => {
  const out = await page.evaluate(async ({ adapterArgs }) => {
    const { api, doc, rend } = (globalThis as any).__t09;
    const pdfjs = (globalThis as any).__pdfjs;
    const adapter = api.createPdfJsReader({ pdfjs, ...adapterArgs });
    const bytes = new Uint8Array(await (await fetch('/fixtures/geometry-0.pdf')).arrayBuffer());
    const handle = await adapter.open({
      bytes,
      sha256: api.hexSha256(bytes),
      generation: 1,
    });
    const checks = adapter.plan(handle, { pages: [0], capabilities: ['render'] });
    const check = checks[0];

    // (a) Adapter-level: already-aborted signal -> terminal cancelled, no work.
    const ctrl0 = new AbortController();
    ctrl0.abort();
    const early = await adapter.extract(handle, check, () => undefined, { signal: ctrl0.signal });

    // (b) Real RenderTask cancelled while in flight: the pre-aborted signal
    // reaches the adapter-owned RenderTask, which must be cancelled and its
    // canvas released to 0x0 in every outcome.
    const created: any[] = [];
    const origCreate = document.createElement.bind(document);
    (document as any).createElement = (tag: string, ...rest: any[]) => {
      const el = origCreate(tag, ...rest);
      if (tag === 'canvas') created.push(el);
      return el;
    };
    let thrown: any = null;
    try {
      const hp = await doc.handlePage(adapter.config, handle, 0);
      const ctrl = new AbortController();
      ctrl.abort();
      await rend.renderPage(adapter.config, handle, hp, 1, 0, ctrl.signal);
    } catch (error: any) {
      thrown = { failure: error.failure ?? null, reason: error.reason ?? String(error) };
    } finally {
      (document as any).createElement = origCreate;
    }
    const canvasStates = created.map((c) => [c.width, c.height]);

    // (c) A healthy render afterwards proves no half-alive task/canvas leaks.
    const ok = await adapter.extract(handle, check, () => undefined);
    await adapter.close(handle);
    return {
      earlyStatus: early.result.status,
      earlyReason: early.result.reason,
      thrown,
      canvasStates,
      afterStatus: ok.result.status,
      afterRaster: ok.raster ? [ok.raster.widthPx, ok.raster.heightPx] : null,
    };
  }, { adapterArgs: ADAPTER_ARGS });

  expect(out.earlyStatus).toBe('cancelled');
  expect(out.earlyReason).toBe('user_cancel');
  expect(out.thrown?.failure).toBe('cancelled');
  expect(out.thrown?.reason).toBe('user_cancel');
  expect(out.canvasStates.length).toBeGreaterThan(0);
  for (const [w, h] of out.canvasStates) {
    expect([w, h], 'cancelled render must release its canvas to 0x0').toEqual([0, 0]);
  }
  expect(out.afterStatus).toBe('completed');
  expect(out.afterRaster).toEqual([960, 700]);
});

test('text extraction mid-walk cancel retains produced evidence', async ({ page }) => {
  const out = await page.evaluate(async ({ adapterArgs }) => {
    const { api } = (globalThis as any).__t09;
    const pdfjs = (globalThis as any).__pdfjs;
    // chunkOccurrences:1 forces a flush per item so the abort lands mid-walk.
    const adapter = api.createPdfJsReader({
      pdfjs,
      ...adapterArgs,
      limits: { chunkOccurrences: 1 },
    });
    const bytes = new Uint8Array(await (await fetch('/fixtures/covered-amount.pdf')).arrayBuffer());
    const handle = await adapter.open({
      bytes,
      sha256: api.hexSha256(bytes),
      generation: 1,
    });
    const checks = adapter.plan(handle, { pages: [0], capabilities: ['native_text'] });
    const ctrl = new AbortController();
    const chunks: any[][] = [];
    const outcome = await adapter.extract(
      handle,
      checks[0],
      (c: any[]) => {
        chunks.push(c);
        ctrl.abort();
      },
      { signal: ctrl.signal },
    );
    await adapter.close(handle);
    return {
      status: outcome.result.status,
      reason: outcome.result.reason,
      produced: outcome.result.produced_occurrence_count,
      retained: outcome.result.retained_occurrence_ids,
      emitted: chunks.flat().length,
    };
  }, { adapterArgs: ADAPTER_ARGS });

  expect(out.status).toBe('cancelled');
  expect(out.reason).toBe('user_cancel');
  expect(out.produced).toBe(1);
  expect(out.retained.length).toBe(1);
  expect(out.emitted).toBe(1);
});

// ---------------------------------------------------------------------------
// Unsupported structure checks — terminal unsupported, never faked
// ---------------------------------------------------------------------------

test('unavailable capabilities terminate unsupported with named reasons', async ({ page }) => {
  const out = await page.evaluate(async ({ adapterArgs }) => {
    const { api } = (globalThis as any).__t09;
    const pdfjs = (globalThis as any).__pdfjs;
    const adapter = api.createPdfJsReader({ pdfjs, ...adapterArgs });
    const bytes = new Uint8Array(await (await fetch('/fixtures/mapping-control.pdf')).arrayBuffer());
    const handle = await adapter.open({
      bytes,
      sha256: api.hexSha256(bytes),
      generation: 1,
    });
    const capabilities = ['structure', 'ocr', 'object_render_mode', 'paint_overlap', 'crop_metadata', 'alignment'];
    const checks = adapter.plan(handle, { pages: [0], capabilities });
    const results = [];
    for (const check of checks) {
      const outcome = await adapter.extract(handle, check, () => undefined);
      results.push({
        capability: check.capability,
        status: outcome.result.status,
        reason: outcome.result.reason,
        produced: outcome.result.produced_occurrence_count,
      });
    }
    await adapter.close(handle);
    return results;
  }, { adapterArgs: ADAPTER_ARGS });

  expect(out.length).toBe(6);
  for (const r of out) {
    expect(r.status, r.capability).toBe('unsupported');
    expect(r.reason, r.capability).toMatch(/^unsupported:/);
    expect(r.produced).toBe(0);
  }
});

// ---------------------------------------------------------------------------
// Lifecycle: digest verification, close isolation, immutable bytes
// ---------------------------------------------------------------------------

test('open verifies digest; closing one generation spares the next', async ({ page }) => {
  const out = await page.evaluate(async ({ adapterArgs }) => {
    const { api } = (globalThis as any).__t09;
    const pdfjs = (globalThis as any).__pdfjs;
    const adapter = api.createPdfJsReader({ pdfjs, ...adapterArgs });
    const bytes = new Uint8Array(await (await fetch('/fixtures/mapping-control.pdf')).arrayBuffer());
    const sha = api.hexSha256(bytes);

    let digestError: string | null = null;
    try {
      await adapter.open({ bytes, sha256: '0'.repeat(64), generation: 1 });
    } catch (error: any) {
      digestError = String(error?.message ?? error);
    }

    const first = await adapter.open({ bytes, sha256: sha, generation: 1 });
    const second = await adapter.open({ bytes, sha256: sha, generation: 2 });
    await adapter.close(first);
    const checks = adapter.plan(second, { pages: [0], capabilities: ['native_text'] });
    const chunks: any[][] = [];
    const outcome = await adapter.extract(second, checks[0], (c: any[]) => chunks.push(c));

    let closedError: string | null = null;
    try {
      await adapter.extract(first, checks[0], () => undefined);
    } catch (error: any) {
      closedError = String(error?.reason ?? error?.message ?? error);
    }
    await adapter.close(second);
    return {
      digestError,
      afterCloseStatus: outcome.result.status,
      occurrences: chunks.flat().length,
      closedError,
      bytesAfter: api.hexSha256(bytes),
      sha,
    };
  }, { adapterArgs: ADAPTER_ARGS });

  expect(out.digestError).toMatch(/digest/);
  expect(out.afterCloseStatus).toBe('completed');
  expect(out.occurrences).toBeGreaterThan(0);
  expect(out.closedError).toMatch(/closed/);
  expect(out.bytesAfter).toBe(out.sha);
});

// ---------------------------------------------------------------------------
// F10/F11 committed fixture bytes and independent raw-reader comparison
// ---------------------------------------------------------------------------

test('F10/F11 real bytes preserve mapping outputs and four duplicate positions', async ({ page }) => {
  const outputs = await page.evaluate(async (adapterArgs) => {
    const { api } = (globalThis as any).__t09;
    const pdfjs = (globalThis as any).__pdfjs;
    const adapter = api.createPdfJsReader({ pdfjs, ...adapterArgs });
    const outputs = [];
    for (const name of [
      'mapping-missing-control.pdf', 'mapping-missing-absent.pdf',
      'mapping-missing-malformed.pdf', 'duplicates-control.pdf', 'duplicates-four.pdf',
    ]) {
      const bytes = new Uint8Array(await (await fetch(`/fixtures/${name}`)).arrayBuffer());
      const sha = api.hexSha256(bytes);
      const handle = await adapter.open({ bytes, sha256: sha, generation: 1 });
      const [check] = adapter.plan(handle, { pages: [0], capabilities: ['native_text'] });
      const chunks: any[][] = [];
      const outcome = await adapter.extract(handle, check, (chunk: any[]) => chunks.push(chunk));
      const task = pdfjs.getDocument({ data: bytes.slice(), enableXfa: false });
      const direct = await task.promise;
      const directPage = await direct.getPage(1);
      const content = await directPage.getTextContent({ includeMarkedContent: true, disableNormalization: true });
      const raw = content.items.filter((item: any) => typeof item.str === 'string').map((item: any) => item.str);
      await task.destroy();
      await adapter.close(handle);
      outputs.push({ name, sha, bytesAfter: api.hexSha256(bytes), status: outcome.result.status, occurrences: chunks.flat(), raw });
    }
    return outputs;
  }, ADAPTER_ARGS);

  for (const output of outputs) {
    expect(output.status, output.name).toBe('completed');
    expect(output.bytesAfter, output.name).toBe(output.sha);
    expect(output.occurrences.map((item: any) => item.raw_text), output.name).toEqual(output.raw);
    expect(output.occurrences.map((item: any) => item.ordinal), output.name).toEqual(output.raw.map((_: string, i: number) => i));
  }
  const control = outputs.find((item) => item.name === 'duplicates-control.pdf')!;
  const duplicate = outputs.find((item) => item.name === 'duplicates-four.pdf')!;
  expect(control.occurrences.filter((item: any) => item.raw_text === '$100')).toHaveLength(1);
  const amounts = duplicate.occurrences.filter((item: any) => item.raw_text === '$100');
  expect(amounts).toHaveLength(4);
  expect(new Set(amounts.map((item: any) => item.id)).size).toBe(4);
  expect(new Set(amounts.map((item: any) => item.ordinal)).size).toBe(4);
  expect(new Set(amounts.map((item: any) => JSON.stringify(item.geometry.polygon))).size).toBe(4);
  expect(amounts.every((item: any) => item.geometry.precision === 'estimated')).toBe(true);
});
