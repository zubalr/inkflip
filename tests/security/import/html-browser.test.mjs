import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { importReport } from '../../../packages/reports/validation/index.ts';
import { renderHtmlReport } from './html_export_double.mjs';

test('browser-bundled guard accepts a portable report whose fixed CSS and PNGs render without network resources', { timeout: 15000 }, async () => {
  const tmp = mkdtempSync(join(tmpdir(), 'inkflip-html-guard-'));
  const entry = join(tmp, 'entry.js');
  const bundle = join(tmp, 'bundle.js');
  const validator = fileURLToPath(new URL('../../../packages/reports/validation/index.ts', import.meta.url));
  writeFileSync(entry, 'import { assertScriptFreeHtml } from ' + JSON.stringify(validator) + '; globalThis.validateReportHtml = assertScriptFreeHtml;');
  const { report, assets } = importReport(readFileSync(new URL('../../../planning/contracts/examples/valid/native-evidence.inkflip.json', import.meta.url)));
  const html = renderHtmlReport(report, assets.sanitizedPngs);
  let browser;
  let server;
  try {
    execFileSync('bun', ['build', entry, '--target', 'browser', '--outfile', bundle], { stdio: 'pipe' });
    const js = readFileSync(bundle);
    server = createServer((req, res) => {
      if (req.url === '/favicon.ico') { res.writeHead(204).end(); return; }
      res.setHeader('Content-Type', req.url === '/bundle.js' ? 'text/javascript' : 'text/html; charset=utf-8');
      res.end(req.url === '/bundle.js' ? js : req.url === '/report' ? html : '<!doctype html><script src="/bundle.js"></script>');
    });
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
    const origin = 'http://127.0.0.1:' + server.address().port;
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    const remoteRequests = [];
    await page.route('**/*', (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) { remoteRequests.push(url.href); return route.abort(); }
      return route.continue();
    });
    await page.goto(origin);
    assert.equal(await page.evaluate((text) => {
      globalThis.validateReportHtml(text);
      return true;
    }, html), true);
    await page.goto(origin + '/report');
    const rendered = await page.evaluate(async () => {
      await Promise.all(Array.from(document.images, (img) => img.decode()));
      return {
        background: getComputedStyle(document.body).backgroundColor,
        scripts: document.scripts.length,
        images: Array.from(document.images, (img) => [img.naturalWidth, img.naturalHeight]),
        text: document.body.textContent,
      };
    });
    assert.equal(rendered.background, 'rgb(245, 243, 238)', 'fixed stylesheet was actually authorized');
    assert.equal(rendered.scripts, 0);
    assert.ok(rendered.images.length > 0);
    assert.ok(rendered.images.every(([width, height]) => width > 0 && height > 0));
    assert.ok(rendered.text.includes('Generated locally.'));
    assert.deepEqual(remoteRequests, []);
  } finally {
    if (browser) await browser.close();
    if (server?.listening) await new Promise((resolve) => server.close(resolve));
    rmSync(tmp, { recursive: true, force: true });
  }
});
