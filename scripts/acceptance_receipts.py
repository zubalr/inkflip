"""Validate coordinator acceptance against committed code and evidence.

This verifies evidence structure and freshness. Independent reviewers remain
responsible for the substance of manual evidence and acceptance criteria.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

import coordination
import test_results

ROOT = Path(__file__).resolve().parents[1]
COMMON_INPUTS = ["scripts/", "config/", "package.json", "bun.lock", "bunfig.toml",
                 "native/pyproject.toml", "native/uv.lock", "execution/overrides.json"]


def git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode().strip() or "Git evidence lookup failed")
    return result.stdout


def contract_digest(task: dict) -> str:
    return hashlib.sha256(json.dumps(task, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def segments(task: dict) -> list[str]:
    commands = [part.strip() for command in task["commands"] for part in command.split("&&")]
    if not commands or any(not part for part in commands):
        raise ValueError(f"{task['id']}: empty acceptance command registration")
    return commands


def evidence_path(path: str, task_id: str) -> str:
    if not isinstance(path, str):
        raise ValueError("evidence path must be a string")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or not path.startswith(f"artifacts/tasks/{task_id}/"):
        raise ValueError(f"{task_id}: evidence must stay in its task namespace")
    return path


def validation_scopes(task_id: str, tasks: dict, overrides: dict) -> list[str]:
    pending, visited, scopes = [task_id], set(), list(COMMON_INPUTS)
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        task = coordination.effective_task(tasks[current], overrides)
        scopes.extend(task["allowed_scope"])
        pending.extend(task["dependencies"])
    return sorted(set(scopes))


def check_freshness(evaluated: str, ref: str, scopes: list[str]) -> None:
    if not isinstance(evaluated, str) or not re.fullmatch(r"[0-9a-f]{40}", evaluated):
        raise ValueError("receipt needs the full evaluated commit")
    git("merge-base", "--is-ancestor", evaluated, ref)
    changed = git("diff", "--name-only", evaluated, ref, "--", *scopes).decode().splitlines()
    if changed:
        raise ValueError(f"stale receipt: validation inputs changed ({', '.join(changed[:5])})")


def validate_commands(records: list[dict], task: dict) -> None:
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ValueError("receipt commands must be a list of result objects")
    if [r.get("segment") for r in records] != segments(task):
        raise ValueError("receipt does not cover the exact effective task commands")
    for record in records:
        if type(record.get("exit")) is not int or record["exit"] != 0:
            raise ValueError("receipt contains an unsuccessful command")
        if not record.get("argv") or not record.get("cwd"):
            raise ValueError("receipt is missing the executed command or working directory")
        if "tests" in record:
            test_results.validate_counts(record["tests"])
    test_results.validate_counts(test_results.total_counts(records))


def validate_evidence(data: dict, task: dict, commit: str, ref: str) -> None:
    evidence = data.get("evidence")
    if not isinstance(evidence, dict) or not set(task["evidence_artifacts"]).issubset(evidence):
        raise ValueError("receipt is missing required evidence artifacts")
    for path, digest in evidence.items():
        evidence_path(path, task["id"])
        blob = git("show", f"{commit}:{path}")
        if not blob.strip() or hashlib.sha256(blob).hexdigest() != digest:
            raise ValueError(f"missing, empty or mismatched evidence: {path}")
        if git("show", f"{ref}:{path}") != blob:
            raise ValueError(f"stale evidence: {path}")
        if path.endswith(".json"):
            json.loads(blob)
    criteria = data.get("criteria")
    if not isinstance(criteria, dict) or set(criteria) != set(task["acceptance_criteria"]):
        raise ValueError("receipt must cover every acceptance criterion")
    for paths in criteria.values():
        if not isinstance(paths, list) or not paths or not all(p in evidence for p in paths):
            raise ValueError("each criterion needs references to bound evidence")
    review = data.get("review", {})
    if review.get("disposition") != "approved" or review.get("path") not in evidence:
        raise ValueError("independent approval and its bound review artifact are required")
    reviewers = review.get("reviewers")
    if not isinstance(reviewers, list) or not reviewers or not all(isinstance(r, str) and r.strip() for r in reviewers):
        raise ValueError("independent reviewer identities are required")
    if not data.get("worker") or data["worker"] in reviewers:
        raise ValueError("the worker cannot approve their own acceptance")


def validate(task_id: str, issue: dict, ref: str = "HEAD") -> dict:
    commit, receipt = coordination.acceptance_reference(task_id, issue)
    git("merge-base", "--is-ancestor", commit, ref)
    try:
        data = json.loads(git("show", f"{commit}:{receipt}"))
        tasks, overrides = coordination.load_contracts()
        task = coordination.effective_task(tasks[task_id], overrides)
        expected = {"schema_version": 1, "task_id": task_id, "beads_id": coordination.bead_id(task_id),
                    "contract_digest": contract_digest(task),
                    "disposition": issue["metadata"]["disposition"]}
        if not isinstance(data, dict) or any(data.get(key) != value for key, value in expected.items()):
            raise ValueError("receipt schema, identity, contract or disposition mismatch")
        if not data.get("evaluated_at"):
            raise ValueError("receipt evaluation timestamp is required")
        scopes = validation_scopes(task_id, tasks, overrides)
        check_freshness(data.get("evaluated_commit"), commit, scopes)
        check_freshness(data["evaluated_commit"], ref, scopes)
        validate_commands(data.get("commands"), task)
        validate_evidence(data, task, commit, ref)
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"{task_id}: malformed acceptance receipt") from error
    return {"task": task_id, "accepted_commit": commit, "receipt": receipt,
            "evaluated_commit": data["evaluated_commit"]}


def require_clean_inputs() -> str:
    # Evidence-only and Beads audit changes can be committed after the run.
    changed = git("status", "--porcelain", "--untracked-files=all", "--", ".",
                  ":(exclude)artifacts/", ":(exclude).beads/").decode().strip()
    if changed:
        raise ValueError("commit implementation changes before recording acceptance evidence")
    return git("rev-parse", "HEAD").decode().strip()
