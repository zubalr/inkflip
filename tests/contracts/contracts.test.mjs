// T03 contract acceptance (TEST-03): strict parsing, structural+semantic
// validation, canonical identity, normalization, occurrence/run/report
// digests, generated artifacts. Runs the same delivered fixtures and goldens
// as native/tests/contracts/test_contracts.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import {
  readdirSync,
  readFileSync,
} from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import {
  ContractError,
  bounded,
  canonical,
  checkSchema,
  digest,
  loadsStrict,
  normalize,
  occurrenceId,
  reportDigest,
  runKey,
  seal,
  sha256,
  validate,
  validateJson,
} from '../../packages/contracts/src/index.ts';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const PLANNING = join(ROOT, 'planning');
const EXAMPLES = join(PLANNING, 'contracts', 'examples');
const VALID_DIR = join(EXAMPLES, 'valid');
const INVALID_INDEX = join(EXAMPLES, 'invalid-index.json');
const FIXTURES = join(
  dirname(fileURLToPath(import.meta.url)),
  'fixtures',
);

const hex = (u8) =>
  [...u8].map((b) => b.toString(16).padStart(2, '0')).join('');

const code = (fn) => {
  try {
    fn();
  } catch (e) {
    if (e instanceof ContractError) return e.code;
    throw e;
  }
  return null;
};

const loadValid = (name) =>
  loadsStrict(readFileSync(join(VALID_DIR, name)));

test('all delivered valid examples pass structural and semantic validation', () => {
  const files = readdirSync(VALID_DIR).filter((f) => f.endsWith('.json'));
  assert.ok(files.length >= 12, `expected >=12 valid examples, got ${files.length}`);
  for (const f of files) {
    validate(loadValid(f), true);
  }
});

test('all delivered invalid examples fail with the expected code', () => {
  const index = JSON.parse(readFileSync(INVALID_INDEX, 'utf8'));
  assert.ok(index.length >= 30, `expected >=30 invalid examples, got ${index.length}`);
  for (const entry of index) {
    const raw = readFileSync(join(PLANNING, entry.path));
    const actual = code(() => validate(loadsStrict(raw)));
    assert.equal(
      actual,
      entry.expected_code,
      `${entry.path}: expected ${entry.expected_code}, got ${actual}`,
    );
  }
});

test('canonical hash vectors agree byte-for-byte', () => {
  const vectors = JSON.parse(
    readFileSync(join(PLANNING, 'contracts', 'hash-vectors.json'), 'utf8'),
  );
  for (const v of vectors) {
    assert.equal(
      hex(canonical(v.value)),
      v.canonical_hex,
      `canonical hex for ${JSON.stringify(v.value)}`,
    );
    assert.equal(
      digest(v.value),
      v.sha256,
      `sha256 for ${JSON.stringify(v.value)}`,
    );
  }
});

test('reference-computed goldens agree (digests, normalize, ids, identities)', () => {
  const golden = JSON.parse(
    readFileSync(join(FIXTURES, 'digest-golden.json'), 'utf8'),
  );
  for (const g of golden.digests) {
    assert.equal(hex(canonical(g.value)), g.canonical_hex);
    assert.equal(digest(g.value), g.sha256);
  }
  for (const g of golden.normalize) {
    const n = normalize(g.input);
    assert.equal(n.text, g.text, `normalize ${JSON.stringify(g.input)}`);
    assert.deepEqual(n.map, g.map);
  }
  for (const g of golden.occurrence_ids) {
    assert.equal(
      occurrenceId(
        g.run_key,
        g.reader_id,
        g.page_index,
        g.ordinal,
        g.raw_source_locator,
      ),
      g.id,
    );
  }
  for (const [name, ids] of Object.entries(golden.report_identities)) {
    const r = loadValid(name);
    assert.equal(runKey(r), ids.run_key, `run_key ${name}`);
    assert.equal(reportDigest(r), ids.report_id, `report_id ${name}`);
    assert.equal(r.report_id, ids.sealed_report_id, `sealed ${name}`);
  }
});

