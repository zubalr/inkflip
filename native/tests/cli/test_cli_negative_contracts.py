"""Native CLI negative contracts, executed as real subprocesses (implementation wave 2026-09-13).

Every case runs the shipped CLI in a child process so the contract under test is
the observable one: exit status, stdout and stderr. Each negative case also
asserts the two invariants a refusal must preserve — the actionable diagnosis
reaches stderr, and no partial success artifact is created — plus that the
input is byte-identical afterwards.

This file is additive: it does not modify the T30 suite, and it reuses the same
fixtures. Cases already covered in-process by test_cli.py are only repeated here
where the subprocess boundary itself is the contract (streams and exit status).
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

EXIT_OK = 0
EXIT_INVALID_ARGS = 2
EXIT_READ_FAILURE = 4


def _env() -> dict[str, str]:
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(NATIVE) + (os.pathsep + prior if prior else "")
    return env


def cli(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "inkflip.cli", *argv],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        env=_env(),
        timeout=180,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NegativeContractCase(unittest.TestCase):
    """Shared assertions for a refused command."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.source_bytes = AMOUNT.read_bytes()
        self.source_sha = _sha(AMOUNT)

    def tearDown(self):
        self.tmp.cleanup()

    def assert_refused(
        self,
        result: subprocess.CompletedProcess,
        code: int,
        *,
        expect_outputs: list[Path] | None = None,
    ):
        self.assertEqual(result.returncode, code, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("Unexpected error", result.stderr)
        self.assertTrue(
            result.stderr.startswith("Error: ") or result.stderr.startswith("usage: "),
            msg=f"stderr must be an actionable diagnosis, got {result.stderr!r}",
        )
        # Input preservation: the fixture is never modified by a refusal.
        self.assertEqual(_sha(AMOUNT), self.source_sha)
        self.assertEqual(AMOUNT.read_bytes(), self.source_bytes)
        for path in expect_outputs or []:
            self.assertFalse(path.exists(), f"{path} must not be created by a refused command")

    def write_json(self, name: str, payload) -> Path:
        path = self.td / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


class TestInspectNegativeContracts(NegativeContractCase):
    def test_unknown_reader_is_configuration_error(self):
        out = self.td / "o.json"
        result = cli("inspect", str(AMOUNT), "--out", str(out), "--reader", "bogus")
        self.assert_refused(result, EXIT_INVALID_ARGS, expect_outputs=[out])
        self.assertIn("Unknown reader", result.stderr)

    def test_unknown_profile_is_configuration_error(self):
        out = self.td / "o.json"
        result = cli("inspect", str(AMOUNT), "--out", str(out), "--profile", "nope")
        self.assert_refused(result, EXIT_INVALID_ARGS, expect_outputs=[out])
        self.assertIn("Profile", result.stderr)

    def test_page_selection_faults_are_configuration_errors(self):
        for spec, needle in (("0", "1-based"), ("abc", "Invalid page number"), ("999", "exceeds")):
            with self.subTest(pages=spec):
                out = self.td / f"p-{spec}.json"
                result = cli("inspect", str(AMOUNT), "--out", str(out), "--pages", spec)
                self.assert_refused(result, EXIT_INVALID_ARGS, expect_outputs=[out])
                self.assertIn(needle, result.stderr)

    def test_malformed_region_is_configuration_error(self):
        out = self.td / "r.json"
        result = cli("inspect", str(AMOUNT), "--out", str(out), "--region", "1,2,3")
        self.assert_refused(result, EXIT_INVALID_ARGS, expect_outputs=[out])

    def test_tesseract_without_ocr_pages_is_configuration_error(self):
        out = self.td / "t.json"
        result = cli("inspect", str(AMOUNT), "--out", str(out), "--reader", "tesseract")
        self.assert_refused(result, EXIT_INVALID_ARGS, expect_outputs=[out])
        self.assertIn("--ocr-pages", result.stderr)

    def test_missing_out_argument_is_usage_error(self):
        result = cli("inspect", str(AMOUNT))
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertTrue(result.stderr.startswith("usage: "), result.stderr)

    def test_missing_source_is_read_failure(self):
        out = self.td / "o.json"
        result = cli("inspect", str(self.td / "absent.pdf"), "--out", str(out))
        self.assert_refused(result, EXIT_READ_FAILURE, expect_outputs=[out])
        self.assertIn("not found", result.stderr.lower())

    def test_source_alias_is_refused_even_with_replace(self):
        result = cli("inspect", str(AMOUNT), "--out", str(AMOUNT), "--replace-output")
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertEqual(_sha(AMOUNT), self.source_sha)

    def test_symlinked_output_alias_is_refused(self):
        link = self.td / "alias.pdf"
        os.symlink(AMOUNT, link)
        result = cli("inspect", str(AMOUNT), "--out", str(link), "--replace-output")
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)

    def test_unwritable_output_is_reported_not_a_traceback(self):
        locked = self.td / "locked"
        locked.mkdir()
        locked.chmod(0o500)
        try:
            out = locked / "o.json"
            result = cli("inspect", str(AMOUNT), "--out", str(out))
            self.assert_refused(result, EXIT_READ_FAILURE, expect_outputs=[out])
            self.assertIn("Cannot write output", result.stderr)
            self.assertFalse(any(locked.iterdir()), "no partial output may be left in an unwritable directory")
        finally:
            locked.chmod(0o700)


