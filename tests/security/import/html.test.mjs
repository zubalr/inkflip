// T24 / TEST-24 — "HTML export opens script-free" evidence.
//
// The planning reference exporter (planning/tools/export_html.py) cannot
// run in this checkout (its contractlib needs the uninstalled planning
// `jsonschema`), so tests render through a faithful test double —
// tests/security/import/html_export_double.mjs — implementing the same
// fixed stylesheet + meta-CSP + escape-everything contract, and feed its
// output through the shipped guard `assertScriptFreeHtml`. Hostile report
// fields prove escaping holds; hand-crafted active documents prove the
// guard fails closed. The T16 product exporter must pass the same guard.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import {
  ContractError,
  normalize,
  seal,
} from '../../../packages/contracts/src/index.ts';
import {
  assertScriptFreeHtml,
  escapeHtml,
  importReport,
} from '../../../packages/reports/validation/index.ts';
import { renderHtmlReport, CSS, cssCspHash } from './html_export_double.mjs';
import { makePng, patternRgba, rowsFor } from './png_helpers.mjs';
import { sha256 } from '../../../packages/contracts/src/index.ts';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const VALID_DIR = join(ROOT, 'planning/contracts/examples/valid');

const code = (fn) => {
  try {
    fn();
  } catch (e) {
    if (e instanceof ContractError) return e.code;
    throw e;
  }
  return null;
};
const hex = (u8) => [...u8].map((b) => b.toString(16).padStart(2, '0')).join('');
const loadJson = (name) => JSON.parse(readFileSync(join(VALID_DIR, name), 'utf8'));

const importAndRender = (raw) => {
  const res = importReport(raw);
  return { res, html: renderHtmlReport(res.report, res.assets.sanitizedPngs) };
};

// ---------------------------------------------------------------------------
// Every delivered valid report renders script-free
// ---------------------------------------------------------------------------

test('all delivered valid reports render script-free HTML', () => {
  const files = readdirSync(VALID_DIR).filter((f) => f.endsWith('.json'));
  for (const f of files) {
    const parsed = JSON.parse(readFileSync(join(VALID_DIR, f), 'utf8'));
    if (parsed.kind !== 'report') continue;
    const { html } = importAndRender(readFileSync(join(VALID_DIR, f)));
    assert.doesNotThrow(() => assertScriptFreeHtml(html), f);
    // lexical spot checks as well (entity-normalize for the escaped CSP)
    const lower = html.toLowerCase();
    assert.ok(!lower.includes('<script'), `${f}: script tag`);
    const plain = lower.replaceAll('&#x27;', "'").replaceAll('&#39;', "'");
    assert.ok(plain.includes("default-src 'none'"), `${f}: CSP`);
  }
});

// ---------------------------------------------------------------------------
// Hostile strings are inert data on import and escaped on export
// ---------------------------------------------------------------------------

const PAYLOADS = [
  '</title><script>alert(document.domain)</script>',
  '<img src=x onerror=alert(1)>',
  '<svg onload=alert(1)>',
  'javascript:alert(1)',
  '"><script>alert(1)</script><"',
  '<iframe src="https://evil.example"></iframe>',
  '<form action="https://evil.example"><input name=x></form>',
  '<base href="https://evil.example/">',
  '<meta http-equiv="refresh" content="0;url=https://evil.example">',
  'x" style="background:url(https://evil.example)" data-x="',
  'text with http://autolink.example/path and https://second.example',
  ' RTL override content',
  '<a href="javascript:alert(1)">click</a>',
  '<object data="data:text/html,<script>alert(1)</script>"></object>',
  '<!--[if IE]><script>alert(1)</script><![endif]-->',
  '</pre><img src="data:image/svg+xml,<svg onload=alert(1)>">',
];

test('hostile report fields import as inert text and export escaped', () => {
  const base = loadJson('native-evidence.inkflip.json');
  let n = 0;
  for (const payload of PAYLOADS) {
    const r = structuredClone(base);
    // rotate hostile text across every rendered string field
    const slot = n % 4;
    if (slot === 0) r.findings[0].title = payload;
    if (slot === 1) r.findings[0].explanation = payload;
    if (slot === 2) r.readers[0].name = payload.slice(0, 100);
    if (slot === 3) {
      r.occurrences[0].raw_text = payload;
      const nrm = normalize(payload);
      r.occurrences[0].normalized_text = nrm.text;
      r.occurrences[0].normalization_map = nrm.map;
    }
    r.limitations = [payload.slice(0, 2000)];
    seal(r);
    n++;
    const raw = JSON.stringify(r);
    const { res, html } = importAndRender(raw); // must import — text is inert
    assert.equal(code(() => assertScriptFreeHtml(html)), null, payload);
    // no markup may survive unescaped; words like `onerror=` or
    // `javascript:` are fine — and expected — inside escaped text.
    for (const tag of ['<script', '<svg', '<iframe', '<form', '<object']) {
      assert.ok(!html.includes(tag), `${tag} leaked via ${payload}`);
    }
    if (escapeHtml(payload) !== payload) {
      assert.ok(!html.includes(payload), `raw payload leaked: ${payload}`);
    }
    // and the escaped evidence is present when the field is rendered
    if (slot === 0) {
      assert.ok(
        html.includes(escapeHtml(payload)),
        `escaped payload missing for ${payload}`,
      );
    }
  }
});

