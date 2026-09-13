# Quickstart

Every command below was executed against this exact snapshot. Results and the
environment they were verified on are stated next to each command; anything
that was **not** exercised is marked as such instead of claimed.

## Prerequisites

| Tool | Used for | Version verified here | Notes |
| --- | --- | --- | --- |
| [Bun](https://bun.sh) | workspace install, scripts, dev server, bundling | Bun 1.4.0 | `packageManager` pin in `package.json`; Bun supplies its own JavaScript/TypeScript runtime, so no separate Node install is needed for the app or tests. |
| [uv](https://docs.astral.sh/uv/) | pinned Python interpreter + native dependencies | 0.9.5 | `uv run --frozen` resolves the exact interpreter pinned in `.python-version` (3.13.15) and `native/uv.lock`; a missing patch version fails closed instead of drifting. |
| Python 3 (system) | bootstrap/coordination check harness | 3.14.7 | The `bun run verify` bootstrap suites are standard-library only; any recent Python 3 works for them. Native product code uses the uv-managed 3.13.15, not your system Python. |
| Playwright browsers | browser, privacy, a11y, visual suites | Chromium via `@playwright/test` 1.57.0 | Already exercised on this machine; a fresh machine needs `bun x playwright install chromium` (this specific step was not re-exercised here because the browser was already installed). |

The dependency freeze also documents Node 22 LTS and Python 3.13.15 as the
supported toolchain ([docs/ATTRIBUTION.md](ATTRIBUTION.md)); the build and
test commands below were additionally confirmed working on this machine's
newer system Node, but the frozen pins are the release baseline.

## Install

From the repository root:

```sh
bun install
```

This installs all workspace dependencies with Bun's isolated linker using the
frozen `bun.lock`. It was exercised in a **fresh clone of this snapshot with
an empty dependency tree** (86 packages installed, exit 0) and additionally
checked with `bun install --dry-run --frozen-lockfile` (exit 0) on the
development machine. Because Bun's download cache was already warm from prior
work on this machine, cold-cache install time and a never-used-machine run
were not measured — that clean-environment test remains release work and is
not claimed here (see [limitations.md](limitations.md#known-failures-in-this-snapshot)).

For the native Python side there is nothing to install by hand:

```sh
uv run --frozen --project native python -c "import pypdf; print(pypdf.__version__)"
```

prints `6.18.0` (verified). The first run on a new machine downloads the
pinned CPython 3.13.15 and creates `native/.venv/` (git-ignored).

## Run the app

Development server (verified — serves HTTP 200 on the printed port). The dev
and preview scripts live in the `apps/web` workspace, so start them from
there:

```sh
cd apps/web
bun run dev
```

This runs Vite for `apps/web`. Open the printed localhost URL in a browser.
The Home screen offers **Try Example** (the prepared synthetic amount example,
no local file needed) and **Open Workspace** to inspect your own PDF. Nothing
is uploaded; files are read locally by the browser tab.

Production build + preview of the built static site (both verified):

```sh
bun run build       # from the repo root: typechecks packages, bundles apps/web
cd apps/web && bun run preview   # serves the built dist/ over loopback
```

`bun run build` produces a static bundle with no server component; the built
site performs no document egress (see
[privacy](#privacy-behavior-you-can-verify) below).

## Run the checks

All commands from the repository root. "Verified" results below were measured
on this snapshot (macOS, arm64):

| Command | Verified result |
| --- | --- |
| `bun run verify` | 111 tests pass in ~37 s (command-registry self-check, bootstrap, native bootstrap, coordination suites) |
| `bun run test:native` | 196 pytest tests pass in ~26 s (PDFium/pypdf/Tesseract adapters, structure, supervision, bridge) |
| `bun run test:fixtures` | 70 tests pass in ~1 s (fixture generator + prepared example integrity) |
| `bun run test:privacy` | 4 canary tests pass (cold / warm / offline / receipt no-egress against the real build) |
| `bun run test:a11y` | 7 tests pass (accessible controls, dialogs, navigation) |
| `bun run test:visual` | 9 tests pass (responsive layout, contrast, motion, focus) |
| `bun run build` | production bundle built successfully |

Browser test files are executed per suite by the registry (for example
`test:a11y` runs `tests/a11y`); `bun run test:browser` is currently broken on
this snapshot for a known, documented reason
([limitations.md](limitations.md#known-failures-in-this-snapshot)) — the
individual browser specs do pass when run with an explicit path, as recorded
in task evidence.

Regenerate or verify the prepared public example (verified):

```sh
python3 scripts/prepare_examples.py --check
```

prints `OK: apps/web/public/examples/amount/ matches generation`. Remove
`--check` to regenerate from `fixtures/public/`.

## Documentation checks

The documentation has its own checks (links, referenced files, mechanically
checkable claims), runnable without any browser:

```sh
python3 -m unittest discover -s tests/docs -v
python3 scripts/check_claims.py
```

Both pass on this snapshot. `check_claims.py --run-commands` additionally
re-executes the cheap command list that the docs present as working; see
[developer-guide.md](developer-guide.md#documentation-checks).

## Privacy behavior you can verify

`bun run test:privacy` builds the real production app, drives a marked
synthetic canary PDF through it in real Chromium, and asserts that no canary
material leaves the tab — across cold start, warm cached-model reuse, a fully
offline session, and an offline cold start (which must fail explicitly, not
silently). A committed, digest-only receipt of the captures lives in
`artifacts/tasks/T15/network-receipt.json`. The suite details, including every
captured channel, are in [tests/privacy/README.md](../tests/privacy/README.md).

## Troubleshooting

- **`uv run --frozen` refuses to run** — your uv is too old to resolve the
  pinned interpreter/lock format; upgrade uv. It fails closed on purpose; do
  not replace `--frozen` with a resolving run.
- **`bun run verify` fails after your own changes** — the harness reports the
  failing suite and requires at least one collected test per registered suite;
  empty or skipped required suites fail. See
  [developer-guide.md](developer-guide.md).
- **Playwright suite cannot find Chromium** — run
  `bun x playwright install chromium` once (see Prerequisites note above).
