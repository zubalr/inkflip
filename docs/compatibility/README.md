# Browser / native compatibility (T46 / P15)

This checkout ran native PDFium inspect and the pinned Node PDF.js wrapper
(`packages/readers-pdfjs/node/bridge.mjs`) against
`fixtures/public/mapping-control.pdf`.

Promised semantic equivalence here is:

- document SHA-256
- check terminals (completed vs failed/unsupported)
- reader/source identities recorded

Not forced equal:

- raw `getTextContent` vs native adapter strings
- occurrence geometry
- raster pixels / engine renders

`python scripts/check_manual_receipts.py compatibility` is the registered
acceptance command. It derives required profiles from
`planning/quality/PERFORMANCE_AND_COMPATIBILITY.md` (Chromium, Firefox,
physical Safari, Linux x86_64 native) and fails closed while coverage is
incomplete. `--inventory` lists missing profiles without certifying them.
Node PDF.js and Playwright WebKit are not substitutes for those profiles.

## Platforms

See `docs/compatibility/manual-receipt.json` and `artifacts/P15/platforms.json`.
Safari device observations and Linux amd64 native binaries remain missing
and block final acceptance. Browser automation results, when present, are
recorded per engine and never implied from the Node wrapper.
