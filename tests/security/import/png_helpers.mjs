// Procedural PNG generator/mutator for T24 tests and fuzz seeds.
//
// Test-side only: uses node:zlib to *produce* candidate PNGs (the product
// decoder under test is dependency-free — the generator is how we prove
// it handles real deflate streams). No fixed binary fixtures are needed;
// every PNG is built here so tests cover the whole color-type/depth
// matrix including Adam7 interlacing and malformed variants.
import zlib from 'node:zlib';

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

export function crc32(data) {
  let c = 0xffffffff;
  for (let i = 0; i < data.length; i++) {
    c = CRC_TABLE[(c ^ data[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

export const PNG_SIG = Uint8Array.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
]);

export function chunk(type, data) {
  const out = new Uint8Array(8 + data.length + 4);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, data.length);
  for (let i = 0; i < 4; i++) out[4 + i] = type.charCodeAt(i);
  out.set(data, 8);
  const crcIn = out.subarray(4, 8 + data.length);
  dv.setUint32(8 + data.length, crc32(crcIn));
  return out;
}

export function ihdr({ width, height, bitDepth = 8, colorType = 6, interlace = 0, compression = 0, filter = 0 }) {
  const b = new Uint8Array(13);
  const dv = new DataView(b.buffer);
  dv.setUint32(0, width);
  dv.setUint32(4, height);
  b[8] = bitDepth;
  b[9] = colorType;
  b[10] = compression;
  b[11] = filter;
  b[12] = interlace;
  return b;
}

export function concatBytes(parts) {
  const n = parts.reduce((a, p) => a + p.length, 0);
  const out = new Uint8Array(n);
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

// Adam7 pass layout, shared with the decoder under test.
const ADAM7 = [
  [0, 0, 8, 8],
  [4, 0, 8, 8],
  [0, 4, 4, 8],
  [2, 0, 4, 4],
  [0, 2, 2, 4],
  [1, 0, 2, 2],
  [0, 1, 1, 2],
];
const passSize = (n, start, step) => (n <= start ? 0 : Math.ceil((n - start) / step));
const SAMPLES = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 };
const rowBytes = (w, bppBits) => Math.ceil((w * bppBits) / 8);

/**
 * Pack one pass of pixels into filtered-0 scanlines.
 * `pixels` is an array of `ph` rows; each row is `pw` samples where a
 * sample is a number (gray/palette) or array (rgb/ga/rgba) of integers
 * already at image bit depth.
 */
function packPass(pixels, pw, ph, bitDepth, colorType) {
  const spp = SAMPLES[colorType];
  const stride = rowBytes(pw, bitDepth * spp);
  const out = new Uint8Array(ph * (1 + stride));
  for (let y = 0; y < ph; y++) {
    const base = y * (1 + stride) + 1;
    if (bitDepth === 16) {
      for (let x = 0; x < pw; x++) {
        const s = pixels[y][x];
        const vals = spp === 1 ? [s] : s;
        for (let k = 0; k < spp; k++) {
          out[base + x * 2 * spp + 2 * k] = (vals[k] >> 8) & 0xff;
          out[base + x * 2 * spp + 2 * k + 1] = vals[k] & 0xff;
        }
      }
    } else if (bitDepth === 8) {
      for (let x = 0; x < pw; x++) {
        const s = pixels[y][x];
        const vals = spp === 1 ? [s] : s;
        for (let k = 0; k < spp; k++) out[base + x * spp + k] = vals[k] & 0xff;
      }
    } else {
      // sub-byte packing, MSB first
      const perByte = 8 / bitDepth;
      for (let x = 0; x < pw; x++) {
        const v = pixels[y][x];
        const byteIdx = Math.floor(x / perByte);
        const shift = 8 - bitDepth * ((x % perByte) + 1);
        out[base + byteIdx] |= (v & ((1 << bitDepth) - 1)) << shift;
      }
    }
  }
  return out;
}

/**
 * Build a complete PNG. `pixelRows[h][w]` holds samples at image bit
 * depth. Extra chunks (PLTE/tRNS/ancillary) can be supplied via
 * `preIdat`/`postIdat` raw chunk byte arrays or {type,data} objects.
 */
export function makePng({
  width,
  height,
  bitDepth = 8,
  colorType = 6,
  interlace = 0,
  pixelRows,
  palette = null,       // Uint8Array of 3*entries for colorType 3
  trns = null,          // Uint8Array raw tRNS payload
  preIdat = [],         // extra chunks before IDAT
  postIdat = [],        // extra chunks after IDAT (before IEND)
  deflateLevel = 6,
  idatSplit = 0,        // split compressed stream into N-byte IDATs
  omitIend = false,
}) {
  const spp = SAMPLES[colorType];
  let scan;
  if (interlace === 0) {
    scan = packPass(pixelRows, width, height, bitDepth, colorType);
  } else {
    const parts = [];
    for (const [x0, y0, dx, dy] of ADAM7) {
      const pw = passSize(width, x0, dx);
      const ph = passSize(height, y0, dy);
      if (pw === 0 || ph === 0) continue;
      const rows = [];
      for (let y = 0; y < ph; y++) {
        const row = [];
        for (let x = 0; x < pw; x++) row.push(pixelRows[y0 + y * dy][x0 + x * dx]);
        rows.push(row);
      }
      parts.push(packPass(rows, pw, ph, bitDepth, colorType));
    }
    scan = concatBytes(parts);
  }
  const zdata = new Uint8Array(zlib.deflateSync(Buffer.from(scan), { level: deflateLevel }));
  const chunks = [
    chunk('IHDR', ihdr({ width, height, bitDepth, colorType, interlace })),
  ];
  if (palette) chunks.push(chunk('PLTE', palette));
  if (trns) chunks.push(chunk('tRNS', trns));
  for (const c of preIdat) chunks.push(typeof c === 'string' ? c : chunk(c.type, c.data));
  if (idatSplit > 0) {
    for (let i = 0; i < zdata.length; i += idatSplit) {
      chunks.push(chunk('IDAT', zdata.subarray(i, i + idatSplit)));
    }
  } else {
    chunks.push(chunk('IDAT', zdata));
  }
  for (const c of postIdat) chunks.push(typeof c === 'string' ? c : chunk(c.type, c.data));
  if (!omitIend) chunks.push(chunk('IEND', new Uint8Array(0)));
  return concatBytes([PNG_SIG, ...chunks]);
}

/** Deterministic RGBA8 test pattern. */
export function patternRgba(w, h) {
  const px = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      px[i] = (x * 37 + y * 11) & 0xff;
      px[i + 1] = (x * 13 + y * 53 + 7) & 0xff;
      px[i + 2] = (x * 91 + y * 3 + 200) & 0xff;
      px[i + 3] = 255;
    }
  }
  return px;
}

