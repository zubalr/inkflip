# License, dependencies and attribution decision

**Selected new-code license: MIT**, subject to the owner's publication approval. New synthetic fixture recipes and original report/prototype code use the same license. User documents remain theirs; the app claims no ownership, training rights or automatic publication. This is an engineering distribution plan, not legal advice.

The primary product does not distribute PyMuPDF. Its AGPL/commercial terms are a consequential choice, not something an MIT notice or separate service automatically eliminates. Retain the old repository's license disclosures accurately and do not claim the combined legacy stack was universally permissive. Any later PyMuPDF-based distribution is a new ADR and qualified-review gate. [Artifex](../research/SOURCES.md#s39).

| Material | Selected treatment | Release evidence required |
|---|---|---|
| React/Vite/pnpm and own TypeScript modules | Selected permissive stack; no third-party runtime telemetry | Exact npm lock, license files and transitive inventory |
| PDF.js distribution | Apache-2.0 with complete selected build's asset notices | Main+worker match, CMaps/standard-font/WASM inventory, notices from actual package |
| Tesseract.js/core and English model | Apache-2.0 plus applicable binary/transitive notices | Exact wrapper/core/model hashes, model source and license, explicit asset preparation |
| pypdfium2/PDFium native build | Wrapper Apache-2.0 OR BSD-3-Clause; PDFium and linked build dependencies separate | Full platform wheel `BUILD_LICENSES`, binary build/version, no three-word blanket license summary |
| pypdf | BSD-3-Clause selected release | Exact distribution/wheel hash and notice |
| Pillow | MIT-CMU plus linked codec notices | Actual wheel and reencoder provenance |
| Tesseract native | Apache-2.0 plus linked libraries | Build/image source, version, model data and notices |
| JSON Schema validators | MIT selected packages | Exact dependency inventory; generated validators cite source schema |
| Own MIB origin | Retain original MIT notice; no legacy runtime import | Origin manifest and accurate historical method caveats |
| Third-party challenge ideas | Material inspiration named; no copied implementation in this planning package | Exact source/path/commit and adaptation notice before any future code port |
| Fonts/UI | System font stack; no bundled font files in this package | If later self-hosted fonts are selected, exact font license and reserved-name compliance |
| Non-Latin fixture fonts | Acquire a reviewed OFL font at build time for the specified script | Exact artifact hash/notice before publishing any embedded font; no random machine fonts |
| Real incidents | Optional, explicit permission and minimization | Consent scope, redistribution decision, removal procedure |

The planning probe used an installed pypdfium2 wheel whose license directory includes multiple build notices (for example FreeType, ICU, JPEG and other components). Those binaries are not redistributed here. The final native package must carry its own actual build's complete license set, not merely copy this prose. The English model hash and original Git blob were matched to the official source tree; the model bytes are not inside this ZIP.

## Attribution ledger rules

For copied/substantially adapted files: record exact upstream path/commit, copyright/license, target file, modifications and required notice. For independently implemented material ideas: cite source and describe the independent implementation/test, rather than erasing influence. For an upstream reported measurement: label it reported and do not incorporate it into new performance claims. For a derived family: record ancestors and do not count forks as independent evidence.

Before merging a new dependency/model/font/fixture, the lock/rights owner checks capability need, maintenance and distribution cost, license obligations and actual binary contents. Unknown terms or absent model provenance block that asset's inclusion. Rejected alternatives remain documented without dormant runtime imports. RapidOCR and a browser PDFium alternative remain controlled experiments; their unverified model/build artifacts do not silently enter the public bundle.

A release NOTICE contains own origin, adapted material and actual dependencies. An SPDX/CycloneDX SBOM is generated from the real build with hashes; the planning dependency JSON is not mislabeled as an SBOM. The package's [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) records material influences and current distribution scope.
