import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { inflateSync, deflateSync } from 'node:zlib';
import { ContractError } from '../../../packages/contracts/src/index.ts';
import {
  assertScriptFreeHtml, importArtifact, importReport, importStringBounds,
  IMPORT_LIMITS, decodePng, inflateZlib,
} from '../../../packages/reports/validation/index.ts';
import { chunk, concatBytes, ihdr, makePng, PNG_SIG } from './png_helpers.mjs';
import { CSS, cssCspHash, renderHtmlReport } from './html_export_double.mjs';
import { createHash } from 'node:crypto';

const fails = (code) => (error) => error instanceof ContractError && error.code === code;
const policy = "default-src 'none'; img-src data:; style-src 'sha256-" + cssCspHash() + "'; base-uri 'none'; form-action 'none'";
const document = (csp = policy, css = CSS) => '<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="' + csp + '"><style>' + css + '</style></head><body><p>report</p></body></html>';
const stylePolicy = (css) => policy.replace(cssCspHash(), createHash('sha256').update(css).digest('base64'));
const reportBytes = () => readFileSync(new URL('../../../planning/contracts/examples/valid/native-evidence.inkflip.json', import.meta.url));

for (const [name, csp] of Object.entries({
  noneWithWildcard: policy.replace("default-src 'none'", "default-src 'none' *"),
  duplicate: "default-src *; " + policy,
  directiveSubstring: policy.replace('default-src', 'fake-default-src'),
  imageHost: policy.replace('img-src data:', 'img-src data: https:'),
  scriptOverride: policy + "; script-src 'unsafe-inline'",
  styleWildcard: policy.replace(/style-src [^;]+/, "style-src * 'unsafe-inline'"),
})) {
  test('CSP refuses ' + name, () => assert.throws(() => assertScriptFreeHtml(document(csp)), fails('HTML')));
}

test('CSP must be a real early meta attribute, never text in another value', () => {
  const fake = '<meta http-equiv="Content-Security-Policy" name=\'content="' + policy + '"\'>';
  const docs = [
    '<!doctype html><html><head>' + fake + '</head><body>report</body></html>',
    '<!doctype html><html><head><!--' + document() + '--></head><body>report</body></html>',
    '<!doctype html><html><head><title>' + document() + '</title></head><body>report</body></html>',
  ];
  for (const html of docs) assert.throws(() => assertScriptFreeHtml(html), fails('HTML'));
});

for (const css of ['@\\69mport "https://example.invalid/x";', 'p{background:u\\72l(https://example.invalid/x)}', 'p{background:url/**/(https://example.invalid/x)}', 'p{x:vbscript:alert(1)}']) {
  test('CSS tripwire checks encoded/comment-separated constructs: ' + css, () => {
    assert.throws(() => assertScriptFreeHtml(document(stylePolicy(css), css)), fails('HTML'));
  });
}

test('styles must close and match their exact CSP hash', () => {
  assert.throws(() => assertScriptFreeHtml(document().replace('</style>', '')), fails('HTML'));
  assert.throws(() => assertScriptFreeHtml(document(policy, 'p{color:red}')), fails('HTML'));
  assert.doesNotThrow(() => assertScriptFreeHtml(document()));
  const safe = '/* owned comment */ p { color: red }';
  assert.doesNotThrow(() => assertScriptFreeHtml(document(stylePolicy(safe), safe)));
});

const header = ihdr({ width: 1, height: 1 });
const packed = new Uint8Array(deflateSync(Uint8Array.from([0, 1, 2, 3, 255])));
const png = (middle) => concatBytes([PNG_SIG, chunk('IHDR', header), ...middle, chunk('IEND', new Uint8Array())]);
for (const [name, middle] of Object.entries({
  duplicateHeader: [chunk('IHDR', header), chunk('IDAT', packed)],
  paletteAfterData: [chunk('IDAT', packed), chunk('PLTE', Uint8Array.from([1, 2, 3]))],
  splitData: [chunk('IDAT', packed.subarray(0, 2)), chunk('tEXt', Uint8Array.from([65, 0, 66])), chunk('IDAT', packed.subarray(2))],
})) {
  test('PNG refuses malformed chunk ordering: ' + name, () => assert.throws(() => decodePng(png(middle)), fails('PNG')));
}

test('PNG refuses duplicate transparency on an otherwise valid RGB image', () => {
  const transparency = chunk('tRNS', new Uint8Array(6));
  const data = concatBytes([PNG_SIG, chunk('IHDR', ihdr({ width: 1, height: 1, colorType: 2 })),
    transparency, transparency, chunk('IDAT', new Uint8Array(deflateSync(Uint8Array.from([0, 1, 2, 3])))), chunk('IEND', new Uint8Array())]);
  assert.throws(() => decodePng(data), fails('PNG'));
});