/** Convert RGBA8 pattern to sample rows for a color type/depth. */
export function rowsFor(rgba, w, h, colorType, bitDepth, paletteSize = 0) {
  const rows = [];
  const max = (1 << bitDepth) - 1;
  for (let y = 0; y < h; y++) {
    const row = [];
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      const r = rgba[i], g = rgba[i + 1], b = rgba[i + 2], a = rgba[i + 3];
      if (colorType === 0) {
        const gray = Math.round(((r + g + b) / 3) * (max / 255));
        row.push(gray);
      } else if (colorType === 2) {
        row.push(bitDepth === 16 ? [r << 8 | r, g << 8 | g, b << 8 | b] : [r, g, b]);
      } else if (colorType === 3) {
        row.push((x + y) % paletteSize);
      } else if (colorType === 4) {
        const gray = Math.round(((r + g + b) / 3) * (max / 255));
        row.push(bitDepth === 16 ? [gray, a * 257] : [gray, a]);
      } else {
        row.push(bitDepth === 16 ? [r << 8 | r, g << 8 | g, b << 8 | b, a << 8 | a] : [r, g, b, a]);
      }
    }
    rows.push(row);
  }
  return rows;
}

/** Expected RGBA8 expansion of gray/palette samples after decode. */
export function expectedRgba(rows, w, h, colorType, bitDepth, palette = null, trns = null) {
  const out = new Uint8Array(w * h * 4);
  const scale = (v) => (bitDepth === 8 ? v : bitDepth === 16 ? v >> 8 : Math.round((v * 255) / ((1 << bitDepth) - 1)));
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      const s = rows[y][x];
      if (colorType === 0) {
        const g = scale(s);
        out[i] = out[i + 1] = out[i + 2] = g;
        const trnsVal = trns ? (trns[0] << 8) | trns[1] : -1;
        out[i + 3] = trnsVal === s ? 0 : 255;
      } else if (colorType === 2) {
        out[i] = scale(s[0]); out[i + 1] = scale(s[1]); out[i + 2] = scale(s[2]);
        let alpha = 255;
        if (trns && trns.length === 6) {
          const tv = [(trns[0] << 8) | trns[1], (trns[2] << 8) | trns[3], (trns[4] << 8) | trns[5]];
          if (s[0] === tv[0] && s[1] === tv[1] && s[2] === tv[2]) alpha = 0;
        }
        out[i + 3] = alpha;
      } else if (colorType === 3) {
        out[i] = palette[3 * s]; out[i + 1] = palette[3 * s + 1]; out[i + 2] = palette[3 * s + 2];
        out[i + 3] = trns && s < trns.length ? trns[s] : 255;
      } else if (colorType === 4) {
        const g = scale(s[0]);
        out[i] = out[i + 1] = out[i + 2] = g;
        out[i + 3] = scale(s[1]);
      } else {
        out[i] = scale(s[0]); out[i + 1] = scale(s[1]); out[i + 2] = scale(s[2]); out[i + 3] = scale(s[3]);
      }
    }
  }
  return out;
}

/** A minimal real PDF-shaped payload for source_pdf assets. */
export function fakePdfBytes(body = new TextEncoder().encode('inkflip synthetic pdf body\n')) {
  return concatBytes([Uint8Array.from([0x25, 0x50, 0x44, 0x46, 0x2d]), body]);
}
