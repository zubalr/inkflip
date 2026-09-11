/**
 * Inkflip contract validation, canonical identity and normalization.
 *
 * TypeScript port of `native/inkflip/contracts/core.py` (itself an exact port
 * of the delivered `planning/tools/contractlib.py`). Structural JSON Schema
 * checks run through `checkSchema`, which is generated code compiled from the
 * single authoritative schema by `scripts/generate_contracts.py`; untrusted
 * report data never compiles, parses or fetches a schema at runtime.
 *
 * Error surface: every rejection is a {@link ContractError} carrying a stable
 * `code`. As in the Python port, malformed JSON syntax reports `JSON` and
 * invalid UTF-8 input reports `UNICODE` (the planning reference let the raw
 * decode errors propagate instead).
 *
 * Browser-safe: canonicalization uses DataView/TextEncoder and a local
 * SHA-256, not Node-specific APIs.
 */

import { checkSchema } from './generated/schema-check.ts';
import type {
  AcceptanceRules,
  Asset,
  Comparison,
  CorpusManifest,
  Geometry,
  Page,
  RawMap,
  Report,
  WorkerMessage,
} from './generated/types.ts';

export const MAX_JSON_BYTES = 32 * 1024 * 1024;
export const MAX_STRING_LENGTH = 28000000;
export const MAX_DEPTH = 24;
export const MAX_ASSET_BYTES = 20 * 1024 * 1024;
export const MAX_ASSET_TOTAL = 20 * 1024 * 1024;
export const MAX_PNG_PIXELS = 4000000;
export const SAFE_INTEGER = 2 ** 53 - 1;
export const SCHEMA_VERSION = '1.0.0';
export const CANONICALIZATION = 'inkflip-c14n-v1';
export const SCHEMA_ID = 'urn:inkflip:schema:1.0.0';

/** A contract rejection carrying a stable machine-readable code. */
export class ContractError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(`${code}: ${message}`);
    this.name = 'ContractError';
    this.code = code;
  }
}

export function require(
  condition: boolean,
  code: string,
  message: string,
): asserts condition {
  if (!condition) throw new ContractError(code, message);
}

// ---------------------------------------------------------------------------
// Strict JSON parsing (untrusted input)
// ---------------------------------------------------------------------------

const TE = new TextEncoder();
const TD = new TextDecoder('utf-8', { fatal: true });
const JSON_WS = new Set([' ', '\t', '\n', '\r']);
const NUMBER_RE = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
const NONFINITE_TOKENS = ['NaN', 'Infinity', '-Infinity'];

/** Parse untrusted JSON text/bytes with duplicate-key and bound checks. */
export function loadsStrict(data: string | Uint8Array): unknown {
  let text: string;
  if (data instanceof Uint8Array) {
    try {
      text = TD.decode(data);
    } catch {
      throw new ContractError('UNICODE', 'Invalid UTF-8 input');
    }
  } else {
    text = data;
  }
  require(
    TE.encode(text).length <= MAX_JSON_BYTES,
    'SIZE',
    'JSON too large',
  );
  let value: unknown;
  try {
    value = parseJson(text);
  } catch (exc) {
    if (exc instanceof RangeError) {
      throw new ContractError('DEPTH', 'JSON nesting');
    }
    throw exc;
  }
  bounded(value);
  return value;
}