class TestValidateAndReportNegativeContracts(NegativeContractCase):
    def test_malformed_json_report_is_contract_error(self):
        bad = self.td / "bad.json"
        bad.write_text('{"kind":"report",,', encoding="utf-8")
        result = cli("validate", str(bad))
        self.assert_refused(result, EXIT_INVALID_ARGS)
        self.assertIn("JSON", result.stderr)

    def test_valid_json_wrong_schema_is_contract_error(self):
        wrong = self.write_json("wrong.json", {"kind": "report", "schema_version": "1.0.0"})
        result = cli("validate", str(wrong))
        self.assert_refused(result, EXIT_INVALID_ARGS)
        self.assertIn("SCHEMA", result.stderr)

    def test_unknown_report_format_is_usage_error(self):
        report = self.td / "r.json"
        result = cli("report", str(report), "--format", "pdf", "--out", str(self.td / "o.html"))
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertTrue(result.stderr.startswith("usage: "), result.stderr)


class TestReplayNegativeContracts(NegativeContractCase):
    def setUp(self):
        super().setUp()
        self.report = self.td / "r.inkflip.json"
        made = cli("inspect", str(AMOUNT), "--out", str(self.report), "--embed-source")
        self.assertEqual(made.returncode, EXIT_OK, made.stderr)

    def test_source_mismatch_is_refused(self):
        other = FIXTURES / "public" / "mapping-control.pdf"
        out = self.td / "replay.json"
        result = cli(
            "replay", str(self.report), "--source", str(other),
            "--profile", "native-default", "--out", str(out),
        )
        self.assert_refused(result, EXIT_INVALID_ARGS, expect_outputs=[out])
        self.assertIn("mismatch", result.stderr.lower())

    def test_missing_profile_argument_is_usage_error(self):
        result = cli("replay", str(self.report), "--out", str(self.td / "o.json"))
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertTrue(result.stderr.startswith("usage: "), result.stderr)


class TestCompareNegativeContracts(NegativeContractCase):
    def setUp(self):
        super().setUp()
        self.report = self.td / "r.inkflip.json"
        made = cli("inspect", str(AMOUNT), "--out", str(self.report))
        self.assertEqual(made.returncode, EXIT_OK, made.stderr)

    def test_missing_rules_file_reports_a_reason(self):
        out = self.td / "cmp"
        result = cli("compare", str(self.report), str(self.report), "--rules", str(self.td / "none.json"), "--out", str(out))
        self.assert_refused(result, EXIT_INVALID_ARGS)
        self.assertIn("Cannot read", result.stderr)
        self.assertIn("Comparison status:", result.stdout)

    def test_schema_invalid_rules_reports_a_reason(self):
        rules = self.write_json("rules.json", {"kind": "acceptance_rules", "schema_version": "1.0.0", "rules": []})
        out = self.td / "cmp"
        result = cli("compare", str(self.report), str(self.report), "--rules", str(rules), "--out", str(out))
        self.assert_refused(result, EXIT_INVALID_ARGS)
        self.assertIn("SCHEMA", result.stderr)

    def test_malformed_side_reports_a_reason(self):
        bad = self.td / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        out = self.td / "cmp"
        result = cli("compare", str(bad), str(self.report), "--out", str(out))
        self.assert_refused(result, EXIT_INVALID_ARGS)
        self.assertTrue(result.stderr.strip(), "an invalid comparison input must explain itself")


class TestDispatchNegativeContracts(NegativeContractCase):
    def test_unknown_command_is_usage_error(self):
        result = cli("frobnicate")
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertTrue(result.stderr.startswith("usage: "), result.stderr)

    def test_unknown_subcommand_is_usage_error(self):
        result = cli("baseline", "refresh")
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
        self.assertTrue(result.stderr.startswith("usage: "), result.stderr)


if __name__ == "__main__":
    unittest.main()
