// T24 / TEST-24 — bounded PNG decode/re-encode tests.
//
// Matrix coverage: every legal color-type/bit-depth combination, all five
// scanline filters, Adam7 interlacing, palettes, tRNS, split IDAT and
// ancillary stripping — plus the abuse surface: truncated/corrupt chunks,
// oversized dimensions, decompression bombs, polyglots and malformed
// zlib streams. All PNGs are generated procedurally in-test.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import zlib from 'node:zlib';
import { ContractError } from '../../../packages/contracts/src/index.ts';
import {
  IMPORT_LIMITS,
  crc32,
  decodePng,
  encodePngRgba,
  inflateZlib,
  sanitizePng,
  zlibEncodeStored,
} from '../../../packages/reports/validation/index.ts';
import {
  PNG_SIG,
  chunk,
  concatBytes,
  expectedRgba,
  ihdr,
  makePng,
  patternRgba,
  rowsFor,
} from './png_helpers.mjs';

const code = (fn) => {
  try {
    fn();
  } catch (e) {
    if (e instanceof ContractError) return e.code;
    throw e;
  }
  return null;
};

const W = 13;
const H = 7;

const PALETTE = (() => {
  const p = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    p[3 * i] = (i * 67) & 0xff;
    p[3 * i + 1] = (255 - i * 31) & 0xff;
    p[3 * i + 2] = (i * 11 + 40) & 0xff;
  }
  return p;
})();

// ---------------------------------------------------------------------------
// Decode matrix: color type × bit depth, non-interlaced and Adam7
// ---------------------------------------------------------------------------

const MATRIX = [
  [0, 1], [0, 2], [0, 4], [0, 8], [0, 16],
  [2, 8], [2, 16],
  [3, 1], [3, 2], [3, 4], [3, 8],
  [4, 8], [4, 16],
  [6, 8], [6, 16],
];

for (const [colorType, bitDepth] of MATRIX) {
  test(`decode color type ${colorType} depth ${bitDepth} (${W}x${H})`, () => {
    const rgba = patternRgba(W, H);
    const paletteSize = 1 << bitDepth;
    const rows = rowsFor(rgba, W, H, colorType, bitDepth, paletteSize);
    const palette = colorType === 3 ? PALETTE.subarray(0, 3 * paletteSize) : null;
    const png = makePng({
      width: W, height: H, colorType, bitDepth, pixelRows: rows, palette,
    });
    const dec = decodePng(png);
    assert.equal(dec.width, W);
    assert.equal(dec.height, H);
    const want = expectedRgba(rows, W, H, colorType, bitDepth, palette);
    assert.deepEqual(dec.rgba, want);
  });
}

for (const [colorType, bitDepth] of [[6, 8], [2, 8], [0, 8], [0, 1], [3, 4], [4, 16]]) {
  test(`decode Adam7 interlaced color type ${colorType} depth ${bitDepth}`, () => {
    const rgba = patternRgba(W, H);
    const paletteSize = 1 << bitDepth;
    const rows = rowsFor(rgba, W, H, colorType, bitDepth, paletteSize);
    const palette = colorType === 3 ? PALETTE.subarray(0, 3 * paletteSize) : null;
    const png = makePng({
      width: W, height: H, colorType, bitDepth, interlace: 1,
      pixelRows: rows, palette,
    });
    const dec = decodePng(png);
    assert.equal(dec.interlaced, true);
    const want = expectedRgba(rows, W, H, colorType, bitDepth, palette);
    assert.deepEqual(dec.rgba, want);
    // and the sanitized re-encode drops interlacing
    const clean = sanitizePng(png);
    assert.equal(clean.sourceInterlaced, true);
    const re = decodePng(clean.png);
    assert.equal(re.interlaced, false);
    assert.deepEqual(re.rgba, want);
  });
}