function parseJson(text: string): unknown {
  let i = 0;
  const n = text.length;
  const fail = (message: string): never => {
    throw new ContractError('JSON', `${message} at offset ${i}`);
  };
  const ws = (): void => {
    while (i < n && JSON_WS.has(text[i] as string)) i++;
  };

  function parseString(): string {
    // text[i] === '"'
    i++;
    let out = '';
    let start = i;
    for (;;) {
      if (i >= n) fail('Unterminated string');
      const c = text.charCodeAt(i);
      if (c === 0x22) {
        out += text.slice(start, i);
        i++;
        return out;
      }
      if (c === 0x5c) {
        out += text.slice(start, i);
        i++;
        if (i >= n) fail('Bad escape');
        const e = text[i];
        i++;
        switch (e) {
          case '"':
            out += '"';
            break;
          case '\\':
            out += '\\';
            break;
          case '/':
            out += '/';
            break;
          case 'b':
            out += '\b';
            break;
          case 'f':
            out += '\f';
            break;
          case 'n':
            out += '\n';
            break;
          case 'r':
            out += '\r';
            break;
          case 't':
            out += '\t';
            break;
          case 'u': {
            if (i + 4 > n) fail('Bad unicode escape');
            const hex = text.slice(i, i + 4);
            if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail('Bad unicode escape');
            out += String.fromCharCode(parseInt(hex, 16));
            i += 4;
            break;
          }
          default:
            fail('Bad escape');
        }
        start = i;
        continue;
      }
      if (c < 0x20) fail('Control character in string');
      i++;
    }
  }

  function parseNumber(): number {
    NUMBER_RE.lastIndex = i;
    const m = NUMBER_RE.exec(text);
    if (!m) return fail('Invalid number');
    i += m[0].length;
    const v = Number(m[0]);
    // Python parses arbitrary-precision integers, so a pure-integer
    // literal that overflows to Infinity is an unsafe integer (NUMBER)
    // there; non-integer literals like 1e999 stay nonfinite in both.
    if (!Number.isFinite(v) && /^-?\d+$/.test(m[0])) {
      throw new ContractError('NUMBER', 'Unsafe integer');
    }
    return v;
  }

  function parseArray(): unknown[] {
    i++; // consume '['
    const out: unknown[] = [];
    ws();
    if (text[i] === ']') {
      i++;
      return out;
    }
    for (;;) {
      out.push(parseValue());
      ws();
      if (text[i] === ',') {
        i++;
        continue;
      }
      if (text[i] === ']') {
        i++;
        return out;
      }
      fail('Expected "," or "]"');
    }
  }

  function parseObject(): Record<string, unknown> {
    i++; // consume '{'
    const out: Record<string, unknown> = {};
    ws();
    if (text[i] === '}') {
      i++;
      return out;
    }
    for (;;) {
      ws();
      if (text[i] !== '"') fail('Expected object key');
      const key = parseString();
      if (Object.prototype.hasOwnProperty.call(out, key)) {
        throw new ContractError('DUPLICATE_KEY', 'Repeated JSON member');
      }
      ws();
      if (text[i] !== ':') fail('Expected ":"');
      i++;
      const value = parseValue();
      if (key === '__proto__') {
        // Plain-object assignment would set the prototype, not a member.
        Object.defineProperty(out, key, {
          value,
          writable: true,
          enumerable: true,
          configurable: true,
        });
      } else {
        out[key] = value;
      }
      ws();
      if (text[i] === ',') {
        i++;
        continue;
      }
      if (text[i] === '}') {
        i++;
        return out;
      }
      fail('Expected "," or "}"');
    }
  }

  function parseValue(): unknown {
    ws();
    if (i >= n) fail('Unexpected end of input');
    const ch = text[i];
    if (ch === '{') return parseObject();
    if (ch === '[') return parseArray();
    if (ch === '"') return parseString();
    if (ch === 't') {
      if (!text.startsWith('true', i)) return fail('Invalid literal');
      i += 4;
      return true;
    }
    if (ch === 'f') {
      if (!text.startsWith('false', i)) return fail('Invalid literal');
      i += 5;
      return false;
    }
    if (ch === 'n') {
      if (!text.startsWith('null', i)) return fail('Invalid literal');
      i += 4;
      return null;
    }
    for (const token of NONFINITE_TOKENS) {
      if (text.startsWith(token, i)) {
        throw new ContractError('NONFINITE', 'Nonfinite number');
      }
    }
    if (ch === '-' || (ch! >= '0' && ch! <= '9')) return parseNumber();
    return fail('Unexpected token');
  }

  const value = parseValue();
  ws();
  if (i !== n) fail('Trailing data');
  return value;
}

/** Enforce depth/size/string/number bounds on a decoded JSON value. */
export function bounded(value: unknown, depth = 0): void {
  require(depth <= MAX_DEPTH, 'DEPTH', 'Nesting exceeds 24');
  if (typeof value === 'string') {
    require(
      codePoints(value) <= MAX_STRING_LENGTH,
      'SIZE',
      'String too large',
    );
    if (hasLoneSurrogate(value)) {
      throw new ContractError('UNICODE', 'Unpaired surrogate');
    }
  } else if (typeof value === 'number') {
    require(
      !Number.isInteger(value) || Number.isSafeInteger(value),
      'NUMBER',
      'Unsafe integer',
    );
    require(Number.isFinite(value), 'NONFINITE', 'Number must be finite');
  } else if (Array.isArray(value)) {
    for (const v of value) bounded(v, depth + 1);
  } else if (typeof value === 'object' && value !== null) {
    for (const [k, v] of Object.entries(value)) {
      bounded(k, depth + 1);
      bounded(v, depth + 1);
    }
  }
}

function codePoints(s: string): number {
  let nCount = 0;
  for (const _ch of s) nCount++;
  return nCount;
}

function hasLoneSurrogate(s: string): boolean {
  return /\p{Surrogate}/u.test(s);
}

// ---------------------------------------------------------------------------
// inkflip-c14n-v1 canonical form, SHA-256 and digests
// ---------------------------------------------------------------------------

function u32be(n: number): Uint8Array {
  const b = new Uint8Array(4);
  new DataView(b.buffer).setUint32(0, n);
  return b;
}

