# Third-party notices and current distribution scope

This planning ZIP distributes original specifications, original helper/probe/prototype source, original fixed synthetic PDFs, and PNGs produced from those PDFs. It does not distribute parser binaries, npm packages, model weights, font files, third-party challenge implementations or private user documents.

Material engineering influences: Zubair Jashim's `mib-intake` evidence separation and adversarial-document work; Vishnu's retained visibility reasons/paint-order distinction; Henry's unrelated-ink counterexample; Handeman's watchdog/retry invariants; BMD's precise source lineage; Arthur's negative experiment ledger; ZeroInfinity's targeted OCR idea; and the grouped-evaluation lessons reported by other challenge entrants. Exact source pointers, inspection depth and limitations are in `research/sources.json` and `research/upstream-ledger.json`.

The selected implementation stack includes PDF.js/Tesseract, React/Vite, PDFium/pypdfium2, pypdf, Pillow and JSON Schema validators. Their own licenses and bundled asset notices govern their actual distribution. This notice is not a substitute for collecting license files from the resolved production artifacts. Product task T47 verifies and generates that complete distribution notice inventory before release.

The fixed PDF generator names base-14 Helvetica but embeds no font program. Raster output reflects the recorded renderer build; cross-renderer font appearance is not assumed identical. The English Tesseract model used in the executed probe is identified by its official commit, blob and SHA-256 in `config/model-assets.json`; no model bytes are shipped here.
