#!/usr/bin/env python3
"""Nonrecursive release-gate runner.

`python3 scripts/gate.py G1` verifies that every required task is closed in
Beads with acceptance disposition, an accepted commit that is an ancestor of
HEAD and a committed receipt; then executes the gate's scenario commands
adapted through execution/overrides.json. Scenario commands run directly —
the runner never invokes task acceptance for gate-owner tasks, and a scenario
that collects zero tests fails the gate. On success it writes a fresh receipt
under artifacts/gates/<gate>/receipt.json (override with --receipt).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import coordination  # noqa: E402
import task_acceptance  # noqa: E402
import acceptance_receipts  # noqa: E402
import test_results  # noqa: E402

GATES_FILE = ROOT / "planning/execution/gates.json"
RUNNER_FILE = ROOT / "planning/execution/gate-runner.json"


class GateError(Exception):
    pass


def load_gates() -> dict:
    gates = {g["id"]: g for g in json.loads(GATES_FILE.read_text())}
    if not gates:
        raise GateError("gate manifest is empty")
    pre = json.loads(RUNNER_FILE.read_text())["pre_release"]
    gates["pre-release"] = {
        "id": "pre-release", "title": "Final candidate review", "task": pre["owner_task"],
        "required_task_ids": pre["required_task_ids"] + [gates[g]["task"] for g in pre["required_gate_ids"]],
        "scenario_commands": pre["scenario_commands"],
    }
    return gates


def check_prerequisites(gate: dict, issues: dict, ref: str = "HEAD") -> tuple[list[dict], list[str]]:
    """Validate committed commands, review evidence and candidate freshness."""
    verified, errors = [], []
    for task_id in gate["required_task_ids"]:
        issue = issues.get(coordination.bead_id(task_id), {})
        try:
            verified.append(acceptance_receipts.validate(task_id, issue, ref))
        except ValueError as error:
            errors.append(str(error))
    return verified, errors


def run_scenarios(gate: dict, overrides: dict, registry: dict) -> tuple[list[dict], list[str]]:
    records, errors = [], []
    for command in gate["scenario_commands"]:
        adapted = coordination.adapt_command(command, overrides)
        argv = shlex.split(adapted)
        if any("task_acceptance.py" in a or "gate.py" in a for a in argv):
            errors.append(f"{command}: recursive gate/task dispatch is forbidden")
            continue
        record = {"command": command, "adapted": adapted}
        try:
            argv = task_acceptance.resolve_interpreter(argv, registry)
            record.update(test_results.execute(argv, ROOT, require_tests=test_results.requires_tests(argv, registry)))
        except (task_acceptance.CommandError, GateError, OSError) as error:
            record.update({"exit": 1, "error": str(error)})
        if record["exit"] != 0:
            errors.append(f"{command}: exit {record['exit']}")
        records.append(record)
    try:
        test_results.validate_counts(test_results.total_counts(records))
    except ValueError as error:
        errors.append(str(error))
    return records, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate_id", nargs="?", help="gate id G1..G5 or pre-release")
    parser.add_argument("--target", help="explicit deployed origin for read-only G5 checks")
    parser.add_argument("--check-prereqs", action="store_true",
                        help="verify accepted prerequisites only; do not run scenarios")
    parser.add_argument("--receipt", type=Path,
                        help="receipt output path (default: artifacts/gates/<gate>/receipt.json)")
    parser.add_argument("--list", action="store_true", help="list gates and exit")
    args = parser.parse_args()

    try:
        gates = load_gates()
        if args.list:
            for gate in gates.values():
                print(f"{gate['id']}  {gate['title']}  owner:{gate['task']}  "
                      f"requires:{len(gate['required_task_ids'])} tasks")
            return 0
        if not args.gate_id:
            raise GateError("pass a gate id (G1..G5) or --list")
        gate = gates.get(args.gate_id)
        if gate is None:
            raise GateError(f"unknown gate {args.gate_id}; known: {', '.join(gates)}")
        if gate["id"] == "G5":
            from urllib.parse import urlsplit
            target = urlsplit(args.target or "")
            if target.scheme != "https" or not target.hostname or target.username or target.password:
                raise GateError("G5 requires an explicit HTTPS origin via --target")
            if target.path not in ("", "/") or target.query or target.fragment:
                raise GateError("G5 target must be an origin, without a path, query or fragment")
            os.environ["INKFLIP_PUBLIC_ORIGIN"] = args.target

        issues = coordination.issues_by_id()
        verified, errors = check_prerequisites(gate, issues)
        if errors:
            for error in errors:
                print(f"prerequisite unmet: {error}", file=sys.stderr)
            return 1
        if args.check_prereqs:
            print(f"{gate['id']}: {len(verified)} prerequisites accepted")
            return 0

        head = acceptance_receipts.require_clean_inputs()
        _, overrides = coordination.load_contracts()
        registry = task_acceptance.load_registry(task_acceptance.DEFAULT_REGISTRY)
        records, errors = run_scenarios(gate, overrides, registry)
        if errors:
            for error in errors:
                print(f"scenario failed: {error}", file=sys.stderr)
            return 1
        if acceptance_receipts.require_clean_inputs() != head:
            raise GateError("HEAD changed while gate scenarios ran")

        receipt = args.receipt or ROOT / "artifacts/gates" / gate["id"] / "receipt.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "gate": gate["id"],
            "title": gate["title"],
            "evaluated_commit": head,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "target": args.target,
            "tests": test_results.total_counts(records),
            "prerequisites": verified,
            "scenarios": [
                {k: v for k, v in r.items() if k not in ("stdout", "stderr")} for r in records
            ],
        }, indent=2) + "\n")
        test_results.export_counts(test_results.total_counts(records))
        print(f"{gate['id']} passed; receipt: {receipt.relative_to(ROOT)}")
        return 0
    except (GateError, ValueError, OSError) as error:
        print(f"gate blocked: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
