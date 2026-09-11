# Start here

This is an implementation-planning package, with executable validation utilities and small probes. It is **not the completed application**. No remote repository was changed or deployed.

## 1. Verify the package locally

Use Python 3.13 with the planning dependencies `jsonschema==4.26.0` and `PyYAML==6.0.3` installed in an isolated tooling environment (see `tools/requirements.txt`). From this directory:

```sh
python tools/validate_package.py
python tools/test_validators.py
python tools/ready_tasks.py
```

The first command verifies schema and semantic examples, task references and cycles, requirement coverage, internal links and checksums. Read [the audit](PACKAGE_AUDIT.md) for actual execution results and limitations. Do not run network installation scripts from an unreviewed source.

## 2. Create a separate local repository

Pick a new empty local directory; do not use the old `mib-intake` checkout. The following helper copies this package under `planning/`, initializes a local Git repository only on explicit request, and performs no network action:

```sh
python tools/bootstrap_repo.py ../inkflip --init-git
cd ../inkflip
```

It refuses nonempty destinations. It does not create a remote, install dependencies, make commits, set your Git identity or deploy. Read [the bootstrap prompt](execution/BOOTSTRAP_PROMPT.md), then give it to a coding session with the new checkout. Task T01 creates the working monorepo and command harness; T02 freezes the real dependency lock, security status and asset inventory. Until those tasks pass, application commands described in this package are **implementation command contracts**, not present application executables.

## 3. Load the coordinator

Use [COORDINATOR_PROMPT.md](execution/COORDINATOR_PROMPT.md). The compact shared context is [PROJECT_BRIEF.md](PROJECT_BRIEF.md), [GLOSSARY_AND_INVARIANTS.md](architecture/GLOSSARY_AND_INVARIANTS.md), [DECISIONS.md](DECISIONS.md), and each task's listed inputs. Workers need not ingest the entire research history.

T01 is the first ready task. T02 and contract/fixture/design tracks become ready from the dependency graph, not because a calendar date arrived. `python planning/tools/ready_tasks.py --state execution/state.json` reads a repository state override after bootstrap; it never launches a provider session itself. See [ownership](execution/OWNERSHIP.md) before dispatching work.

## 4. Protect the first integrated path

Gate G1 requires the real amount fixture **and** its clean counterpart through the browser's live own-file path, correctly anchored results, cancellation/file replacement, selected export/reopen and captured network behavior. A prepared hero alone cannot pass. Source-verified browser dependencies are not browser proof; the native probe bundled here does not substitute for G1.

After G1, continue all downstream mandatory work: larger/narrow-screen UX, native object checks, CLI corpus baselines, version-isolated regression, malicious-import tests, accessibility, evaluation, packaging and static deployment. [Milestones](execution/MILESTONES.md) describe the complete route; [task DAG](execution/ISSUE_DAG.md) identifies parallel work.

## 5. Release only demonstrated claims

G2 completes investigation/export; G3 completes native/regression; G4 completes quality/security/rights; G5 verifies the actual static deployment and release artifacts. [Owner inputs](OWNER_INPUTS.md) are only account/domain/capacity/approval values. Local development needs none of the publication secrets. [Release runbook](deployment/RELEASE_RUNBOOK.md) contains deployment and rollback steps; no paid resource may be created silently.

For all artifacts and their authority, use [PACKAGE_INDEX.md](PACKAGE_INDEX.md). The visual reference is [reference/index.html](reference/index.html); its labeled interactions are not a processing implementation.

The offline package validator requires the pinned planning-only dependencies in `tools/requirements.txt` (jsonschema and PyYAML). Install these explicitly in a virtual environment when absent; bootstrap itself performs no installation or network action.
