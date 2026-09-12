/**
 * Dependency-free zlib (RFC 1950) / DEFLATE (RFC 1951) inflate with a hard
 * output cap, plus a deterministic zlib "stored" encoder used to re-encode
 * sanitized PNG image data.
 *
 * Security posture: `inflateZlib` writes into a single preallocated output
 * buffer whose size the caller derives from data it has already validated
 * (for PNG, the exact scanline byte count implied by a bounded IHDR). The
 * buffer never grows, so a deflate stream that expands past the declared
 * image size fails with `PNG`/`SIZE` instead of allocating attacker-chosen
 * memory — this is the decompression-bomb boundary.
 *
 * Implemented from the RFCs for this project; no third-party code is
 * copied. Decoding uses the canonical count/symbol table method: codes of
 * each bit length are counted, symbols sorted by (length, symbol order),
 * and bits consumed MSB-of-code first inside an LSB-first bit stream.
 */
import { ContractError } from '../../contracts/src/index.ts';

const MAX_BITS = 15;
const MAX_SYMBOLS = 288;
const NUM_LENGTHS = 19;

/** Base match lengths for literal/length symbols 257..285 (RFC 1951). */
const LEN_BASE = [
  3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59,
  67, 83, 99, 115, 131, 163, 195, 227, 258,
];
/** Extra bits for literal/length symbols 257..285. */
const LEN_EXTRA = [
  0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4,
  5, 5, 5, 5, 0,
];
/** Base distances for distance symbols 0..29. */
const DIST_BASE = [
  1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513,
  769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577,
];
/** Extra bits for distance symbols 0..29. */
const DIST_EXTRA = [
  0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10,
  10, 11, 11, 12, 12, 13, 13,
];
/** Order in which code-length-code lengths are stored (dynamic blocks). */
const CL_ORDER = [
  16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15,
];

interface Huffman {
  /** count[len] = number of codes with bit length `len` (index 0 unused). */
  count: Uint16Array;
  /** Symbols ordered by (code length, symbol value). */
  symbol: Uint16Array;
}

class InflateError extends ContractError {
  constructor(message: string) {
    super('PNG', message);
    this.name = 'InflateError';
  }
}

function fail(message: string): never {
  throw new InflateError(message);
}

class BitReader {
  /** Index of the next byte in `data` to consume. */
  pos: number;
  /** Number of bits already consumed from data[pos] (0..7). */
  bit: number;
  private readonly data: Uint8Array;
  /** End of the deflate bit stream (exclusive). */
  private readonly end: number;

  constructor(data: Uint8Array, pos: number, end: number) {
    this.data = data;
    this.end = end;
    this.pos = pos;
    this.bit = 0;
  }

  /** Read one bit (LSB-first within each byte). */
  bitOne(): number {
    if (this.pos >= this.end) fail('Deflate stream ran out of input');
    const b = (this.data[this.pos]! >> this.bit) & 1;
    this.bit++;
    if (this.bit === 8) {
      this.bit = 0;
      this.pos++;
    }
    return b;
  }

  /** Read `n` bits (0..16), LSB-first. */
  bits(n: number): number {
    let v = 0;
    for (let i = 0; i < n; i++) v |= this.bitOne() << i;
    return v;
  }

  /** Discard bits to the next byte boundary; returns the byte position. */
  align(): number {
    if (this.bit !== 0) {
      this.bit = 0;
      this.pos++;
    }
    return this.pos;
  }
}

/**
 * Build a canonical decoding table from a list of code lengths.
 * `checkComplete` applies the zlib dynamic-table rule: the code set must
 * be complete, except that a distance table may be empty for literal-only
 * blocks or hold a single used code. Decoding a length with an empty
 * distance table still fails in decode(). Fixed tables defined by RFC 1951 (which include a
 * legitimately incomplete distance table) skip the check.
 */
function buildTable(
  lengths: Uint8Array,
  isDist: boolean,
  checkComplete: boolean,
): Huffman {
  const count = new Uint16Array(MAX_BITS + 1);
  let maxLen = 0;
  for (const len of lengths) {
    if (len > MAX_BITS) fail('Code length exceeds 15 bits');
    count[len] = count[len]! + 1;
    if (len > maxLen) maxLen = len;
  }
  let left = 1;
  for (let len = 1; len <= MAX_BITS; len++) {
    left <<= 1;
    left -= count[len]!;
    if (left < 0) fail('Over-subscribed Huffman code set');
  }
  if (checkComplete && left > 0 && (!isDist || maxLen > 1)) {
    fail('Incomplete Huffman code set');
  }
  const offs = new Uint16Array(MAX_BITS + 1);
  for (let len = 1; len < MAX_BITS; len++) {
    offs[len + 1] = offs[len]! + count[len]!;
  }
  const symbol = new Uint16Array(lengths.length);
  for (let s = 0; s < lengths.length; s++) {
    const length = lengths[s]!;
    if (length !== 0) {
      const offset = offs[length]!;
      symbol[offset] = s;
      offs[length] = offset + 1;
    }
  }
  return { count, symbol };
}

