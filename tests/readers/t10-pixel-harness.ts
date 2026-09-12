/**
 * T10 light browser harness — shared stub-engine layer.
 *
 * This module is TEST-ONLY. It provides:
 *   - PIXEL_ENTRY_SNIPPET: in-page code appended to the spec's bundle,
 *     defining `globalThis.__px` (stub engine, synthetic 49x80 raster
 *     fixture, decode helpers). It never starts pdf.js or Tesseract.
 *   - runPixelCase / pixelAt / assertion helpers used by the light
 *     describes in tesseract.spec.ts.
 *
 * The stub engine satisfies the engine module port and records every
 * input the production reader hands it — worker languages/options
 * (including the abort signal), image input class and bytes, and
 * recognize/terminate counts — so tests assert adapter semantics
 * without any real OCR. Nothing here weakens production code: the
 * stub is injected through the existing `engine` config port.
 */
import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';

// ---------------------------------------------------------------- fixture --
export const FIXTURE_W = 49;
export const FIXTURE_H = 80;
export const BLACK = [0, 0, 0, 255] as const;
export const RED = [255, 0, 0, 255] as const;

export interface DecodedPng {
  width: number;
  height: number;
  data: number[]; // RGBA
}

export function pixelAt(
  img: DecodedPng,
  x: number,
  y: number,
): readonly number[] {
  const i = (y * img.width + x) * 4;
  return img.data.slice(i, i + 4);
}

// ------------------------------------------------------- in-page snippet ---
/**
 * Appended verbatim to the spec's entrySource (same module scope: it can
 * reference `adapter`, `geom`, `contracts`, `state`, `tryV`, `hex`).
 * Defines `globalThis.__px`.
 */
