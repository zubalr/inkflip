#!/usr/bin/env python3
"""Beads-backed task briefs and admission; no provider launching or product gates."""
from __future__ import annotations

import argparse
import copy
import fcntl
import json
import re
import subprocess
import sys
import unittest
import native_followups as followups
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = {f"T{n:02}" for n in range(41, 46)}


def run(argv: list[str], cwd: Path = ROOT) -> str:
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or f"Command failed: {argv[0]}")
    return result.stdout.strip()


def canonical_root() -> Path:
    common = Path(run(["git", "rev-parse", "--git-common-dir"], cwd=ROOT))
    return (ROOT / common).resolve().parent


def bead_id(task_id: str) -> str:
    return "pdf-" + task_id.lower()


def load_contracts() -> tuple[dict, dict]:
    tasks = json.loads((ROOT / "planning/execution/tasks.json").read_text())
    overrides = json.loads((ROOT / "execution/overrides.json").read_text())
    return {t["id"]: t for t in tasks}, overrides


def adapt_command(command: str, overrides: dict) -> str:
    for before, after in overrides["command_replacements"]:
        command = command.replace(before, after)
    return command


def effective_task(task: dict, overrides: dict) -> dict:
    result = copy.deepcopy(task)
    result.pop("status", None)
    paths = overrides["path_replacements"]
    result["allowed_scope"] = [paths.get(p, p) for p in task["allowed_scope"]]
    result["allowed_scope"] += overrides["scope_additions"].get(task["id"], [])
    for item in result["deliverables"]:
        item["path"] = paths.get(item["path"], item["path"])
    result["commands"] = [adapt_command(c, overrides) for c in task["commands"]]
    result["required_updates"] = [line.replace("execution/state.json", "Beads acceptance state") for line in task["required_updates"]]
    result["rollback"] = "Coordinator only: " + task["rollback"]
    result["state_authority"] = "Beads; template status is not live state"
    result["beads_id"] = bead_id(task["id"])
    result["reserved_paths"] = overrides["reserved_paths"]
    return result


def bd(args: list[str], *, write: bool = False, actor: str | None = None) -> object:
    argv = ["bd", "--sandbox", "--directory", str(canonical_root()), "--json"]
    if not write:
        argv.append("--readonly")
    if actor:
        argv += ["--actor", actor]
    return json.loads(run(argv + args))


def issues_by_id() -> dict:
    return {i["id"]: i for i in bd(["list", "--all", "--limit", "0"])}


def acceptance_reference(task_id: str, issue: dict) -> tuple[str, str]:
    if issue.get("status") != "closed":
        raise ValueError(f"{task_id}: predecessor has not been accepted/closed")
    metadata = issue.get("metadata") or {}
    allowed = {"accepted"}
    if task_id in EXPERIMENTS:
        allowed.add("rejected_experiment")
    if metadata.get("disposition") not in allowed:
        raise ValueError(f"{task_id}: missing or invalid acceptance disposition")
    commit = metadata.get("accepted_commit", "")
    receipt = metadata.get("accepted_receipt", "")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"{task_id}: missing full accepted commit")
    if not isinstance(receipt, str):
        raise ValueError(f"{task_id}: invalid receipt path")
    path = PurePosixPath(receipt)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".json" or not receipt.startswith(f"artifacts/tasks/{task_id}/"):
        raise ValueError(f"{task_id}: receipt must be in its own task namespace")
    return commit, receipt


def check_predecessors(task: dict, issues: dict, *, ref: str) -> None:
    for parent in task["dependencies"]:
        commit, receipt = acceptance_reference(parent, issues.get(bead_id(parent), {}))
        import evidence_store
        evidence_store.require_ancestry(ROOT, commit, ref, parent)
        if run(["git", "cat-file", "-t", f"{commit}:{receipt}"], cwd=ROOT) != "blob":
            raise ValueError(f"{parent}: accepted receipt is not a committed file")


def task_ready(task: dict, issues: dict, ready_ids: set[str]) -> bool:
    if bead_id(task["id"]) not in ready_ids:
        return False
    check_predecessors(task, issues, ref="main")
    return True