function concat(parts: Uint8Array[]): Uint8Array {
  let total = 0;
  for (const p of parts) total += p.length;
  const out = new Uint8Array(total);
  let off = 0;
  for (const p of parts) {
    out.set(p, off);
    off += p.length;
  }
  return out;
}

function utf8Bytes(s: string): Uint8Array {
  if (hasLoneSurrogate(s)) {
    throw new ContractError('UNICODE', 'Unpaired surrogate');
  }
  return TE.encode(s);
}

/** inkflip-c14n-v1 tagged binary canonical form; not RFC 8785/JCS. */
export function canonical(value: unknown): Uint8Array {
  if (value === null) return new Uint8Array([0x4e]); // 'N'
  if (value === true) return new Uint8Array([0x54]); // 'T'
  if (value === false) return new Uint8Array([0x46]); // 'F'
  if (typeof value === 'number') {
    require(
      !Number.isInteger(value) || Number.isSafeInteger(value),
      'NUMBER',
      'Unsafe integer',
    );
    require(
      Number.isFinite(value),
      'NONFINITE',
      'Cannot hash nonfinite number',
    );
    const b = new Uint8Array(9);
    b[0] = 0x44; // 'D'
    new DataView(b.buffer).setFloat64(1, value === 0 ? 0 : value);
    return b;
  }
  if (typeof value === 'string') {
    const raw = utf8Bytes(value);
    return concat([new Uint8Array([0x53]), u32be(raw.length), raw]);
  }
  if (Array.isArray(value)) {
    const parts = [new Uint8Array([0x4c]), u32be(value.length)];
    for (const item of value) parts.push(canonical(item));
    return concat(parts);
  }
  if (typeof value === 'object' && value !== null) {
    // Only plain objects are hashable, mirroring the Python dict check:
    // Map/Set/Date/RegExp/Uint8Array/class instances must TYPE-reject,
    // never hash silently as {} and collide in an identity function.
    const proto: unknown = Object.getPrototypeOf(value);
    require(
      proto === Object.prototype || proto === null,
      'TYPE',
      'Unsupported canonical type',
    );
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record);
    require(
      keys.every((k) => typeof k === 'string'),
      'TYPE',
      'Object keys must be strings',
    );
    keys.sort((a, b) => {
      const x = TE.encode(a);
      const y = TE.encode(b);
      const n = Math.min(x.length, y.length);
      for (let i = 0; i < n; i++) {
        if (x[i] !== y[i]) return x[i]! - y[i]!;
      }
      return x.length - y.length;
    });
    const parts = [new Uint8Array([0x4f]), u32be(keys.length)];
    for (const k of keys) {
      parts.push(canonical(k));
      parts.push(canonical(record[k]));
    }
    return concat(parts);
  }
  throw new ContractError('TYPE', 'Unsupported canonical type');
}

const K256 = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