export const PIXEL_ENTRY_SNIPPET = /* js */ `
const PX_W = ${FIXTURE_W};
const PX_H = ${FIXTURE_H};
const PX_BLACK = [0, 0, 0, 255];
const PX_RED = [255, 0, 0, 255];

function pxFixtureBytes() {
  const d = new Uint8ClampedArray(PX_W * PX_H * 4);
  for (let y = 0; y < PX_H; y++) {
    for (let x = 0; x < PX_W; x++) {
      d.set(x < 42 ? PX_BLACK : PX_RED, (y * PX_W + x) * 4);
    }
  }
  return d;
}
function pxImageData() {
  return new ImageData(pxFixtureBytes(), PX_W, PX_H);
}
function pxCanvas() {
  const c = document.createElement('canvas');
  c.width = PX_W;
  c.height = PX_H;
  c.getContext('2d').putImageData(pxImageData(), 0, 0);
  return c;
}
function pxBuilt() {
  return geom.buildPage({
    index: 0,
    viewBox: [0, 0, PX_W, PX_H],
    userUnit: 1,
    rotation: 0,
    boxSource: 'synthetic 49x80 fixture; UserUnit 1; /Rotate 0',
  });
}
function pxModel() {
  const bytes = new Uint8Array(PX_W * PX_H * 4);
  for (let i = 0; i < bytes.length; i++) bytes[i] = i % 251;
  return {
    id: 'stub-eng',
    version: 'stub',
    lang: 'eng',
    byteLength: bytes.byteLength,
    sha256: hex(contracts.sha256(bytes)),
    sourcePath: '/models/stub-eng/stub/eng.traineddata',
    license: 'Apache-2.0',
    cachePath: 'inkflip/stub',
    _bytes: bytes,
  };
}
function pxPaths() {
  return {
    workerPath: '/stub/worker.js',
    corePath: '/stub/core/',
    langPath: '/stub/models/',
    cachePath: 'inkflip/stub',
  };
}

async function pxDecodePng(bytes) {
  const bmp = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
  const oc = new OffscreenCanvas(bmp.width, bmp.height);
  const cx = oc.getContext('2d');
  cx.drawImage(bmp, 0, 0);
  const d = cx.getImageData(0, 0, bmp.width, bmp.height);
  return { width: bmp.width, height: bmp.height, data: Array.from(d.data) };
}

// A minimal fake IDB whose open succeeds but whose object-store puts
// always fail — exercises the "cache write failed" honesty path.
function pxIdbReq(result, err) {
  const req = { result, error: err || null,
    onsuccess: null, onerror: null, onupgradeneeded: null };
  setTimeout(() => {
    if (req.onupgradeneeded) req.onupgradeneeded();
    if (err) { if (req.onerror) req.onerror(); }
    else if (req.onsuccess) req.onsuccess();
  }, 0);
  return req;
}
function pxWriteFailIdb() {
  const fakeDb = {
    objectStoreNames: { contains: () => true },
    createObjectStore: () => ({}),
    close: () => {},
    transaction: () => ({
      objectStore: () => ({
        get: () => pxIdbReq(undefined),
        put: () => pxIdbReq(undefined, new Error('write denied')),
        delete: () => pxIdbReq(undefined),
      }),
    }),
  };
  return { open: () => pxIdbReq(fakeDb) };
}

function pxStubResult(input) {
  const s = input.stubResult || {};
  return {
    text: Object.prototype.hasOwnProperty.call(s, 'text') ? s.text : null,
    blocks: Object.prototype.hasOwnProperty.call(s, 'blocks') ? s.blocks : [],
  };
}

/**
 * Stub engine factory. kind:
 *   'stub'          - init ok, recognize returns input.stubResult
 *   'hangInit'      - createWorker never settles
 *   'lateInit'      - createWorker resolves after input.lateInitMs
 *   'hangRecognize' - init ok, recognize never settles
 *   'flakyHang'     - createWorker #1 rejects, #2 never settles
 * Every call records languages, options (incl. signal), concurrency
 * depth, abort reason, image input class/bytes, call counts.
 */
function pxEngine(kind, captured, input) {
  let localCalls = 0;
  return {
    createWorker(langs, oem, options) {
      localCalls += 1;
      captured.createWorkerCount = (captured.createWorkerCount || 0) + 1;
      // langs entries are {code, data} objects whose data field is the
      // verified traineddata byte payload — record its class, length
      // and sha256 so tests can prove the engine received THE
      // adapter-verified bytes, not a cache-slot indirection.
      captured.workerLangs = langs.map((l) => typeof l === 'string'
        ? { code: l, dataClass: 'string', data: l }
        : {
            code: l.code,
            dataClass: l.data instanceof Uint8Array
              ? 'Uint8Array'
              : typeof l.data,
            dataBytes: l.data instanceof Uint8Array
              ? l.data.byteLength
              : null,
            dataSha256: l.data instanceof Uint8Array
              ? hex(contracts.sha256(l.data))
              : null,
          });
      captured.workerOptions = {
        workerPath: options.workerPath,
        corePath: options.corePath,
        langPath: options.langPath,
        cachePath: options.cachePath,
        cacheMethod: options.cacheMethod,
        gzip: options.gzip,
        workerBlobURL: options.workerBlobURL,
        oem,
        logger: typeof options.logger,
        errorHandler: typeof options.errorHandler,
        signal: options.signal instanceof AbortSignal
          ? 'AbortSignal'
          : String(options.signal),
      };
      if (options.signal instanceof AbortSignal) {
        captured.signalAbortedAtCreate = options.signal.aborted;
        options.signal.addEventListener('abort', () => {
          const r = options.signal.reason;
          captured.abortReason =
            r instanceof adapter.OcrError ? r.reason : String(r);
        });
      }
      captured.pendingInits = (captured.pendingInits || 0) + 1;
      captured.maxConcurrentInits = Math.max(
        captured.maxConcurrentInits || 0, captured.pendingInits);
      const release = () => { captured.pendingInits -= 1; };
      if (kind === 'hangInit') return new Promise(() => {});
      if (kind === 'flakyHang' && localCalls === 1) {
        release();
        return Promise.reject(new Error('flaky init failure'));
      }
      if (kind === 'flakyHang') return new Promise(() => {});
      const delay = kind === 'lateInit' ? (input.lateInitMs ?? 200) : 0;
      return new Promise((resolve) => setTimeout(() => {
        release();
        resolve({
          async recognize(image) {
            captured.recognizeCount = (captured.recognizeCount || 0) + 1;
            captured.imageClass = image instanceof Uint8Array
              ? 'Uint8Array'
              : (image && image.constructor && image.constructor.name) ||
                String(image);
            captured.imageBytes = image instanceof Uint8Array
              ? Array.from(image)
              : null;
            if (kind === 'hangRecognize') return new Promise(() => {});
            const s = pxStubResult(input);
            return {
              jobId: 'px-job',
              data: {
                text: s.text,
                blocks: s.blocks,
                confidence: null,
                psm: '6',
                oem: 'LSTM_ONLY',
                version: 'stub',
              },
            };
          },
          async terminate() {
            captured.terminateCount = (captured.terminateCount || 0) + 1;
          },
        });
      }, delay));
    },
    OEM: { LSTM_ONLY: 0, TESSERACT_ONLY: 1, DEFAULT: 2 },
    PSM: adapter.OCR_PSM,
  };
}

/**
 * One end-to-end stub case: construct -> open -> plan -> extract ->
 * describe -> decode produced PNG -> close. Every stage is wrapped in
 * tryV so failures are data, not exceptions.
 */
async function pxRunCase(input, unmapPt) {
  const out = {
    input, captured: {}, construct: null, open: null, plan: null,
    checks: null, run: null, output: null, manifest: null,
    decoded: null, imageClass: null, unmapped: null, built: null,
    chunks: null, modelStates: [], progress: [], errors: [],
    elapsedMs: null, docSha: null, model: null,
  };
  const t0 = performance.now();
  const captured = out.captured;
  const model = pxModel();
  out.model = { sha256: model.sha256, byteLength: model.byteLength };
  const renderId = input.renderReaderId ?? 'synthetic-fixture';
  const raster = {
    rasterId: 'px_' + (input.branch || 'canvas') + '_' + (++state.n),
    renderReaderId: input.rasterRenderReaderId ?? renderId,
    scalePxPerPt: 1,
    widthPx: PX_W,
    heightPx: PX_H,
    image: input.branch === 'imagedata' ? pxImageData() : pxCanvas(),
    built: pxBuilt(),
  };
  out.built = raster.built;
  const hooks = {
    fetchImpl: () => Promise.resolve(new Response(model._bytes.slice())),
    online: () => true,
    onProgress: (e) => out.progress.push(
      { status: e.status, progress: e.progress }),
    onModelState: (s) => out.modelStates.push(s),
    onError: (d) => out.errors.push(d),
  };
  if (input.idbFactory === 'none') hooks.idbFactory = null;
  if (input.idbFactory === 'writeFail') hooks.idbFactory = pxWriteFailIdb();
  let reader = null;
  try {
    reader = new adapter.TesseractOcrReader({
      engine: pxEngine(input.engine ?? 'stub', captured, input),
      engineVersion: '0.0.0-stub',
      coreBuild: 'stub',
      model,
      paths: pxPaths(),
      assetHashes: [],
      profile: 'desktop',
      runKey: 't10-pixels',
      renderReaderId: renderId,
      rasterSource: input.stallRaster
        ? () => new Promise(() => {})
        : () => Promise.resolve(raster),
      ...(input.budget ? { budget: input.budget } : {}),
      hooks,
    });
    out.construct = { ok: true };
  } catch (e) {
    out.construct = {
      ok: false,
      name: e && e.name,
      message: e && e.message,
      reason: e instanceof adapter.OcrError ? e.reason : null,
    };
    out.elapsedMs = performance.now() - t0;
    return out;
  }
  try {
    const openOpts = { documentSha256: hex(contracts.sha256(
      new Uint8Array([PX_W, PX_H, 4, 255]))), generation: 1 };
    if (input.openCancelAfterMs != null) {
      const ctl = new AbortController();
      setTimeout(() => ctl.abort(), input.openCancelAfterMs);
      openOpts.cancellation = ctl.signal;
    }
    out.open = await tryV(() => reader.open(openOpts));
    if (!out.open.ok) return out;
    const handle = out.open.value;
    const sel = { pageIndex: 0, purpose: input.region ? 'region' : 'page' };
    if (input.region) sel.region = input.region;
    out.plan = await tryV(() => reader.plan(handle, [sel]));
    if (!out.plan.ok) return out;
    out.checks = out.plan.value;
    const check = out.checks[0];
    // Optional engine swap after open — exercises extract-time init
    // paths (hang/late) while open() succeeded with the plain stub.
    if (input.engineAfterOpen) {
      reader.cfg = Object.assign({}, reader.cfg, {
        engine: pxEngine(input.engineAfterOpen, captured, input),
      });
      await reader.destroyWorker();
    }
    const chunks = [];
    out.chunks = chunks;
    let extractCtl = null;
    if (input.cancelAfterMs != null || input.cancelBeforeExtract) {
      extractCtl = new AbortController();
      if (input.cancelBeforeExtract) extractCtl.abort();
      else setTimeout(() => extractCtl.abort(), input.cancelAfterMs);
    }
    out.run = await tryV(() => reader.extract(
      handle, check,
      (_checkId, occs) => chunks.push(occs),
      extractCtl ? extractCtl.signal : undefined));
    if (!out.run.ok) return out;
    out.output = out.run.value;
    out.manifest = await tryV(() => reader.describe('page'));
    if (input.settleMs) {
      await new Promise((r) => setTimeout(r, input.settleMs));
    }
    if (captured.imageBytes) {
      const u8 = new Uint8Array(captured.imageBytes);
      out.imageClass = captured.imageClass;
      out.decoded = await pxDecodePng(u8);
      if (unmapPt && out.output.crop) {
        const c = out.output.crop;
        const inv = geom.ocrToCanonical(
          raster.built, raster.scalePxPerPt,
          [c.cropX, c.cropY], [c.resizeK, c.resizeK]);
        out.unmapped = geom.apply(inv, unmapPt);
      }
    }
    return out;
  } finally {
    out.elapsedMs = performance.now() - t0;
    try { await reader.close(); } catch { /* cleanup */ }
  }
}

globalThis.__px = {
  runCase: pxRunCase,
  engine: pxEngine,
  model: pxModel,
  paths: pxPaths,
  writeFailIdb: pxWriteFailIdb,
};

// ---- lifecycle/provenance review seam (independent-probe port) ----
// __rv.make(extra) builds a reader wired to an instrumented stub
// engine and recording hooks; tests drive real open/extract/close
// transitions against it. Mirrors the independent reviewer's probe
// harness so those reproduced cases run in the registered file.
const rvDelay = (ms) => new Promise((r) => setTimeout(r, ms));
const rvWrap = async (promise) => {
  try {
    return { ok: true, value: await promise };
  } catch (e) {
    return { ok: false, reason: e && e.reason, message: String(e && e.message || e) };
  }
};
globalThis.__rv = {
  delay: rvDelay,
  wrap: rvWrap,
  make(extra) {
    const x = extra || {};
    const model = pxModel();
    const events = { states: [], progress: [], errors: [], workers: [] };
    const canvas = new OffscreenCanvas(32, 32);
    canvas.getContext('2d').fillRect(0, 0, 32, 32);
    const raster = {
      rasterId: 'review_raster',
      renderReaderId: 'review_renderer',
      scalePxPerPt: 1,
      widthPx: 32,
      heightPx: 32,
      image: canvas,
      built: geom.buildPage({
        index: 0, viewBox: [0, 0, 32, 32], userUnit: 1,
        rotation: 0, boxSource: 'review',
      }),
    };
    const engine = {
      createWorker: async (_langs, _oem, opts) => {
        const worker = {
          opts,
          terminated: false,
          async terminate() { worker.terminated = true; },
          recognize: async () => ({
            jobId: 'stub',
            data: {
              text: '', blocks: [], confidence: null,
              psm: '6', oem: 'LSTM_ONLY', version: 'stub',
            },
          }),
        };
        events.workers.push(worker);
        return worker;
      },
      OEM: { LSTM_ONLY: 1 },
      PSM: {},
    };
    const cfg = {
      engine,
      engineVersion: 'stub',
      model,
      paths: pxPaths(),
      assetHashes: [],
      renderReaderId: 'review_renderer',
      profile: 'desktop',
      runKey: 'review',
      rasterSource: async () => raster,
      budget: { openTimeoutMs: 600, checkTimeoutMs: 600, maxRetries: 0 },
      ...x,
      hooks: {
        fetchImpl: async () => new Response(model._bytes.slice()),
        onModelState: (s) => events.states.push(s),
        onProgress: (e) => events.progress.push(e),
        onError: (e) => events.errors.push(e),
        ...(x.hooks || {}),
      },
    };
    return {
      reader: new adapter.TesseractOcrReader(cfg),
      events, model, cfg, raster, engine,
    };
  },
};
`;

