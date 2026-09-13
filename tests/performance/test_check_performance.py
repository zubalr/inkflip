"""REVIEW.md wrapper defects: --cli is required and labels are not proof."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_performance.py"


def load_checker():
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_performance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCheckPerformanceWrapper(unittest.TestCase):
    def test_missing_cli_fails_without_generating(self) -> None:
        checker = load_checker()
        with mock.patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0)
            code = checker.main(["--mode", "accept", "--profile", "local-mac"])
        self.assertEqual(code, 1)
        run.assert_not_called()

    def test_review_nonexistent_cli_and_label_only_browser_fails(self) -> None:
        checker = load_checker()
        with tempfile.TemporaryDirectory(prefix="inkflip-check-perf-") as raw:
            browser = Path(raw) / "browser.json"
            browser.write_text(
                json.dumps({"stages": {"preview": {"distribution_claim": "n>=30"}}}) + "\n",
                encoding="utf-8",
            )
            missing = Path(raw) / "no-such-cli.json"
            with mock.patch("subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0)
                code = checker.main(
                    [
                        "--mode",
                        "accept",
                        "--profile",
                        "local-mac",
                        "--cli",
                        str(missing),
                        "--browser",
                        str(browser),
                    ]
                )
        self.assertEqual(code, 1)
        run.assert_not_called()

    def test_malformed_cli_is_diagnostic_not_traceback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inkflip-check-bad-") as raw:
            cli = Path(raw) / "bad.json"
            cli.write_text("{not json", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--mode", "accept", "--cli", str(cli)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ACCEPT-FAIL", proc.stderr)
        self.assertNotIn("Traceback (most recent call last)", proc.stderr)

    def test_inventory_lists_incomplete_without_accepting(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inkflip-check-inv-") as raw:
            cli = Path(raw) / "cli.json"
            cli.write_text(
                json.dumps(
                    {
                        "kind": "inkflip-performance",
                        "schema_version": "2.1.0",
                        "host": {"is_specified_reference_desktop": False},
                        "measurement": {"stages": {}},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--mode",
                    "inventory",
                    "--profile",
                    "local-mac",
                    "--cli",
                    str(cli),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("incomplete", proc.stdout.lower())
        self.assertNotIn("performance accept: ok", proc.stdout)


if __name__ == "__main__":
    unittest.main()