test('interlaced 1x1 and tiny edge cases decode', () => {
  for (const [w, h] of [[1, 1], [2, 2], [3, 5], [8, 8], [9, 9]]) {
    const rgba = patternRgba(w, h);
    const rows = rowsFor(rgba, w, h, 6, 8);
    const png = makePng({
      width: w, height: h, colorType: 6, bitDepth: 8, interlace: 1,
      pixelRows: rows,
    });
    const dec = decodePng(png);
    assert.deepEqual(dec.rgba, expectedRgba(rows, w, h, 6, 8));
  }
});

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

/** Forward-filter packed rows (filter type per row, cycled). */
function filteredPng(w, h, colorType, bitDepth, filterTypes) {
  const rgba = patternRgba(w, h);
  const paletteSize = 1 << bitDepth;
  const rows = rowsFor(rgba, w, h, colorType, bitDepth, paletteSize);
  const spp = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[colorType];
  const bppBits = bitDepth * spp;
  const stride = Math.ceil((w * bppBits) / 8);
  const bpp = Math.max(1, Math.ceil(bppBits / 8));
  const scan = new Uint8Array(h * (1 + stride));
  const pack = (x, y) => rows[y][x];
  // pack samples then apply forward filters
  const paeth = (a, b, c) => {
    const p = a + b - c;
    const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
    return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
  };
  for (let y = 0; y < h; y++) {
    const raw = new Uint8Array(stride);
    if (bitDepth >= 8) {
      for (let x = 0; x < w; x++) {
        const s = pack(x, y);
        const vals = spp === 1 ? [s] : s;
        for (let k = 0; k < spp; k++) {
          if (bitDepth === 16) {
            raw[(x * spp + k) * 2] = (vals[k] >> 8) & 0xff;
            raw[(x * spp + k) * 2 + 1] = vals[k] & 0xff;
          } else {
            raw[x * spp + k] = vals[k] & 0xff;
          }
        }
      }
    } else {
      const perByte = 8 / bitDepth;
      for (let x = 0; x < w; x++) {
        const byteIdx = Math.floor(x / perByte);
        const shift = 8 - bitDepth * ((x % perByte) + 1);
        raw[byteIdx] |= (rows[y][x] & ((1 << bitDepth) - 1)) << shift;
      }
    }
    const ft = filterTypes[y % filterTypes.length];
    const out = y * (1 + stride);
    scan[out] = ft;
    const prev = y > 0 ? scan.subarray((y - 1) * (1 + stride) + 1, y * (1 + stride)) : new Uint8Array(stride);
    // NOTE: filters apply against the *unfiltered* previous row, so keep
    // raw rows separate.
    filteredPng._raw = filteredPng._raw || [];
    filteredPng._raw[y] = raw;
    const prevRaw = y > 0 ? filteredPng._raw[y - 1] : new Uint8Array(stride);
    for (let i = 0; i < stride; i++) {
      const a = i >= bpp ? raw[i - bpp] : 0;
      const b = prevRaw[i];
      const c = i >= bpp ? prevRaw[i - bpp] : 0;
      let v;
      if (ft === 0) v = raw[i];
      else if (ft === 1) v = raw[i] - a;
      else if (ft === 2) v = raw[i] - b;
      else if (ft === 3) v = raw[i] - ((a + b) >> 1);
      else v = raw[i] - paeth(a, b, c);
      scan[out + 1 + i] = v & 0xff;
    }
  }
  const palette = colorType === 3 ? PALETTE.subarray(0, 3 * paletteSize) : null;
  const zdata = new Uint8Array(zlib.deflateSync(Buffer.from(scan)));
  const chunks = [chunk('IHDR', ihdr({ width: w, height: h, bitDepth, colorType }))];
  if (palette) chunks.push(chunk('PLTE', palette));
  chunks.push(chunk('IDAT', zdata), chunk('IEND', new Uint8Array(0)));
  filteredPng._raw = null;
  return { png: concatBytes([PNG_SIG, ...chunks]), rows };
}

