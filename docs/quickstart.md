# Quickstart

Every command below was executed against this exact snapshot. Results and the
environment they were verified on are stated next to each command; anything
that was **not** exercised is marked as such instead of claimed.

## Prerequisites

There are two distinct toolchains: **bootstrap tooling** (runs the check
harness and coordination suites) and the **native runtime pin** (the audited
interpreter the product's Python code runs on). Do not conflate them.

| Tool | Used for | Required version | Verified here |
| --- | --- | --- | --- |
| [Bun](https://bun.sh) | workspace install, scripts, dev server, bundling | 1.4.0 (`packageManager` pin) | Bun 1.4.0 |
| Python 3 (system) | bootstrap/coordination check harness only | any recent Python 3; standard-library only | 3.14.7 (system) |
| [uv](https://docs.astral.sh/uv/) | native project runner: resolves the pinned interpreter and frozen lock | **≥ 0.12.13** per the recorded toolchain freeze ([config/test-toolchain.json](../config/test-toolchain.json)) — a cold host needs it to resolve the pinned interpreter's download index; the Linux proof installs `uv==0.12.13` from the pinned PyPI wheel | 0.12.13 (disposable install) and 0.9.5 (host) — see the cold-setup note below |
| Pinned CPython | native product interpreter | exactly 3.13.15 (`.python-version`, `native/pyproject.toml`) | 3.13.15, uv-managed; **not** your system Python |
| Playwright browsers | browser, privacy, a11y, visual suites | Chromium via `@playwright/test` 1.57.0 | already installed on this machine; a fresh machine needs `bun x playwright install chromium` (not re-exercised here) |

The frozen toolchain also records Node 22.23.2 (`.node-version`) as the
comparison-runtime baseline; the build/test commands below additionally ran
on this machine's newer system Node, which is an observation, not a support
claim.

**Cold-setup note (verified 2026-09-13).** In a fresh clone with isolated,
empty Bun/uv caches and an empty uv interpreter store: `bun install
--frozen-lockfile` fetched 86 packages (the network-preparation step), and a
disposable `uv==0.12.13` resolved and downloaded CPython 3.13.15 from its
index, then created the frozen native environment. After that, `bun run
verify`, `bun run build`, `bun run test:native`, and the docs checks were all
re-executed with `HTTP(S)_PROXY` pointed at a dead address and passed —
processing after install requires no network. One observation contradicts the
freeze's assumption: on this host and date, uv 0.9.5 *also* resolved the
pinned interpreter from an empty store (its index lookup appears to be live),
but that behavior cannot be relied on and the recorded ≥ 0.12.13 minimum
stands.

## Install

From the repository root:

```sh
bun install
```

This installs all workspace dependencies with Bun's isolated linker using the
frozen `bun.lock`. It was exercised in a **fresh clone with an empty
dependency tree and an isolated, empty download cache** (86 packages fetched
from the registry — this is the network-preparation step), and re-checked
with `bun install --dry-run --frozen-lockfile` (exit 0). Everything after
install was verified to run with the network cut off (dead proxy); see the
cold-setup note above for the exact procedure and its 2026-09-13 evidence.

For the native Python side there is nothing to install by hand; the first
frozen run provisions the pinned interpreter and environment (a
network-preparation step on a cold host, using uv ≥ 0.12.13 per the freeze):

```sh
uv run --frozen --project native python -c "import pypdf; print(pypdf.__version__)"
```

prints `6.18.0` (verified cold: interpreter downloaded into an empty store,
then 13 locked packages installed). This creates `native/.venv/`
(git-ignored).

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
| `bun run verify` | 169 tests pass across three suites (56 bootstrap + 2 native bootstrap + 111 coordination) plus a 16-command registry self-check |
| `bun run test:native` | 196 pytest tests pass in ~26 s (PDFium/pypdf/Tesseract adapters, structure, supervision, bridge) |
| `bun run test:fixtures` | 70 tests pass in ~1 s (fixture generator + prepared example integrity) |
| `bun run test:privacy` | 4 canary tests pass (cold / warm / offline / receipt no-egress against the real build) |
| `bun run test:a11y` | 7 tests pass (accessible controls, dialogs, navigation) |
| `bun run test:visual` | 9 tests pass (responsive layout, contrast, motion, focus) |
| `bun run build` | production bundle built successfully |

Suite totals are counted per suite (the coordination suite prints its own
summary last; do not mistake it for the group total).

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
