#!/usr/bin/env python3
"""Native app dispatch over Beads and Git; no model runner or second task ledger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import coordination as c
import native_followups as f
import acceptance_receipts as receipts


def plan() -> dict:
    return json.loads((c.ROOT / "execution/passes.json").read_text())


def current_pass(config: dict, issues: dict) -> dict | None:
    for stage in config["passes"]:
        if issues.get(f"pdf-pass{stage['id']}", {}).get("status") != "closed":
            return stage
    return None


def admission_stage(config: dict, issues: dict, task_id: str) -> dict | None:
    """Pass checkpoints track completion; dependencies may admit independent work."""
    mode = config.get("admission_mode", "passes")
    if mode == "passes":
        return current_pass(config, issues)
    if mode != "dependencies":
        raise ValueError(f"Unknown admission mode: {mode}")
    stages = [stage for stage in config["passes"] if task_id in stage["tasks"]]
    if len(stages) != 1 or task_id in config.get("owner_release", []):
        raise ValueError(f"{task_id}: requires one implementation stage; owner release is separate")
    return stages[0]


def workbench_for(config: dict, task_id: str, app: str) -> str | None:
    matches = [(name, lane) for name, lane in config.get("workbenches", {}).items()
               if task_id in lane["tasks"]]
    if len(matches) > 1:
        raise ValueError(f"{task_id}: ambiguous workbench routing")
    if matches and matches[0][1]["app"] != app:
        raise ValueError(f"{task_id}: workbench belongs to another app")
    return matches[0][0] if matches else None


def in_workbench(config: dict, task_id: str, grant: dict, app: str, lane: str | None) -> bool:
    if lane is None:
        return True
    # Explicit saved identity wins. Infer only compatible legacy grants, never mutate them.
    if grant.get("workbench"):
        return grant["workbench"] == lane
    return task_id in config["workbenches"][lane]["tasks"] and grant.get("app", app) == app


def check_fresh_predecessors(task: dict, issues: dict, ref: str) -> None:
    for parent in task["dependencies"]:
        try:
            receipts.validate(parent, issues.get(c.bead_id(parent), {}), ref)
        except ValueError as error:
            raise ValueError(f"{parent}: prerequisite acceptance invalid: {error}") from error


def sync_state() -> None:
    c.run(["bd", "--directory", str(c.canonical_root()), "dolt", "pull"])


def publish_state() -> None:
    c.run(["bd", "--directory", str(c.canonical_root()), "dolt", "commit", "-m", "Publish native app handoff"])
    c.run(["bd", "--directory", str(c.canonical_root()), "dolt", "push"])


def assignment(config: dict, task_id: str, app: str, base: str, stage: int) -> dict:
    if task_id not in config["apps"][app]["tasks"]:
        raise ValueError(f"{task_id} is not owned by {app}")
    grant = {"app": app, "branch": config["apps"][app]["branch_prefix"] + task_id.lower(),
             "base": base, "pass": stage}
    lane = workbench_for(config, task_id, app)
    if lane:
        grant["workbench"] = lane
    return grant


def dispatch_errors(config: dict, stage: dict | None, task_id: str, issue: dict,
                    workers: list[dict], app: str) -> list[str]:
    own = [i for i in workers if ((i.get("metadata") or {}).get("execution") or {}).get("app") == app]
    # None removes a numeric ceiling; each grant still requires coordinator admission.
    global_limit = config["max_active_workers"]
    app_limit = config["worker_budgets"][app]
    checks = [
        (stage is None, "All implementation passes are already closed"),
        (task_id not in (stage or {}).get("tasks", []), "Task is outside the current pass"),
        (issue.get("status") != "open", "Task is already claimed or unavailable; resume its existing assignment"),
        (bool(issue.get("assignee")), "Task already has an assignee"),
        (global_limit is not None and len(workers) >= global_limit, "Global worker capacity is occupied"),
        (app_limit is not None and len(own) >= app_limit, "App worker capacity is occupied"),
    ]
    return [message for failed, message in checks if failed]


def dispatch(task_id: str, app: str) -> None:
    config = plan()
    if (c.ROOT.resolve() != c.canonical_root().resolve()
            or c.run(["git", "config", "--get", "inkflip.role"]) != "integrator"):
        raise ValueError(f"Only the designated {config['integration_owner']} integration clone may dispatch")
    c.run(["git", "fetch", "origin", "main"])
    base = c.run(["git", "rev-parse", "HEAD"])
    if c.run(["git", "branch", "--show-current"]) != "main":
        raise ValueError("Dispatch from the integration clone on main")
    if base != c.run(["git", "rev-parse", "origin/main"]):
        raise ValueError("Publish or fast-forward reviewed main before dispatch")
    if c.run(["git", "status", "--porcelain"]):
        raise ValueError("Commit or preserve current changes before dispatch")
    with c.admission_lock():
        sync_state()
        issues = c.issues_by_id()
        stage = admission_stage(config, issues, task_id)
        workers = c.active_workers(issues)
        errors = dispatch_errors(config, stage, task_id, issues.get(c.bead_id(task_id), {}), workers, app)
        if errors:
            raise ValueError("; ".join(errors))
        tasks, overrides = c.load_contracts()
        task = c.effective_task(tasks[task_id], overrides)
        ready = {i["id"] for i in c.bd(["list", "--ready", "--limit", "0"])}
        if c.bead_id(task_id) not in ready:
            raise ValueError("Beads dependencies are not ready")
        c.check_predecessors(task, issues, ref="HEAD")
        check_fresh_predecessors(task, issues, "HEAD")
        c.check_scope_ownership(task, workers, tasks, overrides)
        grant = assignment(config, task_id, app, base, stage["id"])
        metadata = dict(issues[c.bead_id(task_id)].get("metadata") or {})
        metadata["execution"] = grant
        c.bd(["update", c.bead_id(task_id), "--claim", "--metadata",
              json.dumps(metadata)], write=True, actor=f"{app}-{task_id.lower()}")
        # A failed publication leaves a recoverable local claim. Never launch on failure.
        publish_state()
        print(json.dumps(grant, indent=2))


def status(app: str, sync: bool, workbench: str | None = None) -> None:
    config = plan()
    if workbench is not None and config.get("workbenches", {}).get(workbench, {}).get("app") != app:
        raise ValueError("Unknown workbench or workbench belongs to another app")
    with c.admission_lock():
        if sync:
            sync_state()
        issues = c.issues_by_id()
    stage = current_pass(config, issues)
    assignments = []
    undelivered = []
    # Saved grants outlive changes to the static allocation; never remap their branch/app.
    product_tasks = [task for stage in config["passes"] for task in stage["tasks"]]
    product_ids = {c.bead_id(task): task for task in product_tasks}
    for issue_id, issue in sorted(issues.items()):
        grant = f.execution_grant(issue_id, issue)
        assignee = issue.get("assignee") or ""
        task_id = product_ids.get(issue_id, issue_id)
        if not in_workbench(config, task_id, grant, app, workbench):
            continue
        if (issue.get("status") in {"open", "in_progress"} and not grant
                and (assignee == app or assignee.startswith(app + "-"))):
            undelivered.append({"issue": issue_id, "reason": "Assignee has no execution grant; coordinator dispatch required"})
        if issue.get("status") == "in_progress" and grant.get("app") == app:
            if issue_id not in product_ids:
                f.validate_grant(issue_id, grant, config)
            assignments.append({**grant, "task": product_ids.get(issue_id, issue_id),
                                "assignee": issue.get("assignee"), "notes": issue.get("notes", "")})
    print(json.dumps({"app": app, "workbench": workbench, "admission_mode": config.get("admission_mode", "passes"), "current_pass": stage, "assignments": assignments,
                      "undelivered": undelivered,
                      "worker_budget": config["worker_budgets"][app]}, indent=2))


def dispatch_followup(issue_id: str, app: str, mode: str, scopes: list[str], instructions: str) -> None:
    """Claim a ready follow-up, never infer authority from prose or reassign a writer."""
    config = plan()
    f.validate_id(issue_id)
    if (c.ROOT.resolve() != c.canonical_root().resolve()
            or c.run(["git", "config", "--get", "inkflip.role"]) != "integrator"):
        raise ValueError("Only the canonical integrator may dispatch follow-ups")
    c.run(["git", "fetch", "origin", "main"])
    base = c.run(["git", "rev-parse", "HEAD"])
    if (c.run(["git", "branch", "--show-current"]) != "main"
            or base != c.run(["git", "rev-parse", "origin/main"])
            or c.run(["git", "status", "--porcelain"])):
        raise ValueError("Follow-up dispatch requires clean, published canonical main")
    with c.admission_lock():
        sync_state()
        issues = c.issues_by_id()
        issue = issues.get(issue_id, {})
        stage = current_pass(config, issues)
        workers = c.active_workers(issues)
        # Reuse capacity and unclaimed-state rules without treating a follow-up as a product task.
        admission_stage = {**stage, "tasks": [issue_id]} if stage else None
        errors = dispatch_errors(config, admission_stage, issue_id, issue, workers, app)
        if errors:
            raise ValueError("; ".join(errors))
        grant = {"kind": "followup", "app": app, "branch": config["apps"][app]["branch_prefix"] + issue_id,
                 "base": base, "pass": stage["id"], "mode": mode,
                 "allowed_scope": scopes, "instructions": instructions}
        lane = workbench_for(config, issue_id, app)
        if lane:
            grant["workbench"] = lane
        f.validate_grant(issue_id, grant, config)
        ready = {i["id"] for i in c.bd(["list", "--ready", "--limit", "0"])}
        if issue_id not in ready:
            raise ValueError("Beads dependencies are not ready")
        tasks, overrides = c.load_contracts()
        c.check_scope_ownership({"allowed_scope": scopes}, workers, tasks, overrides)
        metadata = dict(issue.get("metadata") or {})
        metadata["execution"] = grant
        c.bd(["update", issue_id, "--claim", "--add-label", "execution:worker", "--metadata",
              json.dumps(metadata)], write=True, actor=f"{app}-{issue_id}")
        publish_state()
        print(json.dumps({**grant, "task": issue_id}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    view = commands.add_parser("status")
    view.add_argument("app", choices=plan()["apps"])
    view.add_argument("--sync", action="store_true")
    view.add_argument("--workbench", choices=plan().get("workbenches", {}))
    admit = commands.add_parser("dispatch")
    admit.add_argument("task")
    admit.add_argument("--app", required=True, choices=plan()["apps"])
    followup = commands.add_parser("dispatch-followup")
    followup.add_argument("issue")
    followup.add_argument("--app", required=True, choices=plan()["apps"])
    followup.add_argument("--mode", required=True, choices=("audit", "implementation"))
    followup.add_argument("--scope", action="append", required=True)
    followup.add_argument("--instructions-file", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "dispatch":
        dispatch(args.task, args.app)
    elif args.command == "dispatch-followup":
        dispatch_followup(args.issue, args.app, args.mode, args.scope, args.instructions_file.read_text())
    else:
        status(args.app, args.sync, args.workbench)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(f"Native pass blocked: {error}")