// --------------------------------------------------------- node-side API ---
export interface PixelRegion {
  id: string;
  label?: string;
  polygon: Array<[number, number]>;
}

export interface PixelRunInput {
  branch?: 'imagedata' | 'canvas';
  region?: PixelRegion;
  budget?: Record<string, number>;
  renderReaderId?: string;
  rasterRenderReaderId?: string;
  engine?: 'stub' | 'hangInit' | 'lateInit' | 'hangRecognize' | 'flakyHang';
  engineAfterOpen?:
    | 'stub'
    | 'hangInit'
    | 'lateInit'
    | 'hangRecognize'
    | 'flakyHang';
  lateInitMs?: number;
  settleMs?: number;
  stallRaster?: boolean;
  stubResult?: { text?: string | null; blocks?: unknown[] };
  idbFactory?: 'none' | 'writeFail';
  openCancelAfterMs?: number;
  cancelAfterMs?: number;
  cancelBeforeExtract?: boolean;
}

export interface PixelCrop {
  cropX: number;
  cropY: number;
  cropWidthPx: number;
  cropHeightPx: number;
  regionPx: readonly number[] | null;
  paddingPx: number;
  resizeK: number;
  resizeClipPx: readonly [number, number];
  outWidthPx: number;
  outHeightPx: number;
  ocrId: string;
}

