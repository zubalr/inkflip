# Advisory scan — T47 preparation

Queried: 2026-09-13T13:24:18Z — https://api.osv.dev/v1/querybatch (raw output: osv-querybatch.json)
Local audit: `bun audit` at 2026-09-13T13:24:18Z (raw output: bun-audit.txt): no vulnerabilities found (206 packages).

OSV batch results against exact frozen versions, classified:

| purl | classification | advisories |
| --- | --- | --- |
| `pkg:npm/bmp-js@0.1.0` | shipped (bundled in production bundle) | none |
| `pkg:npm/idb-keyval@6.3.0` | shipped (bundled in production bundle) | none |
| `pkg:npm/is-url@1.2.4` | shipped (bundled in production bundle) | none |
| `pkg:npm/node-fetch@2.7.0` | shipped (bundled in production bundle) | none |
| `pkg:npm/opencollective-postinstall@2.0.3` | shipped (bundled; install-script only, blocked) | none |
| `pkg:npm/pdfjs-dist@6.3.289` | shipped (bundled in production bundle) | none |
| `pkg:npm/react@19.2.8` | shipped (bundled in production bundle) | none |
| `pkg:npm/react-dom@19.2.8` | shipped (bundled in production bundle) | none |
| `pkg:npm/regenerator-runtime@0.13.11` | shipped (bundled in production bundle) | none |
| `pkg:npm/scheduler@0.27.0` | shipped (bundled in production bundle) | none |
| `pkg:npm/tesseract.js@7.0.0` | shipped (bundled in production bundle) | none |
| `pkg:npm/tesseract.js-core@7.0.0` | shipped (bundled in production bundle) | none |
| `pkg:npm/tr46@0.0.3` | shipped (bundled in production bundle) | none |
| `pkg:npm/wasm-feature-detect@1.9.0` | shipped (bundled in production bundle) | none |
| `pkg:npm/webidl-conversions@3.0.1` | shipped (bundled in production bundle) | none |
| `pkg:npm/whatwg-url@5.0.0` | shipped (bundled in production bundle) | none |
| `pkg:npm/zlibjs@0.3.1` | shipped (bundled in production bundle) | none |
| `pkg:pypi/attrs@26.1.0` | runtime-tooling (local, not bundled) | none |
| `pkg:pypi/colorama@0.4.6` | development-only | none |
| `pkg:pypi/iniconfig@2.3.0` | development-only | none |
| `pkg:pypi/jsonschema@4.26.0` | runtime-tooling (local, not bundled) | none |
| `pkg:pypi/jsonschema-specifications@2025.9.1` | runtime-tooling (local, not bundled) | none |
| `pkg:pypi/packaging@26.3` | development-only | none |
| `pkg:pypi/pillow@12.3.0` | runtime-tooling (local, not bundled) | none |
| `pkg:pypi/pluggy@1.6.0` | development-only | none |
| `pkg:pypi/pygments@2.21.0` | development-only | none |
| `pkg:pypi/pypdf@6.18.0` | runtime-tooling (local, not bundled) | none |
| `pkg:pypi/pypdfium2@5.8.0` | runtime-tooling (local, not bundled) | none |
| `pkg:pypi/pytest@9.1.1` | development-only | none |
| `pkg:pypi/referencing@0.37.0` | runtime-tooling (local, not bundled) | none |
| `pkg:pypi/rpds-py@2026.6.3` | runtime-tooling (local, not bundled) | none |

Result: 0 advisory entries across 31 exact-version queries.

This is evidence, not a clean bill of health: the scan reflects the query
date above and the advisories known at that moment. Re-run at T47 closure.