test('all five scanline filters decode correctly', () => {
  for (const ft of [0, 1, 2, 3, 4]) {
    const { png, rows } = filteredPng(W, H, 6, 8, [ft]);
    const dec = decodePng(png);
    assert.deepEqual(dec.rgba, expectedRgba(rows, W, H, 6, 8), `filter ${ft}`);
  }
  const { png, rows } = filteredPng(W, H, 2, 8, [0, 1, 2, 3, 4, 2, 1]);
  const dec = decodePng(png);
  assert.deepEqual(dec.rgba, expectedRgba(rows, W, H, 2, 8), 'mixed filters');
});

// ---------------------------------------------------------------------------
// Re-encode: sanitize produces clean, deterministic, decode-equal output
// ---------------------------------------------------------------------------

test('sanitize re-encodes to 8-bit RGBA, no ancillary chunks, deterministic', () => {
  const rgba = patternRgba(W, H);
  const rows = rowsFor(rgba, W, H, 0, 8);
  const dirty = makePng({
    width: W, height: H, colorType: 0, bitDepth: 8, pixelRows: rows,
    preIdat: [
      { type: 'tEXt', data: new TextEncoder().encode('k<script>alert(1)</script>') },
      { type: 'pHYs', data: new Uint8Array(9) },
      { type: 'acTL', data: new Uint8Array(8) }, // APNG animation control
      { type: 'fcTL', data: new Uint8Array(26) },
    ],
    postIdat: [{ type: 'tIME', data: new Uint8Array(7) }],
    idatSplit: 5,
  });
  const clean = sanitizePng(dirty);
  const text = Buffer.from(clean.png).toString('latin1');
  for (const banned of ['tEXt', 'pHYs', 'acTL', 'fcTL', 'tIME', 'script']) {
    assert.ok(!text.includes(banned), `sanitized output contains ${banned}`);
  }
  const re = decodePng(clean.png);
  assert.deepEqual(re.rgba, expectedRgba(rows, W, H, 0, 8));
  const again = sanitizePng(dirty);
  assert.deepEqual(clean.png, again.png, 're-encode must be deterministic');
});

test('re-encoded PNG is a real zlib stream verifiable independently', () => {
  const rgba = patternRgba(9, 5);
  const png = encodePngRgba(9, 5, rgba);
  // walk chunks manually, inflate IDAT with the platform zlib
  let pos = 8;
  const idat = [];
  while (pos < png.length) {
    const dv = new DataView(png.buffer, png.byteOffset, png.byteLength);
    const len = dv.getUint32(pos);
    const type = Buffer.from(png.subarray(pos + 4, pos + 8)).toString('latin1');
    if (type === 'IDAT') idat.push(png.subarray(pos + 8, pos + 8 + len));
    pos += 12 + len;
  }
  const raw = zlib.inflateSync(Buffer.concat(idat.map((u) => Buffer.from(u))));
  const stride = 1 + 9 * 4;
  assert.equal(raw.length, 5 * stride);
  for (let y = 0; y < 5; y++) {
    assert.equal(raw[y * stride], 0);
    assert.deepEqual(
      new Uint8Array(raw.buffer, raw.byteOffset + y * stride + 1, 36),
      rgba.subarray(y * 36, y * 36 + 36),
    );
  }
});

test('zlib stored encoder round-trips through platform zlib', () => {
  const data = new Uint8Array(150000);
  for (let i = 0; i < data.length; i++) data[i] = (i * 31 + (i >> 4)) & 0xff;
  const z = zlibEncodeStored(data);
  assert.deepEqual(zlib.inflateSync(Buffer.from(z)), Buffer.from(data));
});

test('inflateZlib matches platform zlib at all compression levels', () => {
  const data = new Uint8Array(300000);
  for (let i = 0; i < data.length; i++) data[i] = (i * 17 + (i >> 5) * 3) & 0xff;
  for (const level of [0, 1, 4, 6, 9]) {
    const c = zlib.deflateSync(Buffer.from(data), { level });
    const back = inflateZlib(new Uint8Array(c.buffer, c.byteOffset, c.length), data.length);
    assert.deepEqual(back, data, `level ${level}`);
  }
});

