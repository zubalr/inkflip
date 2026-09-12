"""Run the installed pinned constructor's lifecycle regressions in TEST-02."""
from pathlib import Path
import os
import subprocess
import re
import unittest
from unittest import mock


class TesseractWorkerTests(unittest.TestCase):
    def test_installed_constructor_lifecycle(self):
        self.run_node("tests/build/tesseract-worker.test.mjs")

    def test_real_browser_worker_lifecycle(self):
        self.run_node("tests/build/tesseract-browser.test.mjs")

    def test_registered_cases_ignore_negative_control_override(self):
        with mock.patch.dict(os.environ, {"INKFLIP_TEST_TESSERACT_PACKAGE": "/nonexistent/inkflip-control-package"}):
            self.test_installed_constructor_lifecycle()
            self.test_real_browser_worker_lifecycle()

    def run_node(self, path):
        root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        env.pop("INKFLIP_TEST_TESSERACT_PACKAGE", None)
        result = subprocess.run(
            ["node", "--test", "--test-reporter=tap", path],
            cwd=root, env=env, text=True, capture_output=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        counts = dict(re.findall(r"^# (tests|pass|fail|cancelled|skipped) (\d+)$", result.stdout, re.M))
        self.assertGreater(int(counts["tests"]), 0)
        self.assertEqual(counts["tests"], counts["pass"])
        self.assertEqual([counts[key] for key in ("fail", "cancelled", "skipped")], ["0"] * 3)
