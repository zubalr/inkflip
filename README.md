# Inkflip

**Your PDF can look right and read wrong.**

Inkflip is a local-first PDF reading inspector. Compare a rendered page with
its extracted text and OCR, follow disagreements to their source regions,
and export a portable report.

## Inspect the evidence

- Open a PDF locally and select a page or region to investigate.
- Compare named readers while retaining raw text, positions and coverage.
- Follow findings back to the page, including repeated text occurrences.
- Add notes and choose what to include in an HTML or JSON export.
- Reopen a JSON report through the same validation boundary as a local file.

The browser processes documents locally. There is no account or document
upload service. A disagreement is evidence of different readings; it does
not establish which reading is correct or whether a document is safe.

The repository also contains a native CLI (`inkflip`: inspect, compare,
report, replay, corpus, baselines) with version-isolated reader profiles,
an offline-capable browser build, shared report contracts and synthetic
PDF fixtures. Accessibility flows are covered by an automated suite;
release qualification, manual assistive-technology evidence and the
packaged native image remain in progress.

## Run locally

Use Bun **1.4.0**, Node **22.23.2**, and uv **0.12.13 or later**. The native
project pins Python **3.13.15**. The complete toolchain is recorded in
[config/test-toolchain.json](config/test-toolchain.json).

```sh
bun install --frozen-lockfile
uv sync --frozen --project native
cd apps/web
bun run dev
```

Open the localhost address printed by Vite. Dependency installation may use
the network; document processing uses local readers and bundled assets.

## Build and check

From the repository root:

```sh
bun run verify
bun run build
bun run test:native
bun run test:fixtures
```

`bun run test:native` also needs the PDF.js Node profile's own locked dependency,
which is not part of the workspace install:

```sh
cd packages/readers-pdfjs/node && bun install --frozen-lockfile
```

For browser checks, install the test browser explicitly:

```sh
bun x playwright install chromium
bun run test:browser
bun run test:privacy
bun run test:a11y
bun run test:visual
```

The production bundle is written to `apps/web/dist/`. CI checks repository
and command integrity; a green CI run alone does not certify release readiness.
See [validation](docs/ACCEPTANCE.md) for the release evidence requirements.

## Explore the code

| Directory | Contents |
| --- | --- |
| `apps/web/` | React inspector and static browser assets |
| `packages/` | Readers, comparison, geometry, runtime and report contracts |
| `native/` | Python readers and supervised processing |
| `fixtures/` | Public synthetic fixtures and development cases |
| `tests/` | Browser, privacy, contract and integration checks |
| `planning/` | Preserved product specification and invariants |

Source provenance and third-party notices are retained in
[ORIGIN](docs/ORIGIN.md) and [ATTRIBUTION](docs/ATTRIBUTION.md).

## Documentation

| Document | Contents |
| --- | --- |
| [docs/quickstart.md](docs/quickstart.md) | Prerequisites, install, run, build and check |
| [docs/user-guide.md](docs/user-guide.md) | The investigation workflow: open, read, compare, annotate, export, reopen |
| [docs/architecture.md](docs/architecture.md) | Components, data flow, contracts, reader adapters, privacy design |
| [docs/limitations.md](docs/limitations.md) | Implemented vs incomplete vs not built, method limits, known defects |
| [docs/developer-guide.md](docs/developer-guide.md) | Workspace layout, command harness, suites, evidence rules |
| [docs/development-history.md](docs/development-history.md) | How this was built, from Git history and validation records |
| [docs/distribution/README.md](docs/distribution/README.md) | What ships, license/notice evidence, the distribution gate |
| [docs/release-and-rollback.md](docs/release-and-rollback.md) | The release path: build, dist manifest, static preflight, distribution gate, native bundle, artifact identity, rollback |
| [SECURITY.md](SECURITY.md) | Security expectations and reporting status |
