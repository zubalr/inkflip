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
 * Fixed application-owned stylesheet.
 * Adapted from the reference stylesheet in `planning/tools/export_html.py` with
 * additional rules for h3, .warn, .lede, wrapping, print, and ul styling.
 * Any edit changes the CSP hash — the two are derived together at render time
 * so they can never drift. Palette follows the product tokens (paper/ink, teal/rust accents).
 */
export const EXPORT_CSS =
  "body{margin:0;background:#f5f3ee;color:#192327;font:16px/1.55 system-ui,sans-serif}" +
  "main{max-width:1100px;margin:0 auto;padding:32px 24px}" +
  "h1{font-size:28px;line-height:1.2;overflow-wrap:anywhere;margin:8px 0 16px}" +
  "h2{font-size:20px;margin-top:28px;overflow-wrap:anywhere}" +
  "h3{font-size:16px;margin-top:20px;overflow-wrap:anywhere}" +
  ".lede{font-size:18px;margin:0 0 16px;overflow-wrap:anywhere}" +
  ".note{border-left:4px solid #84621e;padding:12px 18px;background:#fff9e9;overflow-wrap:anywhere}" +
  ".warn{border-left:4px solid #934420;padding:12px 18px;background:#fdf0e6;overflow-wrap:anywhere}" +
  "section{background:#fff;padding:20px 24px;margin:20px 0;border:1px solid #d5d9d7;border-radius:12px}" +
  "pre,code,p,li,dd,td,th,h1,h2,h3{overflow-wrap:anywhere}" +
  "pre{white-space:pre-wrap;font:14px/1.55 ui-monospace,monospace}" +
  "img{max-width:100%;height:auto;border:1px solid #d5d9d7}" +
  "dt{font-weight:700}dd{margin:0 0 12px;overflow-wrap:anywhere}" +
  ".tableWrap{overflow-x:auto}" +
  "table{border-collapse:collapse;width:100%;min-width:280px}" +
  "th,td{border-bottom:1px solid #ddd;text-align:left;padding:8px;vertical-align:top}" +
  "ul{margin:8px 0;padding-left:24px}footer{font-size:13px;overflow-wrap:anywhere}" +
  "@media(max-width:640px){main{padding:20px 14px}section{padding:14px}h1{font-size:24px}table{font-size:14px}}" +
  "@media print{body{background:#fff}main{max-width:none;padding:12mm}section{break-inside:avoid;border-radius:0}.note,.warn{break-inside:avoid}}";

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

function jsonIncludesOriginalPdf(report: Report): boolean {
  return (
    report.document.source_asset_id !== null ||
    report.export.included.includes("source_pdf") ||
    report.export.mode === "replayable"
  );
}

function heading(report: Report): string {
  const name = report.document.display_name;
  if (name !== null && name !== "") return name;
  return "Reading report";
}

function summaryLine(report: Report): string {
  const findings = report.findings.length;
  const selected = report.plan.selected_pages.length;
  const pages = report.document.page_count;
  const completed = report.checks.filter((c) => c.status === "completed").length;
  const checks = report.checks.length;
  const incomplete = [
    ...new Set(
      report.checks.filter((c) => c.status !== "completed").map((c) => c.status),
    ),
  ];
  const findingBit =
    findings === 0
      ? "No differences recorded."
      : findings === 1
        ? "1 difference is included."
        : String(findings) + " differences are included.";
  const pageBit =
    "Checked " +
    String(selected) +
    " of " +
    String(pages) +
    (pages === 1 ? " page." : " pages.");
  const checkBit =
    String(completed) +
    " of " +
    String(checks) +
    (checks === 1 ? " check finished." : " checks finished.");
  const incompleteBit =
    incomplete.length === 0
      ? ""
      : " Some checks did not finish (" + incomplete.join(", ") + ").";
  return findingBit + " " + pageBit + " " + checkBit + incompleteBit;
}

