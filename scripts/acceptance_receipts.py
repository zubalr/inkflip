"""Validate coordinator acceptance against committed code and evidence.

This verifies evidence structure and freshness. Independent reviewers remain
responsible for the substance of manual evidence and acceptance criteria.
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import string
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
    registry = json.loads((coordination.ROOT / "config/acceptance-commands.json").read_text())
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ValueError("receipt commands must be a list of result objects")
    if [r.get("segment") for r in records] != segments(task):
        raise ValueError("receipt does not cover the exact effective task commands")
    for record in records:
        if type(record.get("exit")) is not int or record["exit"] != 0:
            raise ValueError("receipt contains an unsuccessful command")
        environment = record.get("environment", {})
        if set(environment) - {"INKFLIP_PUBLIC_ORIGIN"}:
            raise ValueError("receipt contains an unsupported command environment")
        expected = [string.Template(a).substitute(environment) for a in shlex.split(record["segment"])]
        actual = record.get("argv", [])
        mapped = registry.get("interpreters", {}).get(expected[0], expected[0])
        if not actual or actual[1:] != expected[1:] or actual[0] not in (expected[0], mapped):
            raise ValueError("executed argv does not match the effective command")
        if record.get("cwd") != "." or not Path(record.get("checkout", "")).is_absolute():
            raise ValueError("task commands must execute at the recorded repository root")
        if test_results.requires_tests(actual, registry) or "tests" in record:
            test_results.validate_counts(record.get("tests", {}))
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


def verified_run(task: dict, run_path: Path) -> dict:
    run = json.loads(run_path.read_text())
    if run.get("task") != task["id"] or run.get("failures") != [] or run.get("evidence_errors") != []:
        raise ValueError("run report must identify this task and contain no failures or evidence errors")
    validate_commands(run.get("records"), task)
    if run.get("tests") != test_results.total_counts(run["records"]):
        raise ValueError("run totals do not match the per-command counts")
    tasks, overrides = coordination.load_contracts()
    check_freshness(run.get("evaluated_commit"), "HEAD", validation_scopes(task["id"], tasks, overrides))
    return run


def criterion_evidence(task: dict, pending: dict) -> dict[str, list[str]]:
    proofs = pending.get("acceptance_criteria_evidence", {})
    normalized = {key.rstrip("."): value for key, value in proofs.items()}
    criteria = {}
    for criterion in task["acceptance_criteria"]:
        proof = normalized.get(criterion.rstrip("."), {})
        paths = proof.get("evidence")
        if proof.get("status") != "executed" or not isinstance(paths, list) or not paths:
            raise ValueError(f"worker evidence needs executed criterion and explicit evidence paths: {criterion}")
        criteria[criterion] = [evidence_path(path, task["id"]) for path in paths]
    return criteria


def evidence_digests(paths: list[str], task_id: str) -> dict[str, str]:
    result = {}
    for path in sorted(set(paths)):
        evidence_path(path, task_id)
        content = (ROOT / path).read_bytes()
        if not content.strip():
            raise ValueError(f"evidence is empty: {path}")
        result[path] = hashlib.sha256(content).hexdigest()
    return result


def record_acceptance(task: dict, run_path: Path, worker: str, reviewer: str,
                      review_commit: str, review_path: str, disposition: str) -> Path:
    require_clean_inputs()
    if not worker or not reviewer or worker == reviewer:
        raise ValueError("distinct worker and independent reviewer identities are required")
    allowed = {"accepted", *({"rejected_experiment"} if task["id"] in coordination.EXPERIMENTS else set())}
    if disposition not in allowed:
        raise ValueError("this task cannot close with that disposition")
    run = verified_run(task, run_path)
    evidence_path(review_path, task["id"])
    git("merge-base", "--is-ancestor", review_commit, "HEAD")
    review = git("show", f"{review_commit}:{review_path}")
    if not review.strip():
        raise ValueError("committed independent review is empty")
    folder = ROOT / "artifacts/tasks" / task["id"]
    pending = json.loads((folder / "receipt.json").read_text())
    criteria = criterion_evidence(task, pending)
    (folder / "review.md").write_bytes(review)
    transcript = "\n\n".join(shlex.join(r["argv"]) + "\n" + r.get("stdout", "") + r.get("stderr", "")
                              + f"\nExit: {r['exit']}" for r in run["records"])
    (folder / "coordinator-commands.log").write_text(transcript.rstrip() + "\n")
    paths = [*task["evidence_artifacts"], review_path, str(run_path.relative_to(ROOT)),
             f"artifacts/tasks/{task['id']}/coordinator-commands.log"]
    paths.extend(path for bound in criteria.values() for path in bound)
    evidence = evidence_digests(paths, task["id"])
    result = dict(schema_version=1, task_id=task["id"], beads_id=coordination.bead_id(task["id"]),
                  disposition=disposition, evaluated_commit=run["evaluated_commit"], evaluated_at=run["evaluated_at"],
                  contract_digest=contract_digest(task), worker=worker,
                  commands=[{k: v for k, v in r.items() if k not in ("stdout", "stderr")} for r in run["records"]],
                  evidence=evidence, criteria=criteria,
                  review=dict(disposition="approved", reviewers=[reviewer], path=f"artifacts/tasks/{task['id']}/review.md"))
    target = folder / "acceptance.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    return target


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify-run", "record", "verify"))
    parser.add_argument("task")
    parser.add_argument("--run", type=Path)
    parser.add_argument("--worker")
    parser.add_argument("--reviewer")
    parser.add_argument("--review-commit")
    parser.add_argument("--review-path")
    parser.add_argument("--commit")
    parser.add_argument("--disposition", default="accepted")
    args = parser.parse_args()
    tasks, overrides = coordination.load_contracts()
    task = coordination.effective_task(tasks[args.task], overrides)
    path = args.run or ROOT / "artifacts/tasks" / args.task / "run.json"
    path = path if path.is_absolute() else ROOT / path
    if args.command == "verify-run":
        print(json.dumps({"verified": args.task, "tests": verified_run(task, path)["tests"]}))
    elif args.command == "record":
        print(record_acceptance(task, path, args.worker, args.reviewer,
                                args.review_commit, args.review_path, args.disposition))
    else:
        commit = args.commit or git("rev-parse", "HEAD").decode().strip()
        receipt = f"artifacts/tasks/{args.task}/acceptance.json"
        data = json.loads(git("show", f"{commit}:{receipt}"))
        issue = {"status": "closed", "metadata": {"disposition": data["disposition"],
                 "accepted_commit": commit, "accepted_receipt": receipt}}
        print(json.dumps(validate(args.task, issue)))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(f"Acceptance evidence incomplete: {error}")
