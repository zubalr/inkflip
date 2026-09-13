"""T39 measurement driver unit tests (budgets and honest labeling)."""
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
        sys.path.insert(0, str(ROOT / "scripts"))
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
    def test_local_profile_writes_receipt_and_refuses_reference_claim(self) -> None:
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
            hash_stage = data["measurement"]["stages"]["file_read_hash"]
            self.assertEqual(hash_stage["n"], 3)
            self.assertEqual(hash_stage["distribution_claim"], "insufficient_samples")


if __name__ == "__main__":
    unittest.main()
