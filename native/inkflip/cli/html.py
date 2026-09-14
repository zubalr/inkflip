"""Script-free portable HTML conversion for validated reports."""
from __future__ import annotations

import base64
import hashlib
import html
from typing import Any

from inkflip.contracts import core

HTML_CSS = (
    "body{margin:0;background:#f5f3ee;color:#192327;font:16px/1.6 system-ui,sans-serif}"
    "main{max-width:850px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.15}"
    "h2{font-size:23px;margin-top:32px}.note{border-left:4px solid #84621e;padding:12px 18px;background:#fff9e9}"
    "section{background:white;padding:20px 24px;margin:20px 0;border:1px solid #d5d9d7;border-radius:12px}"
    "pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace}"
    "img{max-width:100%;height:auto;border:1px solid #d5d9d7}dt{font-weight:700}dd{margin:0 0 12px}"
    "table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #ddd;text-align:left;padding:8px;vertical-align:top}"
    "code{overflow-wrap:anywhere}footer{font-size:13px}"
    "@media(max-width:500px){main{padding:20px 14px}section{padding:14px}h1{font-size:28px}}"
)


def render_html_report(report: dict[str, Any]) -> str:
    core.validate(report)
    if report.get("kind") != "report":
        raise ValueError("Only report artifacts can be converted to HTML")

    css_hash = base64.b64encode(hashlib.sha256(HTML_CSS.encode()).digest()).decode()
    csp = (
        "default-src 'none'; img-src data:; style-src 'sha256-"
        f"{css_hash}'; base-uri 'none'; form-action 'none'"
    )
    document = report["document"]
    export = report["export"]
    execution = report["execution"]
    readers = {reader["id"]: reader for reader in report["readers"]}

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    lines = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta name="referrer" content="no-referrer">',
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">',
        f"<title>Inkflip — evidence report</title><style>{HTML_CSS}</style></head><body><main>",
        "<p>INKFLIP / PDF READING INSPECTOR</p><h1>Two readings. One document.</h1>",
        f'<p class="note">This is a {esc(export.get("mode"))} report. {esc(export.get("replay"))}. '
        "A disagreement does not establish which reading is correct, fraud or document safety.</p>",
        "<dl>",
        f"<dt>Document SHA-256</dt><dd><code>{esc(document.get('sha256'))}</code></dd>",
        f"<dt>Report identity</dt><dd><code>{esc(report.get('report_id'))}</code></dd>",
        f"<dt>Run</dt><dd>{esc(execution.get('status'))} · {esc(execution.get('result_origin'))}</dd>",
        f"<dt>Environment</dt><dd><code>{esc(execution.get('environment'))}</code></dd>",
        "</dl>",
    ]
    for finding in report.get("findings", []):
        lines.append(f"<section><h2>{esc(finding.get('title'))}</h2><p>{esc(finding.get('explanation'))}</p>")
        lines.append(
            f"<p>Finding kind: {esc(finding.get('kind'))} · Alignment: {esc(finding.get('alignment'))}</p>"
        )
        for oid in finding.get("occurrence_ids", []):
            occurrence = next((item for item in report.get("occurrences", []) if item.get("id") == oid), None)
            if occurrence:
                reader = readers.get(occurrence.get("reader_id"), {})
                lines.append(f"<h3>{esc(reader.get('name'))} {esc(reader.get('version'))}</h3>")
                lines.append(f"<pre>{esc(occurrence.get('raw_text'))}</pre>")
                lines.append(
                    f"<p>Page {occurrence.get('page_index', 0)+1} · geometry "
                    f"{esc(occurrence.get('geometry', {}).get('precision'))}</p>"
                )
        lines.append("</section>")
    lines.append(
        "<section><h2>What was checked</h2><table><thead><tr><th>Check</th><th>Status</th>"
        "<th>Produced</th></tr></thead><tbody>"
    )
    for check in report.get("checks", []):
        lines.append(
            f"<tr><td>{esc(check.get('id'))}</td><td>{esc(check.get('status'))}</td>"
            f"<td>{check.get('produced_occurrence_count', 0)}</td></tr>"
        )
    lines.append("</tbody></table></section>")
    lines.append("<section><h2>Included and omitted data</h2>")
    lines.append(f"<p>Included: {esc(', '.join(export.get('included', [])))}</p>")
    lines.append(f"<p>Omissions: {esc(', '.join(export.get('omissions', [])))}</p>")
    lines.append("</section>")
    lines.append(
        "<footer>Generated locally. No scripts, remote fonts or tracking links.</footer></main></body></html>"
    )
    return "\n".join(lines) + "\n"


def render_html_comparison(comparison: dict[str, Any], extra: str = "") -> str:
    core.validate(comparison)
    css_hash = base64.b64encode(hashlib.sha256(HTML_CSS.encode()).digest()).decode()
    csp = (
        "default-src 'none'; img-src data:; style-src 'sha256-"
        f"{css_hash}'; base-uri 'none'; form-action 'none'"
    )

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    limitation_items = "".join(
        f"<li>{esc(item)}</li>" for item in comparison.get("limitations") or []
    )
    limitations_block = (
        f"<section><h2>Limitations</h2><ul>{limitation_items}</ul></section>"
        if limitation_items
        else ""
    )
    rows = []
    for change in comparison.get("changes", []):
        rows.append(
            "<tr>"
            f"<td>{esc(change.get('id'))}</td>"
            f"<td>{esc(change.get('kind'))}</td>"
            f"<td>{esc(change.get('status'))}</td>"
            f"<td>{esc(change.get('rule_id'))}</td>"
            f"<td>{esc(change.get('explanation'))}</td>"
            "</tr>"
        )
    body_rows = "".join(rows) or "<tr><td colspan='5'>No recorded changes.</td></tr>"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='referrer' content='no-referrer'>"
        f"<meta http-equiv='Content-Security-Policy' content='{csp}'>"
        f"<title>Inkflip comparison</title><style>{HTML_CSS}</style></head><body><main>"
        "<p>INKFLIP / PDF READING INSPECTOR</p>"
        f"<h1>Comparison {esc(comparison.get('status'))}</h1>"
        f"<p>Mode {esc(comparison.get('mode'))}. Left {esc(comparison.get('left_report_id'))}. "
        f"Right {esc(comparison.get('right_report_id'))}.</p>"
        f"{limitations_block}{extra}"
        "<table><thead><tr><th>Id</th><th>Kind</th><th>Status</th><th>Rule</th>"
        "<th>Explanation</th></tr></thead><tbody>"
        f"{body_rows}</tbody></table>"
        "<footer>Generated locally. No scripts or remote resources.</footer>"
        "</main></body></html>\n"
    )
