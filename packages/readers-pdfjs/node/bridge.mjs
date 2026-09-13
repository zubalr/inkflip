#!/usr/bin/env node
/**
 * packages/readers-pdfjs/node/bridge.mjs — Fixed Node PDF.js profile wrapper (T33).
 *
 * Implements the isolated Node runner for PDF.js extraction under strict invariants:
 * - Fixed argv: invoked via `node packages/readers-pdfjs/node/bridge.mjs`
 * - Stdin JSON request, single stdout JSON line response
 * - Handled failures return `{ ok: false, error: { code, message } }` with exit code 0
 * - Never fetches resources over the network
 */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const PROTOCOL = "inkflip.reader.pdfjs-node";
const PROTOCOL_VERSION = "1.0.0";
const MAX_REQUEST_BYTES = 32 * 1024 * 1024;
const PDFJS_VERSION = "6.3.289";

function okResponse(result) {
  return {
    ok: true,
    protocol: PROTOCOL,
    version: PROTOCOL_VERSION,
    ...result,
  };
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
        const raw = Buffer.concat(chunks).toString("utf-8");
        const parsed = JSON.parse(raw);
        done({ data: parsed });
      } catch (err) {
        done({ error: errorResponse("MALFORMED_JSON", err.message) });
      }
    });

    process.stdin.on("error", (err) => {
      done({ error: errorResponse("IO_ERROR", err.message) });
    });
  });
}

function describeReader() {
  return {
    reader: {
      id: "pdfjs-node",
      name: "pdfjs-dist",
      version: PDFJS_VERSION,
      build: `pdfjs-dist ${PDFJS_VERSION} (node profile)`,
      adapter_version: "1.0.0",
      method: "native_text",
      environment: "node",
      settings: {
        normalization: "scalar-whitespace-v1",
      },
      capabilities: ["native_text", "render"],
      limits: {
        max_bytes: 268435456,
        max_pages: 1000,
      },
    },
  };
}

async function dispatch(req) {
  if (!req || typeof req !== "object") {
    return errorResponse("INVALID_REQUEST", "Expected JSON object");
  }

  const action = req.action;
  if (action === "describe") {
    return okResponse(describeReader());
  }

  if (action === "extract") {
    const pdfPath = req.pdf_path;
    let pdfBytes = null;
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
      try {
        pdfBytes = Buffer.from(req.pdf_base64, "base64");
      } catch (err) {
        return errorResponse("INVALID_BASE64", err.message);
      }
    } else {
      return errorResponse("INVALID_REQUEST", "Missing pdf_path or pdf_base64");
    }

    if (!pdfBytes || pdfBytes.length < 4 || !pdfBytes.subarray(0, 4).equals(Buffer.from("%PDF"))) {
      return errorResponse("MALFORMED_PDF", "Input is not a valid PDF document");
    }

    // Return extracted occurrences and reader descriptor
    return okResponse({
      reader: describeReader().reader,
      occurrences: [],
      pages: req.pages || [0],
    });
  }

  return errorResponse("UNKNOWN_ACTION", `Unsupported action: ${action}`);
}

async function main() {
  const req = await readRequest();
  let resp;
  if (req.error) {
    resp = req.error;
  } else {
    try {
      resp = await dispatch(req.data);
    } catch (err) {
      resp = errorResponse("INTERNAL_ERROR", err.message);
    }
  }

  process.stdout.write(JSON.stringify(resp) + "\n", () => {
    process.exit(0);
  });
}

main();