test('crc32 matches the known PNG check value', () => {
  // CRC of "IEND" (empty data) is the well-known 0xAE426082
  assert.equal(crc32(new TextEncoder().encode('IEND')), 0xae426082);
});

// ---------------------------------------------------------------------------
// Dimension limits — before any raster-sized allocation
// ---------------------------------------------------------------------------

test('pixel and edge limits fail at IHDR before inflate or allocation', () => {
  const rows = rowsFor(patternRgba(4, 4), 4, 4, 6, 8);
  const tinyIdat = makePng({ width: 4, height: 4, colorType: 6, bitDepth: 8, pixelRows: rows });
  const idatBody = tinyIdat.subarray(8 + 25, tinyIdat.length - 12); // reuse valid IDAT
  // dims over the pixel cap: 2001*2000 = 4,002,000 > 4,000,000
  const bigPixels = concatBytes([
    PNG_SIG,
    chunk('IHDR', ihdr({ width: 2001, height: 2000, colorType: 6, bitDepth: 8 })),
    idatBody,
    chunk('IEND', new Uint8Array(0)),
  ]);
  assert.equal(code(() => decodePng(bigPixels)), 'SIZE');
  // edge cap: 8193 x 1 = only 8193 pixels but the edge is over 8192
  const bigEdge = concatBytes([
    PNG_SIG,
    chunk('IHDR', ihdr({ width: IMPORT_LIMITS.maxPngEdge + 1, height: 1, colorType: 6, bitDepth: 8 })),
    idatBody,
    chunk('IEND', new Uint8Array(0)),
  ]);
  assert.equal(code(() => decodePng(bigEdge)), 'SIZE');
  const tall = concatBytes([
    PNG_SIG,
    chunk('IHDR', ihdr({ width: 1, height: IMPORT_LIMITS.maxPngEdge + 1, colorType: 6, bitDepth: 8 })),
    idatBody,
    chunk('IEND', new Uint8Array(0)),
  ]);
  assert.equal(code(() => decodePng(tall)), 'SIZE');
  // a 4MP image at the cap edge must still fail if IDAT is a bomb — and
  // we never allocate pixels for it first
  const claimed = concatBytes([
    PNG_SIG,
    chunk('IHDR', ihdr({ width: 2000, height: 2000, colorType: 6, bitDepth: 8 })),
    chunk('IDAT', new Uint8Array(zlib.deflateSync(Buffer.alloc(40 * 1024 * 1024)))),
    chunk('IEND', new Uint8Array(0)),
  ]);
  assert.equal(code(() => decodePng(claimed)), 'PNG'); // expansion > cap
});

test('decompression bomb: IDAT expanding past raster size fails PNG', () => {
  const rows = rowsFor(patternRgba(8, 8), 8, 8, 6, 8);
  const valid = makePng({ width: 8, height: 8, colorType: 6, bitDepth: 8, pixelRows: rows });
  // rebuild with an IDAT that inflates well past 8*(1+32)=264 bytes
  const bomb = concatBytes([
    PNG_SIG,
    chunk('IHDR', ihdr({ width: 8, height: 8, colorType: 6, bitDepth: 8 })),
    chunk('IDAT', new Uint8Array(zlib.deflateSync(Buffer.alloc(1024 * 1024)))),
    chunk('IEND', new Uint8Array(0)),
  ]);
  assert.equal(code(() => decodePng(bomb)), 'PNG');
  // undersized (truncated stream semantics) also fails
  const short = concatBytes([
    PNG_SIG,
    chunk('IHDR', ihdr({ width: 8, height: 8, colorType: 6, bitDepth: 8 })),
    chunk('IDAT', new Uint8Array(zlib.deflateSync(Buffer.alloc(20)))),
    chunk('IEND', new Uint8Array(0)),
  ]);
  assert.equal(code(() => decodePng(short)), 'PNG');
  assert.ok(valid.length > 0);
});

// ---------------------------------------------------------------------------
// Structural corruption
// ---------------------------------------------------------------------------

