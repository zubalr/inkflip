#!/usr/bin/env python3
"""Generate a bounded, script-free human report from a validated Inkflip JSON report.
Reference utility, not the final product export UI. Only generated, sanitized PNGs
should be published. The final product adds full bounded decode/reencode (T24).
"""
from __future__ import annotations
import argparse, base64, hashlib, html
from pathlib import Path
from contractlib import loads_strict, validate
CSS='''body{margin:0;background:#f5f3ee;color:#192327;font:16px/1.6 system-ui,sans-serif}main{max-width:850px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.15}h2{font-size:23px;margin-top:32px}.note{border-left:4px solid #84621e;padding:12px 18px;background:#fff9e9}section{background:white;padding:20px 24px;margin:20px 0;border:1px solid #d5d9d7;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace}img{max-width:100%;height:auto;border:1px solid #d5d9d7}dt{font-weight:700}dd{margin:0 0 12px}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #ddd;text-align:left;padding:8px;vertical-align:top}code{overflow-wrap:anywhere}footer{font-size:13px}@media(max-width:500px){main{padding:20px 14px}section{padding:14px}h1{font-size:28px}}'''
def esc(value):return html.escape(str(value),quote=True)
def render(report: dict) -> str:
    validate(report)
    if report['kind']!='report': raise ValueError('This reference exporter supports report artifacts only')
    csp="default-src 'none'; img-src data:; style-src 'sha256-"+base64.b64encode(hashlib.sha256(CSS.encode()).digest()).decode()+"'; base-uri 'none'; form-action 'none'"
    doc=report['document'];exp=report['export'];execution=report['execution'];reader={r['id']:r for r in report['readers']}
    s=['<!doctype html><html lang="en"><head><meta charset="utf-8">', '<meta name="viewport" content="width=device-width,initial-scale=1">', '<meta name="referrer" content="no-referrer">','<meta http-equiv="Content-Security-Policy" content="'+esc(csp)+'">','<title>Inkflip — evidence report</title><style>'+CSS+'</style></head><body><main>', '<p>INKFLIP / PDF READING INSPECTOR</p><h1>Two readings. One document.</h1>', '<p class="note">This is a '+esc(exp['mode'])+' report. '+esc(exp['replay'])+'. A disagreement does not establish which reading is correct, fraud or document safety.</p>', '<dl><dt>Document SHA-256</dt><dd><code>'+esc(doc['sha256'])+'</code></dd><dt>Report identity</dt><dd><code>'+esc(report['report_id'])+'</code></dd><dt>Run</dt><dd>'+esc(execution['status'])+' · '+esc(execution['result_origin'])+'</dd></dl>']
    for f in report['findings']:
        s+=['<section><h2>'+esc(f['title'])+'</h2><p>'+esc(f['explanation'])+'</p>','<p>Finding kind: '+esc(f['kind'])+' · Alignment: '+esc(f['alignment'])+'</p>']
        if f['limitations']:s.append('<p>Limits: '+esc('; '.join(f['limitations']))+'</p>')
        for oid in f['occurrence_ids']:
            o=next(o for o in report['occurrences'] if o['id']==oid);r=reader[o['reader_id']]
            s+=['<h3>'+esc(r['name'])+' '+esc(r['version'])+'</h3><pre>'+esc(o['raw_text'])+'</pre><p>Page '+str(o['page_index']+1)+' · geometry '+esc(o['geometry']['precision'])+' · occurrence '+esc(o['id'])+'</p>']
        s.append('</section>')
    for asset in report['assets']:
        if asset['media_type']=='image/png' and asset['purpose']=='crop':
            s+=['<section><h2>Included source excerpt</h2><p>Original rendered crop, not a certified redaction.</p>','<img alt="Rendered excerpt for the recorded finding; text alternatives are the named readings above." src="data:image/png;base64,'+asset['data_base64']+'"></section>']
    s+=['<section><h2>What was checked</h2><table><thead><tr><th>Check</th><th>Status</th><th>Reason / produced readings</th></tr></thead><tbody>']
    for c in report['checks']:
        s.append('<tr><td>'+esc(c['id'])+'</td><td>'+esc(c['status'])+'</td><td>'+esc(c['reason'])+' / '+str(c['produced_occurrence_count'])+'</td></tr>')
    s+=['</tbody></table><p>Agreement is limited to completed, comparable readings. Unsupported, unselected, failed and cancelled work is not an all-clear.</p></section>', '<section><h2>Included and omitted data</h2><p>Included: '+esc(', '.join(exp['included']))+'</p><p>Omitted: '+esc(', '.join(exp['omissions']))+'</p><p>Source PDF present in machine report: '+('yes' if doc['source_asset_id'] else 'no')+'. This HTML embeds rendered excerpts, not a replay engine. Reopen the separately exported JSON for machine-readable transforms and configuration.</p></section>', '<footer>Generated locally. No scripts, remote fonts, external resources or tracking links. Browser memory/download deletion is not forensic secure erasure.</footer></main></body></html>']
    return '\n'.join(s)+'\n'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.resolve()==a.report.resolve():raise SystemExit('Output cannot replace source report')
    if a.out.exists():raise SystemExit('Refusing overwrite; select a new output path')
    text=render(loads_strict(a.report.read_bytes()));a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text,encoding='utf-8');print(a.out.name)
if __name__=='__main__':main()
