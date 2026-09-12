/**
 * Bounded, dependency-free PNG decode and re-encode for imported report
 * assets (image/png only; there is deliberately no SVG, no APNG frame
 * handling beyond the default image, and no ancillary-metadata parsing).
 *
 * The planning reference validator checks only the PNG envelope — magic
 * bytes plus IHDR dimensions. This module performs the full decode the
 * threat model requires: every chunk length is bounded against the
 * remaining input, every chunk CRC is verified, critical chunks are
 * limited to the known set, IDAT inflates into a buffer sized exactly by
 * the already-bounded IHDR (decompression bombs fail instead of growing),
 * scanline filters are applied, and the image is re-encoded as a clean
 * 8-bit RGBA PNG (no ancillary chunks, no interlace) for safe embedding.
 *
 * Rejections are ContractError with code 'PNG' (malformed content) or
 * 'SIZE' (a declared limit would be exceeded before allocation).
 */
import { ContractError } from '../../contracts/src/index.ts';
import { inflateZlib, zlibEncodeStored } from './inflate.ts';
import { IMPORT_LIMITS } from './limits.ts';

export const PNG_SIG = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
]);

const fail = (message: string): never => {
  throw new ContractError('PNG', message);
};
const failSize = (message: string): never => {
  throw new ContractError('SIZE', message);
};

// ---------------------------------------------------------------------------
// CRC-32 (ISO 3309, as used by PNG chunks)
// ---------------------------------------------------------------------------

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    t[n] = c >>> 0;
  }
  return t;
})();

export function crc32(data: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < data.length; i++) {
    c = CRC_TABLE[(c ^ data[i]!) & 0xff]! ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

// ---------------------------------------------------------------------------
// Chunk parsing
// ---------------------------------------------------------------------------

interface Chunk {
  /** Four ASCII type letters, e.g. 'IHDR'. */
  type: string;
  data: Uint8Array;
}

const KNOWN_CRITICAL = new Set(['IHDR', 'PLTE', 'IDAT', 'IEND']);

function parseChunks(data: Uint8Array): Chunk[] {
  if (data.length < 8 || !PNG_SIG.every((b, i) => data[i] === b)) {
    fail('Not a PNG (bad signature)');
  }
  const chunks: Chunk[] = [];
  let pos = 8;
  let sawIend = false;
  while (pos < data.length) {
    if (sawIend) fail('Trailing data after IEND');
    if (pos + 8 > data.length) fail('Truncated chunk header');
    const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
    const len = dv.getUint32(pos);
    // Chunk length must fit the remaining bytes before any slice exists.
    if (len > data.length - pos - 12) fail('Chunk length exceeds input');
    let type = '';
    for (let i = 0; i < 4; i++) {
      const c = data[pos + 4 + i]!;
      // PNG type bytes are ASCII letters; anything else is malformed.
      if (!((c >= 0x41 && c <= 0x5a) || (c >= 0x61 && c <= 0x7a))) {
        fail('Non-letter chunk type');
      }
      type += String.fromCharCode(c);
    }
    const body = data.subarray(pos + 8, pos + 8 + len);
    const crcPos = pos + 8 + len;
    const wantCrc = dv.getUint32(crcPos);
    const crcInput = data.subarray(pos + 4, crcPos);
    if (crc32(crcInput) !== wantCrc) fail(`Bad CRC in ${type}`);
    // Second letter lowercase marks ancillary; unknown ancillary chunks
    // are skipped (never interpreted) while unknown critical chunks are a
    // hard failure — the decoder cannot know their semantics.
    const ancillary = (type.charCodeAt(0)! & 0x20) !== 0;
    if (!ancillary && !KNOWN_CRITICAL.has(type)) {
      fail(`Unknown critical chunk ${type}`);
    }
    if (type === 'IEND') {
      if (len !== 0) fail('IEND must be empty');
      sawIend = true;
    }
    chunks.push({ type, data: body });
    pos = crcPos + 4;
  }
  if (!sawIend) fail('Missing IEND');
  if (chunks.length === 0 || chunks[0]!.type !== 'IHDR') {
    fail('First chunk must be IHDR');
  }
  return chunks;
}

// ---------------------------------------------------------------------------
// IHDR and geometry accounting
// ---------------------------------------------------------------------------

/** Samples per pixel for each legal color type. */
const SAMPLES: Record<number, number> = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 };
/** Bit depths legal for each color type (RFC 2083). */
const DEPTHS: Record<number, ReadonlySet<number>> = {
  0: new Set([1, 2, 4, 8, 16]),
  2: new Set([8, 16]),
  3: new Set([1, 2, 4, 8]),
  4: new Set([8, 16]),
  6: new Set([8, 16]),
};

