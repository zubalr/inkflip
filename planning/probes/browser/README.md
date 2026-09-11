# P07 — actual browser-reader probe (not executed here)

Status: **blocked / not run** in planning because container npm registry access failed. No PDF.js/Tesseract.js browser output, production own-file privacy, target-device result or CSP compatibility has been fabricated. Native P01 is separate proof.

This small source probe exercises a real local File, PDF.js first-page rendering/text and optional Tesseract.js OCR. It does not implement the complete app, alignment/export/state/security contract or G1 by itself. It is intended for owned fixed synthetic fixtures on localhost; not a hardened arbitrary-PDF viewer.

After T02 has resolved/verified the exact dependencies and model asset, from the package root:

```sh
pnpm --dir probes/browser install --ignore-scripts
python probes/browser/prepare_model.py --eng /absolute/path/to/verified/eng.traineddata
python -m http.server 8765 --bind 127.0.0.1
```

Open localhost port 8765, path `/probes/browser/index.html`. Explicitly open `fixtures/mapping-amount.pdf`, inspect the actual raw reading, run OCR on the rendered first page, and repeat with `mapping-control.pdf` and a renamed identical copy. The model preparer refuses a wrong hash. The local server serves only this package; do not use it from a directory containing private documents. Application readers must later use versioned static assets rather than expose `node_modules` publicly.

Acceptance: actual PDF.js output contains `$1,000` for the mapping file and `$100` for the control; actual first-page rendering is the same for both under the same build; reader/version printed from runtime, no filename branch; OCR output recorded without deciding truth; cancel destroys pending reader/OCR work and later events cannot replace the current run. G1 additionally needs production geometry, selected export/reopen, clean searchable-scan control and canary/CSP/network tests on the real built application.

Record runtime/browser/package lock, source/model SHA-256, rendered pixel dimensions, raw output, elapsed measurements, cancellation result and network capture. Save `artifacts/P07/result.json` in the implementation repository. Never overwrite the planning `browser-status.json` with a claimed pass unless this probe and its stated acceptance actually execute. T02 may select a maintained compatible patch with recorded evidence if a selected pin fails installation; it may not silently change libraries, download from a runtime CDN or add paid compute.
