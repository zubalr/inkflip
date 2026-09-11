# Start the implementation

This repository contains the verified planning snapshot and local coordination
setup. The application and T01 command harness are still implementation work.

## Start now

Open one **SWE2** session in `../worktrees/pdf-t01` and paste `prompts/T01.md`
from this repository. It owns the bootstrap only. Bring its completion report
back to the coordinator for independent review and integration.

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

Before the parallel pass, the coordinator refreshes the four clean task branches
from the accepted `main`. The startup guard refuses the current seed-only bases
after `main` advances; it will not silently execute future tasks early.

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
All 55 product task IDs and dependencies are in Beads. No product gate has passed.
