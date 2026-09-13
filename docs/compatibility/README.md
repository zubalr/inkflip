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

## Platforms

See `docs/compatibility/manual-receipt.json` and `artifacts/P15/platforms.json`.
Chromium, Firefox, WebKit GUI and Linux amd64 binaries were **unavailable**
in this allocation and are recorded as such. Missing-device checks stay
pending for final acceptance.
