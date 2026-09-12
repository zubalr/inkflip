/**
 * T15 privacy harness mount — a TEST-OWNED page (tests/privacy/harness/)
 * that binds the REAL production collaborators the composed app will use:
 *
 * - the T09 pdf.js reader adapter (pinned pdfjs-dist 6.3.289 legacy pair,
 *   same-origin worker emitted as a build asset) for document open,
 *   contract pages, native-text extraction and page render;
 * - the T10 TesseractOcrReader driven by the real patched
 *   tesseract.js@7.0.0 module against the staged same-origin
 *   worker/core/traineddata assets (prepare → open → plan → extract);
 * - the T16 ExportPanel + packages/reports/export engine for the
 *   pre-export preview and real Blob/anchor downloads;
 * - the contracts seal/normalize helpers for report assembly.
 *
 * Nothing is stubbed at the contract surface: the only test-owned code is
 * the wiring itself (the same role the feature preview mounts play for
 * T08/T22 while app composition remains unlanded). `window.__t15` exposes
 * JSON-safe passthroughs so the Playwright suite can drive the real flow
 * and assert on real results.
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.mjs?url";
import Tesseract from "tesseract.js";

import { createPdfJsReader } from "../../../packages/readers-pdfjs/src/index";
import type { PdfJsApi } from "../../../packages/readers-pdfjs/src/types.ts";
import {
  TesseractOcrReader,
  type OcrSelection,
  type PageRaster,
} from "../../../packages/readers-tesseract/src/index";
import * as contracts from "../../../packages/contracts/src/index";
import {
  buildExportPreview,
  exportFileName,
  projectReport,
  renderReportHtml,
  serializeReportJson,
} from "../../../packages/reports/export/index";
import { ExportPanel } from "../../../apps/web/src/features/export/ExportPanel";

import "../../../apps/web/src/styles/tokens.css";
import "../../../apps/web/src/styles/global.css";

/** Pinned model identity — config/resolved-assets.json (tessdata-fast-eng). */
const MODEL = {
  id: "tessdata-fast-eng",
  version: "65727574dfcd264acbb0c3e07860e4e9e9b22185",
  sha256: "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
  byteLength: 4113088,
  sourcePath: "/models/tessdata-fast-eng/7d4322bd/eng.traineddata",
  lang: "eng",
  license: "Apache-2.0",
  cachePath: "inkflip/models",
} as const;

/** Explicit same-origin staged paths (the adapter never uses CDN defaults). */
const PATHS = {
  workerPath: "/assets/tesseract/7.0.0/worker.min.js",
  corePath: "/assets/tesseract-core/7.0.0/",
  langPath: "/models/tessdata-fast-eng/7d4322bd/",
  cachePath: "inkflip/models",
} as const;

/** Staged asset SHA-256s recorded in the ReaderManifest (resolved-assets.json). */
const ASSET_HASHES = [
  "576b7df7e3393e137e51849357c9adb53fe7ac1bb69bfa06cf3d61520f182c6d",
  "0bc6ce3e5fbbd0cd89706cf2fd70960e3372f4f01ee24265b26990808aaeb286",
  "eef5f8b2f8e20e150680b20adaec4a60babafee3adbe8a94583c81fee46e8680",
  "6b61ef4e911b5cf57e656bbfe983d6e2b3711a02dd164154ddda064566e8e09d",
  "c58b46a4c796c0b8afccf77591d5b875b6896b45d402bbce8caa6f5362447b38",
  "843074aa5bad1cc6421b74a86201768ced9f244795e4d81435435a61a40ce535",
  "861a536cf9ef8e63cb644d57bab39c388f37f7d6b6f60024b741c5f6b39a59b3",
  MODEL.sha256,
];

const adapter = createPdfJsReader({
  pdfjs: pdfjs as unknown as PdfJsApi,
  workerSrc: workerUrl,
  cMapUrl: "/assets/pdfjs/6.3.289/cmaps/",
  standardFontDataUrl: "/assets/pdfjs/6.3.289/standard_fonts/",
  wasmUrl: "/assets/pdfjs/6.3.289/wasm/",
  iccUrl: "/assets/pdfjs/6.3.289/iccs/",
});

function hex(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += b.toString(16).padStart(2, "0");
  return s;
}

function serErr(e: unknown): { name: string; message: string; reason: string | null } {
  return {
    name: (e as { name?: string })?.name ?? "Error",
    message: String((e as { message?: string })?.message ?? e),
    reason: (e as { reason?: string })?.reason ?? null,
  };
}

async function tryV<T>(fn: () => T | Promise<T>) {
  try {
    return { ok: true as const, value: await fn() };
  } catch (e) {
    return { ok: false as const, error: serErr(e) };
  }
}

