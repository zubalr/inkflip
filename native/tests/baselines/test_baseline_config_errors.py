"""Baseline configuration faults must be argument errors, never internal ones.

Regression for the reported defect where `inkflip baseline create` with a
config-invalid `--rules` file exited 4 and printed
`Unexpected error: SCHEMA: ...` instead of the documented exit 2 (invalid
arguments, configuration, or imported contract; docs/CLI.md).

The fix is the narrow translation in `inkflip.baselines.engine`: a missing,
unreadable or malformed configuration file (rules, run index, run identity) is
an operator input fault. Genuine runtime/read failures must still be 4 and a
valid creation must still succeed with no partial artifacts on refusal.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
AMOUNT = FIXTURES / "public" / "mapping-amount.pdf"
AMOUNT_SHA = "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80"

if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.baselines.engine import create_baseline  # noqa: E402
from inkflip.baselines.models import BaselineError  # noqa: E402
from inkflip.contracts import core  # noqa: E402

EXIT_OK = 0
EXIT_INVALID_ARGS = 2
EXIT_READ_FAILURE = 4


def _env() -> dict[str, str]:
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(NATIVE) + (os.pathsep + prior if prior else "")
    return env


def _cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "inkflip.cli", *argv],
        cwd=str(ROOT), capture_output=True, text=True, env=_env(), timeout=180,
    )


VALID_RULES = {
    "kind": "acceptance_rules",
    "schema_version": "1.0.0",
    "policy": {"fail_on_coverage_loss": True, "fail_on_error": True, "unruled_change": "changed"},
    "rules": [
        {
            "id": "amount-text",
            "type": "expected_text",
            "document_sha256": AMOUNT_SHA,
            "page_index": 0,
            "reader_id": None,
            "region_id": None,
            "expected_text": "$1,000",
            "expected_count": None,
            "max_delta_pt": None,
            "capability": None,
            "explanation": "The native reader reports the mapped amount.",
        }
    ],
}


class BaselineConfigErrorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.run = self._make_run(self.td / "run")

    def tearDown(self):
        self.tmp.cleanup()

    def _make_run(self, directory: Path) -> Path:
        reports = directory / "reports"
        reports.mkdir(parents=True)
        report = reports / "amount.json"
        made = _cli("inspect", str(AMOUNT), "--out", str(report))
        self.assertEqual(made.returncode, EXIT_OK, made.stderr)
        payload = json.loads(report.read_text())
        core.validate(payload)
        (directory / "index.json").write_text(
            json.dumps(
                {
                    "kind": "inkflip-run-index",
                    "schema_version": "1.0.0",
                    "status": "complete",
                    "jobs": {
                        "amount": {
                            "key": "amount",
                            "status": "completed",
                            "report_path": "reports/amount.json",
                            "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                            "report_bytes": report.stat().st_size,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (directory / "identity.json").write_text(
            json.dumps(
                {
                    "kind": "inkflip-corpus-identity",
                    "corpus_manifest_sha256": "a" * 64,
                    "profile_sha256": "b" * 64,
                    "profile_name": "native-default",
                    "algorithm_id": "inkflip-inspect-v1",
                    "intended_keys": ["amount"],
                }
            ),
            encoding="utf-8",
        )
        return directory

    def _out(self, name: str = "base.json") -> Path:
        return self.td / name

    def assert_baseline_refused(self, rules: Path | None, out: Path, *, phrase: str | None = None):
        argv = [
            "baseline", "create", "--run", str(self.run),
            "--out", str(out), "--approved-by", "reviewer", "--rationale", "why",
        ]
        if rules is not None:
            insert_at = argv.index("--out")
            argv[insert_at:insert_at] = ["--rules", str(rules)]
        result = _cli(*argv)
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertNotIn("Unexpected error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(result.stderr.startswith("Error: "), result.stderr)
        if phrase:
            self.assertIn(phrase, result.stderr)
        # A refusal must never leave a success-looking baseline or a sidecar.
        self.assertFalse(out.exists(), "no baseline file may be created on refusal")
        self.assertFalse(
            out.with_suffix(out.suffix + ".reports").exists(),
            "no baseline sidecar may be created on refusal",
        )
        return result

    def write(self, name: str, text: str) -> Path:
        path = self.td / name
        path.write_text(text, encoding="utf-8")
        return path


class TestBaselineRulesConfigErrors(BaselineConfigErrorCase):
    def test_missing_rules_file_is_exit_2(self):
        self.assert_baseline_refused(self.td / "absent.json", self._out(), phrase="Cannot read rules file")

    def test_malformed_rules_json_is_exit_2(self):
        bad = self.write("bad.json", '{"kind":"acceptance_rules",,')
        self.assert_baseline_refused(bad, self._out(), phrase="Invalid rules file")

    def test_schema_invalid_rules_is_exit_2(self):
        # The exact reported case: valid JSON, invalid schema/enum.
        bad = self.write(
            "schema.json",
            json.dumps(
                {
                    "kind": "acceptance_rules",
                    "schema_version": "1.0.0",
                    "rules": [
                        {
                            "id": "r1",
                            "type": "not_a_real_type",
                            "document_sha256": AMOUNT_SHA,
                            "page_index": 0,
                            "reader_id": None,
                            "region_id": None,
                        }
                    ],
                }
            ),
        )
        self.assert_baseline_refused(bad, self._out(), phrase="Invalid rules file")

    def test_wrong_kind_rules_is_exit_2(self):
        bad = self.write("kind.json", json.dumps({"kind": "report", "schema_version": "1.0.0"}))
        self.assert_baseline_refused(bad, self._out(), phrase="Invalid rules file")

    def test_rules_with_unknown_member_is_exit_2(self):
        payload = json.loads(json.dumps(VALID_RULES))
        payload["unexpected_member"] = True
        bad = self.write("extra.json", json.dumps(payload))
        self.assert_baseline_refused(bad, self._out(), phrase="Invalid rules file")

    def test_rules_with_invalid_type_is_exit_2(self):
        payload = json.loads(json.dumps(VALID_RULES))
        payload["rules"][0]["page_index"] = "zero"
        bad = self.write("type.json", json.dumps(payload))
        self.assert_baseline_refused(bad, self._out(), phrase="Invalid rules file")


class TestBaselineRunConfigErrors(BaselineConfigErrorCase):
    def test_missing_run_directory_is_exit_2(self):
        result = _cli(
            "baseline", "create", "--run", str(self.td / "absent"),
            "--out", str(self._out()), "--approved-by", "r", "--rationale", "w",
        )
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertFalse(self._out().exists())

    def test_malformed_run_index_is_exit_2_not_4(self):
        (self.run / "index.json").write_text("{broken", encoding="utf-8")
        rules = self.write("rules.json", json.dumps(VALID_RULES))
        self.assert_baseline_refused(rules, self._out(), phrase="Invalid run index")

    def test_malformed_run_identity_is_exit_2_not_4(self):
        (self.run / "identity.json").write_text("not json at all", encoding="utf-8")
        rules = self.write("rules.json", json.dumps(VALID_RULES))
        self.assert_baseline_refused(rules, self._out(), phrase="Invalid run identity")

    def test_incomplete_run_is_exit_2(self):
        index = json.loads((self.run / "index.json").read_text())
        index["status"] = "partial"
        (self.run / "index.json").write_text(json.dumps(index), encoding="utf-8")
        rules = self.write("rules.json", json.dumps(VALID_RULES))
        self.assert_baseline_refused(rules, self._out())


class TestBaselineCreationControl(BaselineConfigErrorCase):
    def test_valid_rules_create_a_verified_baseline(self):
        rules = self.write("rules.json", json.dumps(VALID_RULES))
        out = self._out("ok.json")
        result = _cli(
            "baseline", "create", "--run", str(self.run), "--rules", str(rules),
            "--out", str(out), "--approved-by", "reviewer", "--rationale", "approved",
        )
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertTrue(out.is_file())
        record = json.loads(out.read_text())
        core.validate(record)
        self.assertEqual(record["kind"], "baseline")
        self.assertEqual(record["approved_by"], "reviewer")
        sidecar = out.with_suffix(out.suffix + ".reports")
        self.assertTrue(sidecar.is_dir())
        self.assertTrue(sorted(sidecar.glob("*.json")))

    def test_valid_creation_without_rules_still_succeeds(self):
        out = self._out("no-rules.json")
        result = _cli(
            "baseline", "create", "--run", str(self.run), "--out", str(out),
            "--approved-by", "reviewer", "--rationale", "no rules declared",
        )
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        core.validate(json.loads(out.read_text()))

    def test_existing_baseline_is_not_overwritten(self):
        rules = self.write("rules.json", json.dumps(VALID_RULES))
        out = self._out("keep.json")
        first = _cli(
            "baseline", "create", "--run", str(self.run), "--rules", str(rules),
            "--out", str(out), "--approved-by", "reviewer", "--rationale", "first",
        )
        self.assertEqual(first.returncode, EXIT_OK, first.stderr)
        before = out.read_bytes()
        second = _cli(
            "baseline", "create", "--run", str(self.run), "--rules", str(rules),
            "--out", str(out), "--approved-by", "reviewer", "--rationale", "second",
        )
        self.assertEqual(second.returncode, EXIT_INVALID_ARGS)
        self.assertEqual(out.read_bytes(), before, "an existing baseline must stay byte-identical")


class TestBaselineEngineErrorType(BaselineConfigErrorCase):
    """The library surface must raise BaselineError, not an untranslated ContractError."""

    def test_missing_rules_raises_baseline_error(self):
        with self.assertRaises(BaselineError):
            create_baseline(self.run, self.td / "absent.json", self._out(), "r", "w")

    def test_schema_invalid_rules_raise_baseline_error(self):
        bad = self.write("schema.json", json.dumps({"kind": "acceptance_rules", "schema_version": "1.0.0", "rules": []}))
        with self.assertRaises(BaselineError) as ctx:
            create_baseline(self.run, bad, self._out(), "r", "w")
        self.assertNotIsInstance(ctx.exception, core.ContractError)

    def test_valid_rules_do_not_raise(self):
        rules = self.write("rules.json", json.dumps(VALID_RULES))
        record = create_baseline(self.run, rules, self._out(), "r", "w")
        core.validate(record)


if __name__ == "__main__":
    unittest.main()
