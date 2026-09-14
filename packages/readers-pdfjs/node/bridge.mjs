#!/usr/bin/env node
/**
 * Fixed Node PDF.js profile wrapper (T33).
 *
 * Runs the pinned pdfjs-dist legacy build from this workspace's own
 * lockfile. Stdin is one JSON request; stdout is one JSON response.
 * Network is never used. Failures are `{ ok: false }` with exit 0 when
 * the wrapper itself could run.
 */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const PROTOCOL = "inkflip.reader.pdfjs-node";
const PROTOCOL_VERSION = "1.0.0";
const MAX_REQUEST_BYTES = 32 * 1024 * 1024;
const HERE = path.dirname(fileURLToPath(import.meta.url));

function okResponse(result) {
  return { ok: true, protocol: PROTOCOL, version: PROTOCOL_VERSION, ...result };
}

function errorResponse(code, message) {
  return {
    ok: false,
    protocol: PROTOCOL,
    version: PROTOCOL_VERSION,
    error: { code, message: String(message).slice(0, 500) },
  };
}

function readRequest() {
  return new Promise((resolve) => {
    const chunks = [];
    let total = 0;
    let settled = false;
    const done = (val) => {
      if (!settled) {
        settled = true;
        resolve(val);
      }
    };
    process.stdin.on("data", (chunk) => {
      total += chunk.length;
      if (total > MAX_REQUEST_BYTES) {
        done({ error: errorResponse("OVERSIZED_REQUEST", `Request exceeds ${MAX_REQUEST_BYTES} bytes`) });
        process.stdin.pause();
        return;
      }
      chunks.push(chunk);
    });
    process.stdin.on("end", () => {
      if (chunks.length === 0) {
        done({ error: errorResponse("EMPTY_REQUEST", "Request body is empty") });
        return;
      }
      try {
        done({ data: JSON.parse(Buffer.concat(chunks).toString("utf-8")) });
      } catch (err) {
        done({ error: errorResponse("MALFORMED_JSON", err.message) });
      }
    });
    process.stdin.on("error", (err) => {
      done({ error: errorResponse("IO_ERROR", err.message) });
    });
  });
}

function resolvePdfJs() {
  const localPkg = path.join(HERE, "node_modules", "pdfjs-dist", "package.json");
  if (!fs.existsSync(localPkg)) {
    throw new Error(
      "Cannot find module 'pdfjs-dist/package.json' in the isolated Node wrapper. " +
        "Install the pinned lock with: cd packages/readers-pdfjs/node && bun install --frozen-lockfile " +
        "(do not add pdfjs-dist to a parent package.json; NODE_PATH is not used)",
    );
  }
  const pkgDir = path.dirname(localPkg);
  const pkg = JSON.parse(fs.readFileSync(localPkg, "utf8"));
  const buildDir = path.join(pkgDir, "legacy", "build");
  const pdfPath = path.join(buildDir, "pdf.mjs");
  const workerPath = path.join(buildDir, "pdf.worker.mjs");
  if (!fs.existsSync(pdfPath) || !fs.existsSync(workerPath)) {
    throw new Error(`pinned pdfjs-dist legacy build missing under ${buildDir}`);
  }
  return { pkg, pdfPath, workerPath };
}

async function loadPdfJs() {
  const resolved = resolvePdfJs();
  const pdfjs = await import(pathToFileURL(resolved.pdfPath).href);
  pdfjs.GlobalWorkerOptions.workerSrc = pathToFileURL(resolved.workerPath).href;
  return { pdfjs, identity: resolved.pkg };
}