export interface PngInfo {
  width: number;
  height: number;
  bitDepth: number;
  colorType: number;
  interlace: number;
}

function parseIhdr(
  data: Uint8Array,
  maxPixels: number,
  maxEdge: number,
): PngInfo {
  if (data.length !== 13) fail('IHDR must be 13 bytes');
  const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const width = dv.getUint32(0);
  const height = dv.getUint32(4);
  const bitDepth = data[8]!;
  const colorType = data[9]!;
  const compression = data[10]!;
  const filter = data[11]!;
  const interlace = data[12]!;
  // All size limits are enforced before any pixel-sized allocation exists.
  if (width === 0 || height === 0) fail('Zero image dimension');
  if (width > maxEdge || height > maxEdge) {
    failSize(`PNG edge ${width}x${height} exceeds ${maxEdge}`);
  }
  if (width > maxPixels || width * height > maxPixels) {
    failSize(`PNG ${width}x${height} exceeds ${maxPixels} pixels`);
  }
  const depths = DEPTHS[colorType];
  if (depths === undefined) fail(`Unknown color type ${colorType}`);
  if (!depths.has(bitDepth)) {
    fail(`Bit depth ${bitDepth} illegal for color type ${colorType}`);
  }
  if (compression !== 0) fail('Unknown PNG compression method');
  if (filter !== 0) fail('Unknown PNG filter method');
  if (interlace !== 0 && interlace !== 1) fail('Unknown PNG interlace');
  return { width, height, bitDepth, colorType, interlace };
}

/** Adam7 pass layout: origin (x0,y0) and stride (dx,dy) per pass. */
const ADAM7: ReadonlyArray<readonly [number, number, number, number]> = [
  [0, 0, 8, 8],
  [4, 0, 8, 8],
  [0, 4, 4, 8],
  [2, 0, 4, 4],
  [0, 2, 2, 4],
  [1, 0, 2, 2],
  [0, 1, 1, 2],
];

function passSize(n: number, start: number, step: number): number {
  return n <= start ? 0 : Math.ceil((n - start) / step);
}

/** Bytes in one packed scanline for `w` pixels at `bpp` bits-per-pixel. */
function rowBytes(w: number, bpp: number): number {
  return Math.ceil((w * bpp) / 8);
}

/**
 * Exact inflated IDAT size implied by the bounded header. This is the
 * inflate output cap: a stream producing one byte more is a bomb, one
 * byte fewer is truncated.
 */
function inflatedSize(info: PngInfo): number {
  const bpp = info.bitDepth * SAMPLES[info.colorType]!;
  let total = 0;
  if (info.interlace === 0) {
    total = info.height * (1 + rowBytes(info.width, bpp));
  } else {
    for (const [x0, y0, dx, dy] of ADAM7) {
      const pw = passSize(info.width, x0, dx);
      const ph = passSize(info.height, y0, dy);
      if (pw > 0 && ph > 0) total += ph * (1 + rowBytes(pw, bpp));
    }
  }
  return total;
}

// ---------------------------------------------------------------------------
// Scanline unfiltering (packed bytes, bpp = filter byte distance)
// ---------------------------------------------------------------------------