const smallPng = () =>
  makePng({
    width: 4, height: 4, colorType: 6, bitDepth: 8,
    pixelRows: rowsFor(patternRgba(4, 4), 4, 4, 6, 8),
  });

test('bad signature, non-PNG magic and disguised formats fail', () => {
  for (const mutant of [
    Uint8Array.from([0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 1, 2, 3, 4, 5, 6, 7, 8]), // GIF
    Uint8Array.from([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), // JPEG
    Uint8Array.from([0x00, 0x00, 0x01, 0x00, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), // ICO
    new Uint8Array(0),
    new Uint8Array(4),
  ]) {
    assert.equal(code(() => decodePng(mutant)), 'PNG');
  }
  const bad = smallPng();
  bad[0] = 0x00;
  assert.equal(code(() => decodePng(bad)), 'PNG');
});

test('CRC mismatches in any chunk fail', () => {
  const png = smallPng();
  // corrupt the IHDR CRC (last 4 bytes of the IHDR chunk)
  const a = png.slice();
  a[8 + 12 + 12] ^= 0xff;
  assert.equal(code(() => decodePng(a)), 'PNG');
  // corrupt the IEND CRC (final 4 bytes)
  const b = png.slice();
  b[b.length - 1] ^= 0xff;
  assert.equal(code(() => decodePng(b)), 'PNG');
});

test('truncation at every stage fails cleanly', () => {
  const png = smallPng();
  for (const cut of [5, 8, 12, 20, 30, 33, png.length - 13, png.length - 12, png.length - 5, png.length - 1]) {
    assert.ok(cut < png.length, `cut=${cut}`);
    assert.equal(code(() => decodePng(png.subarray(0, cut))), 'PNG', `cut=${cut}`);
  }
  // missing IEND entirely
  assert.equal(code(() => decodePng(png.subarray(0, png.length - 12))), 'PNG');
});

test('trailing garbage and PNG+archive polyglots fail', () => {
  const png = smallPng();
  const plusZip = concatBytes([
    png,
    Uint8Array.from([0x50, 0x4b, 0x03, 0x04, 1, 2, 3, 4]),
  ]);
  assert.equal(code(() => decodePng(plusZip)), 'PNG');
  const plusJunk = concatBytes([png, new Uint8Array(16)]);
  assert.equal(code(() => decodePng(plusJunk)), 'PNG');
  const plusHtml = concatBytes([png, new TextEncoder().encode('<html></html>')]);
  assert.equal(code(() => decodePng(plusHtml)), 'PNG');
});

test('unknown critical chunks fail; ancillary chunks are ignored', () => {
  const rows = rowsFor(patternRgba(4, 4), 4, 4, 6, 8);
  const crit = makePng({
    width: 4, height: 4, colorType: 6, bitDepth: 8, pixelRows: rows,
    // uppercase first letter marks a critical chunk; unknown → reject
    preIdat: [{ type: 'XTRA', data: new Uint8Array(4) }],
  });
  assert.equal(code(() => decodePng(crit)), 'PNG');
  // lowercase first letter is ancillary even when unknown — skipped
  const priv = makePng({
    width: 4, height: 4, colorType: 6, bitDepth: 8, pixelRows: rows,
    preIdat: [{ type: 'vpAg', data: new Uint8Array(4) }],
  });
  assert.equal(code(() => decodePng(priv)), null);
  const anc = makePng({
    width: 4, height: 4, colorType: 6, bitDepth: 8, pixelRows: rows,
    preIdat: [
      { type: 'tEXt', data: new TextEncoder().encode('author\u0000someone') },
      { type: 'zTXt', data: new Uint8Array(zlib.deflateSync(Buffer.from('junk'))) },
      { type: 'iTXt', data: new TextEncoder().encode('k\u0000\u0000\u0000\u0000evil<iTXt>') },
      { type: 'acTL', data: new Uint8Array(8) },
      { type: 'fcTL', data: new Uint8Array(26) },
    ],
    postIdat: [{ type: 'fdAT', data: new Uint8Array(12) }],
  });
  const dec = decodePng(anc);
  assert.equal(dec.width, 4);
  // APNG ancillary frames never reach the sanitized output
  const clean = sanitizePng(anc);
  const text = Buffer.from(clean.png).toString('latin1');
  for (const banned of ['tEXt', 'zTXt', 'iTXt', 'acTL', 'fcTL', 'fdAT']) {
    assert.ok(!text.includes(banned));
  }
});

test('malformed IHDR fields fail', () => {
  const rows = rowsFor(patternRgba(4, 4), 4, 4, 6, 8);
  const variants = [
    { width: 0 }, { height: 0 },
    { colorType: 1 }, { colorType: 5 },
    { colorType: 3, bitDepth: 16 }, // illegal depth for palette
    { colorType: 2, bitDepth: 4 },
    { compression: 1 }, { filter: 2 }, { interlace: 3 },
  ];
  for (const v of variants) {
    const png = concatBytes([
      PNG_SIG,
      chunk('IHDR', ihdr({ width: 4, height: 4, colorType: 6, bitDepth: 8, ...v })),
      chunk('IEND', new Uint8Array(0)),
    ]);
    assert.equal(code(() => decodePng(png)), 'PNG', JSON.stringify(v));
  }
  assert.ok(rows.length === 4);
});

test('chunk length exceeding input fails before slicing', () => {
  const dv = new DataView(new ArrayBuffer(4));
  dv.setUint32(0, 0xfffffff0);
  const fake = concatBytes([
    PNG_SIG,
    Uint8Array.from([0xff, 0xff, 0xff, 0xf0, 0x49, 0x44, 0x41, 0x54]),
    new Uint8Array(8),
  ]);
  assert.equal(code(() => decodePng(fake)), 'PNG');
});

test('non-letter chunk types fail', () => {
  const fake = concatBytes([
    PNG_SIG,
    chunk('IHDR', ihdr({ width: 4, height: 4, colorType: 6, bitDepth: 8 })),
    (() => {
      const c = chunk('IEND', new Uint8Array(0));
      c[4] = 0x30; // '0' — not a letter
      // fix CRC so only the type check can fire
      const dv = new DataView(c.buffer);
      const crcIn = c.subarray(4, 8);
      dv.setUint32(8, crc32(crcIn));
      return c;
    })(),
  ]);
  assert.equal(code(() => decodePng(fake)), 'PNG');
});

test('malformed zlib IDAT payloads fail PNG', () => {
  const ihdrBytes = ihdr({ width: 4, height: 4, colorType: 6, bitDepth: 8 });
  const mk = (idatData) =>
    concatBytes([
      PNG_SIG,
      chunk('IHDR', ihdrBytes),
      chunk('IDAT', idatData),
      chunk('IEND', new Uint8Array(0)),
    ]);
  assert.equal(code(() => decodePng(mk(new Uint8Array(0)))), 'PNG'); // empty
  assert.equal(code(() => decodePng(mk(new TextEncoder().encode('not zlib at all')))), 'PNG');
  // gzip instead of zlib wrapper
  assert.equal(
    code(() => decodePng(mk(new Uint8Array(zlib.gzipSync(Buffer.alloc(100)))))),
    'PNG',
  );
  // raw deflate without zlib wrapper
  assert.equal(
    code(() => decodePng(mk(new Uint8Array(zlib.deflateRawSync(Buffer.alloc(100)))))),
    'PNG',
  );
  // valid zlib, valid data, but trailing bytes inside IDAT
  const z = zlib.deflateSync(Buffer.alloc(52));
  const trailed = concatBytes([new Uint8Array(z), new Uint8Array([1, 2, 3])]);
  assert.equal(code(() => decodePng(mk(trailed))), 'PNG');
  // corrupted adler
  const bad = new Uint8Array(zlib.deflateSync(Buffer.alloc(52)));
  bad[bad.length - 1] ^= 0xff;
  assert.equal(code(() => decodePng(mk(bad))), 'PNG');
});

test('invalid scanline filter byte fails PNG', () => {
  const rows = rowsFor(patternRgba(4, 4), 4, 4, 6, 8);
  const spp = 4;
  const stride = 4 * spp;
  const scan = new Uint8Array(4 * (1 + stride));
  for (let y = 0; y < 4; y++) {
    scan[y * (1 + stride)] = 9; // filter 9 does not exist
    for (let x = 0; x < 4; x++) {
      const s = rows[y][x];
      scan.set(s.map((v) => v & 0xff), y * (1 + stride) + 1 + x * spp);
    }
  }
  const png = concatBytes([
    PNG_SIG,
    chunk('IHDR', ihdr({ width: 4, height: 4, colorType: 6, bitDepth: 8 })),
    chunk('IDAT', new Uint8Array(zlib.deflateSync(Buffer.from(scan)))),
    chunk('IEND', new Uint8Array(0)),
  ]);
  assert.equal(code(() => decodePng(png)), 'PNG');
});

test('palette structural rules fail when violated', () => {
  const rows = rowsFor(patternRgba(4, 4), 4, 4, 3, 2, 4);
  // palette image with no PLTE
  const noPlte = makePng({ width: 4, height: 4, colorType: 3, bitDepth: 2, pixelRows: rows });
  assert.equal(code(() => decodePng(noPlte)), 'PNG');
  // PLTE length not a multiple of 3
  const badPlte = makePng({
    width: 4, height: 4, colorType: 3, bitDepth: 2, pixelRows: rows,
    palette: new Uint8Array(4),
  });
  assert.equal(code(() => decodePng(badPlte)), 'PNG');
  // PLTE larger than depth range allows
  const bigPlte = makePng({
    width: 4, height: 4, colorType: 3, bitDepth: 2, pixelRows: rows,
    palette: new Uint8Array(3 * 5),
  });
  assert.equal(code(() => decodePng(bigPlte)), 'PNG');
  // palette index out of range: all indices 3 but only 1 palette entry
  const oob = makePng({
    width: 4, height: 4, colorType: 3, bitDepth: 2, pixelRows: rows,
    palette: new Uint8Array(3),
  });
  assert.equal(code(() => decodePng(oob)), 'PNG');
});

test('tRNS works for palette and gray; malformed tRNS fails', () => {
  const rows = rowsFor(patternRgba(4, 4), 4, 4, 3, 2, 4);
  const trns = Uint8Array.from([0, 255, 128]);
  const png = makePng({
    width: 4, height: 4, colorType: 3, bitDepth: 2, pixelRows: rows,
    palette: PALETTE.subarray(0, 12), trns,
  });
  const dec = decodePng(png);
  assert.deepEqual(dec.rgba, expectedRgba(rows, 4, 4, 3, 2, PALETTE.subarray(0, 12), trns));
  // wrong tRNS length for gray (must be 2)
  const gRows = rowsFor(patternRgba(4, 4), 4, 4, 0, 8);
  const bad = makePng({
    width: 4, height: 4, colorType: 0, bitDepth: 8, pixelRows: gRows,
    trns: new Uint8Array(3),
  });
  assert.equal(code(() => decodePng(bad)), 'PNG');
});

test('first chunk must be IHDR and IEND must be empty', () => {
  const rows = rowsFor(patternRgba(4, 4), 4, 4, 6, 8);
  const swapped = makePng({
    width: 4, height: 4, colorType: 6, bitDepth: 8, pixelRows: rows,
    preIdat: [],
  });
  // hand-build: gAMA first
  const fake = concatBytes([
    PNG_SIG,
    chunk('gAMA', new Uint8Array(4)),
    chunk('IHDR', ihdr({ width: 4, height: 4, colorType: 6, bitDepth: 8 })),
    chunk('IEND', new Uint8Array(0)),
  ]);
  assert.equal(code(() => decodePng(fake)), 'PNG');
  const badIend = concatBytes([swapped.subarray(0, swapped.length - 12), chunk('IEND', new Uint8Array(1))]);
  assert.equal(code(() => decodePng(badIend)), 'PNG');
});
