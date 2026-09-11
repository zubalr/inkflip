# Repository layout and dependency strategy

```text
planning/                         this immutable planning snapshot
apps/web/                         React workspace, routes, UI and lifecycle
packages/contracts/               canonical schema + generated TS + validators
packages/geometry/                pure transforms and polygons
packages/compare/                 shared normalization/alignment/rule engine
packages/reports/                  evidence projection, HTML/JSON serialization
packages/readers-pdfjs/            PDF.js adapter, with fixed optional Node profile
packages/readers-tesseract/        Tesseract.js raster OCR adapter
packages/runtime/                 worker messages, lifecycle and backpressure
packages/explanations/            evidence-bound deterministic explanations
packages/compare/node/            fixed shared comparison entry point
native/inkflip/                    Python CLI, native adapters, supervision
native/tests/                     adapter, process and CLI tests
fixtures/{development,public}/             original recipes and approved generated cases
quality/                          policies and public evaluation protocol
scripts/                          checked build/test/package commands
profiles/                         owner-installed reader identities (no shell commands)
docs/                             user, developer, architecture and limitations
execution/state.json              coordinator-owned task state
execution/{receipts,leases}/       actual provenance and shared-edit leases
third_party/                      notices; only audited redistributed material
experiments/                      isolated candidates and complete result records
```

`planning/contracts/inkflip.schema.json` is the delivered contract. T03 copies it without semantic changes to `packages/contracts/schema/inkflip.schema.json`; after bootstrap that runtime copy is authoritative and planning is the frozen origin. Contract revisions increment schema/adapter versions, add migration tests and update ADRs. Do not maintain two active independent schema implementations.

Selected direct versions, evidence status and source are in [dependencies.json](../config/dependencies.json). This is a planning pin manifest, **not a resolved transitive lockfile**. T02 owns actual `pnpm-lock.yaml`, native `uv.lock`, binary/image digests, SBOM and vulnerability triage. Registry access failed in the planning environment, so invented lockfiles or digests are deliberately absent. A failing version resolution is not permission to choose an unrelated stack: select the nearest compatible maintained patch in the same chosen family, run contract/geometry probes, and record the exact substitution under ADR-D02.

Node 22.16.0 and Python 3.13.5 are actual probe toolchains, not claims to be the newest secure patches. T02 checks current advisories and chooses patched supported 22 LTS / Python 3.13 patch releases if needed, freezes them and reruns probes. PDF.js 6.3.289, React 19.2.8, Vite 8.3.0, TypeScript 6.0.2 and Wrangler 4.131.0 are source-verified planned pins. Product pypdf is 6.18.0, whereas the native exploratory result records 5.9.0. Do not relabel that result.

Use pnpm workspaces without a monorepo task orchestrator initially. Shared packages build in explicit topological order. `pnpm verify` runs types, unit/contracts and lint; `pnpm test:browser`, `pnpm test:privacy`, `pnpm test:a11y`, `pnpm test:visual` are distinct commands. Native uses uv with frozen dependencies and `uv run --project native python -m pytest`. Test dependencies selected at bootstrap remain exact-pinned in the same lock. Every dependency has one owner and purpose; no icon/animation/state package by habit.

## Build products

The web artifact is static `apps/web/dist/`. It contains its own worker, core WASM, language data, fonts/CMaps required by the chosen PDF.js route, notices and public sample manifests. Language/OCR chunks are lazy, not initial-page dependencies. A local offline distribution is the same static tree served on localhost; `file://` worker loading is not promised. A small optional service worker caches only explicitly enumerated static assets, never user content or arbitrary URLs.

Native release includes a Python wheel, shared Node compare/reader tarball, profiles, notice bundle and a reproducible OCI build recipe. The initial supported binary reference is Linux x86_64. Additional arm64/macOS/Windows claims require actual matrix evidence. Source portability alone is not a binary support claim.

No postinstall downloads models silently. `pnpm assets:prepare` or `inkflip models prepare` is an explicit development/install action using the allowlisted manifest; ordinary inspection is offline. Cache integrity uses SHA-256 of uncompressed model bytes. Package install scripts run only in isolated reviewed build environments, with pnpm's package-build allowlist explicitly frozen.

## Updating readers

A library update is an experiment: record old/new package+build identities, run the golden and untouched checks, inspect differences, and update a baseline only by a new explicit approval. Keep two incompatible versions in separate environments. A source-identical package with a different binary build is still a different reader identity.