test('strict parser rejects duplicate keys, nonfinite and unsafe values', () => {
  assert.equal(code(() => loadsStrict('{"a":1,"a":2}')), 'DUPLICATE_KEY');
  assert.equal(
    code(() => loadsStrict('{"a":{"b":1,"b":2}}')),
    'DUPLICATE_KEY',
  );
  assert.equal(code(() => loadsStrict('{"a":1,"a":{"x":1}}')), 'DUPLICATE_KEY');
  for (const s of ['NaN', 'Infinity', '-Infinity', '[NaN]', '{"x":Infinity}']) {
    assert.equal(code(() => loadsStrict(s)), 'NONFINITE', s);
  }
  for (const s of ['9007199254740993', '-9007199254740993']) {
    assert.equal(code(() => loadsStrict(s)), 'NUMBER', s);
  }
  for (const s of ['9007199254740992.0', '-9007199254740992.0', '1e20']) {
    assert.equal(code(() => loadsStrict(s)), 'NUMBER', s);
  }
  // -0 parses and canonicalizes as +0, matching the Python reference.
  assert.equal(hex(canonical(loadsStrict('-0'))), '440000000000000000');
});

test('strict parser rejects lone surrogates and excessive depth', () => {
  for (const s of ['"\\ud800"', '"\\udc00"', '"\\ud800x"', '"a\\udc00"']) {
    assert.equal(code(() => loadsStrict(s)), 'UNICODE', s);
  }
  // A well-formed surrogate pair is a scalar value and stays legal.
  assert.equal(loadsStrict('"\\ud83d\\ude00"'), '😀');
  const deep24 = '['.repeat(24) + '0' + ']'.repeat(24);
  const deep25 = '['.repeat(25) + '0' + ']'.repeat(25);
  let inner = loadsStrict(deep24);
  for (let i = 0; i < 24; i++) inner = inner[0];
  assert.equal(inner, 0);
  assert.equal(code(() => loadsStrict(deep25)), 'DEPTH');
  // Malformed documents report JSON, not a contract code.
  for (const s of ['{', '{"a":}', '[1,]', '{"a":1,}', '{a:1}', '"unterminated']) {
    assert.equal(code(() => loadsStrict(s)), 'JSON', s);
  }
});

test('strict parser accepts bytes and enforces UTF-8', () => {
  assert.deepEqual(loadsStrict(new TextEncoder().encode('{"a":[1,2]}')), {
    a: [1, 2],
  });
  assert.equal(
    code(() => loadsStrict(new Uint8Array([0xff, 0xfe, 0x41]))),
    'UNICODE',
  );
});

test('__proto__ keys parse as ordinary members', () => {
  const v = loadsStrict('{"__proto__":1,"a":2}');
  assert.equal(Object.getPrototypeOf(v), Object.prototype);
  assert.equal(v.__proto__, 1);
  assert.equal(code(() => loadsStrict('{"__proto__":1,"__proto__":2}')), 'DUPLICATE_KEY');
});

test('bounded() rejects unsafe values passed programmatically', () => {
  assert.equal(code(() => bounded({ a: Number.MAX_SAFE_INTEGER + 2 })), 'NUMBER');
  assert.equal(code(() => bounded([Infinity])), 'NONFINITE');
  assert.equal(code(() => bounded([NaN])), 'NONFINITE');
  assert.equal(code(() => bounded('x'.repeat(0), 25)), 'DEPTH');
  assert.equal(
    code(() => canonical({ 1: 'non-string key in JS is a string anyway' })),
    null,
  );
});

test('canonical() rejects unsupported or unsafe values', () => {
  for (const v of [undefined, 10n, Symbol('s'), () => {}]) {
    assert.equal(code(() => canonical(v)), 'TYPE', String(v));
  }
  assert.equal(code(() => canonical(Infinity)), 'NONFINITE');
  assert.equal(code(() => canonical(2 ** 53)), 'NUMBER');
  // JS object keys are always strings; the reference TYPE check for
  // non-string keys has no reachable counterpart after JSON parsing.
  assert.equal(code(() => canonical({ 1: 'x' })), null);
});

