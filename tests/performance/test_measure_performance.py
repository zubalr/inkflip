"""T39 measurement driver unit tests (honest naming and fail-closed accept)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "measure_performance.py"


class TestRasterBudgets(unittest.TestCase):
    def test_finite_positive_and_edge_pixel_caps(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("measure_performance", SCRIPT)
        assert spec and spec.loader
        mp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mp)

        ok = mp.validate_raster_request(800, 600)
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(ok["live_buffers"], 2)
        self.assertEqual(ok["ocr_workers"], 1)
        bad = mp.validate_raster_request(float("nan"), 10)
        self.assertFalse(bad["ok"])
        edge = mp.validate_raster_request(9000, 100)
        self.assertFalse(edge["ok"])
        mobile = mp.validate_raster_request(2000, 2000, mobile=True)
        self.assertEqual(mobile["pixel_budget"], 2_000_000)
        self.assertEqual(mobile["mobile_ocr_pages"], 1)


class TestMeasureDriver(unittest.TestCase):
    def test_inventory_refuses_reference_claim(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inkflip-t39-out-") as raw:
            out = Path(raw)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--profile",
                    "reference-desktop",
                    "--samples",
                    "3",
                    "--mode",
                    "inventory",
                    "--out",
                    str(out),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            path = out / "reference-desktop.json"
            self.assertTrue(path.is_file(), proc.stdout)
            data = json.loads(path.read_text())
            self.assertFalse(data["host"]["is_specified_reference_desktop"])
            self.assertIn("gap", data["host"])
            self.assertFalse(data["accepting"])
            hash_stage = data["measurement"]["stages"]["file_sha256"]
            self.assertEqual(hash_stage["n"], 3)
            self.assertEqual(hash_stage["distribution_claim"], "insufficient_samples")
            self.assertEqual(data["measurement"]["stages"]["inspect_cli"]["n"], 3)
            align = data["measurement"]["stages"]["alignment_cli"]
            self.assertEqual(align["n"], 3)
            self.assertTrue(align["measured"])

    def test_accept_fails_for_unavailable_reference_profile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inkflip-t39-accept-") as raw:
            out = Path(raw)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--profile",
                    "reference-desktop",
                    "--samples",
                    "1",
                    "--mode",
                    "accept",
                    "--out",
                    str(out),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("ACCEPT-FAIL", proc.stderr)

    def test_review_n1_failures29_label_is_rejected(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("measure_performance", SCRIPT)
        assert spec and spec.loader
        mp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mp)
        stage = {
            "n": 1,
            "failures": 29,
            "measured": True,
            "distribution_claim": "n>=30",
            "samples_ms": [1.0],
            "p50": 1.0,
            "p95": 1.0,
            "max": 1.0,
        }
        body = {
            "kind": "inkflip-performance",
            "schema_version": "2.1.0",
            "host": {"is_specified_reference_desktop": False, "is_physical_mobile": False},
            "source_binding": {"fixture_sha256": "a" * 64, "git_head": "deadbeef"},
            "measurement": {
                "stages": {
                    "file_sha256": stage,
                    "inspect_cli": stage,
                    "report_html": stage,
                    "alignment_cli": stage,
                    "ocr_cli": stage,
                }
            },
        }
        problems = mp.acceptance_problems(body, mode="accept", profile="local-mac")
        joined = " ".join(problems)
        self.assertTrue(problems)
        self.assertIn("n>=30", joined)
        self.assertTrue(any("browser" in item.lower() for item in problems))

    def test_stale_schema_20_is_rejected(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("measure_performance", SCRIPT)
        assert spec and spec.loader
        mp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mp)
        problems = mp.acceptance_problems(
            {
                "kind": "inkflip-performance",
                "schema_version": "2.0.0",
                "measurement": {"stages": {}},
            },
            mode="accept",
            profile="local-mac",
        )
        self.assertTrue(any("stale" in item for item in problems))

    def test_local_mac_accept_without_browser_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inkflip-t39-nobrowser-") as raw:
            out = Path(raw)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--profile",
                    "local-mac",
                    "--samples",
                    "1",
                    "--mode",
                    "accept",
                    "--out",
                    str(out),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("ACCEPT-FAIL", proc.stderr)


if __name__ == "__main__":
    unittest.main()
