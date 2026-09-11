#!/usr/bin/env python3
"""Honest command harness for the Inkflip workspace.

Reads config/acceptance-commands.json: `active` commands run now; `declared`
commands fail explicitly until their `requires` prerequisites materialize.
Test commands must collect at least one test — an empty suite is a failure,
never a pass. `task <Txx>` executes the effective task commands from
planning/execution/tasks.json adapted through execution/overrides.json. This
script never writes task state; Beads (via scripts/coordination.py) is the
only task-state authority.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "config/acceptance-commands.json"
KINDS = {"group", "test", "check", "build"}
STATUSES = {"active", "declared"}
COLLECTION_MODES = {"harness-unittest", "runner-exit"}


class CommandError(Exception):
    """A command is unregistered, unavailable, or failed its contract."""


def load_coordination():
    spec = importlib.util.spec_from_file_location(
        "coordination", ROOT / "scripts/coordination.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_registry(path: Path) -> dict:
    if not path.is_file():
        raise CommandError(f"command registry missing: {path.relative_to(ROOT)}")
    try:
        registry = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise CommandError(f"command registry is not valid JSON: {error}") from error
    commands = registry.get("commands")
    if not isinstance(commands, dict) or not commands:
        raise CommandError("command registry contains no commands")
    return registry


def registry_path(args_registry: str | None) -> Path:
    if args_registry is None:
        return DEFAULT_REGISTRY
    path = Path(args_registry)
    return path if path.is_absolute() else (ROOT / path)


def resolve_interpreter(argv: list[str], registry: dict) -> list[str]:
    """Map argv[0] through registry interpreters when the literal is absent."""
    if not argv:
        raise CommandError("empty argv")
    mapped = registry.get("interpreters", {}).get(argv[0])
    if mapped and shutil.which(argv[0]) is None:
        if shutil.which(mapped) is None:
            raise CommandError(f"interpreter unavailable: neither {argv[0]} nor {mapped} on PATH")
        return [mapped, *argv[1:]]
    if shutil.which(argv[0]) is None:
        raise CommandError(f"executable not found on PATH: {argv[0]}")
    return argv


def missing_requires(entry: dict) -> list[str]:
    return [p for p in entry.get("requires", []) if not (ROOT / p).exists()]


def unittest_suite_dir(argv: list[str]) -> Path | None:
    """Locate the `-s <dir>` discovery target of a unittest command."""
    if "-m" in argv and "unittest" in argv and "discover" in argv:
        for index, token in enumerate(argv):
            if token == "-s" and index + 1 < len(argv):
                return ROOT / argv[index + 1]
        return ROOT
    return None


def unittest_collect_count(suite_dir: Path) -> int:
    if not suite_dir.is_dir():
        raise CommandError(f"unittest suite directory missing: {suite_dir.relative_to(ROOT)}")
    return unittest.defaultTestLoader.discover(str(suite_dir)).countTestCases()


def unittest_ran_count(output: str) -> int | None:
    match = re.search(r"Ran (\d+) tests?", output)
    return int(match.group(1)) if match else None


def execute(argv: list[str], cwd: Path) -> dict:
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return {
        "argv": argv,
        "cwd": str(cwd),
        "exit": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def run_leaf(name: str, entry: dict, registry: dict, tail: list[str]) -> dict:
    if entry.get("status") not in STATUSES:
        raise CommandError(f"{name}: unknown status {entry.get('status')!r}")
    argv = entry.get("argv")
    if not argv:
        raise CommandError(
            f"{name}: no implementation registered (owner {entry.get('owner_task', 'unknown')}); "
            "declared commands fail until their suite lands"
        )
    missing = missing_requires(entry)
    if missing:
        raise CommandError(
            f"{name}: prerequisites missing: {', '.join(missing)} "
            f"(owner {entry.get('owner_task', 'unknown')})"
        )
    cwd = ROOT / entry.get("cwd", ".")
    full_argv = resolve_interpreter([*argv, *tail], registry)

    collected = None
    if entry.get("kind") == "test":
        mode = entry.get("collection")
        if mode == "harness-unittest":
            suite_dir = unittest_suite_dir(full_argv)
            if suite_dir is None:
                raise CommandError(f"{name}: harness-unittest collection needs `-m unittest discover -s <dir>`")
            collected = unittest_collect_count(suite_dir)
            if collected == 0:
                raise CommandError(f"{name}: zero tests collected in {suite_dir.relative_to(ROOT)} — empty suites fail")
        elif mode != "runner-exit":
            raise CommandError(f"{name}: unknown collection mode {mode!r}; cannot prove nonzero tests")

    record = execute(full_argv, cwd)
    record["command"] = name
    record["collected"] = collected

    if entry.get("kind") == "test" and entry.get("collection") == "harness-unittest":
        ran = unittest_ran_count(record["stderr"])
        record["ran"] = ran
        if record["exit"] == 0 and not ran:
            record["exit"] = 1
            record["harness_override"] = "runner exited 0 but reported zero tests — treated as failure"
    return record


def run_command(name: str, registry: dict, tail: list[str]) -> dict:
    commands = registry["commands"]
    entry = commands.get(name)
    if entry is None:
        known = ", ".join(sorted(commands))
        raise CommandError(f"{name}: not a documented command (registered names: {known})")
    kind = entry.get("kind")
    if kind == "group":
        members = entry.get("members", [])
        if not members:
            raise CommandError(f"{name}: group has no members")
        records = []
        for member in members:
            record = run_command(member, registry, [])
            records.append(record)
            if record["exit"] != 0:
                break
        return {
            "command": name,
            "argv": [f"group:{m}" for m in members],
            "cwd": str(ROOT),
            "exit": records[-1]["exit"],
            "stdout": "",
            "stderr": "",
            "collected": sum(r.get("collected") or 0 for r in records),
            "members": records,
        }
    if kind not in KINDS:
        raise CommandError(f"{name}: unknown kind {kind!r}")
    return run_leaf(name, entry, registry, tail)


def run_task(task_id: str, registry: dict, require_evidence: bool, report: Path | None) -> int:
    coordination = load_coordination()
    tasks, overrides = coordination.load_contracts()
    if task_id not in tasks:
        raise CommandError(f"unknown task {task_id}; use T01 through T55")
    task = coordination.effective_task(tasks[task_id], overrides)
    records = []
    failures = []
    for command in task["commands"]:
        for segment in [s.strip() for s in command.split("&&") if s.strip()]:
            argv = shlex.split(segment)
            record = {"segment": segment}
            try:
                argv = resolve_interpreter(argv, registry)
                collected = None
                suite_dir = unittest_suite_dir(argv)
                if suite_dir is not None:
                    collected = unittest_collect_count(suite_dir)
                    if collected == 0:
                        raise CommandError(f"zero tests collected in {suite_dir.relative_to(ROOT)}")
                record.update(execute(argv, ROOT))
                record["collected"] = collected
                if suite_dir is not None:
                    ran = unittest_ran_count(record["stderr"])
                    record["ran"] = ran
                    if record["exit"] == 0 and not ran:
                        record["exit"] = 1
                        record["harness_override"] = "zero tests ran — treated as failure"
            except (CommandError, OSError) as error:
                record.update({"argv": argv, "exit": 1, "error": str(error)})
            records.append(record)
            if record["exit"] != 0:
                failures.append(segment)
                break
    evidence_missing = []
    if require_evidence:
        for artifact in task.get("evidence_artifacts", []):
            path = ROOT / artifact
            if not path.is_file():
                evidence_missing.append(artifact)
            elif path.suffix == ".json":
                try:
                    json.loads(path.read_text())
                except json.JSONDecodeError:
                    evidence_missing.append(f"{artifact} (invalid JSON)")
    result = {
        "task": task_id,
        "beads_id": task.get("beads_id"),
        "commands_run": len(records),
        "failures": failures,
        "evidence_missing": evidence_missing,
        "records": [
            {k: v for k, v in r.items() if k not in ("stdout", "stderr")} for r in records
        ],
    }
    print(json.dumps(result, indent=2))
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({**result, "records": records}, indent=2) + "\n")
    if failures or evidence_missing:
        return 1
    return 0


def self_check(registry: dict, registry_file: Path) -> list[str]:
    errors = []
    commands = registry["commands"]
    for name, entry in commands.items():
        kind, status = entry.get("kind"), entry.get("status")
        if kind not in KINDS:
            errors.append(f"{name}: kind {kind!r} not in {sorted(KINDS)}")
        if status not in STATUSES:
            errors.append(f"{name}: status {status!r} not in {sorted(STATUSES)}")
        if kind == "group":
            for member in entry.get("members", []):
                target = commands.get(member)
                if target is None:
                    errors.append(f"{name}: member {member} not registered")
                elif target.get("kind") == "group":
                    errors.append(f"{name}: nested group member {member} not allowed")
            continue
        if entry.get("argv") is None:
            if status == "active":
                errors.append(f"{name}: active command has no argv")
            continue
        if kind == "test" and entry.get("collection") not in COLLECTION_MODES:
            errors.append(f"{name}: test command needs a known collection mode")
        missing = missing_requires(entry)
        if status == "active" and missing:
            errors.append(f"{name}: active but requires missing: {', '.join(missing)}")
        try:
            resolve_interpreter(entry["argv"], registry)
        except CommandError as error:
            if status == "active":
                errors.append(f"{name}: {error}")
    package = json.loads((ROOT / "package.json").read_text())
    scripts = package.get("scripts", {})
    for name in commands:
        script = scripts.get(name)
        if script is None:
            errors.append(f"package.json has no script for documented command {name}")
        elif "task_acceptance.py" not in script:
            errors.append(f"package.json script {name} does not route through task_acceptance.py")
    registry_file_label = registry_file.relative_to(ROOT) if registry_file.is_relative_to(ROOT) else registry_file
    if registry_file == DEFAULT_REGISTRY:
        print(f"self-check: {len(commands)} commands in {registry_file_label}")
    return errors


def list_commands(registry: dict) -> None:
    for name, entry in registry["commands"].items():
        if entry.get("kind") == "group":
            members = ", ".join(entry.get("members", []))
            print(f"{name:<24} {entry.get('status'):<9} group [{members}]")
            continue
        argv = entry.get("argv")
        missing = missing_requires(entry) if argv else ["(no implementation)"]
        state = "runnable" if argv and not missing else "unavailable"
        owner = entry.get("owner_task", "-")
        print(f"{name:<24} {entry.get('status'):<9} {state:<11} owner:{owner}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", help="registry path (default: config/acceptance-commands.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="run a registered command")
    run_p.add_argument("name")
    run_p.add_argument("tail", nargs=argparse.REMAINDER, help="arguments after -- append to the command")
    task_p = sub.add_parser("task", help="run a task's effective acceptance commands")
    task_p.add_argument("task_id")
    task_p.add_argument("--require-evidence", action="store_true",
                        help="also verify the task's evidence_artifacts exist and parse")
    task_p.add_argument("--report", type=Path, help="write a JSON run record")
    sub.add_parser("list", help="list the documented command surface")
    sub.add_parser("self-check", help="validate the registry and script wiring")
    args = parser.parse_args()

    try:
        reg_file = registry_path(args.registry)
        registry = load_registry(reg_file)
        if args.command == "list":
            list_commands(registry)
            return 0
        if args.command == "self-check":
            errors = self_check(registry, reg_file)
            for error in errors:
                print(f"self-check failed: {error}", file=sys.stderr)
            return 1 if errors else 0
        if args.command == "task":
            return run_task(args.task_id, registry, args.require_evidence, args.report)
        tail = args.tail[1:] if args.tail[:1] == ["--"] else args.tail
        record = run_command(args.name, registry, tail)
        return 0 if record["exit"] == 0 else 1
    except CommandError as error:
        print(f"blocked: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
