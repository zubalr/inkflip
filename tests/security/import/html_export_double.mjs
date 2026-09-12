// Test double for the script-free HTML report export.
//
// planning/tools/export_html.py is the frozen reference exporter; it
// cannot run here because its contractlib import needs the (uninstalled)
// planning `jsonschema` dependency. This double reproduces its exact
// security semantics — same fixed stylesheet, same meta-CSP formula
// (default-src 'none'; img-src data:; style-src 'sha256-<hash>';
// base-uri 'none'; form-action 'none'), same escape-everything rule via
// escapeHtml, same content sections — so tests can prove the script-free
// invariant that the T16 product exporter must also satisfy. It is NOT
// the product exporter and deliberately lives under tests/.
//
// Image embedding uses the *sanitized* PNG re-encodes produced by the
// import gate, never the attacker-supplied asset bytes.
import { createHash } from 'node:crypto';
import { escapeHtml } from '../../../packages/reports/validation/html_guard.ts';

export const CSS =
  'body{margin:0;background:#f5f3ee;color:#192327;font:16px/1.6 system-ui,sans-serif}' +
  'main{max-width:850px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.15}' +
  'h2{font-size:23px;margin-top:32px}.note{border-left:4px solid #84621e;padding:12px 18px;background:#fff9e9}' +
  'section{background:white;padding:20px 24px;margin:20px 0;border:1px solid #d5d9d7;border-radius:12px}' +
  'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace}' +
  'img{max-width:100%;height:auto;border:1px solid #d5d9d7}dt{font-weight:700}dd{margin:0 0 12px}' +
  'table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #ddd;text-align:left;padding:8px;vertical-align:top}' +
  'code{overflow-wrap:anywhere}footer{font-size:13px}';

export function cssCspHash() {
  return createHash('sha256').update(CSS, 'utf8').digest('base64');
}

const b64 = (u8) => Buffer.from(u8).toString('base64');

/**
 * Render the script-free HTML report, mirroring the reference exporter.
 * `report` is a validated report object; `sanitizedPngs` is the
 * Map<assetId, SanitizedPng> returned by the import gate.
 */
export function renderHtmlReport(report, sanitizedPngs = new Map()) {
  const esc = escapeHtml;
  const csp =
    "default-src 'none'; img-src data:; style-src 'sha256-" +
    cssCspHash() +
    "'; base-uri 'none'; form-action 'none'";
  const doc = report.document;
  const exp = report.export;
  const execution = report.execution;
  const readers = new Map(report.readers.map((r) => [r.id, r]));
  const s = [
    '<!doctype html><html lang="en"><head><meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width,initial-scale=1">',
    '<meta name="referrer" content="no-referrer">',
    '<meta http-equiv="Content-Security-Policy" content="' + esc(csp) + '">',
    '<title>Inkflip — evidence report</title><style>' + CSS + '</style></head><body><main>',
    '<p>INKFLIP / PDF READING INSPECTOR</p><h1>Two readings. One document.</h1>',
    '<p class="note">This is a ' + esc(exp.mode) + ' report. ' + esc(exp.replay) +
      '. A disagreement does not establish which reading is correct, fraud or document safety.</p>',
    '<dl><dt>Document SHA-256</dt><dd><code>' + esc(doc.sha256) +
      '</code></dd><dt>Report identity</dt><dd><code>' + esc(report.report_id) +
      '</code></dd><dt>Run</dt><dd>' + esc(execution.status) + ' · ' +
      esc(execution.result_origin) + '</dd></dl>',
  ];
  for (const f of report.findings) {
    s.push(
      '<section><h2>' + esc(f.title) + '</h2><p>' + esc(f.explanation) + '</p>',
      '<p>Finding kind: ' + esc(f.kind) + ' · Alignment: ' + esc(f.alignment) + '</p>',
    );
    if (f.limitations.length) s.push('<p>Limits: ' + esc(f.limitations.join('; ')) + '</p>');
    for (const oid of f.occurrence_ids) {
      const o = report.occurrences.find((x) => x.id === oid);
      const r = readers.get(o.reader_id);
      s.push(
        '<h3>' + esc(r.name) + ' ' + esc(r.version) + '</h3><pre>' + esc(o.raw_text) + '</pre>',
        '<p>Page ' + String(o.page_index + 1) + ' · geometry ' + esc(o.geometry.precision) +
          ' · occurrence ' + esc(o.id) + '</p>',
      );
    }
    s.push('</section>');
  }
  for (const asset of report.assets) {
    if (asset.media_type === 'image/png' && asset.purpose === 'crop') {
      const clean = sanitizedPngs.get(asset.id);
      // Only the sanitized re-encode is embedded, never the raw import bytes.
      if (!clean) throw new Error('Missing sanitized PNG for ' + asset.id);
      const data = b64(clean.png);
      s.push(
        '<section><h2>Included source excerpt</h2><p>Original rendered crop, not a certified redaction.</p>',
        '<img alt="Rendered excerpt for the recorded finding; text alternatives are the named readings above." src="data:image/png;base64,' +
          data + '"></section>',
      );
    }
  }
  s.push(
    '<section><h2>What was checked</h2><table><thead><tr><th>Check</th><th>Status</th><th>Reason / produced readings</th></tr></thead><tbody>',
  );
  for (const c of report.checks) {
    s.push(
      '<tr><td>' + esc(c.id) + '</td><td>' + esc(c.status) + '</td><td>' +
        esc(String(c.reason)) + ' / ' + String(c.produced_occurrence_count) + '</td></tr>',
    );
  }
  s.push(
    '</tbody></table><p>Agreement is limited to completed, comparable readings. Unsupported, unselected, failed and cancelled work is not an all-clear.</p></section>',
    '<section><h2>Included and omitted data</h2><p>Included: ' + esc(exp.included.join(', ')) +
      '</p><p>Omitted: ' + esc(exp.omissions.join(', ')) +
      '</p><p>Source PDF present in machine report: ' +
      (doc.source_asset_id ? 'yes' : 'no') +
      '. This HTML embeds rendered excerpts, not a replay engine. Reopen the separately exported JSON for machine-readable transforms and configuration.</p></section>',
    '<footer>Generated locally. No scripts, remote fonts, external resources or tracking links. Browser memory/download deletion is not forensic secure erasure.</footer></main></body></html>',
  );
  return s.join('\n') + '\n';
}
