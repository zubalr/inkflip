# Browser / native compatibility (T46 / P15)

This checkout ran native PDFium inspect, the pinned Node PDF.js wrapper
(v22.23.2; historical unpinned host observation remains v26.7.0), and
Playwright Chromium 143.0.7499.4, Firefox 144.0.2, and WebKit 26.0 against
`fixtures/public/mapping-control.pdf` through the `@inkflip/readers-pdfjs`
browser adapter (pdfjs-dist 6.3.289). WebKit `native_text` completed after
an adapter repair for missing `ReadableStream` async iteration. Playwright
WebKit is not a physical Safari result.

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
Physical Safari, Linux amd64 native, Chromium previous-stable, and Firefox
ESR remain missing and block final acceptance. Node PDF.js is recorded but
is not a browser substitute. Do not treat `webkit-safari` as `safari`.
Cold/missing, prepared/warm, wrong-hash, and clear OCR-cache observations
were executed through the merged T25 `tests/privacy/cache.spec.ts` (4/4).
