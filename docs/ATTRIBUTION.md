# Attribution and provenance ledger

Started by T02 (supply-chain owner). Per `planning/security/LICENSE_AND_ATTRIBUTION.md`:
record exact upstream path/commit, copyright/license, target file, modifications
and required notice for copied or substantially adapted material; name material
influences rather than erasing them; unknown terms or absent provenance block an
asset's inclusion.

## Dependency selections (T02 freeze, 2026-09-12)

Versions selected by the planning package (`planning/config/dependencies.json`,
research sources S22–S39) were re-verified against registry.npmjs.org and
pypi.org, then locked exactly in `bun.lock` (isolated linker) and
`native/uv.lock`. No library-family substitutions were needed; every planned
pin resolved. Publish dates were checked against bunfig's 7-day
`minimumReleaseAge`: vite@8.3.0, wrangler@4.131.0, oxlint@1.82.0 and
oxfmt@0.67.0 (plus wrangler's same-day transitive workerd/miniflare) were
younger than the gate and are exempted explicitly in `bunfig.toml` — the gate
still applies to everything else.

| Package | Version | License | Role / purpose |
|---|---|---|---|
| react / react-dom | 19.2.8 | MIT | Web UI runtime |
| vite | 8.3.0 | MIT | Static build (build-time only) |
| @vitejs/plugin-react | 6.1.1 | MIT | React plugin for Vite |
| typescript | 6.0.2 | Apache-2.0 | Typecheck all packages |
| pdfjs-dist | 6.3.289 | Apache-2.0 + bundled asset notices | Browser PDF reader; runtime assets staged same-origin |
| tesseract.js | 7.0.0 | Apache-2.0 | Browser OCR wrapper; CDN defaults unused |
| tesseract.js-core | 7.0.0 | Apache-2.0 + binary notices | WASM OCR engine (single-threaded scalar/SIMD) |
| ajv | 8.18.0 | MIT | Schema-build validator generation (test/build tool). **Justified substitution:** plan pin 8.17.1 → 8.18.0 (patch bump, 2026-02-14) to clear GHSA-2g4f-4pwh-qvx6 (`$data` ReDoS); the option is unused — zero `$data` in the inkflip schema — but the advisory-free pin removes the class entirely |
| @playwright/test | 1.57.0 | Apache-2.0 | Test-only browser runner |
| @axe-core/playwright | 4.13.0 | MIT (wrapper; axe-core MPL-2.0) | Test-only accessibility audits |
| oxlint / oxfmt | 1.82.0 / 0.67.0 | MIT | Owner-selected lint/format tools |
| wrangler | 4.131.0 | MIT OR Apache-2.0 | Deploy-only static-assets publish; no Worker |
| pypdfium2 | 5.8.0 | Apache-2.0 OR BSD-3-Clause; PDFium build notices separate | Native PDFium reader |
| pypdf | 6.18.0 | BSD-3-Clause | Native PDF structure reader |
| Pillow | 12.3.0 | MIT-CMU + codec notices | Native image re-encode |
| jsonschema | 4.26.0 | MIT | Native + planning validation |
| pytest | 9.1.1 | MIT | Test-only native runner (dev group) |

Toolchain pins: node 22.23.2 (22 LTS "Jod", latest patch on freeze date),
python 3.13.15 (latest 3.13 patch; uv standalone build 20260901),
bun 1.4.0 (`packageManager`), uv ≥0.12.13 for the managed-interpreter index.

## Staged browser assets (`config/resolved-assets.json`)

Every staged file carries source, SHA-256, byte count and license in the
manifest; `scripts/prepare_assets.py verify` re-hashes them. Sources:

- **pdfjs-dist@6.3.289** (npm, Apache-2.0): `cmaps/` (169), `standard_fonts/`
  (16), `wasm/` incl. `LICENSE_OPENJPEG`/`LICENSE_JBIG2`/`LICENSE_QCMS` and
  `LICENSE_PDFJS_*` notices, `iccs/` + `LICENSE`, package `LICENSE`, plus
  `quickjs-eval.{js,wasm}` (MIT QuickJS by Fabrice Bellard and Charlie Gordon) — staged
  under `apps/web/public/assets/pdfjs/6.3.289/`.
- **tesseract.js@7.0.0** (npm, Apache-2.0): `dist/worker.min.js`,
  `dist/worker.min.js.LICENSE.txt`, `LICENSE.md` — staged under
  `apps/web/public/assets/tesseract/7.0.0/`.
- **tesseract.js-core@7.0.0** (npm, Apache-2.0 + binary notices): the six
  feature-detected `tesseract-core*.wasm.js` builds + `LICENSE` — staged under
  `apps/web/public/assets/tesseract-core/7.0.0/`.
- **tessdata_fast eng.traineddata** (upstream Apache-2.0): commit
  `65727574dfcd264acbb0c3e07860e4e9e9b22185` of
  `tesseract-ocr/tessdata_fast`, git blob `bbef4675053b5b468cdb477053e28b1c698ba08e`,
  SHA-256 `7d4322bd…7170b2`, 4,113,088 bytes — staged at
  `apps/web/public/models/tessdata-fast-eng/7d4322bd/eng.traineddata`.

## Build provenance (`build/base-image.lock.json`)

- OCI reference image `python:3.13.15-slim-trixie` pinned by index digest
  `sha256:9d2e5553…e00285` (linux/arm64 `sha256:c89921a0…44b0b4`).
- `actions/checkout@v4` resolved to commit
  `11d5960a326750d5838078e36cf38b85af677262` (v4.4.0) — recorded; the workflow
  file itself awaits the owning-surface pin (see `docs/proposals/T02.md`).
- Proof-time downloads (node 22.23.2 tarball, bun 1.4.0 zip, uv 0.12.13 wheel)
  verified against publisher checksums inside the Linux proof.

## Material influences and blocked items

- tesseract.js's default CDN endpoints (jsdelivr for worker/core/lang data)
  are documented upstream behavior we deliberately do not use: the adapter
  contract requires explicit same-origin paths with `workerBlobURL:false`.
- `opencollective-postinstall` (tesseract.js transitive dep) runs a
  donation-message install script; `trustedDependencies` stays `[]` so it is
  blocked with no capability loss.
- No code was copied from upstream sources in T02; `scripts/prepare_assets.py`
  and `scripts/check_dependencies.py` are original implementations. RapidOCR
  and browser-PDFium candidates remain controlled experiments and are absent.

## T12 — comparison normalization and alignment (2026-09-12)

`packages/compare/normalization/` and `packages/compare/alignment/` are
original implementations written against `planning/architecture/
ALIGNMENT_AND_FINDINGS.md` (contract 1.0.0). No third-party code was
copied or adapted:

- The whitespace-collapse itself reuses the contract package's own
  `normalize`/`WS` (T03) so normalized views are byte-for-byte the
  contract views; the Unicode `White_Space` membership table originates
  there, not in this module.
- Standard textbook techniques are used without vendored source: scalar
  Levenshtein dynamic programming (`alignment/text.ts`), a bounded
  non-crossing interval assignment (`alignment/match.ts`), segment
  intersection/point-in-polygon tests (`alignment/spatial.ts`) built on
  the project geometry package's predicates (T04).
- The frozen cost weights (0.65/0.20/0.15), acceptance thresholds
  (0.45/0.12), span cap (4) and component cap (64) are specified by the
  planning document, not tuned against fixtures.

### Local Tesseract client patch

The Apache-2.0 tesseract.js 7.0.0 source constructor and its types carry the
Inkflip cancellation patch in `patches/tesseract.js@7.0.0.patch`. Upstream and
modified hashes are recorded in `config/dependency-patches.json`. The staged
worker, WASM and model bytes and existing license notices are unchanged.

## T16 — portable JSON + escaped HTML export foundation (2026-09-13)

- `packages/reports/export/html.ts`: The static HTML report stylesheet (`EXPORT_CSS`) and document layout adapt the reference template in `planning/tools/export_html.py` (an assigned project task input), with additions for `h3`, `.warn`, `ul` and strict static HTML hardening (meta CSP with runtime style SHA-256 derivation, script-free assertions, and sanitized PNG re-encoding).

## T30 — native HTML report conversion (2026-09-13)

- `native/inkflip/cli/html.py`: Script-free portable HTML for validated reports and comparisons adapts the same `planning/tools/export_html.py` stylesheet tokens (colors, type scale, section cards) with a CSP `style-src` hash and no script tags.

## T40 — native containment recipe (2026-09-13)

- `build/native/Dockerfile` follows `planning/deployment/examples/Dockerfile.native` and pins the T02-recorded `python:3.13.15-slim-trixie` index digest. No third-party Dockerfile was copied beyond that planning recipe.

## T46 — compatibility receipt checker (2026-09-13)

- `scripts/check_manual_receipts.py` is a small shared checker (T37/T46/T53 kinds). T46 lands the `compatibility` kind so the documented command can run. Other kinds fail closed until their owners add receipts. See `docs/proposals/T46.md`.

