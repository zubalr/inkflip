# Developer guide

This is a Bun-workspaces monorepo with a Python native side. It explains the
layout, the command harness that gates every change, and how evidence is
recorded. All commands shown were run on this snapshot.

## Repository layout

```
apps/web/            Browser inspector — React 19 + Vite 8, CSS Modules
packages/            Shared TypeScript packages (see table below)
native/              Python reader library + tests (uv-managed, pinned 3.13.15)
fixtures/            Original synthetic fixture PDFs + manifest (development/
                     and public/ families)
planning/            Frozen specification snapshot (byte-identical; do not edit)
config/              Frozen dependency/toolchain records, command registry,
                     resolved asset manifests
scripts/             Command harness, fixture/example generators, gates
tests/               Browser, privacy, a11y, visual, bootstrap, contracts…
native/tests/        Native adapter/runtime/structure/bridge suites
docs/                Product documentation (this directory)
artifacts/           Task evidence: receipts, runs, screenshots, captures
```

### Workspace packages

| Package | Role |
| --- | --- |
| `packages/contracts` | JSON Schema, generated types, report sealing/normalization |
| `packages/geometry` | Canonical page space, transforms (ADR-004) |
| `packages/readers-pdfjs` | PDF.js rendering/text reader adapter |
| `packages/readers-tesseract` | Tesseract.js OCR reader adapter |
| `packages/runtime` | Run lifecycle, backpressure, cancellation |
| `packages/compare` | Alignment/comparison; the Node comparison bridge |
| `packages/explanations` | Plain-language finding explanations |
| `packages/reports` | Portable JSON + script-free HTML export |

### Native Python modules

`native/inkflip/` contains `readers/` (`pdfium.py`, `pypdf.py`,
`tesseract.py`), `checks/structure.py` (bounded structural observations),
`runtime/` (supervisor, atomic partial artifacts) and the comparison bridge
glue. The package is deliberately not packaged/installable yet
(`[tool.uv] package = false` in `native/pyproject.toml`); tests import it via
explicit paths. The standalone CLI wrapping it is specified but **not
implemented** (see [limitations.md](limitations.md)).

## The command harness

Every documented command goes through `scripts/task_acceptance.py`, which
reads `config/acceptance-commands.json`. `bun run <name>` is a thin alias for
`python3 scripts/task_acceptance.py run <name>`.

Registry semantics (enforced, not conventional):

- `active` commands must pass now. An active command whose `requires` files
  are missing fails the registry self-check.
- `declared` commands run once their `requires` files exist — until then they
  fail explicitly with the owning task named. This is how the registry grows
  without editing: an owner lands the suite, the prereqs appear, the same
  command starts executing.
- **Test commands must collect at least one test.** Zero collected tests is a
  failure, never a pass. Required skips and expected failures also fail.
- `bun run verify` is the group of every suite that exists today; it is the
  minimum bar for any commit.

Inspect the effective registry rather than guessing:

```sh
python3 scripts/task_acceptance.py self-check   # registry consistency (verified)
python3 scripts/task_acceptance.py run verify   # the full active group (verified: 111 tests)
```

## Running the suites

| Suite | Command | What it covers |
| --- | --- | --- |
| Bootstrap/coordination | `bun run verify` | Registry, bootstrap contracts, native bootstrap, coordination |
| Native | `bun run test:native` | Reader adapters, structure, supervision, bridge (196 tests) |
| Fixtures | `bun run test:fixtures` | Generator + prepared example integrity (70 tests) |
| Privacy | `bun run test:privacy` | No-egress canary against the real build (4 tests) |
| Accessibility | `bun run test:a11y` | Controls, dialogs, focus, announcements |
| Visual | `bun run test:visual` | Layout, contrast, motion, focus styling |
| Browser flows | per-spec with explicit path | Open/viewer/export/amount flows (see limitations for the registry issue) |
| Docs checks | `python3 -m unittest discover -s tests/docs -v` && `python3 scripts/check_claims.py` | Links, referenced files, claim hygiene for this documentation |

Playwright suites build on the production bundles and per-suite configs under
`tests/<area>/`. The privacy suite is the slowest (it makes a two-pass Vite
build); everything else runs in seconds to a minute.

## Toolchain pins and rules

- **Bun** with `linker = "isolated"`, exact versions, `minimumReleaseAge`
  gating (7 days, with documented exemptions in `bunfig.toml`).
- **TypeScript 6**, **oxlint** (0-error policy; warnings exist), **oxfmt**
  (config not yet landed — `format:check` currently fails; see limitations).
- **Python**: `native/pyproject.toml` pins `requires-python == 3.13.15`;
  `.python-version` matches. `uv run --frozen` is mandatory — never let uv
  resolve a new environment for product code.
- `patches/tesseract.js@7.0.0.patch` pins the OCR wrapper's behavior
  (CDN-off, worker lifecycle); it is applied via `patchedDependencies`.
- `apps/web/src` must typecheck cleanly in CI-critical paths; the standalone
  `typecheck` script currently fails on a known cross-package `.ts`-extension
  issue (limitations.md) even though the production build passes.

## Changing things safely

- `planning/` is a frozen specification snapshot: keep it byte-identical.
  Accepted changes go in implementation files and recorded decisions outside
  it. If reality and the spec disagree, file a proposal instead of editing
  either silently.
- Fixtures are rights-cleared originals with recorded digests
  (`fixtures/manifest.json`); never regenerate or edit existing fixture bytes,
  and never add third-party material without a provenance record
  ([docs/ATTRIBUTION.md](ATTRIBUTION.md) is the ledger).
- Command registry edits (`config/acceptance-commands.json`), root manifests
  and lockfiles are shared-surface changes: make them deliberately, keep pins
  exact, and never weaken a check to make a failure disappear.
- Shared contracts (schema, geometry, report identity) have named owners;
  a contract change requires updating generated types and both browser and
  Python consumers together.

## Evidence and acceptance

Work is recorded, not asserted. For each task, `artifacts/tasks/<Txx>/`
carries the command log, run results and review files; acceptance receipts
bind an evaluated commit to executed commands and test counts. The mechanics
— receipt format, freshness rules, what counts as manual evidence — are
specified in [docs/ACCEPTANCE.md](ACCEPTANCE.md). Two habits matter for any
contributor:

1. Run `bun run verify` (plus the suites your change touches) **after
   committing** and record the exact commands and outcomes.
2. Do not refresh goldens, weaken token rules, or suppress type errors to
   conceal a failure; a red suite with an honest report beats a green one
   that hides a regression.

## Documentation checks

`tests/docs/` plus `scripts/check_claims.py` keep this documentation honest
mechanically:

- every local markdown link/anchor in the public docs resolves to a real
  file/heading;
- every referenced image/evidence path exists and is non-empty;
- versions quoted in prose match the frozen pins in `package.json`,
  `.python-version` and `native/pyproject.toml`;
- every `bun run <name>` mentioned in the docs exists in the command registry;
- a forbid-list of unsupported claim phrases (data-driven, in
  `tests/docs/claims-rules.json`) fails the build if one appears;
- the licensing status stays explicitly recorded as pending until the root
  LICENSE/NOTICE work lands;
- the checker itself is regression-tested against deliberately broken input
  (it must fail when the docs break).

Add a check there — not a prose snapshot — when you add a claim to the docs
that a machine could verify.

## Where the product is headed

The task-level roadmap and the release gates live in the frozen planning
snapshot (`planning/execution/`, `planning/PROJECT_BRIEF.md`); live work
state is tracked in the repository's Beads database. The docs-side view of
what is done, missing and pending is maintained in
[limitations.md](limitations.md).
