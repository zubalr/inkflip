# Browser / native compatibility (T46 / P15)

This checkout ran native PDFium inspect, the pinned Node PDF.js wrapper,
and Playwright Chromium 143.0.7499.4 plus Firefox 144.0.2 against
`fixtures/public/mapping-control.pdf` through the `@inkflip/readers-pdfjs`
browser adapter (pdfjs-dist 6.3.289). Playwright WebKit 26.0 launched but
`getTextContent` failed with a ReadableStream TypeError; that is not a
physical Safari result.

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

## Platforms

See `docs/compatibility/manual-receipt.json` and `artifacts/P15/`.
Physical Safari and Linux amd64 native remain missing and block final
acceptance. Node PDF.js is recorded but is not a browser substitute.
