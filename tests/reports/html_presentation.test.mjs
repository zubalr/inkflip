// Product HTML exporter: lead with the file/summary, tell the truth about
// source-PDF presence, and keep hostile/long text readable and inert.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { normalize, seal } from "../../packages/contracts/src/index.ts";
import { assertScriptFreeHtml, escapeHtml } from "../../packages/reports/validation/index.ts";
import { projectReport, renderReportHtml } from "../../packages/reports/export/index.ts";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const VALID_DIR = join(ROOT, "planning/contracts/examples/valid");
const loadExample = (name) => JSON.parse(readFileSync(join(VALID_DIR, name), "utf8"));

function htmlFor(name, options = {}) {
  const { report } = projectReport(loadExample(name), options);
  const html = renderReportHtml(report);
  assertScriptFreeHtml(html);
  return { report, html };
}

test("default evidence HTML does not claim the file contains a PDF or is replayable", () => {
  const { html } = htmlFor("native-evidence.inkflip.json");
  assert.match(html, /<h1><bdi>Reading report<\/bdi><\/h1>/);
  assert.match(html, /1 difference is included/);
  assert.match(html, /This HTML file does not contain the original PDF/);
  assert.match(html, /The separately saved JSON also omitted the original PDF/);
  assert.match(html, /This HTML file is not a replayable inspection/);
  assert.equal(html.includes("This is a evidence report"), false);
  assert.equal(html.includes("requires_original"), false);
  assert.equal(html.includes("Source PDF present in this report"), false);
  assert.equal(html.includes("This report includes the original PDF"), false);
  assert.equal(html.includes("data:application/pdf"), false);
  assert.equal(html.includes("JVBER"), false);
  assert.match(html, /Two readings of the selected region differ/);
  assert.match(html, /Technical details/);
  const h1At = html.indexOf("<h1>");
  const shaAt = html.indexOf("Document SHA-256");
  const findingAt = html.indexOf("Two readings of the selected region differ");
  assert.ok(h1At < findingAt && findingAt < shaAt);
});

test("source-bearing JSON is disclosed without implying the HTML embeds PDF bytes", () => {
  const { html, report } = htmlFor("native-replay.inkflip.json", { sourcePdf: "carry" });
  assert.notEqual(report.document.source_asset_id, null);
  assert.match(
    html,
    /The separately saved JSON includes the original PDF: every page and any hidden content/,
  );
  assert.match(html, /This HTML file does not contain those PDF bytes/);
  assert.match(html, /cannot reopen the inspection by itself/);
  assert.equal(html.includes("Source PDF present in this report: yes"), false);
  assert.equal(html.includes("This report includes the original PDF"), false);
  assert.equal(html.includes("data:application/pdf"), false);
  assert.equal(html.includes("JVBER"), false);
});

test("zero findings with an incomplete check are stated in the summary", () => {
  const { html } = htmlFor("failed.json");
  assert.match(html, /No differences recorded/);
  assert.match(html, /Some checks did not finish \(failed\)/);
  assert.match(html, /No differences were recorded in this export/);
});

test("included filename leads the report and long names stay escaped", () => {
  const named = structuredClone(loadExample("native-evidence.inkflip.json"));
  named.document.display_name = `${"year-end-".repeat(18)}<b>2026</b>.pdf`;
  seal(named);
  const { report } = projectReport(named, { filename: true });
  const html = renderReportHtml(report);
  assertScriptFreeHtml(html);
  assert.ok(named.document.display_name.length <= 255);
  assert.equal(html.includes("<b>2026</b>.pdf"), false);
  assert.match(html, /<h1><bdi>year-end-.*&lt;b&gt;2026&lt;\/b&gt;\.pdf<\/bdi><\/h1>/);
  assert.match(html, /overflow-wrap:anywhere/);
});

test("hostile text and a long unbroken reading remain inert data", () => {
  const r = structuredClone(loadExample("native-evidence.inkflip.json"));
  const title = '</title><script>alert(1)</script>';
  const payload = title + "AMOUNT".repeat(80);
  r.findings[0].title = title;
  r.occurrences[0].raw_text = payload;
  const n = normalize(payload);
  r.occurrences[0].normalized_text = n.text;
  r.occurrences[0].normalization_map = n.map;
  seal(r);
  const { report } = projectReport(r, {});
  const html = renderReportHtml(report);
  assertScriptFreeHtml(html);
  assert.equal(html.includes("<script>alert(1)</script>"), false);
  assert.ok(html.includes(escapeHtml(title)));
  assert.ok(html.includes(escapeHtml(payload)));
  assert.match(html, /white-space:pre-wrap/);
});

test("print and narrow layout rules are present in the authorized stylesheet", () => {
  const { html } = htmlFor("native-evidence.inkflip.json");
  assert.match(html, /@media\(max-width:640px\)/);
  assert.match(html, /@media print/);
  assert.match(html, /break-inside:avoid/);
  assert.match(html, /max-width:1100px/);
});
