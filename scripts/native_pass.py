#!/usr/bin/env python3
"""Native app dispatch over Beads and Git; no model runner or second task ledger."""
from __future__ import annotations

import argparse
import json

import coordination as c


def plan() -> dict:
    return json.loads((c.ROOT / "execution/passes.json").read_text())


def current_pass(config: dict, issues: dict) -> dict | None:
    for stage in config["passes"]:
        if issues.get(f"pdf-pass{stage['id']}", {}).get("status") != "closed":
            return stage
    return None


def sync_state() -> None:
    c.run(["bd", "--directory", str(c.canonical_root()), "dolt", "pull"])


def publish_state() -> None:
    c.run(["bd", "--directory", str(c.canonical_root()), "dolt", "commit", "-m", "Publish native app handoff"])
    c.run(["bd", "--directory", str(c.canonical_root()), "dolt", "push"])


def assignment(config: dict, task_id: str, app: str, base: str, stage: int) -> dict:
    if task_id not in config["apps"][app]["tasks"]:
        raise ValueError(f"{task_id} is not owned by {app}")
    return {"app": app, "branch": config["apps"][app]["branch_prefix"] + task_id.lower(),
            "base": base, "pass": stage}


def dispatch_errors(config: dict, stage: dict | None, task_id: str, issue: dict,
                    workers: list[dict], app: str) -> list[str]:
    own = [i for i in workers if i.get("metadata", {}).get("execution", {}).get("app") == app]
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
    if c.run(["git", "config", "--get", "inkflip.role"]) != "integrator":
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
        stage = current_pass(config, issues)
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
        c.check_scope_ownership(task, workers, tasks, overrides)
        grant = assignment(config, task_id, app, base, stage["id"])
        metadata = dict(issues[c.bead_id(task_id)].get("metadata") or {})
        metadata["execution"] = grant
        c.bd(["update", c.bead_id(task_id), "--claim", "--metadata",
              json.dumps(metadata)], write=True, actor=f"{app}-{task_id.lower()}")
        # A failed publication leaves a recoverable local claim. Never launch on failure.
        publish_state()
        print(json.dumps(grant, indent=2))


def status(app: str, sync: bool) -> None:
    config = plan()
    with c.admission_lock():
        if sync:
            sync_state()
        issues = c.issues_by_id()
    stage = current_pass(config, issues)
    assignments = []
    # Saved grants outlive changes to the static allocation; never remap their branch/app.
    product_tasks = [task for stage in config["passes"] for task in stage["tasks"]]
    for task_id in product_tasks:
        issue = issues.get(c.bead_id(task_id), {})
        grant = issue.get("metadata", {}).get("execution", {})
        if issue.get("status") == "in_progress" and grant.get("app") == app:
            assignments.append({"task": task_id, "assignee": issue.get("assignee"),
                                "notes": issue.get("notes", ""), **grant})
    print(json.dumps({"app": app, "current_pass": stage, "assignments": assignments,
                      "worker_budget": config["worker_budgets"][app]}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    view = commands.add_parser("status")
    view.add_argument("app", choices=plan()["apps"])
    view.add_argument("--sync", action="store_true")
    admit = commands.add_parser("dispatch")
    admit.add_argument("task")
    admit.add_argument("--app", required=True, choices=plan()["apps"])
    args = parser.parse_args()
    if args.command == "dispatch":
        dispatch(args.task, args.app)
    else:
        status(args.app, args.sync)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(f"Native pass blocked: {error}")
