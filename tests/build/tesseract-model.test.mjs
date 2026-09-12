import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import test, { after, before } from 'node:test';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');
const packageRoot = process.env.INKFLIP_TEST_TESSERACT_PACKAGE ?? join(root, 'apps/web/node_modules/tesseract.js');
const publicRoot = join(root, 'apps/web/public');
const model = readFileSync(join(publicRoot, 'models/tessdata-fast-eng/7d4322bd/eng.traineddata'));
const expectedHash = '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2';
let browser;
let server;
let temp;
let base;
let modelRequests = 0;
const missingRequests = [];

before(async () => {
  assert.equal(createHash('sha256').update(model).digest('hex'), expectedHash);
  temp = mkdtempSync(join(tmpdir(), 'inkflip-model-payload-'));
  const entry = join(temp, 'entry.js');
  writeFileSync(entry, `import Tesseract from ${JSON.stringify(join(packageRoot, 'src/index.js'))}; window.Tesseract = Tesseract;`);
  execFileSync('bun', ['build', entry, '--target=browser', '--outfile', join(temp, 'bundle.js')], { cwd: root });
  const assets = new Map([
    ['/bundle.js', readFileSync(join(temp, 'bundle.js'))],
    ['/worker.min.js', readFileSync(join(publicRoot, 'assets/tesseract/7.0.0/worker.min.js'))],
    ['/worker-no-idb.js', Buffer.from("Object.defineProperty(self, 'indexedDB', { get() { throw Error('IndexedDB unavailable'); } }); importScripts('/worker.min.js');")],
  ]);
  const core = join(publicRoot, 'assets/tesseract-core/7.0.0');
  for (const name of readdirSync(core).filter((name) => name.endsWith('.wasm.js'))) {
    assets.set(`/core/${name}`, readFileSync(join(core, name)));
  }
  server = createServer((req, res) => {
    const path = new URL(req.url, 'http://localhost').pathname;
    res.setHeader('content-type', 'text/javascript');
    if (assets.has(path)) res.end(assets.get(path));
    else if (path === '/model.bin') {
      modelRequests += 1;
      res.setHeader('content-type', 'application/octet-stream');
      res.end(modelRequests === 1 ? model : Buffer.from([0]));
    } else if (path === '/') {
      res.setHeader('content-type', 'text/html');
      res.end('<script src="/bundle.js"></script>');
    } else {
      missingRequests.push(path);
      res.writeHead(404).end();
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true });
});

after(async () => {
  await browser?.close();
  if (server) await new Promise((resolve) => server.close(resolve));
  if (temp) rmSync(temp, { recursive: true, force: true });
});

for (const mode of ['unavailable', 'corrupt-cache']) {
  test(`real engine initializes and reinitializes from exact model bytes with ${mode}`, { timeout: 20000 }, async () => {
    modelRequests = 0;
    missingRequests.length = 0;
    const context = await browser.newContext();
    const remoteRequests = [];
    await context.route('**/*', (route) => {
      if (new URL(route.request().url()).origin === base) return route.continue();
      remoteRequests.push(route.request().url());
      return route.abort();
    });
    const page = await context.newPage();
    try {
      await page.goto(base);
      const hashes = await page.evaluate(async (mode) => {
        const bytes = new Uint8Array(await (await fetch('/model.bin')).arrayBuffer());
        if (mode === 'corrupt-cache') {
          await new Promise((resolve, reject) => {
            const open = indexedDB.open('keyval-store');
            open.onupgradeneeded = () => open.result.createObjectStore('keyval');
            open.onerror = () => reject(open.error);
            open.onsuccess = () => {
              const db = open.result;
              const tx = db.transaction('keyval', 'readwrite');
              tx.objectStore('keyval').put(new Uint8Array([0, 1, 2]), 'payload-test/eng.traineddata');
              tx.oncomplete = () => { db.close(); resolve(); };
              tx.onerror = () => { db.close(); reject(tx.error); };
            };
          });
        }
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(new Error('model initialization deadline')), 8000);
        let worker;
        try {
          worker = await Tesseract.createWorker([{ code: 'eng', data: bytes }], 1, {
            workerPath: mode === 'unavailable' ? '/worker-no-idb.js' : '/worker.min.js',
            corePath: '/core/', langPath: '/forbidden-model-download/',
            cachePath: 'payload-test', cacheMethod: 'none', gzip: false,
            workerBlobURL: false, signal: controller.signal,
          });
          const hashModel = async () => {
            const loaded = await worker.FS('readFile', ['eng.traineddata']);
            const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', loaded.data));
            return Array.from(hash, (byte) => byte.toString(16).padStart(2, '0')).join('');
          };
          const first = await hashModel();
          await worker.reinitialize([{ code: 'eng', data: bytes.slice() }], 1);
          return [first, await hashModel()];
        } finally {
          clearTimeout(timer);
          controller.abort();
          await worker?.terminate();
        }
      }, mode);
      assert.deepEqual(hashes, [expectedHash, expectedHash]);
      assert.equal(modelRequests, 1, 'only the preparation fetch obtains the model; a second would return corrupt data');
      assert.deepEqual(missingRequests.filter((path) => path !== '/favicon.ico'), []);
      assert.deepEqual(remoteRequests, []);
    } finally {
      await context.close();
    }
  });
}