test('an occurrence with markup payloads keeps raw text fidelity (I03)', () => {
  const r = structuredClone(loadJson('native-evidence.inkflip.json'));
  const payload = '<bdo>\u202e<script>alert(1)</script> total: $1,200.00';
  r.occurrences[0].raw_text = payload;
  const nrm = normalize(payload);
  r.occurrences[0].normalized_text = nrm.text;
  r.occurrences[0].normalization_map = nrm.map;
  seal(r);
  const res = importReport(JSON.stringify(r));
  // raw text is preserved byte-for-byte; normalization never erased the
  // digit/currency content
  assert.equal(res.report.occurrences[0].raw_text, payload);
  assert.ok(nrm.text.includes('1,200.00'));
});

// ---------------------------------------------------------------------------
// The guard fails closed on hand-crafted active documents
// ---------------------------------------------------------------------------

const VALID_PREFIX =
  '<!doctype html><html><head><meta charset="utf-8">' +
  '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'sha256-' +
  cssCspHash() + '\'; base-uri \'none\'; form-action \'none\'">' +
  '<title>t</title><style>' + CSS + '</style></head><body><main>';
const VALID_SUFFIX = '</main></body></html>';

test('guard accepts a minimal conforming document', () => {
  const doc = VALID_PREFIX + '<p>hi</p>' + VALID_SUFFIX;
  assert.equal(code(() => assertScriptFreeHtml(doc)), null);
  const withImg =
    VALID_PREFIX +
    '<img alt="x" src="data:image/png;base64,iVBORw0KGgo=">' +
    VALID_SUFFIX;
  assert.equal(code(() => assertScriptFreeHtml(withImg)), null);
});

test('guard rejects every active-content construct', () => {
  const active = [
    '<script>alert(1)</script>',
    '<ScRiPt>alert(1)</ScRiPt>',
    '<img src=x onerror=alert(1)>',
    '<p onclick="x">t</p>',
    '<a href="https://e.example">l</a>',
    '<img src="https://e.example/x.png">',
    '<img srcset="https://e.example/x.png 2x">',
    '<img src="data:image/svg+xml;base64,AAAA">',
    '<img src="data:text/html;base64,AAAA">',
    '<iframe src="x"></iframe>',
    '<object data="x"></object>',
    '<embed src="x">',
    '<form><input></form>',
    '<input value="x">',
    '<button>x</button>',
    '<link rel="stylesheet" href="x.css">',
    '<base href="https://e.example/">',
    '<meta http-equiv="refresh" content="0;url=x">',
    '<svg><rect/></svg>',
    '<video src="x"></video>',
    '<audio src="x"></audio>',
    '<template><script>x</script></template>',
    '<math><mi>x</mi></math>',
    '<?xml version="1.0"?>',
    '<!--[if IE]>x<![endif]-->',
    '<img src="xjavascript:alert(1)">',
    '<img src="java&#x73;cript:alert(1)">',
    '<p style="background:url(x)">t</p>',
  ];
  for (const frag of active) {
    const doc = VALID_PREFIX + frag + VALID_SUFFIX;
    assert.equal(
      code(() => assertScriptFreeHtml(doc)),
      'HTML',
      frag,
    );
  }
});

test('guard rejects missing or weakened CSP', () => {
  const noCsp = '<!doctype html><html><body><p>x</p></body></html>';
  assert.equal(code(() => assertScriptFreeHtml(noCsp)), 'HTML');
  const weak = VALID_PREFIX.replace("default-src 'none'", "default-src 'self'") + 'x' + VALID_SUFFIX;
  assert.equal(code(() => assertScriptFreeHtml(weak)), 'HTML');
  const noImg = VALID_PREFIX.replace('img-src data:', 'img-src *') + 'x' + VALID_SUFFIX;
  assert.equal(code(() => assertScriptFreeHtml(noImg)), 'HTML');
});

test('guard rejects hostile CSS inside the style block', () => {
  for (const css of [
    'body{background:url(https://e.example)}',
    '@import "https://e.example/x.css";',
    'x{behavior:url(x.htc)}',
    'x{width:expression(alert(1))}',
    'x{background:-moz-binding:url(x.xml#xss)}',
  ]) {
    const doc = VALID_PREFIX.replace(CSS, css) + 'x' + VALID_SUFFIX;
    assert.equal(code(() => assertScriptFreeHtml(doc)), 'HTML', css);
  }
});

test('embedded crops are the sanitized re-encode, not attacker bytes', () => {
  const r = structuredClone(loadJson('native-evidence.inkflip.json'));
  // give the crop a hostile ancillary chunk — the sanitized bytes carried
  // into the HTML must contain none of it
  const tEXt = new TextEncoder().encode('evil\u0000<script>alert(1)</script>');
  const png = makePng({
    width: 4, height: 4, colorType: 6, bitDepth: 8,
    pixelRows: rowsFor(patternRgba(4, 4), 4, 4, 6, 8),
    preIdat: [{ type: 'tEXt', data: tEXt }],
  });
  const a = r.assets[0];
  a.sha256 = hex(sha256(png));
  a.byte_length = png.length;
  a.pixel_size = [4, 4];
  a.data_base64 = Buffer.from(png).toString('base64');
  seal(r);
  const { res, html } = importAndRender(JSON.stringify(r));
  const clean = res.assets.sanitizedPngs.get(a.id);
  assert.ok(html.includes(Buffer.from(clean.png).toString('base64')));
  assert.ok(!html.includes('<script'));
});
