// T03 review round-3: bounded differential fuzz over multi-fault JSON.
//
// Generates malformed/adversarial JSON documents combining duplicate keys,
// unsafe integers, nonfinite tokens, lone surrogates, bad escapes,
// truncation, trailing garbage, nesting-depth violations and member-level
// faults at varying positions — then compares the failure code reported by
// the TypeScript strict parser against the Python port (which mirrors the
// delivered contractlib ordering) on every case.
//
// Usage: node tests/contracts/differential_fuzz.mjs
// Exit 0 = full parity; exit 1 prints every divergence.
//
// Known implementation-limit edge (not a contract deviation): documents
// nested deeper than CPython's json scanner recursion limit (~1000) fail
// DEPTH in Python while V8 still parses them; corpus stays under that.

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadsStrict, ContractError } from '../../packages/contracts/src/index.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..', '..');
const RUNNER = join(HERE, 'fuzz_py_runner.py');

const BIG = '9'.repeat(400);
const BIG_SAFE_EDGE = '9007199254740993';

// Faulty fragments (each is a complete JSON-ish value or fragment).
const FAULTS = [
  'NaN', 'Infinity', '-Infinity', '1e999', '-1e999',
  BIG, '-' + BIG, BIG_SAFE_EDGE, '-' + BIG_SAFE_EDGE,
  '9007199254740992.0', '-9007199254740992.0', '1e20',
  '"\\ud800"', '"\\udc00"', '"a\\ud800b"', '"\\ud800\\ud800"',
  '"\\x"', '"\\u12"', '"\\q"', '"\\ud8"',
  '"unterminated', 'tru', 'nul', 'undefined', 'nan', '+1', '.5', '01', '1.',
  '', '}', ']', ',', ':', '{', '[', '1e', 'e5', '--1',
];
// Well-formed fragments.
const OKS = [
  '1', '0', '-2', '1.5', '-0', '"s"', '""', 'true', 'false', 'null',
  '[1]', '[]', '{}', '{"k":1}', '"\\ud83d\\ude00"', '"é"', '"\\n"',
  '9007199254740991',
];

function tsCode(doc) {
  try {
    loadsStrict(doc);
    return 'OK';
  } catch (e) {
    return e instanceof ContractError
      ? 'CE:' + e.code
      : 'RAW:' + e.constructor.name;
  }
}

// Deterministic PRNG so the corpus is stable run to run.
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(0x1f1f1f);
const pick = (arr) => arr[Math.floor(rand() * arr.length)];

const corpus = [];
const add = (doc) => corpus.push(doc);

// --- Enumerated N3-family templates: dup key × fault × position ----------
const TEMPLATES = [
  (f) => `{"a":1,"a":${f}}`,
  (f) => `{"a":1,"a":5,"b":${f}}`,
  (f) => `{"a":1,"a":${f},"b":2}`,
  (f) => `{"a":{"b":1,"b":${f}}}`,
  (f) => `{"a":{"b":1,"b":2},"c":${f}}`,
  (f) => `{"a":{"b":1,"b":${f}},"c":2}`,
  (f) => `{"a":1,"b":{"c":1,"c":2},"d":${f}}`,
  (f) => `{"a":1,"b":{"c":1,"c":${f}},"d":2}`,
  (f) => `[${f},{"a":1,"a":2}]`,
  (f) => `[{"a":1,"a":2},${f}]`,
  (f) => `[{"a":1,"a":${f}},3]`,
  (f) => `{"x":{"a":1,"a":${f}}}`,
  (f) => `{"a":1,"a":2}${f}`,
  (f) => `{"a":{"b":1,"b":2}}${f}`,
  (f) => `[{"a":1,"a":2},${f}`,
  (f) => `{"a":1,"a":${f}`,
  (f) => `{"a":${f},"a":2}`,
  (f) => `{"a":{"b":{"c":1,"c":${f}}}}`,
];
for (const t of TEMPLATES) for (const f of FAULTS) add(t(f));

