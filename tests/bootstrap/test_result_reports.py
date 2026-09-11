"""Structured outcomes reject skipped, missing and unsuccessful required cases."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import test_results
import gate
import coordination


class ResultReportTests(unittest.TestCase):
    def test_junit_counts_cases_instead_of_trusting_the_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            path.write_text('<testsuites tests="999"><testsuite><testcase name="pass"/>'
                            '<testcase name="skip"><skipped/></testcase>'
                            '<testcase name="fail"><failure/></testcase></testsuite></testsuites>')
            counts = test_results.junit_counts(path)
            self.assertEqual(counts, dict(collected=3, passed=1, failed=1, skipped=1))
            with self.assertRaises(ValueError):
                test_results.validate_counts(counts)

    def test_custom_runner_must_supply_real_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = test_results.execute([sys.executable, "-c", "print('success')"],
                                              Path(folder), require_tests=True)
            self.assertNotEqual(result["exit"], 0)
            script = "import os,json; open(os.environ['INKFLIP_TEST_REPORT_FILE'],'w').write(json.dumps(dict(collected=1,passed=1,failed=0,skipped=0)))"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = test_results.execute([sys.executable, "-c", script], Path(folder), require_tests=True)
            self.assertEqual(result["exit"], 0)

    def test_expected_failure_is_not_required_test_success(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test_expected.py"
            path.write_text("import unittest\nclass T(unittest.TestCase):\n"
                            " @unittest.expectedFailure\n def test_it(self): self.fail('known failure')\n")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = test_results.execute([sys.executable, "-m", "unittest", "discover", "-s", folder],
                                              Path(folder), require_tests=True)
            self.assertNotEqual(result["exit"], 0)
            self.assertEqual(result["tests"]["skipped"], 1)

    def test_empty_gate_scenarios_fail(self):
        _, overrides = coordination.load_contracts()
        records, errors = gate.run_scenarios({"scenario_commands": []}, overrides, {})
        self.assertEqual(records, [])
        self.assertTrue(errors)

    def test_pre_release_checks_accepted_prior_gate_owners(self):
        gates = gate.load_gates()
        pre = gates["pre-release"]
        self.assertEqual(pre["task"], "T55")
        for name in ("G1", "G2", "G3", "G4"):
            self.assertIn(gates[name]["task"], pre["required_task_ids"])

    def test_node_unmatched_pattern_cannot_fall_back_to_all_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            argv, kind = test_results.runner_command(["node", "--test", "missing/*.test.mjs"],
                                                     Path(folder) / "results", Path(folder))
            self.assertEqual(kind, "xml")
            self.assertIn("missing/*.test.mjs", argv)


if __name__ == "__main__":
    unittest.main()
