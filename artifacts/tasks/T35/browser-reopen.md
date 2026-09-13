# T35 browser reopen attempt

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
3. `curl -sI http://127.0.0.1:5195/mapping-control.html` → HTTP 200,
   `Content-type: text/html`, `Content-Length: 2390`
4. Body SHA-256 `06a40137d13dc4d5834893b607dcb7176c498909f007294421841e838a515460`
   contains `<!doctype html>`, `Content-Security-Policy`, check
   `chk_pdfium_text_p0`, and no `<script`.
5. Cursor IDE browser MCP `browser_tabs` list: empty. `browser_navigate`
   with `newTab: true` to that URL returned **No browser tab available**.
   `file://` navigation is also blocked by that MCP.

## Disposition

Visual reopen inside the Cursor-owned browser is **blocked** by missing
browser-tab capability. HTML generation, contract tests, and HTTP fetch
are executed. A human or a later reviewer with a working browser can open
the committed `mapping-control.html`.