/** Synchronous SHA-256 over bytes; browser- and Node-safe. */
export function sha256(data: Uint8Array): Uint8Array {
  const bitLen = data.length * 8;
  const padded = Math.ceil((data.length + 9) / 64) * 64;
  const m = new Uint8Array(padded);
  m.set(data);
  m[data.length] = 0x80;
  const dv = new DataView(m.buffer);
  dv.setUint32(padded - 8, Math.floor(bitLen / 2 ** 32));
  dv.setUint32(padded - 4, bitLen >>> 0);
  const h = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  const w = new Uint32Array(64);
  for (let off = 0; off < padded; off += 64) {
    for (let t = 0; t < 16; t++) w[t] = dv.getUint32(off + t * 4);
    for (let t = 16; t < 64; t++) {
      const x = w[t - 15]!;
      const y = w[t - 2]!;
      const s0 =
        (((x >>> 7) | (x << 25)) >>> 0) ^
        (((x >>> 18) | (x << 14)) >>> 0) ^
        (x >>> 3);
      const s1 =
        (((y >>> 17) | (y << 15)) >>> 0) ^
        (((y >>> 19) | (y << 13)) >>> 0) ^
        (y >>> 10);
      w[t] = (w[t - 16]! + s0 + w[t - 7]! + s1) >>> 0;
    }
    let a = h[0]!;
    let b = h[1]!;
    let c = h[2]!;
    let d = h[3]!;
    let e = h[4]!;
    let f = h[5]!;
    let g = h[6]!;
    let hh = h[7]!;
    for (let t = 0; t < 64; t++) {
      const s1 =
        (((e >>> 6) | (e << 26)) >>> 0) ^
        (((e >>> 11) | (e << 21)) >>> 0) ^
        (((e >>> 25) | (e << 7)) >>> 0);
      const ch = (e & f) ^ (~e & g);
      const t1 = (hh + s1 + ch + K256[t]! + w[t]!) >>> 0;
      const s0 =
        (((a >>> 2) | (a << 30)) >>> 0) ^
        (((a >>> 13) | (a << 19)) >>> 0) ^
        (((a >>> 22) | (a << 10)) >>> 0);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (s0 + maj) >>> 0;
      hh = g;
      g = f;
      f = e;
      e = (d + t1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (t1 + t2) >>> 0;
    }
    h[0] = (h[0]! + a) >>> 0;
    h[1] = (h[1]! + b) >>> 0;
    h[2] = (h[2]! + c) >>> 0;
    h[3] = (h[3]! + d) >>> 0;
    h[4] = (h[4]! + e) >>> 0;
    h[5] = (h[5]! + f) >>> 0;
    h[6] = (h[6]! + g) >>> 0;
    h[7] = (h[7]! + hh) >>> 0;
  }
  const out = new Uint8Array(32);
  const odv = new DataView(out.buffer);
  for (let j = 0; j < 8; j++) odv.setUint32(j * 4, h[j]!);
  return out;
}

function toHex(data: Uint8Array): string {
  let s = '';
  for (const b of data) s += b.toString(16).padStart(2, '0');
  return s;
}

export function digest(value: unknown): string {
  return toHex(sha256(canonical(value)));
}

/** Report identity excluding report_id, execution timing and asset bytes. */
export function reportDigest(report: Report): string {
  const p = structuredClone(report) as Report;
  delete (p as Partial<Report>).report_id;
  const execution = p.execution as Partial<Report['execution']>;
  delete execution.execution_id;
  delete execution.started_at;
  delete execution.duration_ms;
  for (const asset of p.assets) {
    delete (asset as Partial<Asset>).data_base64;
  }
  return digest(p);
}

export function runKey(report: Report): string {
  return digest({
    document_sha256: report.document.sha256,
    readers: report.readers,
    plan: report.plan,
  });
}

export function seal(report: Report): Report {
  report.execution.run_key = runKey(report);
  report.report_id = reportDigest(report);
  return report;
}

/**
 * Hash-based production occurrence identity: `o_` plus the first 32 hex
 * characters of the canonical digest of
 * `{run_key, reader_id, page_index, ordinal, raw_source_locator}`.
 * The text value is never the key; equal values at different positions stay
 * separate. Imported readable IDs remain valid under schema v1; this
 * generator is for newly produced occurrences.
 */
export function occurrenceId(
  runKeyValue: string,
  readerId: string,
  pageIndex: number,
  ordinal: number,
  rawSourceLocator: string,
): string {
  return (
    'o_' +
    digest({
      run_key: runKeyValue,
      reader_id: readerId,
      page_index: pageIndex,
      ordinal,
      raw_source_locator: rawSourceLocator,
    }).slice(0, 32)
  );
}

// ---------------------------------------------------------------------------
// scalar-whitespace-v1 normalization
// ---------------------------------------------------------------------------

export const WS = new Set([
  '\u0009', '\u000a', '\u000b', '\u000c', '\u000d', '\u0020', '\u0085', '\u00a0', '\u1680', '\u2000', '\u2001', '\u2002', '\u2003', '\u2004', '\u2005', '\u2006', '\u2007', '\u2008', '\u2009', '\u200a', '\u2028', '\u2029', '\u202f', '\u205f', '\u3000',
]);

/**
 * scalar-whitespace-v1: collapse Unicode White_Space runs to one space.
 * Returns the normalized view plus the reversible raw map. Index units are
 * Unicode code points, matching the Python port exactly.
 */
export function normalize(s: string): { text: string; map: RawMap[] } {
  const chars = [...s];
  const out: string[] = [];
  const map: RawMap[] = [];
  let i = 0;
  let n = 0;
  while (i < chars.length) {
    const start = i;
    const white = WS.has(chars[i] as string);
    while (i < chars.length && WS.has(chars[i] as string) === white) i++;
    const segment = white ? ' ' : chars.slice(start, i).join('');
    out.push(segment);
    map.push({
      raw_start: start,
      raw_end: i,
      normalized_start: n,
      normalized_end: n + (white ? 1 : i - start),
      operation: white ? 'whitespace' : 'identity',
    });
    n += white ? 1 : i - start;
  }
  return { text: out.join(''), map };
}

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

export function apply(m: number[], p: number[]): [number, number] {
  const [a, b, c, d, e, f] = m as [
    number,
    number,
    number,
    number,
    number,
    number,
  ];
  return [a * p[0]! + c * p[1]! + e, b * p[0]! + d * p[1]! + f];
}

export function inverse(m: number[]): number[] {
  const [a, b, c, d, e, f] = m as [
    number,
    number,
    number,
    number,
    number,
    number,
  ];
  const det = a * d - b * c;
  require(Math.abs(det) > 1e-12, 'TRANSFORM', 'Singular transform');
  return [
    d / det,
    -b / det,
    -c / det,
    a / det,
    (c * f - d * e) / det,
    (b * e - a * f) / det,
  ];
}

// ---------------------------------------------------------------------------
// Semantic validation
// ---------------------------------------------------------------------------

type Dict = Record<string, unknown>;

function asDict(value: unknown): Dict {
  return value as Dict;
}

export function unique<T extends { id: string }>(
  items: T[],
  code: string,
): Map<string, T> {
  const out = new Map<string, T>();
  for (const x of items) {
    require(!out.has(x.id), code, 'Duplicate identifiers');
    out.set(x.id, x);
  }
  return out;
}

function keySet<V>(m: Map<string, V>): Set<string> {
  return new Set(m.keys());
}

function setsEqual(a: Set<unknown>, b: Set<unknown>): boolean {
  if (a.size !== b.size) return false;
  for (const x of a) if (!b.has(x)) return false;
  return true;
}

function subset(a: Set<unknown>, b: Set<unknown>): boolean {
  for (const x of a) if (!b.has(x)) return false;
  return true;
}

function mapsEqual(a: RawMap[], b: RawMap[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i]!;
    const y = b[i]!;
    if (
      x.raw_start !== y.raw_start ||
      x.raw_end !== y.raw_end ||
      x.normalized_start !== y.normalized_start ||
      x.normalized_end !== y.normalized_end ||
      x.operation !== y.operation
    ) {
      return false;
    }
  }
  return true;
}

