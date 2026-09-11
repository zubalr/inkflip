"""Regression checks for the acceptance failures found in T01 review."""
import copy
import importlib.util
import io
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import gate
import task_acceptance as harness


class AcceptanceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.registry = harness.load_registry(harness.DEFAULT_REGISTRY)
        self.coordination = harness.load_coordination()
        self.tasks, self.overrides = self.coordination.load_contracts()

    def skipped_suite(self, folder):
        suite = Path(folder) / "suite"
        suite.mkdir()
        (suite / "test_required.py").write_text(
            "import unittest\nclass Required(unittest.TestCase):\n"
            "    @unittest.skip('required device unavailable')\n"
            "    def test_required(self): self.fail('must execute')\n")
        return suite

    def test_all_skipped_registered_tests_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            suite = self.skipped_suite(folder)
            registry = Path(folder) / "registry.json"
            registry.write_text(json.dumps({"commands": {"required": {
                "kind": "test", "status": "active", "collection": "harness-unittest",
                "argv": [sys.executable, "-m", "unittest", "discover", "-s", str(suite)]
            }}}))
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/task_acceptance.py"),
                 "--registry", str(registry), "run", "required"],
                text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertIn("skipped", result.stderr)

    def test_all_skipped_gate_scenarios_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            suite = self.skipped_suite(folder)
            command = shlex.join([sys.executable, "-m", "unittest", "discover", "-s", str(suite)])
            with redirect_stdout(io.StringIO()):
                records, errors = gate.run_scenarios(
                    {"scenario_commands": [command]}, self.overrides, self.registry)
            self.assertTrue(errors, records)

    def test_empty_task_commands_cannot_pass(self):
        task = copy.deepcopy(self.tasks["T01"])
        task["commands"] = []
        task["evidence_artifacts"] = []
        with patch.object(self.coordination, "load_contracts", return_value=({"T01": task}, self.overrides)), \
             patch.object(harness, "load_coordination", return_value=self.coordination), \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(harness.CommandError):
                harness.run_task("T01", self.registry, False, None)

    def test_blob_existence_alone_does_not_accept_a_prerequisite(self):
        issue = {"status": "closed", "metadata": {
            "disposition": "accepted", "accepted_commit": "a" * 40,
            "accepted_receipt": "artifacts/tasks/T01/acceptance.json"
        }}
        def git_result(argv):
            return {"merge-base": "", "cat-file": "blob", "show": "{}"}.get(argv[1], "")
        with patch.object(gate.coordination, "run", side_effect=git_result):
            verified, errors = gate.check_prerequisites(
                {"required_task_ids": ["T01"]}, {"pdf-t01": issue})
        self.assertEqual(verified, [])
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
