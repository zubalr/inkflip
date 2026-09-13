# Contributing to Inkflip

Inkflip is currently a **private, in-development repository** built through a
task-based workflow with evidence-based acceptance. This page describes how
to work inside that workflow. For what the project is and is not, start with
the [README](README.md) and [docs/limitations.md](docs/limitations.md).

## Ground rules

1. **Read before writing.** `AGENTS.md` and `docs/NATIVE_PASSES.md` are the
   standing instructions for any session that touches this repository;
   `docs/ACCEPTANCE.md` defines how work is evidenced and accepted. The
   planning snapshot under `planning/` is the specification.
2. **Keep `planning/` byte-identical.** It is a frozen snapshot. Accepted
   changes go into owned implementation files and recorded decisions outside
   it. If the code and the spec disagree, file a proposal (under
   `docs/proposals/`) instead of silently editing either side.
3. **Stay inside your assigned scope.** Work happens per task, on a per-task
   branch, in an isolated checkout. Shared surfaces — schemas/contracts, root
   manifests and lockfiles, the command registry, fixtures, the release
   gates — have named owners and change only through review.
4. **Preserve existing work.** Never reset, clean, force-push or overwrite
   another checkout or branch. Worktrees and task evidence are history, not
   clutter.

## The development loop

1. **Claim work through the tracker.** Live task state lives in the
   repository's Beads tracker; static planning files are not live state. Do
   not self-assign tasks outside the recorded flow.
2. **Implement in your own checkout.** One branch per task; keep commits
   focused. Commit messages in this repository conventionally state the task
   and the action, e.g. `feat(experiment): execute P09 … evaluation (T41)`,
   `docs(evidence): record acceptance receipt and review for T41`.
3. **Verify honestly.** After committing, run the checks your change touches
   and at minimum:

   ```sh
   bun run verify
   python3 -m unittest discover -s tests/docs -v && python3 scripts/check_claims.py
   ```

   The harness fails empty or skipped required suites by design. Never
   weaken a check, refresh a golden, or suppress a type error to hide a
   failure — record the failure and its exact cause instead.
4. **Record evidence.** Put the exact commands, results, screenshots and
   limitations into your task's `artifacts/tasks/<Txx>/` directory
   (`commands.log`, `run.json`, `review.md`). Acceptance is bound to an
   evaluated commit and executed commands — see [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md).
5. **Submit for independent review.** Author and reviewer are different
   people/sessions by rule; the integrator accepts after merged-state checks.

## Changing shared things

- **Contracts** (JSON Schema, report identity, geometry): coordinate with the
  contract owner first; regenerate consumers in the same change; both browser
  and Python sides must agree.
- **Dependencies / lockfiles**: exact pins only; the freeze tooling and
  release-age gate in `bunfig.toml` apply. A vulnerability-driven bump is a
  recorded change ([docs/ATTRIBUTION.md](docs/ATTRIBUTION.md) is the ledger).
- **Fixtures**: existing fixture bytes and their digests are immutable;
  new fixtures need a rights/provenance record before anything else.
- **Command registry** (`config/acceptance-commands.json`): new suites must
  collect at least one test; a suite owner must not disable the harness
  reporter.
- **Documentation**: the public docs (README, `docs/*.md`, CONTRIBUTING,
  SECURITY) are checked mechanically — see below — and their final claims
  are re-verified together before any release.

## Documentation checks

If your change affects anything the docs state — commands, versions,
capabilities, security behavior — update the docs and keep them green:

```sh
python3 -m unittest discover -s tests/docs -v
python3 scripts/check_claims.py
```

These verify links, referenced files, version consistency with the frozen
pins, and the claims rules in `tests/docs/claims-rules.json`. When you add a
claim a machine could check, extend the checks rather than trusting prose.

## Licensing and provenance

Newly authored code and documentation are intended for the MIT license per
the recorded planning decision (ADR-003), but the repository-root LICENSE,
NOTICE and final copyright statement are **pending** unfinished distribution
work — do not add license headers or copyright lines of your own invention.
Copied or materially adapted third-party material is blocked without exact
provenance (upstream path/commit, license, modifications, notice); material
inspiration must be credited in [docs/ATTRIBUTION.md](docs/ATTRIBUTION.md)
even when code is independently written.

## What not to build

No accounts, upload endpoints, extraction APIs, cloud storage, collaboration
features, fraud/safety scoring, document repair or sanitization, redaction
certificates, or agent-orchestration features. The product boundary in
[planning/PROJECT_BRIEF.md](planning/PROJECT_BRIEF.md) is deliberate; scope
expansion proposals go through the recorded decision process, not a pull
request that quietly adds one.
