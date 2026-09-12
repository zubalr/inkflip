/**
 * Script-free human report (`.html`) — T16 product exporter.
 *
 * Contract (REPORT_EXPORT_IMPORT.md §Static HTML hardening): self-contained
 * document, no JavaScript, no forms, no external resources, every
 * report-controlled string escaped, bounded PNGs embedded as `data:` URLs
 * and a fixed stylesheet authorized by a `style-src 'sha256-…'` meta CSP.
 * It opens after the application tab closes and never embeds source PDF
 * bytes — source lives only in the explicit JSON replay bundle.
 *
 * Every serialized byte is checked against `assertScriptFreeHtml` (T24
 * guard) before return, so a template regression fails closed instead of
 * shipping active markup. Embedded images are the *sanitized re-encode*
 * from the bounded PNG path, never the stored asset bytes.
 *
 * `renderReportHtml` is deterministic: identical report values produce
 * identical output, including the stylesheet hash.
 */
import { validate } from "../../contracts/src/index.ts";
import type { Report } from "../../contracts/src/index.ts";
import { assertScriptFreeHtml, escapeHtml } from "../validation/html_guard.ts";
import { decodeBase64 } from "../validation/assets.ts";
import { sanitizePng } from "../validation/png.ts";
import { sha256 } from "../../contracts/src/index.ts";
import { encodeBase64 } from "./serialize.ts";
import { ContractError } from "../../contracts/src/index.ts";

/**
 * Fixed application-owned stylesheet. Any edit changes the CSP hash — the
 * two are derived together at render time so they can never drift.
 * Palette follows the product tokens (paper/ink, teal/rust accents).
 */
export const EXPORT_CSS =
  "body{margin:0;background:#f5f3ee;color:#192327;font:16px/1.6 system-ui,sans-serif}" +
  "main{max-width:850px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.15}" +
  "h2{font-size:23px;margin-top:32px}h3{font-size:18px;margin-top:24px}" +
  ".note{border-left:4px solid #84621e;padding:12px 18px;background:#fff9e9}" +
  ".warn{border-left:4px solid #934420;padding:12px 18px;background:#fdf0e6}" +
  "section{background:white;padding:20px 24px;margin:20px 0;border:1px solid #d5d9d7;border-radius:12px}" +
  "pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace}" +
  "img{max-width:100%;height:auto;border:1px solid #d5d9d7}dt{font-weight:700}dd{margin:0 0 12px}" +
  "table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #ddd;text-align:left;padding:8px;vertical-align:top}" +
  "code{overflow-wrap:anywhere}ul{margin:8px 0;padding-left:24px}footer{font-size:13px}" +
  "@media(max-width:500px){main{padding:20px 14px}section{padding:14px}h1{font-size:28px}}";

function styleHash(): string {
  const bytes = new TextEncoder().encode(EXPORT_CSS);
  let binary = "";
  for (const b of sha256(bytes)) binary += String.fromCharCode(b);
  return btoa(binary);
}

/** Content-Security-Policy meta value for the fixed stylesheet. */
export function exportCsp(): string {
  return (
    "default-src 'none'; script-src 'none'; connect-src 'none'; " +
    "object-src 'none'; img-src data:; style-src 'sha256-" +
    styleHash() +
    "'; base-uri 'none'; form-action 'none'"
  );
}

const esc = escapeHtml;

/**
 * Render a document-controlled string for display: HTML-escaped, with NUL
 * replaced so hostile raw text cannot inject a NUL byte the guard forbids.
 * The JSON export always carries the unmodified raw bytes.
 */
function text(value: string): string {
  return esc(value.replaceAll("\u0000", "�"));
}

function findingSections(
  report: Report,
  readers: Map<string, Report["readers"][number]>,
): string[] {
  const out: string[] = [];
  const occurrences = new Map(report.occurrences.map((o) => [o.id, o]));
  for (const f of report.findings) {
    out.push(
      "<section><h2>" + text(f.title) + "</h2><p>" + text(f.explanation) + "</p>",
      "<p>Finding kind: " +
        esc(f.kind) +
        " · Alignment: " +
        esc(f.alignment) +
        " · Basis: " +
        text(f.basis) +
        "</p>",
    );
    if (f.limitations.length > 0) {
      out.push("<p>Limits: " + text(f.limitations.join("; ")) + "</p>");
    }
    for (const oid of f.occurrence_ids) {
      const o = occurrences.get(oid);
      if (o === undefined) continue; // pruned by selection — never rendered
      const r = readers.get(o.reader_id);
      out.push(
        "<h3><bdi>" +
          text(r === undefined ? o.reader_id : r.name + " " + r.version) +
          "</bdi></h3><pre><bdi>" +
          text(o.raw_text) +
          "</bdi></pre>",
        "<p>Page " +
          String(o.page_index + 1) +
          " · geometry " +
          esc(o.geometry.precision) +
          " · occurrence " +
          esc(o.id) +
          "</p>",
      );
    }
    out.push("</section>");
  }
  return out;
}

