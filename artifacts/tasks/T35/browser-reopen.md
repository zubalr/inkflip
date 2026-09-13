# T35 browser reopen — named-profile after HTML

The example and `docs/READER_UPGRADE.md` ask to open the generated
named-profile after HTML and comparison HTML in a local browser.

This record is bound to implementation commit
`5c8f52ae74d1a4ee5e10ed961ef0d964c711a9df`. The earlier PDFium inspect
reopen remains under `historical-pdfium-inspect/` and is not reused here.

## What ran

1. From an ordinary shell (`python` missing on PATH) in a disposable root
   whose path contains spaces, `sh examples/reader-upgrade/run.sh` used
   `native/.venv/bin/python`, installed pypdf 5.9.0 (`before`) and 6.18.0
   (`after`), created `baselines/before.json`, compared, and wrote
   `runs/after/mapping-control.html`. Exit 0. Comparison status: unchanged.
   Copied outputs: `artifacts/tasks/T35/named-profile-run/`.
   Identities: `named-profile-run/identities.json`.
2. `python3 -m http.server 5196 --bind 127.0.0.1 --directory artifacts/tasks/T35/named-profile-run`
3. HTTP GET `http://127.0.0.1:5196/runs/after/mapping-control.html` → 200,
   `Content-type: text/html`, `Content-Length: 2633`.
   Body SHA-256 `7a72da06b05b08549b7cb9097bdd1c0c7cd85ef55915b81d8c8bdcd4011c2909`.
4. HTTP GET `http://127.0.0.1:5196/comparisons/upgrade/comparison.html` → 200,
   `Content-Length: 1761`.
   Body SHA-256 `c2d1474895548dbb34768c65c1b5217e3c5730f0d0ccfe67e3db343b9ba099d7`.
5. Cursor IDE browser tab creation failed in this session: `browser_tabs`
   returned a viewId, then `browser_navigate` reported `Browser view not
   found` / `No browser tab available`. That is not treated as a successful
   Cursor-owned reopen.
6. `agent-browser` Chromium opened the live HTTP URLs.
   After HTML title **Inkflip — evidence report**. Snapshot showed document
   SHA `19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed`,
   `profile_name=after`, `reader_version=6.18.0`, check `chk_pypdf_text_p0`
   completed, `scripts: 0`, no `chk_pdfium_text_p0`. Screenshot:
   `named-profile-run/after-browser.png`.
   Comparison HTML title **Inkflip comparison**, heading **Comparison
   unchanged**, mode `reader_upgrade`, `scripts: 0`. Screenshot:
   `named-profile-run/comparison-browser.png`.

## Disposition

Named-profile after HTML and comparison HTML visual reopen is **executed**
in Chromium via `agent-browser`. Cursor IDE browser reopen is **blocked**
in this session (tab handle vanished). Independent review remains pending.