/** Decode one symbol; fails if the input ends mid-code. */
function decode(br: BitReader, h: Huffman): number {
  let code = 0;
  let first = 0;
  let index = 0;
  for (let len = 1; len <= MAX_BITS; len++) {
    code |= br.bitOne();
    const count = h.count[len]!;
    if (code - first < count) return h.symbol[index + (code - first)]!;
    index += count;
    first = (first + count) << 1;
    code <<= 1;
  }
  fail('Invalid Huffman code');
}

let FIXED_LIT: Huffman | null = null;
let FIXED_DIST: Huffman | null = null;

function fixedTables(): { lit: Huffman; dist: Huffman } {
  if (FIXED_LIT === null || FIXED_DIST === null) {
    const litLen = new Uint8Array(MAX_SYMBOLS);
    litLen.fill(8, 0, 144);
    litLen.fill(9, 144, 256);
    litLen.fill(7, 256, 280);
    litLen.fill(8, 280, 288);
    const distLen = new Uint8Array(30);
    distLen.fill(5);
    // Build into locals first so a failure cannot leave a half-populated
    // cache behind for the next call.
    const lit = buildTable(litLen, false, false);
    const dist = buildTable(distLen, true, false);
    FIXED_LIT = lit;
    FIXED_DIST = dist;
  }
  return { lit: FIXED_LIT, dist: FIXED_DIST! };
}

function dynamicTables(br: BitReader): { lit: Huffman; dist: Huffman } {
  const nLit = br.bits(5) + 257;
  const nDist = br.bits(5) + 1;
  const nCl = br.bits(4) + 4;
  if (nLit > 286 || nDist > 30) fail('Dynamic table sizes out of range');
  const clLen = new Uint8Array(NUM_LENGTHS);
  for (let i = 0; i < nCl; i++) clLen[CL_ORDER[i]!] = br.bits(3);
  const cl = buildTable(clLen, false, true);
  const lengths = new Uint8Array(nLit + nDist);
  let i = 0;
  while (i < lengths.length) {
    const sym = decode(br, cl);
    if (sym < 16) {
      lengths[i++] = sym;
    } else if (sym === 16) {
      if (i === 0) fail('Repeat with no previous code length');
      const prev = lengths[i - 1]!;
      const rep = 3 + br.bits(2);
      if (i + rep > lengths.length) fail('Code length repeat overflow');
      lengths.fill(prev, i, i + rep);
      i += rep;
    } else if (sym === 17) {
      const rep = 3 + br.bits(3);
      if (i + rep > lengths.length) fail('Code length repeat overflow');
      i += rep; // zeros
    } else if (sym === 18) {
      const rep = 11 + br.bits(7);
      if (i + rep > lengths.length) fail('Code length repeat overflow');
      i += rep; // zeros
    } else {
      fail('Invalid code-length symbol');
    }
  }
  if (lengths[256] === 0) fail('Literal table has no end-of-block code');
  return {
    lit: buildTable(lengths.subarray(0, nLit), false, true),
    dist: buildTable(lengths.subarray(nLit), true, true),
  };
}

function inflateBlock(
  br: BitReader,
  out: Uint8Array,
  view: { produced: number },
  lit: Huffman,
  dist: Huffman,
): void {
  for (;;) {
    const sym = decode(br, lit);
    if (sym < 256) {
      if (view.produced >= out.length) fail('Inflated data exceeds bound');
      out[view.produced++] = sym;
      continue;
    }
    if (sym === 256) return; // end of block
    const li = sym - 257;
    if (li >= LEN_BASE.length) fail('Invalid length symbol');
    const len = LEN_BASE[li]! + br.bits(LEN_EXTRA[li]!);
    const dsym = decode(br, dist);
    if (dsym >= DIST_BASE.length) fail('Invalid distance symbol');
    const d = DIST_BASE[dsym]! + br.bits(DIST_EXTRA[dsym]!);
    if (d > view.produced) fail('Distance reaches before output start');
    if (view.produced + len > out.length) {
      fail('Inflated data exceeds bound');
    }
    for (let k = 0; k < len; k++) {
      out[view.produced] = out[view.produced - d]!;
      view.produced++;
    }
  }
}