function describeReader(pkg, runtimeVersion) {
  const version = runtimeVersion || pkg.version;
  const slug = `pdfjs-${String(version).replace(/[^a-z0-9]+/gi, "_").toLowerCase()}-text`;
  return {
    id: slug.slice(0, 96),
    name: "pdf.js",
    version,
    build: `pdfjs-dist ${pkg.version} (node profile; actual runtime ${version})`,
    adapter_version: "1.0.0",
    method: "native_text",
    environment: "node",
    settings: {
      normalization: "scalar-whitespace-v1",
      language: null,
      psm: null,
      render_reader_id: null,
      raster_dpi: null,
      annotation_mode: "not_applicable",
    },
    capabilities: [
      {
        name: "native_text",
        support: "supported",
        limits: [
          "raw_text is the unmodified getTextContent API string",
          "geometry is page_only in this Node wrapper; precise overlays stay in the browser adapter",
        ],
      },
    ],
    model_hashes: [],
    limitations: [
      "fixed Node wrapper over the workspace-locked pdfjs-dist; no network, no scripting",
    ],
  };
}

async function extractPdf(pdfjs, pdfBytes, pages, reader) {
  const task = pdfjs.getDocument({
    data: new Uint8Array(pdfBytes),
    disableFontFace: true,
    isEvalSupported: false,
    useSystemFonts: false,
    stopAtErrors: false,
  });
  const doc = await task.promise;
  try {
    const pageCount = doc.numPages;
    const selected = (pages && pages.length ? pages : [0]).filter(
      (p) => Number.isInteger(p) && p >= 0 && p < pageCount,
    );
    const pageResults = [];
    for (const pageIndex of selected) {
      try {
        const page = await doc.getPage(pageIndex + 1);
        const content = await page.getTextContent({
          disableNormalization: true,
          includeMarkedContent: false,
        });
        const raw = (content.items || [])
          .map((item) => (item && typeof item.str === "string" ? item.str : ""))
          .join(" ");
        pageResults.push({
          page_index: pageIndex,
          status: "completed",
          reason: null,
          raw_text: raw,
        });
      } catch (err) {
        pageResults.push({
          page_index: pageIndex,
          status: "failed",
          reason: `getTextContent failed: ${err && err.message ? err.message : err}`,
          raw_text: null,
        });
      }
    }
    return {
      reader,
      pages: pageResults,
      pdfjs_version: pdfjs.version,
      node: process.version,
    };
  } finally {
    if (doc && typeof doc.destroy === "function") {
      await doc.destroy();
    } else if (doc && typeof doc.cleanup === "function") {
      await doc.cleanup();
    }
  }
}

async function dispatch(req) {
  if (!req || typeof req !== "object") {
    return errorResponse("INVALID_REQUEST", "Expected JSON object");
  }
  const { pdfjs, identity } = await loadPdfJs();
  const reader = describeReader(identity, pdfjs.version);
  if (req.action === "describe") {
    return okResponse({ reader, pdfjs_version: pdfjs.version, node: process.version });
  }
  if (req.action === "extract") {
    let pdfBytes = null;
    const pdfPath = req.pdf_path || req.source;
    if (pdfPath) {
      if (typeof pdfPath !== "string") {
        return errorResponse("INVALID_REQUEST", "pdf_path must be a string");
      }
      try {
        pdfBytes = fs.readFileSync(pdfPath);
      } catch (err) {
        return errorResponse("FILE_ERROR", `Failed to read ${pdfPath}: ${err.message}`);
      }
    } else if (req.pdf_base64) {
      pdfBytes = Buffer.from(req.pdf_base64, "base64");
    } else {
      return errorResponse("INVALID_REQUEST", "Missing pdf_path or pdf_base64");
    }
    if (!pdfBytes || pdfBytes.length < 4 || !pdfBytes.subarray(0, 4).equals(Buffer.from("%PDF"))) {
      return errorResponse("MALFORMED_PDF", "Input is not a valid PDF document");
    }
    const extracted = await extractPdf(pdfjs, pdfBytes, req.pages || [0], reader);
    return okResponse(extracted);
  }
  return errorResponse("UNKNOWN_ACTION", `Unsupported action: ${req.action}`);
}

const req = await readRequest();
let resp;
if (req.error) {
  resp = req.error;
} else {
  try {
    resp = await dispatch(req.data);
  } catch (err) {
    resp = errorResponse("INTERNAL_ERROR", err.message || String(err));
  }
}
process.stdout.write(JSON.stringify(resp) + "\n", () => process.exit(0));