test('consecutive IDAT chunks and ignored ancillary metadata remain valid', () => {
  const data = png([chunk('IDAT', packed.subarray(0, 2)), chunk('IDAT', packed.subarray(2)), chunk('tEXt', Uint8Array.from([65, 0, 66]))]);
  assert.deepEqual(decodePng(data).rgba, Uint8Array.from([1, 2, 3, 255]));
});

// RFC1951 dynamic block: literal 0 and end-of-block are used; no distance
// code exists. Node zlib is an independent decoder, not the oracle under test.
function noDistanceStream(useLength = false) {
  const bits = [];
  const write = (value, count) => { for (let n = 0; n < count; n++) bits.push((value >> n) & 1); };
  write(1, 1); write(2, 2); write(1, 5); write(0, 5); write(14, 4);
  const order = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1];
  for (const symbol of order) write(symbol === 0 ? 1 : symbol === 1 || symbol === 2 ? 2 : 0, 3);
  for (let symbol = 0; symbol < 259; symbol++) {
    const length = symbol === 0 ? 1 : symbol === 256 || symbol === 257 ? 2 : 0;
    write(length === 0 ? 0 : length === 1 ? 1 : 3, length === 0 ? 1 : 2);
  }
  write(0, 1); // literal 0
  if (useLength) write(3, 2); // length257 requires an unavailable distance
  write(1, 2); // end-of-block256
  const bytes = new Uint8Array(Math.ceil(bits.length / 8));
  bits.forEach((bit, i) => { bytes[i >> 3] |= bit << (i & 7); });
  return concatBytes([Uint8Array.from([0x78, 0x01]), bytes, Uint8Array.from([0, 1, 0, 1])]);
}

test('valid literal-only deflate accepts an empty distance table', () => {
  const data = noDistanceStream();
  assert.deepEqual(new Uint8Array(inflateSync(data)), Uint8Array.from([0]));
  assert.deepEqual(inflateZlib(data, 1), Uint8Array.from([0]));
  assert.throws(() => inflateZlib(noDistanceStream(true), 4), fails('PNG'));
});

test('import string limits cover keys, array strings and only real root asset payloads', () => {
  const large = 'x'.repeat(IMPORT_LIMITS.maxStringChars + 1);
  for (const value of [{ [large]: 0 }, { notes: [large] }, { data_base64: large }, { nested: { assets: [{ data_base64: large }] } }]) {
    assert.throws(() => importStringBounds(value), fails('SIZE'));
  }
  assert.doesNotThrow(() => importStringBounds({ assets: [{ data_base64: large }] }));
  assert.throws(() => importStringBounds({ assets: [{ data_base64: large, notes: [large] }] }), fails('SIZE'));
  assert.doesNotThrow(() => importStringBounds({ notes: ['😀'.repeat(IMPORT_LIMITS.maxStringChars)] }));
});

test('imports cannot opt out of identity verification', () => {
  const changed = JSON.parse(reportBytes());
  changed.findings[0].title += ' changed without resealing';
  const raw = JSON.stringify(changed);
  for (const importer of [importArtifact, importReport]) {
    assert.throws(() => importer(raw, false), fails('HASH'));
    assert.throws(() => importer(raw), fails('HASH'));
  }
  assert.doesNotThrow(() => importReport(reportBytes()));
});

test('unpaired surrogates cannot be replaced during string input encoding', () => {
  assert.throws(() => importArtifact('{"x":"' + '\ud800' + '"}'), fails('UNICODE'));
});

test('reports package self-reference resolves its maintained validation entry', () => {
  const cwd = new URL('../../../packages/reports/', import.meta.url);
  assert.equal(execFileSync(process.execPath, ['--input-type=module', '-e', 'import { importReport } from "@inkflip/reports"; process.stdout.write(typeof importReport)'], { cwd, encoding: 'utf8' }), 'function');
});

test('HTML image references require a complete strict PNG data URL', () => {
  const bad = ['iVBORw0KGgo=not-base64', 'iVBORw0KGgo=', 'PHN2Zz48L3N2Zz4='];
  for (const value of bad) {
    const html = document().replace('<p>report</p>', '<img src="data:image/png;base64,' + value + '">');
    assert.throws(() => assertScriptFreeHtml(html), fails('HTML'));
  }
  const good = makePng({ width: 1, height: 1, pixelRows: [[[1, 2, 3, 255]]] });
  const html = document().replace('<p>report</p>', '<img src="data:image/png;base64,' + Buffer.from(good).toString('base64') + '">');
  assert.doesNotThrow(() => assertScriptFreeHtml(html));
});

test('the export test double refuses missing sanitized image bytes', () => {
  const report = JSON.parse(reportBytes());
  const pngAsset = report.assets.find((asset) => asset.media_type === 'image/png');
  assert.ok(pngAsset, 'fixture contains a PNG');
  assert.throws(() => renderHtmlReport(report, new Map()), /sanitized/i);
});