def admission_errors(task_id: str, issue: dict, *, branch: str, dirty: bool,
                     fresh: bool, active: int, maximum: int) -> list[str]:
    checks = [
        (branch != f"work/{bead_id(task_id)}", "Use the assigned worktree and task branch"),
        (dirty, "Preserve existing changes; ask the coordinator for a reviewed resume"),
        (not fresh, "Task branch differs from main; the coordinator must prepare its reviewed starting point"),
        (issue.get("status") != "open", "Task is already claimed or unavailable; do not start another writer"),
        (bool(issue.get("assignee")), "Task already has an assignee; coordinate the handoff"),
        (active >= maximum, f"Configured worker capacity is occupied ({active}/{maximum}); wait for coordinator admission"),
    ]
    return [message for failed, message in checks if failed]


def validate_actor(actor: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", actor):
        raise ValueError("Use a unique lowercase session label for --actor")


@contextmanager
def admission_lock():
    lock_path = canonical_root() / ".beads/coordination-admission.lock"
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield issues_by_id()


def active_workers(issues: dict) -> list[dict]:
    return [i for i in issues.values()
            if i.get("status") == "in_progress" and
            ("execution:worker" in i.get("labels", []) or followups.execution_grant(i.get("id", "unknown"), i))]


def scopes_overlap(left: str, right: str) -> bool:
    # Wildcards conservatively reserve their literal directory prefix.
    a, b = (re.split(r"[*?\[]", scope, maxsplit=1)[0].rstrip("/") for scope in (left, right))
    return not a or not b or a == b or a.startswith(b + "/") or b.startswith(a + "/")


def check_scope_ownership(task: dict, workers: list[dict], tasks: dict, overrides: dict) -> None:
    known = {bead_id(tid): effective_task(t, overrides) for tid, t in tasks.items()}
    for issue in workers:
        grant = followups.execution_grant(issue["id"], issue)
        if "execution:review" in issue.get("labels", []) and grant.get("kind") != "followup":
            continue
        owner = known.get(issue["id"])
        if owner is None:
            if grant.get("kind") == "followup":
                config = json.loads((ROOT / "execution/passes.json").read_text())
                followups.validate_grant(issue["id"], grant, config)
                owner = {"allowed_scope": grant["allowed_scope"]}
        if owner is None:
            raise ValueError(f"{issue['id']} has no known writer scope; coordinator must resolve it")
        conflicts = [(a, b) for a in task["allowed_scope"] for b in owner["allowed_scope"]
                     if scopes_overlap(a, b)]
        if conflicts:
            raise ValueError(f"Writer scope overlaps {issue['id']}: {conflicts[0]}; finish its ownership first")


def start(task: dict, actor: str, overrides: dict) -> None:
    raise ValueError(
        "Deprecated local admission is refused: the coordinator admits work only "
        "through 'python3 scripts/native_pass.py dispatch' from the canonical "
        "integration checkout, which records the grant in Beads. Workers never "
        "self-claim; ask the coordinator for a grant or a reviewed resume.")


def start_review(issue_id: str, actor: str, overrides: dict) -> None:
    raise ValueError(
        "Deprecated local review admission is refused: request an explicit "
        "independent review assignment from the coordinator through existing "
        "native facilities. Workers never self-claim.")


def ready(tasks: dict) -> None:
    issues = issues_by_id()
    ready_ids = {i["id"] for i in bd(["list", "--ready", "--limit", "0"])}
    shown = 0
    for task in tasks.values():
        try:
            if task_ready(task, issues, ready_ids):
                print(f"{task['id']} | {bead_id(task['id'])} | {task['title']}")
                shown += 1
        except ValueError as error:
            print(f"BLOCKED {task['id']}: {error}", file=sys.stderr)
    if not shown:
        print("No product task is ready with accepted predecessor evidence.")


def check() -> None:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests/coordination"))
    if not suite.countTestCases():
        raise ValueError("No coordination tests were collected")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise ValueError("Coordination tests failed")
    print("Coordination checks passed. No product acceptance was executed.")


def render_prompt(task: dict, actor: str, overrides: dict) -> str:
    validate_actor(actor)
    tid = task["id"]
    port = overrides["development_port_base"] + int(tid[1:])
    inputs = "\n".join(f"- `planning/{p}`" for p in task["input_files"])
    scope = "\n".join(f"- `{p}`" for p in task["allowed_scope"])
    assertions = "\n".join(f"- {a}" for a in task["acceptance_criteria"])
    commands = "\n".join(task["commands"])
    focus = {
        "T01": """The coordinator has already created Git, Beads, the planning snapshot, task
branches, and this coordination helper. Preserve them; implement the actual
monorepo and command harness now. The original task's integrator title does
not give this worker merge or acceptance authority.

Create Bun workspace manifests, bunfig.toml with the isolated linker, the
React/Vite entry, shared package build boundaries, native project boundary,
and meaningful bootstrap tests. Root check/verify must test existing behavior;
unregistered future suites and zero collected tests must fail explicitly.
Adapt task acceptance and the nonrecursive gate runner to Beads and the shared
command/path overrides. Keep the current admission helper as the single place
for task claiming, not another JSON state writer. T02 owns resolved installs,
locks, audited test dependencies and model assets. Make unavailable tooling
explicit; do not create fabricated lockfiles or dependency digests.

Establish the CSS Modules contract and central token location in the initial
scaffold, following the supplied visual direction. T06 takes ownership of
apps/web/src/styles/ after this bootstrap is accepted. Read AGENTS.md again if
the automatic product contract updates it. Discover and run the repository's
actual engineering gates. Preserve the exact historical origin license under
the package's required path without importing the old runtime. Do not modify
the sibling mib-intake repository.""",
        "T02": """You exclusively own the root dependency/lock/toolchain/model surfaces for
this pass. T03, T05, and T06 have other writers. Gather their dependency needs,
declare them explicitly, and coordinate coherent installable checkpoints with
the integrator. They must not produce competing lockfiles. Use Bun's isolated
linker, an explicit trusted install-script policy, and frozen installs.

Verify planned versions against official sources, actual registry resolution,
engine compatibility, and advisories. Preserve the selected library families
and record justified substitutions. The setup's Python interpreter is only a
planning tool, not an audited native production pin. Exercise real browser
PDF.js/Tesseract loading on the bundled fixture/control as an early feasibility
probe, clearly separated from unimplemented application acceptance. Keep
assets same-origin, record hashes and rights, and preserve explicit model
preparation. Finish the entire T02 acceptance, including provenance; a small
probe alone does not complete this task.""",
        "T03": """You own the cross-language data contract, semantic validators, canonical
identity, and generated types. T02 owns installation and root manifests;
request dependencies instead of editing that surface. Implement the delivered
schema without semantic redesign. Keep one schema authoritative, generated TS
types deterministic, and Python/TS validators in parity. Preserve raw strings,
duplicate occurrences, incomplete checks, precise versus page-only geometry,
strict parsing, and every hash vector. Do not create a second schema in a new
validation framework. Hand off a stable consumer interface for T04 and readers.
T04 is a later assignment after this task has been reviewed and merged.""",
        "T05": """You own public/development fixture recipes and the shared fixture manifest.
Readers may request fixture additions but do not edit this surface concurrently.
Preserve the amount example's mapping/clean pair and include the legitimate
searchable-scan F03 control before G1. Produce original, deterministic fixtures
and record source/rights/generation provenance. Rendering/extraction assertions
must use real installed readers at the recorded versions; request tooling from
T02 and disclose anything still blocked. Keep public/development fixtures apart
from genuinely held-out evaluation labels. No filename-specific app behavior
or private documents may enter the fixtures.""",
        "T06": """Translate the provided desktop/narrow reference into a polished visual
foundation using CSS Modules and central semantic CSS-variable tokens. Preserve
the warm paper/ink palette, restrained teal/rust accents, editorial type,
document-led composition, and exact relevant copy. Make customization happen
through the shared tokens; component styles stay isolated. Do not add Effect,
StyleX, Tailwind, a new framework, or a general UI library for this task.

Use the supplied design as the visual brief with the installed design workflow.
Verify actual rendered output at all required widths and reduced motion.
Implement DocumentStage's presentation states within the owned component;
processing belongs to the reader tasks. Clearly label contract-example data.
Keep root App composition and dependency changes with their owners. Request
test harness/mount integration from the coordinator if needed. T07's controls
are a subsequent task after T03 and T06 acceptance, not extra scope here.""",
    }.get(tid, "Follow the effective task contract and its referenced specification.")
    return f"""# {tid}: {task['title']}

You are an implementation worker in the owner's PDF inspector project.
Use the exact branch saved in your Beads execution grant and the checkout
assigned separately by the coordinator; do not create or assume a worktree
or branch.
Beads task: `{bead_id(tid)}`. Suggested unique session label: `{actor}`.
Development port: `{port}` with strict-port behavior; tests use separate ports.

## Goal and authority

Build a browser-only PDF reading inspector plus useful local native/corpus/
regression tools. Reports preserve named readings and uncertainty. Original
bytes remain immutable; document data stays local. The complete product is
defined by the package; this assignment is **only {tid}**.

The owner selected Bun (isolated), React/Vite/TypeScript, CSS Modules with central
tokens, oxlint/oxfmt, Python/uv, and the explicit Node comparison runtime.
Effect is excluded. AGENTS.md, docs/COORDINATION.md and execution/overrides.json
override conflicting pnpm, task-state-file, or role instructions in the frozen
planning material. Product acceptance, data/geometry contracts and quality
thresholds remain mandatory. Leave planning/ unchanged.

## Start safely

1. Open the assigned checkout and inspect Git status. You are not alone in this
   repository: preserve other work and edit only your assigned files.
2. Read AGENTS.md and docs/COORDINATION.md, then inspect the effective
   contract:

```sh
python3 scripts/coordination.py task {tid}
```

3. Start editing only inside a coordinator-granted checkout. The coordinator
   admits work through `scripts/native_pass.py dispatch`, which records the
   grant in Beads; it separately prepares and names the granted checkout.
   Workers never self-claim and
   the historical `coordination.py start`/`start-review` commands refuse.
   A blocked future task, stale base, dirty checkout, occupied claim, or
   absent grant needs a coordinator handoff. Do not reset, force-refresh,
   reinitialize Beads, or work around it. For a resumed session, ask the
   coordinator to confirm its existing claim.
4. Read the task record and the following relevant inputs; do not ingest the
   entire package or any held-out labels:

{inputs}

## Task focus

{focus}

## Owned implementation scope

{scope}

You may also write your own `artifacts/tasks/{tid}/` evidence and
`docs/proposals/{tid}*.md` mismatch proposals. Shared root manifests/locks,
schema, geometry, fixtures, tokens, composition and deployment policy retain
their named owners. Reserved coordination files require a coordinator change.
Being able to see another worktree is not permission to edit it.

## Acceptance

{assertions}

Use the implemented task harness when available and execute the effective task
commands below with the installed, recorded toolchain. Treat unavailable
commands as blockers, not a pass:

```sh
{commands}
```

Run the relevant engineering checks and inspect rendered output for visual
work. Record actual command output and collected/passed/failed/skipped counts.
Do not weaken assertions, omit required cases, overwrite baselines, or call
native/prepared evidence proof of browser behavior. If a shared contract is
wrong, supply a minimal reproducer and request a coordinated correction.

## Finish and handoff

Create coherent local implementation commits with actual attribution. Local
commits are authorized. The coordinator owns merges, Beads closure, acceptance
metadata, shared baseline decisions, and integration-branch rollback. Remote
creation, pushes/PRs, publication, deployment, paid resources, and messages to
other people are outside this assignment.

Leave an evidence receipt and command log in `artifacts/tasks/{tid}/`. Do not
write an independent review or acceptance approval for your own work. Return:

- Task, branch, exact commit(s), and changed paths.
- What now works and which acceptance assertions have executed evidence.
- Commands, exit codes, counts, and artifact/screenshot paths.
- Unverified behavior, environment limits, dependency requests, and blockers.
- Any required shared-interface change and its reproducer.

Then stop for independent review and integration. Do not self-assign another
task. Multiple sessions may use the same model; ownership stays with this task.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ready")
    sub.add_parser("check")
    sub.add_parser("task").add_argument("task_id")
    prompt = sub.add_parser("prompt")
    prompt.add_argument("task_id")
    prompt.add_argument("--actor", required=True)
    begin = sub.add_parser("start")
    begin.add_argument("task_id")
    begin.add_argument("--actor", required=True)
    review = sub.add_parser("start-review")
    review.add_argument("issue_id")
    review.add_argument("--actor", required=True)
    args = parser.parse_args()
    tasks, overrides = load_contracts()
    if args.command == "ready":
        ready(tasks)
    elif args.command == "check":
        check()
    elif args.command == "start-review":
        start_review(args.issue_id, args.actor, overrides)
    else:
        if args.task_id not in tasks:
            raise ValueError("Unknown planning task ID; use T01 through T55")
        task = effective_task(tasks[args.task_id], overrides)
        if args.command == "task":
            print(json.dumps(task, indent=2, ensure_ascii=False))
        elif args.command == "prompt":
            print(render_prompt(task, args.actor, overrides))
        else:
            start(task, args.actor, overrides)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(f"Coordination blocked: {error}", file=sys.stderr)
        sys.exit(1)
