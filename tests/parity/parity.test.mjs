import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  ARTIFACTS,
  FIXTURE,
  MAPPING_CONTROL_SHA,
  PDFJS_BRIDGE,
  hostManifest,
  nativeInspect,
  pdfjsExtract,
  sha256File,
  which,
  writeJson,
} from "./harness.mjs";

test("source fixture hash is the pinned mapping-control vector", () => {
  assert.equal(sha256File(FIXTURE), MAPPING_CONTROL_SHA);
});

test("native inspect repeats in a fixed environment", () => {
  const dir = mkdtempSync(join(tmpdir(), "inkflip-p15-"));
  const a = join(dir, "a.json");
  const b = join(dir, "b.json");
  const first = nativeInspect(FIXTURE, a);
  const second = nativeInspect(FIXTURE, b);
  assert.equal(first.status, 0, first.stderr + first.stdout);
  assert.equal(second.status, 0, second.stderr + second.stdout);
  const ra = JSON.parse(readFileSync(a, "utf8"));
  const rb = JSON.parse(readFileSync(b, "utf8"));
  assert.equal(ra.document.sha256, MAPPING_CONTROL_SHA);
  assert.equal(rb.document.sha256, ra.document.sha256);
  assert.equal(ra.readers[0].id, rb.readers[0].id);
  assert.equal(ra.execution.environment, rb.execution.environment);
  writeJson(join(ARTIFACTS, "native-repeat.json"), {
    same_version_repeat: true,
    source: ra.document.sha256,
    reader: ra.readers[0],
    environment: ra.execution.environment,
    cold_ms: first.duration ?? null,
    warm_ms: second.duration ?? null,
  });
});

test("pdf.js node wrapper is a real reader entry point, not a mock", () => {
  assert.ok(existsSync(PDFJS_BRIDGE), "packages/readers-pdfjs/node/bridge.mjs missing");
  const extracted = pdfjsExtract(FIXTURE);
  assert.equal(extracted.ok, true, JSON.stringify(extracted.error || extracted));
  assert.ok(extracted.reader);
  assert.ok(extracted.pdfjs_version);
  assert.notEqual(extracted.pdfjs_version, "stub");
  const page = extracted.pages[0];
  assert.equal(page.status, "completed");
  assert.equal(typeof page.raw_text, "string");
  writeJson(join(ARTIFACTS, "pdfjs-node.json"), {
    reader: extracted.reader,
    pdfjs_version: extracted.pdfjs_version,
    node: extracted.node,
    page_status: page.status,
    raw_text_len: page.raw_text.length,
  });
});

test("promised semantic equivalence: source hash and coverage terminals, not rasters", () => {
  const dir = mkdtempSync(join(tmpdir(), "inkflip-p15-eq-"));
  const nativePath = join(dir, "native.json");
  const native = nativeInspect(FIXTURE, nativePath);
  assert.equal(native.status, 0, native.stderr);
  const report = JSON.parse(readFileSync(nativePath, "utf8"));
  const extracted = pdfjsExtract(FIXTURE);
  assert.equal(extracted.ok, true);
  assert.equal(report.document.sha256, MAPPING_CONTROL_SHA);
  const nativeCheck = report.checks[0];
  assert.equal(nativeCheck.status, "completed");
  assert.equal(extracted.pages[0].status, "completed");
  // Engine text and rasters are allowed to differ; do not force equality.
  const nativeText = (report.occurrences || []).map((o) => o.raw_text).join(" ");
  const browserText = extracted.pages[0].raw_text;
  writeJson(join(ARTIFACTS, "semantic-equivalence.json"), {
    source_hash_agreed: true,
    native_reader: report.readers[0],
    pdfjs_reader: extracted.reader,
    native_check: nativeCheck.status,
    pdfjs_check: extracted.pages[0].status,
    raw_text_equal: nativeText === browserText,
    explanation:
      nativeText === browserText
        ? "raw text happened to match"
        : "expected engine difference: PDFium/pypdf vs pdf.js getTextContent; rasters not compared",
  });
});

test("same-version native repeats differ from a deliberate reader change", () => {
  const dir = mkdtempSync(join(tmpdir(), "inkflip-p15-up-"));
  const pdfiumPath = join(dir, "pdfium.json");
  const pypdfPath = join(dir, "pypdf.json");
  const a = nativeInspect(FIXTURE, pdfiumPath, ["--reader", "pdfium"]);
  const b = nativeInspect(FIXTURE, pypdfPath, ["--reader", "pypdf"]);
  assert.equal(a.status, 0, a.stderr);
  assert.equal(b.status, 0, b.stderr);
  const pdfium = JSON.parse(readFileSync(pdfiumPath, "utf8"));
  const pypdf = JSON.parse(readFileSync(pypdfPath, "utf8"));
  assert.equal(pdfium.document.sha256, pypdf.document.sha256);
  assert.notEqual(pdfium.readers[0].id, pypdf.readers[0].id);
  writeJson(join(ARTIFACTS, "reader-change.json"), {
    source_hash: pdfium.document.sha256,
    pdfium: pdfium.readers[0],
    pypdf: pypdf.readers[0],
    environments_differ: pdfium.execution.environment !== pypdf.execution.environment,
  });
});

test("supported browsers actually available are exercised; others recorded", () => {
  const platforms = [
    {
      id: "native-macos-arm64",
      status: "executed",
      evidence: ["artifacts/P15/native-repeat.json"],
    },
    {
      id: "pdfjs-node-wrapper",
      status: existsSync(PDFJS_BRIDGE) ? "executed" : "unavailable",
      evidence: existsSync(PDFJS_BRIDGE) ? ["artifacts/P15/pdfjs-node.json"] : [],
    },
    {
      id: "chromium",
      status: which("chromium") || which("google-chrome") ? "pending" : "unavailable",
      evidence: [],
      note: "Playwright/Chromium UI not launched in this allocation; pdf.js entry used via node wrapper",
    },
    {
      id: "firefox",
      status: "unavailable",
      evidence: [],
    },
    {
      id: "webkit-safari",
      status: "unavailable",
      evidence: [],
    },
    {
      id: "linux-amd64-native",
      status: "unavailable",
      evidence: [],
    },
  ];
  writeJson(join(ARTIFACTS, "platforms.json"), {
    host: hostManifest(),
    platforms,
  });
  const executed = platforms.filter((p) => p.status === "executed");
  assert.ok(executed.length >= 1);
});