/**
 * Inflate a complete zlib stream into a bounded buffer.
 *
 * @param data   bytes containing exactly one zlib stream
 * @param maxOut hard cap on inflated size; the output buffer is allocated
 *               once at this size and never grows
 * @param exact  when true (PNG IDAT), the stream must end exactly at the
 *               last four (Adler-32) bytes with no trailing garbage
 * @returns the produced bytes, `length <= maxOut`
 */
export function inflateZlib(
  data: Uint8Array,
  maxOut: number,
  exact = true,
): Uint8Array {
  if (data.length < 6) fail('Zlib stream too short');
  const cmf = data[0]!;
  const flg = data[1]!;
  if ((cmf & 0x0f) !== 8) fail('Zlib stream is not deflate');
  if (cmf >> 4 > 7) fail('Zlib window exceeds 32 KiB');
  if ((cmf * 256 + flg) % 31 !== 0) fail('Bad zlib header check');
  if ((flg & 0x20) !== 0) fail('Preset dictionaries are not accepted');
  const out = new Uint8Array(maxOut);
  const br = new BitReader(data, 2, data.length - 4);
  const view = { produced: 0 };
  for (;;) {
    const bfinal = br.bitOne();
    const btype = br.bits(2);
    if (btype === 0) {
      const p = br.align();
      if (p + 4 > data.length - 4) fail('Truncated stored block');
      const len = data[p]! | (data[p + 1]! << 8);
      const nlen = data[p + 2]! | (data[p + 3]! << 8);
      if (len !== (~nlen & 0xffff)) fail('Stored block length check');
      if (p + 4 + len > data.length - 4) fail('Truncated stored block');
      if (view.produced + len > out.length) {
        fail('Inflated data exceeds bound');
      }
      out.set(data.subarray(p + 4, p + 4 + len), view.produced);
      view.produced += len;
      br.pos = p + 4 + len;
      br.bit = 0;
    } else if (btype === 1) {
      const { lit, dist } = fixedTables();
      inflateBlock(br, out, view, lit, dist);
    } else if (btype === 2) {
      const { lit, dist } = dynamicTables(br);
      inflateBlock(br, out, view, lit, dist);
    } else {
      fail('Reserved deflate block type');
    }
    if (bfinal) break;
  }
  const endPos = br.align();
  if (exact && endPos !== data.length - 4) {
    fail('Trailing data after deflate stream');
  }
  const want =
    (data[data.length - 4]! << 24) |
    (data[data.length - 3]! << 16) |
    (data[data.length - 2]! << 8) |
    data[data.length - 1]!;
  if (adler32(out.subarray(0, view.produced)) !== want >>> 0) {
    fail('Zlib Adler-32 mismatch');
  }
  return out.subarray(0, view.produced);
}

/** RFC 1950 Adler-32 checksum. */
export function adler32(data: Uint8Array): number {
  let a = 1;
  let b = 0;
  // Split modulo steps so b stays well below 2^32 on typed-array loops.
  const MOD = 65521;
  const NMAX = 5552;
  for (let i = 0; i < data.length; i += NMAX) {
    const end = Math.min(i + NMAX, data.length);
    for (let j = i; j < end; j++) {
      a += data[j]!;
      b += a;
    }
    a %= MOD;
    b %= MOD;
  }
  return ((b << 16) | a) >>> 0;
}

/**
 * Encode `data` as a zlib stream made of uncompressed DEFLATE stored
 * blocks. Deterministic, bounded (`n + 5 * ceil(n/65535) + 6` bytes), and
 * dependency-free — used when re-encoding sanitized PNG image data where
 * correctness and auditability matter more than compression ratio.
 */
export function zlibEncodeStored(data: Uint8Array): Uint8Array {
  const blocks = Math.max(1, Math.ceil(data.length / 65535));
  const out = new Uint8Array(2 + data.length + 5 * blocks + 4);
  const dv = new DataView(out.buffer);
  out[0] = 0x78;
  out[1] = 0x01; // 0x7801: deflate, 32 KiB window, FCHECK valid
  let i = 0;
  let o = 2;
  do {
    const len = Math.min(65535, data.length - i);
    const last = i + len >= data.length;
    out[o++] = last ? 0x01 : 0x00; // BFINAL + BTYPE=00, already aligned
    dv.setUint16(o, len, true);
    dv.setUint16(o + 2, ~len & 0xffff, true);
    o += 4;
    out.set(data.subarray(i, i + len), o);
    o += len;
    i += len;
  } while (i < data.length);
  dv.setUint32(o, adler32(data), false);
  return out.subarray(0, o + 4);
}