export interface PixelRunResult {
  input: PixelRunInput;
  captured: {
    createWorkerCount?: number;
    workerLangs?: Array<{
      code: string;
      dataClass: string;
      data?: string;
      dataBytes?: number | null;
      dataSha256?: string | null;
    }>;
    workerOptions?: Record<string, unknown>;
    pendingInits?: number;
    maxConcurrentInits?: number;
    signalAbortedAtCreate?: boolean;
    abortReason?: string;
    recognizeCount?: number;
    terminateCount?: number;
    imageClass?: string;
    imageBytes?: number[] | null;
  };
  construct: {
    ok: boolean;
    name?: string;
    message?: string;
    reason?: string | null;
  } | null;
  open: {
    ok: boolean;
    value?: {
      model?: {
        state?: string;
        provenance?: string | null;
        limitations?: string[];
      };
    };
    error?: { reason?: string | null; message?: string };
  } | null;
  plan: { ok: boolean; value?: Array<Record<string, unknown>>; error?: { reason?: string | null } } | null;
  checks: Array<{ id: string; reader_ids: string[]; region_id: string | null }> | null;
  run: { ok: boolean; value?: PixelOutput; error?: { reason?: string | null; message?: string } } | null;
  output: PixelOutput | null;
  manifest: { ok: boolean; value?: { reader: { id: string } } } | null;
  built: { page: unknown; canonical: unknown } | null;
  decoded: DecodedPng | null;
  imageClass: string | null;
  unmapped: [number, number] | null;
  chunks: unknown[][] | null;
  modelStates: string[];
  progress: Array<{ status: string; progress: number }>;
  errors: Array<Record<string, unknown>>;
  elapsedMs: number | null;
  docSha: string | null;
  model: { sha256: string; byteLength: number } | null;
}

