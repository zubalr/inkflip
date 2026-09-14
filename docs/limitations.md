# Limitations

Inkflip compares readings from a PDF. It helps locate differences; it does
not determine whether a document is authentic or which reading is correct.
The browser app is available at [inkflip-rose.vercel.app](https://inkflip-rose.vercel.app).

## Reading and comparison

- OCR can misread text, particularly on low-resolution, noisy or skewed
  scans. The bundled OCR language is English.
- Only selected pages and regions are checked. Failed, skipped and
  unsupported checks are shown with their coverage.
- Some text boxes are estimates from reader APIs. Ambiguous matches remain
  unresolved instead of being forced into a correspondence.
- Repeated strings are separate occurrences. A missing match does not by
  itself establish that text is absent from the document.
- A difference is not proof of fraud. An inspection with no findings is
  not a certification, and Inkflip does not repair or redact PDFs.

## Files, reports and offline use

- One document is active at a time. The browser session is held in memory;
  save a report before closing the tab.
- HTML reports contain the selected evidence without embedding the PDF.
  JSON can include the original PDF when explicitly selected. Including it
  includes the complete file, including any hidden content.
- Reopening JSON restores recorded evidence. Re-running an inspection also
  requires the matching source PDF and reader environment.
- Offline preparation caches the app's declared assets, models and examples.
  It does not cache user documents. Initial installation and asset download
  require a connection.
- Processing uses browser-local readers and same-origin assets. This does
  not extend to other software or extensions installed on the device.

## Browsers and accessibility

Automated browser checks cover Chromium, Firefox and Playwright WebKit.
WebKit results are separate from testing the Safari application. See
[compatibility](compatibility/README.md) for the recorded coverage.
Manual assistive-technology review is incomplete; no accessibility
conformance certification is claimed.

## Native tools and Docker

The repository includes a macOS CLI and Docker build recipes. The recorded
production image targets linux/amd64 and was exercised through emulation on
an Apple Silicon Mac. This does not establish native x86_64 hardware results,
cross-machine byte-identical builds, signing or provenance attestations.
Windows and Linux desktop applications are outside the current release.
See [distribution](distribution/README.md) for image-specific records.

The PDF.js Node profile has a separate dependency install:

```sh
cd packages/readers-pdfjs/node && bun install --frozen-lockfile
```

## Known snapshot defects

The 13 September setup check recorded failures in the web package's
standalone `typecheck` and `format:check` commands. Those checks are distinct
from the production build and registered verification suite; a successful
deployment is not evidence that these separate tooling issues are resolved.
The setup procedure also assumes Bun, Node, uv and the required browser are
installed. See [quickstart](quickstart.md).

## Support

There is no support SLA or cross-device performance guarantee.
[SECURITY.md](../SECURITY.md) describes vulnerability reporting.
Licenses and third-party notices are listed in [NOTICE](../NOTICE) and
[distribution](distribution/README.md).

## What this documentation still needs for final release

A broader native release would need fresh image-specific validation and
any signing or reproducibility claims supported separately. These items are
not implied by publication of the browser app.
