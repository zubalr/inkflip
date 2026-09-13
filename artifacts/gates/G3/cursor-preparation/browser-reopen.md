# G3 cursor preparation — HTML transfer and browser reopen

This is **not** a `gate.py G3` receipt. `python scripts/gate.py G3` was not run.

Implementation commit: `95438c95fc36c5e10052119829b147a24d2c6fad`
Base (T35 repair): `78750769d1a29d58b7b79f91c1c8ffd749dc4eac`

## Files opened

Served at `http://127.0.0.1:5196` was **not** used (T35 used 5196). This reopen used
`http://127.0.0.1:5197/` from `python3 -m http.server` bound to the
`artifacts/gates/G3/cursor-preparation/` directory, then `agent-browser`
(Cursor IDE browser tab creation failed in the prior T35 session).

| File | SHA-256 | Bytes |
|---|---|---|
| `inspect.html` | `febf16eabc3c7fee6530a56356d5b120300362f1830c21e7e62c4d96e9b6365c` | 2388 |
| `inspect.json` | `d2f1aa467eee34287cbe4e34cdab07e2e004a5ac4fd5fbf9a3d64636f32a2271` | 10816 |
| `comparison.html` | `1d67710efd525a3390046932a5a9e026b774d10a3ca1363bda0d4ac617abb82e` | 1925 |
| `comparison.json` | `17358cd8137ddca8899f093bb27d807a63b7fe7e9cf68e5b2c8f5d126e8ef570` | 1371 |

## Observed identities (inspect HTML)

Opened `inspect.html` produced by `PYTHONPATH=native python -m inkflip.cli inspect … --reader pypdf` then `report --format html`. This is a **named pypdf** inspect, not a default PDFium HTML:

- Document SHA-256: `19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed` (mapping-control.pdf)
- Report identity: `32fa2820b0fa8b49c8c495fa64ebec1b0db13d27328efdc696412ad284ac570f`
- Check: `chk_pypdf_text_p0` completed
- Reader in JSON: `pypdf-native` / pypdf 6.18.0
- Environment string in HTML: `Python 3.13.15; darwin; algorithm=inkflip-inspect-v1; profile_name=native-default`
- CSP present; no `<script>` tags
- Screenshot: `inspect-reopen.png`
- Accessibility snapshot: `inspect-snapshot.txt`

## Observed comparison HTML

`comparison.html` is from a **declared regression** compare (mutated corpus run vs immutable baseline using `examples/reader-upgrade/upgrade-rules.json`). Exit code 5. Headline in the browser: **Comparison regressed**. Rules `mapping-control-expected-text` and `mapping-control-coverage` reported missing expected text/coverage. That is the G3 scenario for declared regression, not a silent pass.

Screenshot: `comparison-reopen.png`. Snapshot: `comparison-snapshot.txt`.

The HTTP server was stopped after screenshots.