function annotationSections(report: Report): string[] {
  if (report.annotations.length === 0) return [];
  const out = ["<section><h2>Included notes</h2>"];
  for (const a of report.annotations) {
    const author = a.author_label === null ? "unlabeled" : a.author_label;
    out.push(
      "<p><bdi>" +
        text(a.text) +
        "</bdi></p><p>Note " +
        esc(a.id) +
        " · page " +
        String(a.page_index + 1) +
        " · author <bdi>" +
        text(author) +
        "</bdi> · human-entered</p>",
    );
  }
  out.push("</section>");
  return out;
}

function imageSections(report: Report): string[] {
  const out: string[] = [];
  for (const asset of report.assets) {
    if (asset.media_type !== "image/png") continue; // never embed source PDF
    let png: Uint8Array;
    try {
      png = sanitizePng(decodeBase64(asset.data_base64)).png;
    } catch (error) {
      if (error instanceof ContractError) {
        throw new ContractError("ASSET", `Asset ${asset.id} cannot be embedded`);
      }
      throw error;
    }
    const caption =
      asset.purpose === "crop"
        ? "Selected rendered excerpt — a crop is not a certified redaction."
        : "Complete rendered page — shows the whole page, not only a selection.";
    out.push(
      "<section><h2>" +
        (asset.purpose === "crop" ? "Included source excerpt" : "Included page image") +
        "</h2><p>" +
        caption +
        "</p>",
      '<img alt="' +
        (asset.purpose === "crop"
          ? "Rendered excerpt for the recorded finding; text alternatives are the named readings above."
          : "Rendered full page accompanying the recorded checks.") +
        '" src="data:image/png;base64,' +
        encodeBase64(png) +
        '"></section>',
    );
  }
  return out;
}

function checkTable(report: Report): string {
  const out = [
    "<section><h2>What was checked</h2><table><thead><tr>" +
      "<th>Check</th><th>Capability</th><th>Status</th>" +
      "<th>Reason / readings</th></tr></thead><tbody>",
  ];
  const plans = new Map(report.plan.checks.map((p) => [p.id, p]));
  for (const c of report.checks) {
    const plan = plans.get(c.id);
    out.push(
      "<tr><td>" +
        esc(c.id) +
        "</td><td>" +
        esc(plan === undefined ? "—" : plan.capability) +
        "</td><td>" +
        esc(c.status) +
        "</td><td>" +
        text(c.reason === null ? "—" : c.reason) +
        " / produced " +
        String(c.produced_occurrence_count) +
        ", retained " +
        String(c.retained_occurrence_ids.length) +
        "</td></tr>",
    );
  }
  out.push("</tbody></table>");
  return out.join("");
}

function coverageSection(report: Report): string {
  const completed = report.checks.filter((c) => c.status === "completed").length;
  const out = [
    checkTable(report),
    "<p>Coverage: " +
      String(report.plan.selected_pages.length) +
      " of " +
      String(report.document.page_count) +
      " document page(s) selected; " +
      String(completed) +
      " of " +
      String(report.checks.length) +
      " planned checks completed. " +
      "Agreement is limited to completed, comparable readings on selected " +
      "pages — never a document-wide verdict.</p></section>",
  ];
  return out.join("");
}