interface DocRec {
  handle: unknown;
  sha256: string;
  pageCount: number;
  byteLength: number;
}
interface ReaderRec {
  reader: TesseractOcrReader;
  handle: unknown;
  checks: Map<string, unknown>;
  hooks: { progress: unknown[]; models: unknown[]; errors: unknown[] };
}

const state = {
  n: 0,
  docs: new Map<string, DocRec>(),
  rasters: new Map<string, PageRaster>(),
  readers: new Map<string, ReaderRec>(),
  exportRoot: null as Root | null,
};

const api = {
  adapter,
  contracts,
  Tesseract,
  MODEL,
  PATHS,
  ASSET_HASHES,
  engineKind: typeof (Tesseract as { createWorker?: unknown })?.createWorker,

  /** Open the canary bytes through the real adapter open() path. */
  async openDoc(arr: number[]) {
    return tryV(async () => {
      const bytes = new Uint8Array(arr);
      const sha = hex(contracts.sha256(bytes));
      const handle = await adapter.open({ bytes, sha256: sha, generation: 1 });
      const docId = `doc_${++state.n}`;
      state.docs.set(docId, {
        handle,
        sha256: sha,
        pageCount: handle.doc.numPages,
        byteLength: bytes.length,
      });
      return { docId, sha256: sha, pageCount: handle.doc.numPages };
    });
  },

  /** Contract pages + transforms for the opened document (real geometry). */
  async contractPages(docId: string) {
    return tryV(async () => {
      const rec = state.docs.get(docId);
      if (!rec) throw new Error("unknown doc");
      return adapter.pages(rec.handle as never);
    });
  },

  /**
   * Render a page through the real adapter render path, then package the
   * outcome as the PageRaster the OCR reader consumes (built page comes
   * from the adapter's own HandlePage cache).
   */
  async rasterize(docId: string, pageIndex: number, scale: number) {
    return tryV(async () => {
      const rec = state.docs.get(docId);
      if (!rec) throw new Error("unknown doc");
      const checks = adapter.plan(rec.handle as never, {
        pages: [pageIndex],
        capabilities: ["render"],
      });
      const check = checks[0];
      if (!check) throw new Error("render check was not planned");
      const outcome = await adapter.extract(
        rec.handle as never,
        check,
        () => undefined,
        {},
        { renderScalePxPerPt: scale },
      );
      const raster = outcome.raster;
      if (!raster) throw new Error(outcome.result.reason ?? "render failed");
      const hp = (rec.handle as { pages: ({ built: PageRaster["built"] } | null)[] }).pages[
        pageIndex
      ];
      if (!hp?.built) throw new Error("built page missing after render");
      const pageRaster: PageRaster = {
        rasterId: raster.rasterId,
        renderReaderId: adapter.readers.render.id,
        scalePxPerPt: raster.scalePxPerPt,
        widthPx: raster.widthPx,
        heightPx: raster.heightPx,
        image: new ImageData(
          new Uint8ClampedArray(raster.imageData),
          raster.widthPx,
          raster.heightPx,
        ),
        built: hp.built,
      };
      state.rasters.set(`${docId}:${pageIndex}`, pageRaster);
      return {
        rasterId: raster.rasterId,
        widthPx: raster.widthPx,
        heightPx: raster.heightPx,
        scalePxPerPt: raster.scalePxPerPt,
        pixelSha256: hex(contracts.sha256(new Uint8Array(raster.imageData.buffer.slice(0)))),
        transforms: raster.transforms,
        check: outcome.result,
        plan: check,
      };
    });
  },

  /** Plan + extract a native_text check; returns plan, result and emitted occurrences. */
  async extractText(docId: string, pageIndex: number, regionId: string | null) {
    return tryV(async () => {
      const rec = state.docs.get(docId);
      if (!rec) throw new Error("unknown doc");
      const regions = regionId === null ? {} : { [`native_text:p${pageIndex}`]: regionId };
      const checks = adapter.plan(rec.handle as never, {
        pages: [pageIndex],
        capabilities: ["native_text"],
        regions,
      });
      const check = checks[0];
      if (!check) throw new Error("text check was not planned");
      const emitted: unknown[] = [];
      const outcome = await adapter.extract(
        rec.handle as never,
        check,
        (chunk: readonly unknown[]) => {
          emitted.push(...chunk);
        },
        {},
        {},
      );
      return { plan: check, result: outcome.result, emitted };
    });
  },

  /**
   * Create the real OCR reader bound to the prepared rasters for docId.
   * `docId` may be null when the caller only exercises model preparation
   * (e.g. the cold-offline failure leg never reaches a raster request).
   */
  makeOcrReader(docId: string | null, runKey: string) {
    if (docId !== null && !state.docs.has(docId)) throw new Error("unknown doc");
    const hooks = { progress: [] as unknown[], models: [] as unknown[], errors: [] as unknown[] };
    const reader = new TesseractOcrReader({
      engine: Tesseract as never,
      engineVersion: "7.0.0",
      coreBuild: "feature-detected single-threaded lstm",
      model: MODEL,
      paths: PATHS,
      assetHashes: ASSET_HASHES,
      profile: "desktop",
      runKey,
      renderReaderId: adapter.readers.render.id,
      rasterSource: async (pageIndex: number) => {
        const r = docId === null ? undefined : state.rasters.get(`${docId}:${pageIndex}`);
        if (!r) throw new Error(`no raster prepared for page ${pageIndex}`);
        return r;
      },
      hooks: {
        onProgress: (e) => hooks.progress.push({ status: e.status, progress: e.progress }),
        onModelState: (s) => hooks.models.push(s),
        onError: (d) => hooks.errors.push(d),
      },
    });
    const readerId = `ocr_${++state.n}`;
    state.readers.set(readerId, { reader, handle: null, checks: new Map(), hooks });
    return { readerId, describe: reader.describe("page") };
  },

  async ocrPrepare(readerId: string) {
    return tryV(() => {
      const rec = state.readers.get(readerId);
      if (!rec) throw new Error("unknown reader");
      return rec.reader.prepareModel();
    });
  },

  async ocrOpen(readerId: string, documentSha256: string, generation: number) {
    return tryV(async () => {
      const rec = state.readers.get(readerId);
      if (!rec) throw new Error("unknown reader");
      const handle = await rec.reader.open({ documentSha256, generation });
      rec.handle = handle;
      return handle;
    });
  },

  ocrPlan(readerId: string, selections: readonly OcrSelection[]) {
    return tryV(() => {
      const rec = state.readers.get(readerId);
      if (!rec) throw new Error("unknown reader");
      const checks = rec.reader.plan(rec.handle as never, selections);
      for (const c of checks) rec.checks.set(c.id, c);
      return checks;
    });
  },

  async ocrExtract(readerId: string, checkId: string) {
    return tryV(async () => {
      const rec = state.readers.get(readerId);
      if (!rec) throw new Error("unknown reader");
      const check = rec.checks.get(checkId);
      if (!check) throw new Error(`unplanned check ${checkId}`);
      const chunks: unknown[] = [];
      const output = await rec.reader.extract(
        rec.handle as never,
        check as never,
        (id: string, occ: readonly unknown[]) => chunks.push({ checkId: id, n: occ.length }),
        new AbortController().signal,
      );
      return { output, chunks, hooks: rec.hooks };
    });
  },

  async ocrClose(readerId: string) {
    return tryV(async () => {
      const rec = state.readers.get(readerId);
      if (!rec) throw new Error("unknown reader");
      await rec.reader.close(rec.handle as never);
      return true;
    });
  },

  /** Seal an assembled report object (recomputes run_key + report_id). */
  seal(report: unknown) {
    return contracts.seal(report as never);
  },

  /** The real T16 engine surface for direct calls. */
  exportEngine: {
    projectReport: (s: unknown, r: unknown) => projectReport(s as never, r as never),
    serializeReportJson: (r: unknown) => serializeReportJson(r as never),
    renderReportHtml: (r: unknown) => renderReportHtml(r as never),
    exportFileName: (r: unknown, f: "json" | "html") => exportFileName(r as never, f),
    buildExportPreview: (r: unknown, o: unknown) => buildExportPreview(r as never, o as never),
  },

  /**
   * Mount the REAL T16 ExportPanel against a report object and an original
   * bytes provider — the pre-export preview and Blob/anchor downloads are
   * the production path, including the privacy-default inclusion state.
   */
  showExportPanel(report: unknown, sourceBytes: number[] | null) {
    const container = document.getElementById("export-root");
    if (!container) throw new Error("missing #export-root");
    const bytes = sourceBytes === null ? null : new Uint8Array(sourceBytes);
    const engine = {
      project: (s: unknown, r: unknown) => projectReport(s as never, r as never),
      preview: (rep: unknown, o?: { html?: string | null; notices?: never }) =>
        buildExportPreview(rep as never, { html: o?.html ?? null, notices: o?.notices }),
      serializeJson: (r: unknown) => serializeReportJson(r as never),
      renderHtml: (r: unknown) => renderReportHtml(r as never),
      fileName: (r: unknown, f: "json" | "html") => exportFileName(r as never, f),
    };
    if (state.exportRoot === null) state.exportRoot = createRoot(container);
    state.exportRoot.render(
      React.createElement(ExportPanel, {
        engine,
        source: report,
        ...(bytes === null ? {} : { sourcePdfBytes: () => bytes }),
      }),
    );
    return true;
  },
};

(globalThis as { __t15?: unknown }).__t15 = api;

const rootElement = document.getElementById("root");
if (rootElement) {
  rootElement.innerHTML =
    '<p data-testid="harness-banner">T15 privacy harness — real pdfjs + tesseract + export wiring</p>' +
    '<div id="export-root"></div>';
}
