import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import test, { after, before } from 'node:test';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');
const packageRoot = process.env.INKFLIP_TEST_TESSERACT_PACKAGE ?? join(root, 'apps/web/node_modules/tesseract.js');
let browser;
let server;
let temp;
let base;
let ticks = 0;

before(async () => {
  temp = mkdtempSync(join(tmpdir(), 'inkflip-worker-cancel-'));
  const entry = join(temp, 'entry.js');
  writeFileSync(entry, `import Tesseract from ${JSON.stringify(join(packageRoot, 'src/index.js'))};
window.start = (stage) => {
  window.controller = new AbortController();
  window.outcome = 'pending';
  window.ready = Tesseract.createWorker('eng', 1, {
    signal: controller.signal, workerPath: '/worker.js?stage=' + stage,
    corePath: '/unused-core/', langPath: '/unused-model/',
    workerBlobURL: false, cacheMethod: 'none', gzip: false,
  }).then((worker) => { window.worker = worker; window.outcome = 'ready'; },
    (error) => { window.outcome = error.message; });
};`);
  execFileSync('bun', ['build', entry, '--target=browser', '--outfile', join(temp, 'bundle.js')], { cwd: root });
  const bundle = readFileSync(join(temp, 'bundle.js'));
  const worker = `const stage = new URL(location.href).searchParams.get('stage');
setInterval(() => fetch('/tick'), 15);
onmessage = ({data}) => {
  if (data.action !== stage) postMessage({...data, status: 'resolve', data: {text: 'control'}});
};`;
  server = createServer((req, res) => {
    const path = new URL(req.url, 'http://localhost').pathname;
    res.setHeader('content-type', 'text/javascript');
    if (path === '/bundle.js') res.end(bundle);
    else if (path === '/worker.js') res.end(worker);
    else if (path === '/tick') { ticks += 1; res.end('ok'); }
    else { res.setHeader('content-type', 'text/html'); res.end('<script src="/bundle.js"></script>'); }
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

for (const stage of ['load', 'loadLanguage', 'initialize', 'ready']) {
  test(`real browser worker stops independent activity when aborted at ${stage}`, { timeout: 15000 }, async () => {
    const page = await browser.newPage();
    try {
      await page.goto(base);
      await page.evaluate((stage) => window.start(stage), stage);
      await page.waitForTimeout(120);
      const first = ticks;
      await page.waitForTimeout(90);
      assert.ok(ticks > first, 'positive control: real worker independently sends tick requests');
      const expected = stage === 'ready' ? 'ready' : 'pending';
      assert.equal(await page.evaluate(() => window.outcome), expected);
      await page.evaluate(() => controller.abort(new Error('cancelled by test')));
      if (stage !== 'ready') {
        await page.waitForFunction(() => window.outcome === 'cancelled by test', undefined, { timeout: 500 });
      }
      // Drain requests issued before terminate(), then prove the worker's own
      // activity stops. Suppressing its main-thread logger cannot pass this.
      await page.waitForTimeout(80);
      const stopped = ticks;
      await page.waitForTimeout(120);
      assert.equal(ticks, stopped);
    } finally {
      await page.close();
    }
  });
}

test('prepared byte input rejects on abort before any job is posted', { timeout: 15000 }, async () => {
  const page = await browser.newPage();
  try {
    await page.goto(base);
    await page.evaluate(() => window.start('ready'));
    await page.waitForFunction(() => window.outcome === 'ready');
    const outcome = await page.evaluate(async () => {
      const pending = worker.recognize(new Uint8Array([137, 80, 78, 71]));
      controller.abort(new Error('abort before image microtask'));
      return pending.then(() => 'unexpected success', (error) => error.message);
    });
    assert.equal(outcome, 'abort before image microtask');
  } finally {
    await page.close();
  }
});