function readerSection(report: Report): string {
  const out = [
    "<section><h2>Readers, settings and limits</h2><table><thead><tr>" +
      "<th>Reader</th><th>Method</th><th>Environment</th><th>Settings</th>" +
      "</tr></thead><tbody>",
  ];
  for (const r of report.readers) {
    const s = r.settings;
    const settings =
      "normalization " +
      esc(s.normalization) +
      " · language " +
      text(s.language === null ? "—" : s.language) +
      " · psm " +
      (s.psm === null ? "—" : String(s.psm)) +
      " · annotation mode " +
      esc(s.annotation_mode);
    out.push(
      "<tr><td><bdi>" +
        text(r.name) +
        " " +
        text(r.version) +
        "</bdi><br>" +
        "<code>" +
        esc(r.id) +
        "</code></td><td>" +
        esc(r.method) +
        "</td><td>" +
        esc(r.environment) +
        "</td><td>" +
        settings +
        "</td></tr>",
    );
  }
  out.push("</tbody></table>");
  const b = report.plan.budget;
  out.push(
    "<p>Run profile " +
      esc(report.plan.profile) +
      " · budget: raster ≤ " +
      String(b.max_raster_pixels) +
      " px, OCR ≤ " +
      String(b.max_run_ocr_pixels) +
      " px, timeout " +
      String(b.timeout_ms) +
      " ms, retries ≤ " +
      String(b.max_retries) +
      ". Normalization " +
      esc(report.plan.normalization_version) +
      " · alignment " +
      esc(report.plan.alignment_version) +
      ".</p>",
  );
  out.push("</section>");
  return out.join("");
}

function disclosureSection(report: Report): string {
  const exp = report.export;
  const items = exp.included.map((i) => "<li>" + esc(i) + "</li>").join("");
  const misses = exp.omissions.map((i) => "<li>" + text(i) + "</li>").join("");
  return (
    "<section><h2>Included and omitted data</h2><ul>" +
    items +
    "</ul>" +
    "<p>Omitted:</p><ul>" +
    misses +
    "</ul>" +
    "<p>Source PDF present in this report: " +
    (report.document.source_asset_id === null ? "no" : "yes") +
    ". This HTML embeds rendered excerpts, not a replay engine. Reopen the " +
    "separately exported JSON for machine-readable transforms and " +
    "configuration.</p></section>"
  );
}

/**
 * Render the complete script-free HTML document for a sealed report.
 * The report is fully re-validated (identity + hashes) before rendering,
 * and the serialized output passes the T24 script-free guard before it is
 * returned — both fail closed with ContractError.
 */
export function renderReportHtml(report: Report): string {
  validate(report);
  const readers = new Map(report.readers.map((r) => [r.id, r]));
  const doc = report.document;
  const exp = report.export;
  const execution = report.execution;
  const parts: string[] = [
    '<!doctype html><html lang="en"><head><meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width,initial-scale=1">',
    '<meta name="referrer" content="no-referrer">',
    '<meta http-equiv="Content-Security-Policy" content="' + esc(exportCsp()) + '">',
    "<title>Inkflip — evidence report</title><style>" + EXPORT_CSS + "</style></head><body><main>",
    "<p>INKFLIP / PDF READING INSPECTOR</p><h1>Two readings. One document.</h1>",
    '<p class="note">This is a ' +
      esc(exp.mode) +
      " report. " +
      esc(exp.replay) +
      ". A disagreement does not establish which reading is correct, fraud " +
      "or document safety.</p>",
    "<dl><dt>Document SHA-256</dt><dd><code>" +
      esc(doc.sha256) +
      "</code></dd><dt>Report identity</dt><dd><code>" +
      esc(report.report_id) +
      "</code></dd><dt>Document size</dt><dd>" +
      String(doc.byte_length) +
      " bytes · " +
      String(doc.page_count) +
      " page(s)</dd>" +
      (doc.display_name === null
        ? ""
        : "<dt>Original filename</dt><dd><bdi>" + text(doc.display_name) + "</bdi></dd>") +
      "<dt>Run</dt><dd>" +
      esc(execution.status) +
      " · " +
      esc(execution.result_origin) +
      " · <bdi>" +
      text(execution.environment) +
      "</bdi></dd></dl>",
  ];
  if (exp.mode === "replayable") {
    parts.push(
      '<p class="warn">This report includes the original PDF: every page ' +
        "and any hidden content. A crop is not a safe redaction.</p>",
    );
  }
  parts.push(...findingSections(report, readers));
  parts.push(...annotationSections(report));
  parts.push(...imageSections(report));
  parts.push(coverageSection(report));
  parts.push(readerSection(report));
  parts.push(disclosureSection(report));
  parts.push(
    "<footer>Generated locally. No scripts, remote fonts, external " +
      "resources or tracking links. Browser memory/download deletion is " +
      "not forensic secure erasure.</footer></main></body></html>",
  );
  const html = parts.join("\n") + "\n";
  assertScriptFreeHtml(html);
  return html;
}