test('canonical() rejects lone surrogates in strings', () => {
  const lone = String.fromCharCode(0xd800);
  assert.equal(code(() => canonical(lone)), 'UNICODE');
  assert.equal(code(() => canonical(`a${lone}b`)), 'UNICODE');
});

test('object key order is canonical; array order is significant', () => {
  const a = loadsStrict('{"z":1,"a":2,"m":{"y":1,"b":2}}');
  const b = loadsStrict('{"m":{"b":2,"y":1},"a":2,"z":1}');
  assert.equal(digest(a), digest(b), 'object member order must not matter');
  assert.notEqual(digest([1, 2]), digest([2, 1]), 'array order must matter');
  const r = loadValid('native-evidence.inkflip.json');
  const flipped = structuredClone(r);
  flipped.readers = [...flipped.readers].reverse();
  assert.notEqual(
    runKey(flipped),
    runKey(r),
    'reader array order must change run identity',
  );
});

test('report digest excludes execution_id, timestamps and asset bytes only', () => {
  const r = loadValid('native-evidence.inkflip.json');
  const base = reportDigest(r);
  const same = structuredClone(r);
  same.execution.execution_id = '37dfed38-ed9a-436c-b4a8-c61dfb164694';
  same.execution.started_at = '2030-01-01T00:00:00+00:00';
  same.execution.duration_ms += 1;
  for (const a of same.assets) a.data_base64 = 'AA==';
  assert.equal(reportDigest(same), base, 'excluded fields must not hash');
  const changed = structuredClone(r);
  changed.limitations.push('Additional actual limitation.');
  assert.notEqual(reportDigest(changed), base, 'semantic change must hash');
  const assetMeta = structuredClone(r);
  assetMeta.assets[0].byte_length += 1;
  assert.notEqual(
    reportDigest(assetMeta),
    base,
    'asset byte_length stays in the digest',
  );
});

test('seal() computes run_key and report_id so a stale report revalidates', () => {
  const r = loadValid('native-evidence.inkflip.json');
  const original = r.report_id;
  r.report_id = '0'.repeat(64);
  assert.equal(code(() => validate(r)), 'HASH');
  seal(r);
  assert.equal(r.report_id, original);
  validate(r);
});

test('check_hashes=False skips digest verification only', () => {
  const r = loadValid('native-evidence.inkflip.json');
  r.report_id = '0'.repeat(64);
  assert.equal(code(() => validate(r)), 'HASH');
  validate(r, false); // stale digest tolerated when explicitly disabled
  r.limitations.push('Broken elsewhere.');
  assert.equal(code(() => validate(r)), 'HASH');
  validate(r, false); // semantic content still validates
  r.plan.checks.pop(); // now semantically inconsistent
  assert.equal(code(() => validate(r, false)), 'COVERAGE');
});

test('readable imported occurrence ids and duplicates stay distinct', () => {
  const r = loadValid('repeated-occurrences.json');
  validate(r);
  const texts = r.occurrences.map((o) => o.raw_text);
  assert.ok(
    new Set(texts).size < texts.length,
    'fixture must carry duplicate raw text',
  );
  assert.equal(
    new Set(r.occurrences.map((o) => o.id)).size,
    r.occurrences.length,
    'occurrence ids stay unique even with equal text',
  );
});

test('occurrenceId is positional, hash based and deterministic', () => {
  const rk = 'a'.repeat(64);
  const id = occurrenceId(rk, 'r_pdfium', 0, 63, 'locator [0,1)');
  assert.match(id, /^o_[a-f0-9]{32}$/);
  assert.equal(id, occurrenceId(rk, 'r_pdfium', 0, 63, 'locator [0,1)'));
  assert.notEqual(id, occurrenceId(rk, 'r_pdfium', 0, 64, 'locator [0,1)'));
  assert.notEqual(id, occurrenceId(rk, 'r_pdfium', 1, 63, 'locator [0,1)'));
  assert.notEqual(id, occurrenceId(rk, 'r_pdfium', 0, 63, 'locator [0,2)'));
  // The text value never keys identity: same text, different position.
  const a = occurrenceId(rk, 'r_pdfium', 0, 0, 'pos A');
  const b = occurrenceId(rk, 'r_pdfium', 0, 1, 'pos B');
  assert.notEqual(a, b);
});

