# Run an assigned implementation task

This repository contains the planning snapshot, implementation and coordination
tools. Beads owns current task readiness and acceptance. Check it before starting:

```sh
python3 scripts/coordination.py ready
```

Open each session in its assigned worktree below and use its prompt. A task that
is already claimed needs a coordinator-approved resume. Do not create another
worktree through the harness; the prepared checkout already has the correct
branch and shared Beads database. For the bootstrap assignment, T01 uses
`../worktrees/pdf-t01` and `prompts/T01.md`.

## First parallel pass, after T01 is accepted

| Session | Task | Worktree | Prompt | Development port |
| --- | --- | --- | --- | --- |
| SWE2 A | T02 dependencies, assets, provenance | `../worktrees/pdf-t02` | `prompts/T02.md` | 5182 |
| SWE2 B | T03 schema, validation, identity | `../worktrees/pdf-t03` | `prompts/T03.md` | 5183 |
| SWE2 C | T05 fixtures and clean controls | `../worktrees/pdf-t05` | `prompts/T05.md` | 5185 |
| Gemini | T06 visual foundations | `../worktrees/pdf-t06` | `prompts/T06.md` | 5186 |

These four task scopes do not overlap. T02 owns shared dependency installation;
the others can implement concurrently but need its usable toolchain for the
relevant validation. None may modify its lockfiles. Use the fifth worker slot
for a bounded independent review or newly ready task. A further SWE2 session
can take T06 if Gemini's allowance is unavailable. GLM is available for later
long experiments, fixture extensions, and documentation that do not delay the
critical path. These are planned assignments, not running sessions.

The coordinator refreshes clean, unclaimed task branches from accepted `main`
before dispatch. The startup guard refuses stale bases and unaccepted dependencies.
Return implementation commit IDs and actual test evidence to the coordinator.
A harness merge action is not Beads acceptance: review, Git integration,
merged-branch checks, a committed acceptance receipt and task closure must all
finish before dependents can start. See `docs/ACCEPTANCE.md` for the evidence
format. Workers stop after their own handoff.

## Coordination commands

```sh
python3 scripts/coordination.py ready
python3 scripts/coordination.py task T01
python3 scripts/coordination.py check
```

`ready` uses the single Beads database in the canonical checkout and verifies
accepted predecessor commit/receipt references. `check` tests this coordination
code only. It is not an application acceptance command.

The planning environment lives only in `original/.tools/planning`. From the
canonical checkout, its existing package checks are:

```sh
PYTHONDONTWRITEBYTECODE=1 .tools/planning/bin/python planning/tools/validate_package.py --json
PYTHONDONTWRITEBYTECODE=1 .tools/planning/bin/python planning/tools/test_validators.py
```

Read `docs/COORDINATION.md` for admission, review, merge, and resume rules.
All 55 product task IDs, dependencies and acceptance dispositions are in Beads.