function findingSections(
  report: Report,
  readers: Map<string, Report["readers"][number]>,
): string[] {
  const out: string[] = [];
  const occurrences = new Map(report.occurrences.map((o) => [o.id, o]));
  if (report.findings.length === 0) {
    out.push(
      "<section><h2>Differences</h2><p>No differences were recorded in this export.</p></section>",
    );
    return out;
  }
  for (const f of report.findings) {
    out.push(
      "<section><h2>" + text(f.title) + "</h2><p>" + text(f.explanation) + "</p>",
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
    out.push(
      "<p>Kind " +
        esc(f.kind) +
        " · alignment " +
        esc(f.alignment) +
        " · basis " +
        text(f.basis) +
        "</p></section>",
    );
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
    "<h3>What was checked</h3><div class=\"tableWrap\"><table><thead><tr>" +
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
  out.push("</tbody></table></div>");
  return out.join("");
}

function coverageSection(report: Report): string {
  const completed = report.checks.filter((c) => c.status === "completed").length;
  return (
    checkTable(report) +
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
    "pages — never a document-wide verdict.</p>"
  );
}

function readerSection(report: Report): string {
  const out = [
    "<h3>Readers, settings and limits</h3><div class=\"tableWrap\"><table><thead><tr>" +
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
  out.push("</tbody></table></div>");
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
  return out.join("");
}

function disclosureSection(report: Report): string {
  const exp = report.export;
  const items = exp.included.map((i) => "<li>" + esc(i) + "</li>").join("");
  const misses = exp.omissions.map((i) => "<li>" + text(i) + "</li>").join("");
  const jsonBit = jsonIncludesOriginalPdf(report)
    ? "The separately saved JSON includes the original PDF."
    : "The separately saved JSON also omitted the original PDF.";
  return (
    "<h3>Included and omitted data</h3><ul>" +
    items +
    "</ul>" +
    "<p>Omitted:</p><ul>" +
    misses +
    "</ul>" +
    "<p>This HTML file does not contain the original PDF. " +
    jsonBit +
    " This HTML embeds rendered excerpts when they were selected, not a " +
    "replay engine. Reopen the separately exported JSON in Inkflip for " +
    "machine-readable transforms and configuration.</p>"
  );
}

function technicalSection(report: Report): string {
  const doc = report.document;
  const execution = report.execution;
  return (
    "<section><h2>Technical details</h2><dl><dt>Document SHA-256</dt><dd><code>" +
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
    "</bdi></dd></dl>" +
    coverageSection(report) +
    readerSection(report) +
    disclosureSection(report) +
    "</section>"
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
  const parts: string[] = [
    '<!doctype html><html lang="en"><head><meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width,initial-scale=1">',
    '<meta name="referrer" content="no-referrer">',
    '<meta http-equiv="Content-Security-Policy" content="' + esc(exportCsp()) + '">',
    "<title>Inkflip — reading report</title><style>" + EXPORT_CSS + "</style></head><body><main>",
    "<p>INKFLIP / PDF READING INSPECTOR</p><h1><bdi>" + text(heading(report)) + "</bdi></h1>",
    '<p class="lede">' + esc(summaryLine(report)) + "</p>",
    '<p class="note">A disagreement does not establish which reading is correct, fraud or document safety. This HTML file is not a replayable inspection.</p>',
  ];
  if (jsonIncludesOriginalPdf(report)) {
    parts.push(
      '<p class="warn">The separately saved JSON includes the original PDF: every page ' +
        "and any hidden content. This HTML file does not contain those PDF bytes and " +
        "cannot reopen the inspection by itself. A crop is not a safe redaction.</p>",
    );
  }
  parts.push(...imageSections(report));
  parts.push(...findingSections(report, readers));
  parts.push(...annotationSections(report));
  parts.push(technicalSection(report));
  parts.push(
    "<footer>Generated locally. No scripts, remote fonts, external " +
      "resources or tracking links. Browser memory/download deletion is " +
      "not forensic secure erasure.</footer></main></body></html>",
  );
  const html = parts.join("\n") + "\n";
  assertScriptFreeHtml(html);
  return html;
}
