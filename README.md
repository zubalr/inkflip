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

The repository also contains Python reader adapters, a supervised native
runtime, shared report contracts and synthetic PDF fixtures. The complete
CLI and corpus workflow is still being integrated. Release qualification
and the expanded example gallery are in progress.

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