export interface PixelOutput {
  check: {
    id: string;
    status: string;
    reason: string | null;
    produced_occurrence_count: number;
    retained_occurrence_ids: string[];
  };
  reader: { id: string; settings: Record<string, unknown> };
  raster: { rasterId: string; renderReaderId: string; scalePxPerPt: number };
  crop: PixelCrop;
  raw: { text: string | null; blocks: unknown };
  occurrences: Array<{
    id: string;
    reader_id: string;
    raw_text: string;
    raw_source_locator: string;
    geometry: { polygon: Array<[number, number]> | null; transform_ids: string[] };
  }>;
  transforms: Array<{ id: string; operation: string; matrix: number[] }>;
  diagnostics: { downscaled: boolean; pixelsOcr: number; attempt: number };
  limitations: string[];
}

export async function runPixelCase(
  page: Page,
  input: PixelRunInput = {},
  unmapPt?: [number, number],
): Promise<PixelRunResult> {
  return page.evaluate(
    ({ input, unmapPt }) =>
      (
        globalThis as unknown as {
          __px: {
            runCase: (i: unknown, u: unknown) => Promise<PixelRunResult>;
          };
        }
      ).__px.runCase(input, unmapPt),
    { input, unmapPt },
  );
}

// ----------------------------------------------------------- assertions ---
/**
 * The recorded k is the drawn factor: a 50-px cap plans k=0.1125 ->
 * 5x9 output; the fractional-destination draw clips the right 0.5125px
 * so every output pixel is black (the old integer-stretch draw would
 * paint column 4 red).
 */