function b64decode(s: string): Uint8Array {
  if (s.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(s)) {
    throw new ContractError('ASSET', 'Invalid base64');
  }
  const alphabet =
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const pad = s.endsWith('==') ? 2 : s.endsWith('=') ? 1 : 0;
  const out = new Uint8Array((s.length / 4) * 3 - pad);
  let acc = 0;
  let bits = 0;
  let o = 0;
  for (const ch of s) {
    if (ch === '=') break;
    const v = alphabet.indexOf(ch);
    acc = (acc << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      if (o < out.length) out[o++] = (acc >> bits) & 0xff;
    }
  }
  return out;
}

/** Full contract validation: bounds, schema, then semantic relations. */
export function validate(value: unknown, checkHashes = true): void {
  bounded(value);
  const errs = checkSchema(value);
  require(
    errs.length === 0,
    'SCHEMA',
    errs.length ? errs[0]!.message.slice(0, 250) : '',
  );
  const kind = asDict(value).kind;
  if (kind === 'report') {
    validateReport(value as unknown as Report, checkHashes);
  } else if (kind === 'comparison') {
    const v = value as unknown as Comparison;
    if (v.status === 'improved' || v.status === 'regressed') {
      require(
        v.acceptance_rules_sha256 !== null,
        'RULE',
        'Judgment without rules',
      );
    }
    for (const ch of v.changes) {
      if (ch.status === 'improved' || ch.status === 'regressed') {
        require(ch.rule_id !== null, 'RULE', 'Change judgment has no rule');
      }
    }
    if (
      v.mode !== 'document_versions' &&
      v.left_document_sha256 !== v.right_document_sha256
    ) {
      require(
        v.status === 'incomparable',
        'DOCUMENT',
        'Different bytes are not the same file',
      );
    }
  } else if (kind === 'worker_message') {
    const v = value as unknown as {
      payload: {
        occurrences: unknown[];
        check_id: string | null;
        status: string | null;
        completed_units: number | null;
        total_units: number | null;
        transfer_slot: string | null;
        transfer_bytes: number;
      };
      event: string;
    };
    const p = v.payload;
    const e = v.event;
    require(
      p.occurrences.length === 0 || e === 'chunk',
      'MESSAGE',
      'Occurrences outside chunk',
    );
    if (e === 'check_terminal') {
      require(
        p.status !== null && p.check_id !== null,
        'MESSAGE',
        'Terminal fields missing',
      );
    }
    if (e === 'chunk') {
      require(
        p.check_id !== null && p.status === null,
        'MESSAGE',
        'Invalid chunk',
      );
    }
    if (e === 'progress') {
      require(
        p.completed_units !== null,
        'MESSAGE',
        'Progress has no completed units',
      );
      if (p.total_units !== null) {
        require(
          (p.completed_units as number) <= p.total_units,
          'MESSAGE',
          'Invalid progress denominator',
        );
      }
    }
    require(
      (p.transfer_slot === null) === (p.transfer_bytes === 0),
      'MESSAGE',
      'Transfer metadata mismatch',
    );
  } else if (kind === 'corpus_manifest') {
    const v = value as unknown as CorpusManifest;
    const keys = new Set<string>();
    for (const entry of v.entries) {
      const p = entry.source_path;
      require(
        !p.startsWith('/') &&
          !p.startsWith('\\') &&
          !p.includes('\\') &&
          !p.includes(':') &&
          !p.split('/').includes('..'),
        'PATH',
        'Unsafe corpus path',
      );
      require(!keys.has(entry.key), 'ID', 'Duplicate corpus key');
      keys.add(entry.key);
    }
  } else if (kind === 'acceptance_rules') {
    const v = value as unknown as AcceptanceRules;
    unique(v.rules, 'ID');
    for (const rule of v.rules) {
      const need = (
        {
          expected_text: 'expected_text',
          expected_occurrence_count: 'expected_count',
          max_geometry_delta: 'max_delta_pt',
          required_coverage: 'capability',
        } as Record<string, keyof typeof rule | undefined>
      )[rule.type];
      if (need) {
        require(rule[need] !== null, 'RULE', 'Rule operand absent');
      }
    }
  }
}

