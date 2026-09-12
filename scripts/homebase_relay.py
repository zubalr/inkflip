#!/usr/bin/env python3
"""Explicit Mac relay: publish after bd dolt push; collect product tasks and granted follow-ups.

No Beads writes or worker launching. JSON success is emitted only after all
requested Git operations succeed. Failures may follow earlier collections;
retry is safe. Configuration is project-owned, never supplied on the command line.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import coordination as c
import native_followups as f
import native_pass as p

DOLT_REF = "refs/dolt/data"


def config() -> dict:
    return json.loads((c.ROOT / "config/homebase.json").read_text())


def git(*args: str) -> str:
    return c.run(["git", *args], cwd=c.ROOT)


def validate_clone(settings: dict) -> None:
    if c.ROOT.resolve() != Path(settings["canonical_root"]).resolve():
        raise ValueError("Relay requires the configured canonical integrator clone")
    if c.ROOT.resolve() != c.canonical_root():
        raise ValueError("Relay cannot run in a linked worktree")
    if git("config", "--get", "inkflip.role") != "integrator":
        raise ValueError("Relay requires inkflip.role=integrator")
    for remote in ("origin", "homebase"):
        expected = [settings["remotes"][remote]]
        if git("remote", "get-url", "--all", remote).splitlines() != expected:
            raise ValueError(f"Unexpected {remote} fetch target")
        if git("remote", "get-url", "--push", "--all", remote).splitlines() != expected:
            raise ValueError(f"Unexpected {remote} push target")


def advertised(remote: str, *patterns: str) -> dict[str, str]:
    # A successful empty advertisement means waiting; transport errors propagate.
    lines = git("ls-remote", "--refs", remote, *patterns).splitlines()
    return {ref: sha for sha, ref in (line.split() for line in lines)}


def fetch_snapshot(remote: str, refs: dict[str, str]) -> dict[str, str]:
    if not refs:
        return {}
    destinations = {ref: f"refs/inkflip/relay/{remote}/{ref.removeprefix('refs/')}" for ref in refs}
    # Dolt periodically prunes its Git transport history into a parentless snapshot.
    refspecs = [f"{'+' if ref == DOLT_REF else ''}{ref}:{local}"
                for ref, local in destinations.items()]
    git("fetch", "--no-tags", "--no-write-fetch-head", "--refmap=", remote, *refspecs)
    received = git("rev-parse", *destinations.values()).splitlines()
    if received != list(refs.values()):
        raise ValueError(f"{remote} references changed during fetch; retry")
    return dict(refs)


def require_ancestor(base: str, candidate: str, context: str) -> None:
    try:
        git("merge-base", "--is-ancestor", base, candidate)
    except ValueError as error:
        raise ValueError(f"{context}: candidate does not descend from {base}") from error


def publish() -> dict:
    validate_clone(config())
    if git("branch", "--show-current") != "main":
        raise ValueError("Publish requires main")
    if git("status", "--porcelain"):
        raise ValueError("Publish requires a clean checkout")
    refs = fetch_snapshot("origin", advertised(
        "origin", "refs/heads/main", "refs/heads/work/*", "refs/heads/review/*", DOLT_REF))
    if DOLT_REF not in refs:
        raise ValueError("Publish native Beads with bd dolt push before relay publication")
    if refs.get("refs/heads/main") != git("rev-parse", "HEAD"):
        raise ValueError("Publish requires clean, published main")
    previous = fetch_snapshot("homebase", advertised("homebase", *refs))
    for ref, sha in previous.items():
        if ref != DOLT_REF:
            require_ancestor(sha, refs[ref], f"Homebase divergence at {ref}")
    # Atomic prevents a rejected code/state ref from looking like dispatched work.
    # Only the native storage snapshot may roll over, and only at the observed SHA.
    lease = f"--force-with-lease={DOLT_REF}:{previous.get(DOLT_REF, '')}"
    git("push", "--atomic", "--no-follow-tags", "--recurse-submodules=no", lease,
        "homebase", *(f"{sha}:{ref}" for ref, sha in refs.items()))
    return {"status": "published", "refs": refs}


def grant_for(task: str, issues: dict) -> dict:
    product = re.fullmatch(r"T(?:0[1-9]|[1-4][0-9]|5[0-5])", task)
    issue_id = c.bead_id(task) if product else task
    issue = issues.get(issue_id, {})
    grant = f.execution_grant(issue_id, issue)
    if issue.get("status") != "in_progress" or grant.get("app") != "zcode":
        raise ValueError(f"{task}: requires an active zcode grant")
    if not product:
        f.validate_grant(task, grant, p.plan())
        return grant
    if grant.get("branch") != f"work/zcode/{task.lower()}":
        raise ValueError(f"{task}: unsafe or mismatched assigned branch")
    if not re.fullmatch(r"[0-9a-f]{40}", str(grant.get("base", ""))):
        raise ValueError(f"{task}: grant requires an exact full base commit")
    return grant


def collect_one(task: str, grant: dict) -> dict:
    incoming = f"refs/heads/hb/inkflip/{task.lower()}"
    refs = advertised("homebase", incoming)
    if incoming not in refs:
        return {"task": task, "status": "waiting"}
    candidate = refs[incoming]
    tracking = f"refs/remotes/homebase/hb/inkflip/{task.lower()}"
    git("fetch", "--no-tags", "--no-write-fetch-head", "--refmap=", "homebase", f"{incoming}:{tracking}")
    if git("rev-parse", tracking) != candidate:
        raise ValueError(f"{task}: incoming branch changed during fetch; retry")
    require_ancestor(grant["base"], candidate, f"{task} grant base")
    target = f"refs/heads/{grant['branch']}"
    published = fetch_snapshot("origin", advertised("origin", target))
    if target in published:
        require_ancestor(published[target], candidate, f"{task} published branch")
    status = "unchanged"
    if published.get(target) != candidate:
        git("push", "--no-follow-tags", "--recurse-submodules=no", "origin", f"{candidate}:{target}")
        status = "collected"
    return {"task": task, "status": status, "branch": grant["branch"], "commit": candidate}


def collect(task: str | None = None) -> dict:
    validate_clone(config())
    issues = c.issues_by_id()
    if not isinstance(issues, dict):
        raise ValueError("Malformed issue records")
    tasks = [task] if task is not None else []
    if task is None:
        for issue_id, issue in issues.items():
            if not isinstance(issue_id, str):
                raise ValueError("Malformed issue ID")
            grant = f.execution_grant(issue_id, issue)
            if issue.get("status") == "in_progress" and grant.get("app") == "zcode":
                product = re.fullmatch(r"pdf-t(?:0[1-9]|[1-4][0-9]|5[0-5])", issue_id)
                tasks.append(issue_id.removeprefix("pdf-").upper() if product else issue_id)
        tasks.sort()
    grants = [(tid, grant_for(tid, issues)) for tid in tasks]
    return {"status": "ok", "results": [collect_one(tid, grant) for tid, grant in grants]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("publish")
    commands.add_parser("collect").add_argument("task", nargs="?")
    args = parser.parse_args()
    try:
        result = publish() if args.command == "publish" else collect(args.task)
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "error", "error": str(error)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