function paeth(a: number, b: number, c: number): number {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

/**
 * Unfilter one pass. `raw` holds `rows` scanlines of `stride` filtered
 * bytes each preceded by a filter-type byte; recon is written packed into
 * `raw` itself? No — writes into `recon` rows of `stride` bytes.
 */
function unfilter(
  raw: Uint8Array,
  offset: number,
  rows: number,
  stride: number,
  bpp: number,
  recon: Uint8Array,
): void {
  let src = offset;
  for (let y = 0; y < rows; y++) {
    if (src + 1 + stride > raw.length) fail('Truncated scanline data');
    const ft = raw[src]!;
    const row = y * stride;
    recon.set(raw.subarray(src + 1, src + 1 + stride), row);
    const prev = row - stride;
    switch (ft) {
      case 0:
        break;
      case 1:
        for (let x = bpp; x < stride; x++) {
          recon[row + x] = (recon[row + x]! + recon[row + x - bpp]!) & 0xff;
        }
        break;
      case 2:
        for (let x = 0; x < stride; x++) {
          recon[row + x] = (recon[row + x]! + (y ? recon[prev + x]! : 0)) &
            0xff;
        }
        break;
      case 3:
        for (let x = 0; x < stride; x++) {
          const a = x >= bpp ? recon[row + x - bpp]! : 0;
          const b = y ? recon[prev + x]! : 0;
          recon[row + x] = (recon[row + x]! + ((a + b) >> 1)) & 0xff;
        }
        break;
      case 4:
        for (let x = 0; x < stride; x++) {
          const a = x >= bpp ? recon[row + x - bpp]! : 0;
          const b = y ? recon[prev + x]! : 0;
          const c = y && x >= bpp ? recon[prev + x - bpp]! : 0;
          recon[row + x] = (recon[row + x]! + paeth(a, b, c)) & 0xff;
        }
        break;
      default:
        fail(`Unknown scanline filter ${ft}`);
    }
    src += 1 + stride;
  }
}

// ---------------------------------------------------------------------------
// Packed-sample expansion to RGBA8
// ---------------------------------------------------------------------------

/** Extract the `i`-th packed sample of width `bitDepth` from a scanline. */
function packedSample(line: Uint8Array, row: number, i: number, depth: number): number {
  if (depth === 8) return line[row + i]!;
  if (depth === 16) return line[row + 2 * i]!; // high byte only
  const perByte = 8 / depth;
  const byte = line[row + Math.floor(i / perByte)]!;
  const shift = 8 - depth * ((i % perByte) + 1);
  return (byte >> shift) & ((1 << depth) - 1);
}

/** Full-precision sample for tRNS comparison (16-bit at depth 16). */
function fullSample(line: Uint8Array, row: number, i: number, depth: number): number {
  if (depth === 16) return (line[row + 2 * i]! << 8) | line[row + 2 * i + 1]!;
  return packedSample(line, row, i, depth);
}

/** Scale a sub-byte sample to 0..255 (PNG low-bit-depth expansion). */
function scaleSample(v: number, depth: number): number {
  if (depth === 8) return v;
  if (depth === 16) return v; // already the high byte
  const max = (1 << depth) - 1;
  return Math.round((v * 255) / max);
}

interface Palette {
  rgb: Uint8Array;
  entries: number;
  alpha: Uint8Array | null;
}

function decodePassToRgba(
  recon: Uint8Array,
  info: PngInfo,
  pw: number,
  ph: number,
  x0: number,
  y0: number,
  dx: number,
  dy: number,
  rgba: Uint8Array,
  palette: Palette | null,
  trns: Uint8Array | null,
): void {
  const { width, bitDepth, colorType } = info;
  const spp = SAMPLES[colorType]!;
  const stride = rowBytes(pw, bitDepth * spp);
  for (let y = 0; y < ph; y++) {
    const row = y * stride;
    const outY = y0 + y * dy;
    for (let x = 0; x < pw; x++) {
      const outX = x0 + x * dx;
      const o = (outY * width + outX) * 4;
      if (colorType === 3) {
        const idx = packedSample(recon, row, x, bitDepth);
        if (palette === null || idx >= palette.entries) {
          fail('Palette index out of range');
        }
        rgba[o] = palette.rgb[3 * idx]!;
        rgba[o + 1] = palette.rgb[3 * idx + 1]!;
        rgba[o + 2] = palette.rgb[3 * idx + 2]!;
        rgba[o + 3] = palette.alpha !== null && idx < palette.alpha.length
          ? palette.alpha[idx]!
          : 255;
      } else if (colorType === 0) {
        const raw = packedSample(recon, row, x, bitDepth);
        const g = scaleSample(raw, bitDepth);
        rgba[o] = g;
        rgba[o + 1] = g;
        rgba[o + 2] = g;
        // tRNS gray is one sample stored big-endian at image bit depth.
        rgba[o + 3] =
          trns !== null &&
          trns.length === 2 &&
          fullSample(recon, row, x, bitDepth) ===
            ((trns[0]! << 8) | trns[1]!)
            ? 0
            : 255;
      } else if (colorType === 2) {
        const r = packedSample(recon, row, 3 * x, bitDepth);
        const g = packedSample(recon, row, 3 * x + 1, bitDepth);
        const b = packedSample(recon, row, 3 * x + 2, bitDepth);
        rgba[o] = r;
        rgba[o + 1] = g;
        rgba[o + 2] = b;
        rgba[o + 3] =
          trns !== null &&
          trns.length === 6 &&
          fullSample(recon, row, 3 * x, bitDepth) ===
            ((trns[0]! << 8) | trns[1]!) &&
          fullSample(recon, row, 3 * x + 1, bitDepth) ===
            ((trns[2]! << 8) | trns[3]!) &&
          fullSample(recon, row, 3 * x + 2, bitDepth) ===
            ((trns[4]! << 8) | trns[5]!)
            ? 0
            : 255;
      } else if (colorType === 4) {
        const g = packedSample(recon, row, 2 * x, bitDepth);
        rgba[o] = g;
        rgba[o + 1] = g;
        rgba[o + 2] = g;
        rgba[o + 3] = packedSample(recon, row, 2 * x + 1, bitDepth);
      } else {
        // colorType 6
        rgba[o] = packedSample(recon, row, 4 * x, bitDepth);
        rgba[o + 1] = packedSample(recon, row, 4 * x + 1, bitDepth);
        rgba[o + 2] = packedSample(recon, row, 4 * x + 2, bitDepth);
        rgba[o + 3] = packedSample(recon, row, 4 * x + 3, bitDepth);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Public surface
// ---------------------------------------------------------------------------

export interface DecodedPng {
  width: number;
  height: number;
  /** RGBA8 pixel data, `width * height * 4` bytes. */
  rgba: Uint8Array;
  /** True when the source used Adam7 interlacing. */
  interlaced: boolean;
}

/**
 * Fully decode a PNG to RGBA8 under the import pixel/edge limits. Every
 * structural and size check runs before the matching allocation: chunk
 * bounds before slicing, IHDR caps before the inflate buffer exists, and
 * the inflate cap equals the exact scanline byte count.
 */
export function decodePng(
  data: Uint8Array,
  limits: {
    maxPixels?: number;
    maxEdge?: number;
  } = {},
): DecodedPng {
  const maxPixels = limits.maxPixels ?? IMPORT_LIMITS.maxPngPixels;
  const maxEdge = limits.maxEdge ?? IMPORT_LIMITS.maxPngEdge;
  const chunks = parseChunks(data);
  const info = parseIhdr(chunks[0]!.data, maxPixels, maxEdge);
  let plte: Chunk | null = null;
  let trns: Chunk | null = null;
  const idat: Uint8Array[] = [];
  for (const c of chunks.slice(1)) {
    if (c.type === 'PLTE') {
      if (plte !== null) fail('Duplicate PLTE');
      if (c.data.length === 0 || c.data.length % 3 !== 0) {
        fail('Malformed PLTE');
      }
      plte = c;
    } else if (c.type === 'tRNS') {
      trns = c;
    } else if (c.type === 'IDAT') {
      idat.push(c.data);
    } else if (c.type === 'IEND') {
      break;
    }
    // Ancillary chunks (tEXt, zTXt, iTXt, acTL, fcTL, fdAT, pHYs, …) are
    // ignored entirely: their bytes are never interpreted and are dropped
    // by the re-encode, which also removes APNG animation data.
  }
  if (idat.length === 0) fail('Missing IDAT');
  const packedLen = idat.reduce((n, c) => n + c.length, 0);
  const packed = new Uint8Array(packedLen);
  {
    let o = 0;
    for (const c of idat) {
      packed.set(c, o);
      o += c.length;
    }
  }
  // The inflate cap is the exact raster size implied by the bounded IHDR —
  // not an estimate — so expansion attacks have nowhere to write.
  const expected = inflatedSize(info);
  const raw = inflateZlib(packed, expected);
  if (raw.length !== expected) fail('IDAT size does not match header');
  if (info.colorType === 3 && plte === null) {
    fail('Palette image missing PLTE');
  }
  const entries = plte === null ? 0 : plte.data.length / 3;
  if (plte !== null && entries > 256) fail('PLTE exceeds 256 entries');
  if (info.colorType === 3 && entries > 1 << info.bitDepth) {
    fail('PLTE exceeds depth range');
  }
  if (trns !== null) {
    // tRNS length is fixed by color type (2 bytes gray, 6 bytes RGB,
    // 1..256 palette alphas); a malformed one is rejected, not ignored.
    const want =
      info.colorType === 0 ? 2 : info.colorType === 2 ? 6 : null;
    if (want === null) {
      if (info.colorType !== 3 || trns.data.length > entries) {
        fail('Malformed tRNS');
      }
    } else if (trns.data.length !== want) {
      fail('Malformed tRNS');
    }
  }
  const palette: Palette | null =
    plte === null
      ? null
      : {
          rgb: plte.data,
          entries,
          alpha:
            trns !== null && info.colorType === 3 ? trns.data : null,
        };
  // One bounded pixel allocation for the whole image.
  const rgba = new Uint8Array(info.width * info.height * 4);
  const bpp = Math.max(1, Math.ceil((info.bitDepth * SAMPLES[info.colorType]!) / 8));
  if (info.interlace === 0) {
    const stride = rowBytes(info.width, info.bitDepth * SAMPLES[info.colorType]!);
    const recon = new Uint8Array(info.height * stride);
    unfilter(raw, 0, info.height, stride, bpp, recon);
    decodePassToRgba(
      recon, info, info.width, info.height, 0, 0, 1, 1, rgba, palette,
      trns?.data ?? null,
    );
  } else {
    let offset = 0;
    for (const [x0, y0, dx, dy] of ADAM7) {
      const pw = passSize(info.width, x0, dx);
      const ph = passSize(info.height, y0, dy);
      if (pw === 0 || ph === 0) continue;
      const stride = rowBytes(pw, info.bitDepth * SAMPLES[info.colorType]!);
      const recon = new Uint8Array(ph * stride);
      unfilter(raw, offset, ph, stride, bpp, recon);
      offset += ph * (1 + stride);
      decodePassToRgba(
        recon, info, pw, ph, x0, y0, dx, dy, rgba, palette,
        trns?.data ?? null,
      );
    }
  }
  return { width: info.width, height: info.height, rgba, interlaced: info.interlace === 1 };
}

/**
 * Re-encode RGBA8 pixels as a clean PNG: 8-bit RGBA, filter type 0,
 * zlib stored blocks, chunked IDAT, no ancillary chunks, no interlace.
 * The output contains nothing from the input except the decoded pixels.
 */
export function encodePngRgba(
  width: number,
  height: number,
  rgba: Uint8Array,
): Uint8Array {
  if (width < 1 || height < 1 || rgba.length !== width * height * 4) {
    fail('encodePngRgba: inconsistent raster');
  }
  const rows = new Uint8Array(height * (1 + width * 4));
  for (let y = 0; y < height; y++) {
    rows[y * (1 + width * 4)] = 0; // filter: none
    rows.set(
      rgba.subarray(y * width * 4, (y + 1) * width * 4),
      y * (1 + width * 4) + 1,
    );
  }
  const zdata = zlibEncodeStored(rows);
  const parts: Uint8Array[] = [PNG_SIG.slice()];
  const pushChunk = (type: string, body: Uint8Array): void => {
    const head = new Uint8Array(8);
    new DataView(head.buffer).setUint32(0, body.length);
    for (let i = 0; i < 4; i++) head[4 + i] = type.charCodeAt(i);
    const crc = new Uint8Array(4);
    const crcIn = new Uint8Array(4 + body.length);
    crcIn.set(head.subarray(4, 8), 0);
    crcIn.set(body, 4);
    new DataView(crc.buffer).setUint32(0, crc32(crcIn));
    parts.push(head, body, crc);
  };
  const ihdr = new Uint8Array(13);
  const dv = new DataView(ihdr.buffer);
  dv.setUint32(0, width);
  dv.setUint32(4, height);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  // compression, filter, interlace already zero
  pushChunk('IHDR', ihdr);
  const IDAT_CHUNK = 512 * 1024;
  for (let i = 0; i < zdata.length; i += IDAT_CHUNK) {
    pushChunk('IDAT', zdata.subarray(i, i + IDAT_CHUNK));
  }
  pushChunk('IEND', new Uint8Array(0));
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

export interface SanitizedPng {
  /** Clean re-encoded PNG bytes (8-bit RGBA, no ancillary chunks). */
  png: Uint8Array;
  width: number;
  height: number;
  /** True when the *source* image was Adam7-interlaced (output never is). */
  sourceInterlaced: boolean;
}

/** Decode an imported PNG and return its sanitized re-encode plus dims. */
export function sanitizePng(
  data: Uint8Array,
  limits: { maxPixels?: number; maxEdge?: number } = {},
): SanitizedPng {
  const decoded = decodePng(data, limits);
  const png = encodePngRgba(decoded.width, decoded.height, decoded.rgba);
  return {
    png,
    width: decoded.width,
    height: decoded.height,
    sourceInterlaced: decoded.interlaced,
  };
}