// --- Dup variants: escaped keys, surrogate keys, proto, triples ----------
add('{"a":1,"\\u0061":2}');
add('{"a":1,"\\u0061":}');
add('{"\\ud800":1,"\\ud800":2}');
add('{"\\ud800":1,"\\ud800":}');
add('{"__proto__":1,"__proto__":2}');
add('{"__proto__":1,"__proto__":NaN}');
add('{"a":1,"a":2,"a":3}');
add('{"a":1,"a":NaN,"a":3}');
add('{"a":1,"b":2,"a":NaN}');
add('{"a":1,"b":NaN,"a":3}');
add('{"a":1,"a":{"b":2,"b":3}}');
add('{"a":{"b":1,"b":2},"a":3}');
add('{"a":{"b":1,"b":2},"a":NaN}');
add('[[{"a":1,"a":2}]]');
add('{"o":{"o":{"a":1,"a":2}}}');
add('{"a":1,"a":2,"b":2,"b":3}');
add('{"a":1,"a":' + BIG + '}');
add('{"a":' + BIG + ',"a":2}');
add('{"a":1,"a":' + BIG_SAFE_EDGE + '}');
add('{"a":1,"a":"\\ud800"}');
add('{"a":"\\ud800","a":2}');
add('{"a":1,"a":');
add('{"a":1,"a');
add('{"a":1,"a"');
add('{"a":1,"a":2');
add('{"a":1,"a":2 ');
add('{"a":1 ,"a" :2}');
add('{"a" : 1 , "a" : 2 }');

// --- Depth combos (parseable depth below CPython's recursion limit) ------
for (const d of [20, 24, 25, 30, 50, 80]) {
  for (const inner of [
    '{"a":1,"a":2}', '{"a":1,"a":NaN}', BIG, '"\\ud800"', 'NaN',
  ]) {
    add('['.repeat(d) + inner + ']'.repeat(d));
  }
  // Dup object embedded at the bottom of a depth-violating nest.
  add('['.repeat(d) + '{"a":1,"a":2,"b":NaN}' + ']'.repeat(d));
}

// --- Seeded random pairings: two faults, fault+ok, truncation ------------
for (let k = 0; k < 160; k++) {
  const shape = Math.floor(rand() * 8);
  const a = pick(FAULTS), b = pick([...FAULTS, ...OKS]), c = pick(OKS);
  switch (shape) {
    case 0: add(`[${a},${b}]`); break;
    case 1: add(`{"k":${a},"l":${b}}`); break;
    case 2: add(`{"k":{"m":${a}},"l":${b}}`); break;
    case 3: add(`[${c},${a},${b}`); break;
    case 4: add(`{"k":${a},"k":${b}}`); break;
    case 5: add(`{"k":${a},"l":{"m":1,"m":${b}}}`); break;
    case 6: add(`[[${a}],[{"q":1,"q":${b}}]]`); break;
    case 7: add(`{"k":[${a},{"q":1,"q":2}],"l":${b}}`); break;
  }
}

// --- Trailing/leading garbage and whitespace oddities --------------------
for (const t of ['x', '#', ' ', '@', '0', '"']) {
  add(`{"a":1,"a":2}${t}`);
  add(`${t}{"a":1,"a":2}`);
  add(`[${BIG}]${t}`);
}
add('{"a":1,"a":2}\n\n');
add('\ufeff{"a":1,"a":2}');
add('{"a":1,"a":2}\ufeff');
add('  {"a":1,"a":2}  ');

console.log(`corpus: ${corpus.length} cases`);

// TS codes.
const ts = corpus.map((doc, id) => ({ id, doc, code: tsCode(doc) }));

// Python codes via the contract runner.
const tmp = mkdtempSync(join(tmpdir(), 'inkflip-fuzz-'));
const corpusPath = join(tmp, 'corpus.jsonl');
writeFileSync(
  corpusPath,
  corpus.map((doc, id) => JSON.stringify({ id, doc })).join('\n') + '\n',
);
const pyOut = execFileSync(
  'uv',
  ['run', '--project', 'native', 'python', RUNNER, corpusPath],
  { cwd: ROOT, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 },
);
const py = new Map();
for (const line of pyOut.trim().split('\n')) {
  const row = JSON.parse(line);
  py.set(row.id, row.code);
}

const mismatches = [];
for (const c of ts) {
  const p = py.get(c.id);
  if (p !== c.code) mismatches.push({ doc: c.doc, ts: c.code, py: p });
}
writeFileSync(
  join(tmp, 'result.json'),
  JSON.stringify({ total: corpus.length, mismatches }, null, 2),
);
if (mismatches.length) {
  console.log(`MISMATCHES: ${mismatches.length} (details: ${join(tmp, 'result.json')})`);
  for (const m of mismatches.slice(0, 40)) {
    console.log(`  ts=${m.ts} py=${m.py} doc=${JSON.stringify(m.doc.slice(0, 80))}`);
  }
  process.exit(1);
}
console.log(`parity: ${corpus.length}/${corpus.length} codes agree`);
