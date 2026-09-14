# Development history

Development began on 11 September 2026. The browser app was published on
14 September 2026 at [inkflip-rose.vercel.app](https://inkflip-rose.vercel.app).
Git history records the individual changes.

## Foundations

The initial work established the Bun workspace, Python runtime, pinned
dependencies, report schema and page-coordinate model. Synthetic fixtures
cover text mappings, painted-over content, rotation, repeated amounts and
other cases where rendering and extraction can disagree.

## Browser inspector

The reading pipeline combines PDF.js rendering and extraction with
Tesseract OCR. The inspector places named readings beside the page, records
incomplete checks, and supports notes and portable HTML/JSON reports.
Privacy and import tests cover local processing and untrusted report input.

## Native tools

The Python CLI adds PDFium and pypdf readers, supervised corpus processing,
version-isolated profiles, immutable baselines and reader-upgrade comparisons.
Docker recipes provide a reproducible environment for these tools.
See [distribution](distribution/README.md) for the recorded image identities
and platform limits.

## Browser release

The public release added a longer product overview, six examples, direct
file selection and clearer export controls. GitHub Actions builds and checks
the static app before promoting a Vercel deployment. The initial editorial
release is recorded in [deployment run 34867919566](https://github.com/zubalr/inkflip/actions/runs/34867919566).

## Origins

[ORIGIN](ORIGIN.md) records the snapshot import and conceptual influences.
[ATTRIBUTION](ATTRIBUTION.md) and the repository's license files record
third-party materials and notices.