test('normalization preserves meaning and maps raw indexes in code points', () => {
  for (const s of [
    '$1,000',
    '-$100',
    'not paid',
    'لا',
    'ﬁle',
    'é',
    '😀',
  ]) {
    assert.equal(normalize(s).text, s, JSON.stringify(s));
  }
  assert.notEqual(normalize('$100').text, normalize('$1,000').text);
  assert.equal(normalize(' A\n\tB ').text, ' A B ');
  // Code-point indexing: the emoji occupies one index despite two UTF-16 units.
  const n = normalize('x😀 y');
  assert.deepEqual(n.map[0], {
    raw_start: 0,
    raw_end: 2,
    normalized_start: 0,
    normalized_end: 2,
    operation: 'identity',
  });
  assert.equal(n.map[0].raw_end, 2, 'emoji counts as one index');
});

test('unknown schema version fails closed', () => {
  const r = loadValid('acceptance-rules.json');
  r.schema_version = '9.9.9';
  assert.equal(code(() => validate(r)), 'SCHEMA');
  r.schema_version = '2.0.0';
  assert.equal(code(() => validate(r)), 'SCHEMA');
  r.schema_version = '1.0.0';
  validate(r);
});

test('untrusted report validation never compiles a schema', () => {
  assert.equal(typeof checkSchema, 'function');
  // The structural validator is generated code, not a schema interpreter:
  // replacing eval/Function must not affect validation of untrusted input.
  const realEval = globalThis.eval;
  const RealFunction = globalThis.Function;
  globalThis.eval = () => {
    throw new Error('eval used during validation');
  };
  globalThis.Function = function () {
    throw new Error('Function used during validation');
  };
  try {
    for (const f of readdirSync(VALID_DIR)) {
      validate(loadValid(f));
    }
    const bad = loadValid('acceptance-rules.json');
    bad.schema_version = '9.9.9';
    assert.equal(code(() => validate(bad)), 'SCHEMA');
  } finally {
    globalThis.eval = realEval;
    globalThis.Function = RealFunction;
  }
  // The generated module itself contains no dynamic code construction.
  const src = readFileSync(
    join(
      ROOT,
      'packages/contracts/src/generated/schema-check.ts',
    ),
    'utf8',
  );
  assert.ok(!/eval\s*\(|new Function|Function\s*\(|import\s*\(/.test(src),
    'generated validator must not build code at runtime');
});

test('type generation is deterministic and drift-free', () => {
  const out = execFileSync(
    'python3',
    [join(ROOT, 'scripts/generate_contracts.py'), '--check'],
    { encoding: 'utf8' },
  );
  assert.match(out, /match/);
});

test('vendored schemas are byte-identical to the authoritative schema', () => {
  const authority = readFileSync(
    join(PLANNING, 'contracts', 'inkflip.schema.json'),
  );
  for (const p of [
    'packages/contracts/schema/inkflip.schema.json',
    'native/inkflip/contracts/schema/inkflip.schema.json',
  ]) {
    assert.deepEqual(readFileSync(join(ROOT, p)), authority, p);
  }
});

test('validateJson parses and validates untrusted input in one step', () => {
  validateJson(readFileSync(join(VALID_DIR, 'acceptance-rules.json')));
  assert.equal(
    code(() => validateJson('{"kind":"report","schema_version":"1.0.0"}')),
    'SCHEMA',
  );
});

test('local task fixture: comparison and worker semantics', () => {
  const cmp = loadValid('comparison.json');
  validate(cmp);
  cmp.status = 'regressed';
  cmp.acceptance_rules_sha256 = null;
  assert.equal(code(() => validate(cmp)), 'RULE');
  const wm = loadValid('worker-terminal.json');
  validate(wm);
  wm.payload.transfer_slot = 'pdf_bytes';
  assert.equal(code(() => validate(wm)), 'MESSAGE');
});
