# T35 browser reopen

The example and `docs/READER_UPGRADE.md` ask to open generated HTML in a
local browser. Tests already assert script-free HTML with a CSP.

## What ran

1. Native CLI inspect + HTML report of `planning/fixtures/mapping-control.pdf`
   into this directory (`mapping-control.inkflip.json`, `mapping-control.html`).
   Document SHA-256 `19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed`.
   This is the same public fixture the example uses; it is a default PDFium
   inspect, not the named-profile `after` report from the unittest sandbox
   (that sandbox is deleted in `tearDownClass`).
2. `python3 -m http.server 5195 --bind 127.0.0.1 --directory artifacts/tasks/T35`
3. HTTP GET `http://127.0.0.1:5195/mapping-control.html` → 200,
   `Content-type: text/html`, `Content-Length: 2390`.
   Body SHA-256 `06a40137d13dc4d5834893b607dcb7176c498909f007294421841e838a515460`
   contains `<!doctype html>`, `Content-Security-Policy`, check
   `chk_pdfium_text_p0`, and no `<script`.
4. Cursor IDE browser (viewId `f7c6ed`) navigated to that URL. Rendered
   title **Inkflip — evidence report**. Accessibility snapshot showed
   headings `Two readings. One document.`, `What was checked`, and
   `Included and omitted data`. CDP `Runtime.evaluate` returned
   `scripts: 0`, document SHA present, `chk_pdfium_text_p0` present,
   footer `No scripts`, and CSP
   `default-src 'none'; img-src data:; style-src 'sha256-7vbGh6aU5B6pXVY91JPIFovlo1Hxk9qdZRmsB8oEf0k='; base-uri 'none'; form-action 'none'`.
5. Full-page screenshot: `artifacts/tasks/T35/mapping-control-browser.png`.

## Disposition

Visual reopen in the Cursor-owned browser is **executed**. The first
attempt in this session could not create a tab (`No browser tab
available`); a later attempt locked an existing tab and loaded the live
HTTP URL. Independent review remains pending.