export function expectDownscaledFixture(out: PixelRunResult): void {
  expect(out.open?.ok).toBe(true);
  expect(out.run?.ok).toBe(true);
  const output = out.output!;
  expect(output.check.status).toBe('completed');
  expect(output.check.reason).toBe('unreadable_pixels');
  expect(out.imageClass).toBe('Uint8Array');

  const crop = output.crop;
  expect(crop.cropX).toBe(0);
  expect(crop.cropY).toBe(0);
  expect(crop.cropWidthPx).toBe(49);
  expect(crop.cropHeightPx).toBe(80);
  expect(crop.resizeK).toBe(0.1125);
  expect(crop.outWidthPx).toBe(5);
  expect(crop.outHeightPx).toBe(9);
  expect(output.diagnostics.downscaled).toBe(true);
  expect(output.diagnostics.pixelsOcr).toBe(45);
  expect(Math.abs(crop.resizeClipPx[0] - 0.5125)).toBeLessThan(1e-9);
  expect(crop.resizeClipPx[1]).toBe(0);
  expect(output.limitations.join(' ')).toContain('ocr_resize_clipped');
  expect(output.limitations.join(' ')).toContain('downsampled');
  const resize = output.transforms.find((t) => t.operation === 'ocr_resize');
  expect(resize?.matrix[0]).toBe(0.1125);
  expect(resize?.matrix[3]).toBe(0.1125);

  const img = out.decoded!;
  expect(img).not.toBeNull();
  expect(img.width).toBe(5);
  expect(img.height).toBe(9);
  // Every output pixel samples source x<=40 — the seam at x>=42 is
  // unreachable under k=0.1125, so the whole image is opaque black.
  for (let y = 0; y < img.height; y++) {
    for (let x = 0; x < img.width; x++) {
      expect(pixelAt(img, x, y), `pixel (${x},${y})`).toEqual([...BLACK]);
    }
  }
  // Inverse mapping of output pixel (4,4)'s center lands inside source
  // pixel [40,41) x [40,41) — inside the black region, before the seam.
  expect(out.unmapped![0]).toBeGreaterThanOrEqual(39.999999);
  expect(out.unmapped![0]).toBeLessThan(41);
  expect(out.unmapped![1]).toBeGreaterThanOrEqual(39.999999);
  expect(out.unmapped![1]).toBeLessThan(41);
}

/** Control: with no cap the fixture passes through byte-exact. */
export function expectNoResizeControl(out: PixelRunResult): void {
  expect(out.run?.ok).toBe(true);
  const output = out.output!;
  expect(output.check.status).toBe('completed');
  expect(out.imageClass).toBe('Uint8Array');
  const img = out.decoded!;
  expect(img.width).toBe(49);
  expect(img.height).toBe(80);
  expect(output.crop.resizeK).toBe(1);
  expect(output.crop.outWidthPx).toBe(49);
  expect(output.crop.outHeightPx).toBe(80);
  expect(output.crop.resizeClipPx).toEqual([0, 0]);
  expect(output.diagnostics.downscaled).toBe(false);
  const resize = output.transforms.find((t) => t.operation === 'ocr_resize');
  expect(resize?.matrix[0]).toBe(1);
  expect(resize?.matrix[3]).toBe(1);
  expect(output.limitations.join(' ')).not.toContain('ocr_resize_clipped');
  expect(output.limitations.join(' ')).not.toContain('downsampled');
  // Byte-exact identity: seam column preserved verbatim.
  expect(pixelAt(img, 41, 4)).toEqual([...BLACK]);
  expect(pixelAt(img, 42, 4)).toEqual([...RED]);
  expect(pixelAt(img, 48, 79)).toEqual([...RED]);
}

/**
 * Crop with a non-zero origin: region canonical polygon -> raster
 * bounds [34,10]-[41,26]; pad max(8, ceil(16*0.1))=8 -> crop
 * (26,2)-(49,34): 23x32 at origin (26,2), k=1. The red seam at source
 * x=42 lands at output x=16 — its position proves the source origin
 * offset was applied; the exact 23x32 size proves no padding leaked.
 */
export function expectCropOffset(out: PixelRunResult): void {
  expect(out.run?.ok).toBe(true);
  const output = out.output!;
  expect(output.check.status).toBe('completed');
  const crop = output.crop;
  expect(crop.cropX).toBe(26);
  expect(crop.cropY).toBe(2);
  expect(crop.cropWidthPx).toBe(23);
  expect(crop.cropHeightPx).toBe(32);
  expect(crop.paddingPx).toBe(8);
  expect(crop.regionPx).toEqual([34, 10, 41, 26]);
  expect(crop.resizeK).toBe(1);
  expect(crop.resizeClipPx).toEqual([0, 0]);
  const img = out.decoded!;
  expect(img.width).toBe(23);
  expect(img.height).toBe(32);
  // Seam source x=42 -> output x = 42-26 = 16.
  expect(pixelAt(img, 15, 16)).toEqual([...BLACK]);
  expect(pixelAt(img, 16, 16)).toEqual([...RED]);
}
