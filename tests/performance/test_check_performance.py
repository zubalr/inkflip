"""REVIEW.md wrapper defects: --cli is required and labels are not proof."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_performance.py"
RECEIPT_TESTS = ROOT / "tests" / "performance" / "test_performance_receipt.py"
CANONICAL_CLI = Path(
    "/Users/zubair/Code/Projects/pdf project/original/artifacts/performance/local-mac.json"
)
OLD_BROWSER = Path(
    "/Users/zubair/Code/Projects/pdf project/handoffs/cursor-release-closeout-20260913/evidence/browser-local-mac.json"
)
FRESH_BROWSER = Path(
    "/Users/zubair/Code/Projects/pdf project/original/artifacts/performance/browser-local-mac.json"
)


def load_checker():
    spec = importlib.util.spec_from_file_location("check_performance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_receipt_tests():
    spec = importlib.util.spec_from_file_location("test_performance_receipt", RECEIPT_TESTS)
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


class TestCheckerCombinesProducerFiles(unittest.TestCase):
    def setUp(self) -> None:
        self.tpr = load_receipt_tests()
        self.rec = self.tpr.load_receipt()
        self.body = self.tpr.valid_receipt(self.rec)

    def _run(self, cli_body: dict, browser_body: dict | None) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory(prefix="inkflip-check-combo-") as raw:
            cli = Path(raw) / "cli.json"
            cli.write_text(json.dumps(cli_body) + "\n", encoding="utf-8")
            cmd = [sys.executable, str(SCRIPT), "--mode", "accept", "--profile", "local-mac", "--cli", str(cli)]
            if browser_body is not None:
                browser = Path(raw) / "browser.json"
                browser.write_text(json.dumps(browser_body) + "\n", encoding="utf-8")
                cmd.extend(["--browser", str(browser)])
            return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)

    def test_combined_valid_files_accept(self) -> None:
        browser = self.body.pop("browser")
        proc = self._run(self.body, browser)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("performance accept: ok", proc.stdout)

    def test_old_browser_file_with_new_cli_file_fails(self) -> None:
        browser = copy.deepcopy(self.body["browser"])
        del self.body["browser"]
        browser["source_binding"]["implementation"]["browser_sha256"] = "b" * 64
        browser["source_binding"]["inputs_sha256"] = "b" * 64
        browser["build"]["built_from_browser_sha256"] = "b" * 64
        proc = self._run(self.body, browser)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("stale implementation identity: browser_sha256", proc.stderr)
        self.assertNotIn("Traceback (most recent call last)", proc.stderr)

    def test_missing_browser_binding_on_combined_files_fails(self) -> None:
        browser = copy.deepcopy(self.body["browser"])
        del self.body["browser"]
        del browser["source_binding"]
        proc = self._run(self.body, browser)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("CLI identity is not a substitute", proc.stderr)

    def test_review_repro_old_browser_with_cli_recorded_binding(self) -> None:
        if not CANONICAL_CLI.is_file() or not OLD_BROWSER.is_file() or not FRESH_BROWSER.is_file():
            self.skipTest("canonical/old performance receipts are not on this host")
        rec = self.rec
        cli_body, err = rec.load_json_object(CANONICAL_CLI)
        self.assertIsNone(err)
        assert cli_body is not None
        old_browser, err = rec.load_json_object(OLD_BROWSER)
        self.assertIsNone(err)
        fresh_browser, err = rec.load_json_object(FRESH_BROWSER)
        self.assertIsNone(err)
        assert old_browser is not None and fresh_browser is not None
        current = copy.deepcopy(cli_body["source_binding"])
        settings = json.loads((ROOT / "planning/config/settings.json").read_text())
        combined_fresh = dict(cli_body)
        combined_fresh["browser"] = fresh_browser
        combined_old = dict(cli_body)
        combined_old["browser"] = old_browser
        fresh_problems = rec.validate_receipt(
            combined_fresh,
            mode="accept",
            profile="local-mac",
            settings=settings,
            current_binding=current,
        )
        old_problems = rec.validate_receipt(
            combined_old,
            mode="accept",
            profile="local-mac",
            settings=settings,
            current_binding=current,
        )
        self.assertTrue(
            any("browser" in item.lower() and ("binding" in item.lower() or "stale" in item.lower() or "substitute" in item.lower()) for item in old_problems),
            old_problems,
        )
        # Fresh browser from canonical still lacks its own producer binding until rebuilt.
        self.assertTrue(
            any("substitute" in item or "binding" in item or "stale" in item for item in fresh_problems),
            fresh_problems,
        )
        self.assertNotEqual(fresh_browser.get("build", {}).get("tree_sha256"), old_browser.get("build", {}).get("tree_sha256"))


if __name__ == "__main__":
    unittest.main()
