# Quickstart

Commands below were verified against this snapshot; where a result depends on
your machine, that is stated. Results are dated — treat them as evidence of
that run, not a permanent claim.

## Prerequisites

There are two distinct toolchains: **bootstrap tooling** (runs the check
harness) and the **native runtime pin** (the audited interpreter the
product's Python code runs on). Do not conflate them.

| Tool | Used for | Required version | Notes |
| --- | --- | --- | --- |
| [Bun](https://bun.sh) | workspace install, scripts, dev server, bundling | 1.4.0 (`packageManager` pin) | Bun supplies its own JavaScript runtime; no separate Node install needed for the app or tests. |
| Python 3 (system) | bootstrap/coordination check harness only | any recent Python 3; standard-library only | Native product code does **not** use your system Python. |
| [uv](https://docs.astral.sh/uv/) | native project runner: resolves the pinned interpreter and frozen lock | **≥ 0.12.13** on a cold host (recorded freeze in [config/test-toolchain.json](../config/test-toolchain.json)) | Older uv cannot be relied on to resolve the pinned interpreter's download index. |
| Pinned CPython | native product interpreter | exactly 3.13.15 (`.python-version`, `native/pyproject.toml`) | Provisioned automatically by `uv sync --frozen`. |
| Playwright browsers | browser, privacy, a11y, visual suites | Chromium via `@playwright/test` | Install explicitly with `bun x playwright install chromium`; browsers are never installed by an install script. |
| pdf.js Node profile (optional) | native `--reader` profiles that use the PDF.js bridge | pinned `pdfjs-dist@6.3.289` (own lock) | `cd packages/readers-pdfjs/node && bun install --frozen-lockfile` |

The frozen toolchain also records Node 22.23.2 (`.node-version`) as the
comparison-runtime baseline.

## Install and run

```sh
bun install --frozen-lockfile   # network step: fetches the frozen workspace dependencies
uv sync --frozen --project native   # network step on a cold host: provisions CPython 3.13.15 + locked wheels
cd apps/web && bun run dev          # development server; open the printed localhost URL
```

Dependency installation may use the network. Document processing does not:
the app reads files locally in the browser tab, and everything after install
runs without network access. This was verified on 2026-09-13 in a fresh clone
with isolated, empty download caches: after the two install steps above,
`bun run verify`, `bun run build`, and `bun run test:native` were re-executed
with all proxies pointed at a dead address and passed.

## Build and check

From the repository root (verified 2026-09-13 on this snapshot, macOS/arm64):

| Command | Verified result |
| --- | --- |
| `bun run verify` | passes — 176 tests across three suites (63 bootstrap + 2 native bootstrap + 111 coordination) plus a 16-command registry self-check |
| `bun run build` | passes — production bundle in `apps/web/dist/` |
| `bun run test:native` | passes — native reader/runtime/bridge suites |
| `bun run test:privacy` (offline lifecycle) | the cache suite verifies prepare/removal semantics with digest re-verification |
| `bun run test:browser` | passes — full browser flow suite |
| `bun run test:fixtures` | passes — fixture generator + prepared example integrity |
| `bun run test:privacy` | passes — cold/warm/offline/receipt no-egress canary |
| `bun run test:a11y` / `bun run test:visual` | pass — accessibility and visual-foundation checks |

Suite totals are counted per suite (the last suite's own summary is not the
group total). Counts are dated evidence of this snapshot; they are expected
to change as suites grow, so do not treat them as release constants.

Known non-blocking failures on this snapshot (details in
[limitations.md](limitations.md#known-snapshot-defects)):
`apps/web`'s standalone `typecheck` and `format:check` scripts fail; the
production build and registered checks do not depend on them.

## Documentation checks

The public documentation has mechanical checks (links against **tracked**
files, referenced files, claim hygiene, dated source-bound facts):

```sh
python3 -m unittest discover -s tests/docs -v
python3 scripts/check_claims.py
```

## Distribution preparation

The distribution surface (staged browser assets, prepared example, and the
native third-party bundle inputs) is declared in
`config/distribution-manifest.json` and verified by:

```sh
python3 scripts/check_distribution.py --release
python3 -m unittest discover -s tests/release -v
```

See [distribution/README.md](distribution/README.md) for what ships, the
license/notice evidence, and how the native bundle is prepared.

## Troubleshooting

- **`uv sync --frozen` refuses to resolve** — upgrade uv to ≥ 0.12.13 (the
  recorded minimum for resolving the pinned interpreter on a cold host). It
  fails closed on purpose; never replace `--frozen` with a resolving run.
- **Playwright suite cannot find Chromium** — run
  `bun x playwright install chromium` once.
- **`bun run verify` fails after your own changes** — the harness fails
  empty or skipped required suites by design; see
  [developer-guide.md](developer-guide.md).
