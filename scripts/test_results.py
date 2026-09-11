"""Execute checks and collect required-test outcomes from structured reports.

Unittest uses its result object; pytest, Node and Playwright use JUnit XML.
Custom test runners can write the same count object to INKFLIP_TEST_REPORT_FILE.
Exit status alone is never evidence that required tests ran.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

COUNT_KEYS = ("collected", "passed", "failed", "skipped")
REPORT_ENV = "INKFLIP_TEST_REPORT_FILE"


def requires_tests(argv: list[str], registry: dict) -> bool:
    if argv[:2] == ["bun", "run"] and len(argv) > 2:
        commands = registry["commands"]
        entry = commands.get(argv[2], {})
        kinds = [entry.get("kind"), *(commands.get(m, {}).get("kind") for m in entry.get("members", []))]
        return "test" in kinds
    return any(a in ("unittest", "pytest", "playwright", "--test", "scripts/gate.py")
               or Path(a).name.startswith("test_") or a.startswith("tests/") for a in argv)


def validate_counts(counts: dict) -> None:
    if not isinstance(counts, dict):
        raise ValueError("test counts must be an object")
    if any(type(counts.get(k)) is not int or counts[k] < 0 for k in COUNT_KEYS):
        raise ValueError("test counts must contain nonnegative integers")
    if counts["collected"] == 0:
        raise ValueError("zero tests collected — empty required suites fail")
    if counts["failed"] or counts["skipped"]:
        raise ValueError(f"required tests failed={counts['failed']} skipped={counts['skipped']}")
    if counts["passed"] != counts["collected"]:
        raise ValueError("not every collected test passed")


def total_counts(records: list[dict]) -> dict:
    return {key: sum(r.get("tests", {}).get(key, 0) for r in records) for key in COUNT_KEYS}


def junit_counts(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    skipped = sum(case.find("skipped") is not None for case in cases)
    failed = sum(any(case.find(tag) is not None for tag in ("failure", "error")) for case in cases)
    # Some runners report setup errors at suite level without any test case.
    suite_errors = sum(int(suite.get("errors", "0")) for suite in root.iter("testsuite"))
    failed = max(failed, suite_errors)
    return dict(collected=len(cases), passed=max(0, len(cases) - skipped - failed),
                failed=failed, skipped=skipped)


def runner_command(argv: list[str], report: Path, cwd: Path) -> tuple[list[str], str]:
    if "unittest" in argv and "-m" in argv:
        index = argv.index("-m")
        return [*argv[:index], str(Path(__file__).resolve()), "--unittest", *argv[index + 2:]], "json"
    if "pytest" in argv:
        return [*argv, f"--junitxml={report}"], "xml"
    if "playwright" in argv and "test" in argv:
        return [*argv, "--reporter=junit"], "xml"
    if Path(argv[0]).name == "node" and "--test" in argv:
        expanded = [match for arg in argv[1:] for match in
                    (sorted(glob.glob(arg, root_dir=cwd)) or [arg] if glob.has_magic(arg) else [arg])]
        return [argv[0], "--test-reporter=junit", f"--test-reporter-destination={report}", *expanded], "xml"
    return argv, "optional"


def execute(argv: list[str], cwd: Path, *, require_tests: bool = False) -> dict:
    with tempfile.TemporaryDirectory(prefix="inkflip-tests-") as folder:
        report = Path(folder) / "results"
        actual, report_type = runner_command(argv, report, cwd)
        env = {**os.environ, REPORT_ENV: str(report), "PLAYWRIGHT_JUNIT_OUTPUT_FILE": str(report)}
        result = subprocess.run(actual, cwd=cwd, env=env, text=True, capture_output=True, check=False)
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        record = {"argv": argv, "executed_argv": actual, "cwd": str(cwd), "exit": result.returncode,
                  "stdout": result.stdout, "stderr": result.stderr}
        try:
            if report_type == "xml":
                record["tests"] = junit_counts(report)
            elif report.is_file():
                record["tests"] = json.loads(report.read_text())
            if report_type != "optional" or require_tests or "tests" in record:
                validate_counts(record.get("tests", {}))
        except (ValueError, OSError, ET.ParseError) as error:
            record.update(exit=1, error=f"test evidence invalid: {error}")
            print(record["error"], file=sys.stderr)
        return record


def export_counts(counts: dict) -> None:
    """Propagate nested harness/gate results to their calling task runner."""
    destination = os.environ.get(REPORT_ENV)
    if destination:
        Path(destination).write_text(json.dumps(counts) + "\n")


def run_unittest() -> int:
    program = unittest.main(module=None, argv=["unittest", *sys.argv[2:]], exit=False)
    result = program.result
    failed = len(result.errors) + len(result.failures) + len(result.unexpectedSuccesses)
    skipped = len(result.skipped) + len(result.expectedFailures)
    counts = dict(collected=program.test.countTestCases(),
                  passed=max(0, result.testsRun - failed - skipped), failed=failed, skipped=skipped)
    export_counts(counts)
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    if sys.argv[1:2] != ["--unittest"]:
        raise SystemExit("internal unittest adapter: expected --unittest")
    raise SystemExit(run_unittest())