export function validateReport(r: Report, checkHashes = true): void {
  const doc = r.document;
  const readers = unique(r.readers, 'ID');
  const trans = unique(r.transforms, 'ID');
  const occ = unique(r.occurrences, 'ID');
  const findings = unique(r.findings, 'ID');
  const assets = unique(r.assets, 'ID');
  const pages = new Map<number, Page>();
  for (const p of r.pages) pages.set(p.index, p);
  require(pages.size === r.pages.length, 'PAGE', 'Duplicate page');
  for (const i of pages.keys()) {
    require(
      i >= 0 && i < doc.page_count,
      'PAGE',
      'Page outside document',
    );
  }
  const regions = unique(r.plan.regions, 'ID');
  const plans = unique(r.plan.checks, 'ID');
  const checks = unique(r.checks, 'ID');
  require(
    setsEqual(keySet(plans), keySet(checks)),
    'COVERAGE',
    'Planned and terminal check IDs differ',
  );
  require(
    subset(new Set(r.plan.selected_pages), new Set(pages.keys())),
    'PAGE',
    'Selected page metadata absent',
  );
  for (const p of pages.values()) {
    require(
      trans.has(p.raw_to_canonical_transform_id),
      'REFERENCE',
      'Missing page transform',
    );
    for (const b of [p.media_box, p.crop_box, p.effective_view_box]) {
      if (b) {
        require(
          b[2]! > b[0]! && b[3]! > b[1]!,
          'GEOMETRY',
          'Invalid page box',
        );
      }
    }
    const u = p.user_unit;
    const v = p.effective_view_box;
    const expected = [u * (v[2]! - v[0]!), u * (v[3]! - v[1]!)];
    require(
      expected.every(
        (a, idx) => Math.abs(a - p.canonical_size_pt[idx]!) <= 1e-5,
      ),
      'GEOMETRY',
      'Canonical dimensions inconsistent',
    );
    const expectedC = [u, 0, 0, -u, -u * v[0]!, u * v[3]!];
    const c = trans.get(p.raw_to_canonical_transform_id)!;
    require(
      c.page_index === p.index &&
        c.matrix.every(
          (a, idx) => Math.abs(a - expectedC[idx]!) <= 1e-5,
        ),
      'TRANSFORM',
      'Wrong raw-to-canonical matrix',
    );
  }
  for (const t of trans.values()) {
    require(pages.has(t.page_index), 'PAGE', 'Transform page absent');
    const inv = inverse(t.matrix);
    require(
      inv.every((a, idx) => Math.abs(a - t.inverse[idx]!) <= 1e-5),
      'TRANSFORM',
      'Incorrect inverse',
    );
  }

  function geometry(g: Geometry, pageIndex: number | null = null): void {
    require(
      subset(new Set(g.transform_ids), keySet(trans)),
      'REFERENCE',
      'Missing geometry transform',
    );
    require(
      (g.polygon === null) ===
        (g.precision === 'unknown' || g.precision === 'page_only'),
      'GEOMETRY',
      'Precision/polygon conflict',
    );
    if (pageIndex !== null) {
      require(
        g.transform_ids.every((t) => trans.get(t)!.page_index === pageIndex),
        'TRANSFORM',
        'Geometry crosses transform pages',
      );
    }
    if (g.polygon !== null) {
      const pts = g.polygon;
      let area = 0;
      for (let i = 0; i < pts.length; i++) {
        const [x1, y1] = pts[i]!;
        const [x2, y2] = pts[(i + 1) % pts.length]!;
        area += x1 * y2 - x2 * y1;
      }
      require(
        Math.abs(area) > 1e-12,
        'GEOMETRY',
        'Degenerate source polygon',
      );
    }
  }

  for (const region of regions.values()) {
    require(pages.has(region.page_index), 'PAGE', 'Region page absent');
    geometry(region.geometry, region.page_index);
  }
  for (const p of plans.values()) {
    require(
      r.plan.selected_pages.includes(p.page_index),
      'COVERAGE',
      'Check outside selected pages',
    );
    require(
      subset(new Set(p.reader_ids), keySet(readers)),
      'REFERENCE',
      'Unknown planned reader',
    );
    require(
      p.region_id === null || regions.has(p.region_id),
      'REFERENCE',
      'Unknown planned region',
    );
    require(
      p.region_id === null ||
        regions.get(p.region_id)!.page_index === p.page_index,
      'PAGE',
      'Plan region crosses page',
    );
  }
  for (const o of occ.values()) {
    require(
      readers.has(o.reader_id) && pages.has(o.page_index),
      'REFERENCE',
      'Unknown occurrence reader/page',
    );
    geometry(o.geometry, o.page_index);
    const n = normalize(o.raw_text);
    require(
      o.normalized_text === n.text && mapsEqual(o.normalization_map, n.map),
      'NORMALIZATION',
      'Raw/normalized view mismatch',
    );
    require(
      o.source_asset_id === null || assets.has(o.source_asset_id),
      'REFERENCE',
      'Unknown occurrence asset',
    );
    if (o.engine_score) {
      const s = o.engine_score;
      require(
        s.scale_min <= s.value && s.value <= s.scale_max,
        'SCORE',
        'Score outside own scale',
      );
    }
  }
  for (const c of checks.values()) {
    require(
      subset(new Set(c.retained_occurrence_ids), keySet(occ)),
      'REFERENCE',
      'Check occurrence absent',
    );
    require(
      c.retained_occurrence_ids.length ===
        new Set(c.retained_occurrence_ids).size,
      'ID',
      'Repeated check occurrence reference',
    );
    require(
      c.produced_occurrence_count >= c.retained_occurrence_ids.length,
      'COVERAGE',
      'Retained more than produced',
    );
    if (c.status !== 'completed') {
      require(c.reason !== null, 'COVERAGE', 'Incomplete check lacks reason');
    }
    const p = plans.get(c.id)!;
    for (const oid of c.retained_occurrence_ids) {
      const o = occ.get(oid)!;
      require(
        p.reader_ids.includes(o.reader_id) && o.page_index === p.page_index,
        'REFERENCE',
        'Check/occurrence binding mismatch',
      );
    }
  }
  for (const f of findings.values()) {
    require(pages.has(f.page_index), 'PAGE', 'Finding page absent');
    require(
      subset(new Set(f.occurrence_ids), keySet(occ)) &&
        subset(new Set(f.check_ids), keySet(checks)),
      'REFERENCE',
      'Finding references absent',
    );
    require(
      f.region_id === null || regions.has(f.region_id),
      'REFERENCE',
      'Finding region absent',
    );
    require(
      f.region_id === null ||
        regions.get(f.region_id)!.page_index === f.page_index,
      'PAGE',
      'Finding region crosses page',
    );
    for (const oid of f.occurrence_ids) {
      require(
        occ.get(oid)!.page_index === f.page_index,
        'PAGE',
        'Finding crosses page',
      );
    }
    if (f.kind === 'reading_difference') {
      const readerIds = new Set(
        f.occurrence_ids.map((o) => occ.get(o)!.reader_id),
      );
      require(
        readerIds.size >= 2,
        'EVIDENCE',
        'Difference requires two actual readings',
      );
      require(
        f.check_ids.every((c) => checks.get(c)!.status === 'completed'),
        'EVIDENCE',
        'Difference cites incomplete read',
      );
      const supported = new Set<string>();
      for (const cid of f.check_ids) {
        for (const oid of checks.get(cid)!.retained_occurrence_ids) {
          supported.add(oid);
        }
      }
      require(
        subset(new Set(f.occurrence_ids), supported),
        'EVIDENCE',
        'Difference occurrence lacks cited completed-read support',
      );
    }
    if (f.alignment === 'unique') {
      require(
        f.region_id !== null &&
          f.occurrence_ids.every(
            (o) => occ.get(o)!.geometry.polygon !== null,
          ),
        'GEOMETRY',
        'Unique match without geometry',
      );
    }
  }
  unique(r.annotations, 'ID');
  for (const a of r.annotations) {
    require(pages.has(a.page_index), 'PAGE', 'Annotation page absent');
    require(
      a.finding_id === null || findings.has(a.finding_id),
      'REFERENCE',
      'Annotation finding absent',
    );
    require(
      a.finding_id === null ||
        findings.get(a.finding_id)!.page_index === a.page_index,
      'PAGE',
      'Annotation finding crosses page',
    );
  }
  const complete = [...checks.values()].filter(
    (c) => c.status === 'completed',
  ).length;
  const status = r.execution.status;
  if (status === 'complete') {
    require(
      complete === checks.size,
      'COVERAGE',
      'Complete run includes incomplete check',
    );
  } else if (status === 'failed') {
    require(
      complete === 0 &&
        [...checks.values()].some(
          (c) => c.status === 'failed' || c.status === 'timeout',
        ),
      'COVERAGE',
      'Failed state inconsistent',
    );
  } else if (status === 'partial') {
    require(
      complete < checks.size,
      'COVERAGE',
      'Partial state has no incomplete checks',
    );
  }
  let total = 0;
  for (const a of assets.values()) {
    const data = b64decode(a.data_base64);
    total += data.length;
    require(
      data.length === a.byte_length && toHex(sha256(data)) === a.sha256,
      'ASSET',
      'Hash/length mismatch',
    );
    require(data.length <= MAX_ASSET_BYTES, 'SIZE', 'Asset too large');
    if (a.media_type === 'image/png') {
      require(
        (a.purpose === 'crop' || a.purpose === 'page_render') &&
          a.page_index !== null &&
          pages.has(a.page_index),
        'ASSET',
        'Image purpose/page mismatch',
      );
      const pngSig = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
      require(
        data.length >= 24 && pngSig.every((b, idx) => data[idx] === b),
        'ASSET',
        'Not PNG',
      );
      const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
      const wh = [dv.getUint32(16), dv.getUint32(20)];
      require(
        // List-equality with Python: schema-legal pixel_size:null must
        // fail as ASSET, never crash on a null index.
        a.pixel_size !== null &&
          wh[0] === a.pixel_size[0] &&
          wh[1] === a.pixel_size[1] &&
          wh[0] * wh[1] <= MAX_PNG_PIXELS,
        'ASSET',
        'PNG size mismatch',
      );
    } else if (a.media_type === 'application/pdf') {
      require(
        a.purpose === 'source_pdf' &&
          data.length >= 5 &&
          [0x25, 0x50, 0x44, 0x46, 0x2d].every((b, idx) => data[idx] === b),
        'ASSET',
        'Wrong PDF purpose/header',
      );
    }
    if (a.geometry) {
      geometry(a.geometry, a.page_index);
    }
  }
  require(total <= MAX_ASSET_TOTAL, 'SIZE', 'Decoded asset total too large');
  const included = new Set<string>(r.export.included);
  require(
    ['document_hash', 'settings', 'coverage'].every((x) => included.has(x)),
    'PRIVACY',
    'Required metadata disclosure absent',
  );
  require(
    r.occurrences.length === 0 || included.has('selected_text'),
    'PRIVACY',
    'Undisclosed reading text',
  );
  require(
    r.annotations.length === 0 || included.has('annotations'),
    'PRIVACY',
    'Undisclosed annotations',
  );
  require(
    ![...assets.values()].some((a) => a.purpose === 'page_render') ||
      included.has('page_renders'),
    'PRIVACY',
    'Undisclosed full-page image',
  );
  const source = doc.source_asset_id;
  if (source !== null) {
    const sa = assets.get(source);
    require(
      sa !== undefined &&
        sa.sha256 === doc.sha256 &&
        sa.byte_length === doc.byte_length,
      'SOURCE',
      'Original bytes not bound',
    );
    require(
      sa.media_type === 'application/pdf' && sa.purpose === 'source_pdf',
      'SOURCE',
      'Source is not a PDF asset',
    );
    require(included.has('source_pdf'), 'PRIVACY', 'Undisclosed original');
  }
  if (r.export.mode === 'replayable') {
    require(
      source !== null &&
        r.export.replay === 'source_included_environment_required',
      'REPLAY',
      'Replayable without source',
    );
  }
  if (r.export.replay === 'source_included_environment_required') {
    require(source !== null, 'REPLAY', 'Source unavailable');
  }
  require(
    (doc.display_name !== null) === included.has('filename'),
    'PRIVACY',
    'Filename disclosure mismatch',
  );
  require(
    ![...assets.values()].some((a) => a.purpose === 'source_pdf') ||
      included.has('source_pdf'),
    'PRIVACY',
    'Undisclosed PDF asset',
  );
  require(
    ![...assets.values()].some((a) => a.purpose === 'crop') ||
      included.has('crops'),
    'PRIVACY',
    'Undisclosed crop',
  );
  if (checkHashes) {
    require(
      r.execution.run_key === runKey(r),
      'HASH',
      'Run key mismatch',
    );
    require(
      r.report_id === reportDigest(r),
      'HASH',
      'Report digest mismatch',
    );
  }
}

/** Parse untrusted JSON then run full contract validation. */
export function validateJson(
  data: string | Uint8Array,
  checkHashes = true,
): unknown {
  const value = loadsStrict(data);
  validate(value, checkHashes);
  return value;
}
