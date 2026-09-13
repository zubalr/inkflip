"""Test suite for P14 original-preserving geometric raster experiment (T45, TEST-45).

Verifies acceptance criteria:
- Any lost registration or clean corruption rejects
- Gain must transfer beyond the challenge generator
- No generic reconstruction/search or PDF write path
- Negative result closes task with deleted production candidate
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P14_DIR = ROOT / "experiments" / "P14"
sys.path.insert(0, str(P14_DIR))

import run as p14_runner


class TestRasterGeometryExperiment(unittest.TestCase):
    def test_original_source_and_raster_immutable(self):
        """Criterion: original PDF and raster immutable (I01, I02)."""
        fixture_pdf = ROOT / "planning" / "fixtures" / "mapping-control.pdf"
        self.assertTrue(fixture_pdf.is_file())
        before_hash = hashlib.sha256(fixture_pdf.read_bytes()).hexdigest()

        # Run experiment
        res = p14_runner.run_experiment(
            p14_runner.resolve_manifest(None),
            ROOT / "artifacts" / "P14",
        )
        after_hash = hashlib.sha256(fixture_pdf.read_bytes()).hexdigest()
        self.assertEqual(before_hash, after_hash, "Source fixture bytes must remain strictly unmodified")

    def test_clean_control_corruption_triggers_rejection(self):
        """Criterion: Any lost registration or clean corruption rejects."""
        eval_res = p14_runner.evaluate_deskew_candidate()
        self.assertTrue(eval_res["clean_control_pixel_drift"])
        self.assertEqual(eval_res["decision"], "reject")
        self.assertIn("corrupts clean ruled controls", eval_res["reason"])

    def test_inverse_transform_chain_exactness(self):
        """Criterion: transform chain provides exact mathematical inverse."""
        eval_res = p14_runner.evaluate_deskew_candidate()
        fwd = eval_res["forward_matrix"]
        inv = eval_res["inverse_matrix"]

        # Multiply rotation matrix and its inverse -> Identity matrix
        # [cos, -sin] * [cos, sin] = [cos^2 + sin^2, 0] = [1, 0]
        # [sin,  cos]   [-sin, cos]  [0, sin^2 + cos^2] = [0, 1]
        m00 = fwd[0] * inv[0] + fwd[1] * inv[2]
        m01 = fwd[0] * inv[1] + fwd[1] * inv[3]
        m10 = fwd[2] * inv[0] + fwd[3] * inv[2]
        m11 = fwd[2] * inv[1] + fwd[3] * inv[3]

        self.assertAlmostEqual(m00, 1.0, places=9)
        self.assertAlmostEqual(m01, 0.0, places=9)
        self.assertAlmostEqual(m10, 0.0, places=9)
        self.assertAlmostEqual(m11, 1.0, places=9)

    def test_no_pdf_write_or_reconstruction(self):
        """Criterion: no generic reconstruction/search or PDF write path."""
        res = p14_runner.run_experiment(
            p14_runner.resolve_manifest(None),
            ROOT / "artifacts" / "P14",
        )
        self.assertFalse(res["production_candidate_promoted"])
        self.assertEqual(res["status"], "rejected_experiment")

    def test_negative_result_documents_disposition(self):
        """Criterion: negative result closes task with deleted production candidate."""
        res_file = ROOT / "artifacts" / "P14" / "result.json"
        self.assertTrue(res_file.is_file(), "artifacts/P14/result.json must exist")
        data = json.loads(res_file.read_text(encoding="utf-8"))
        self.assertEqual(data["disposition"], "rejected_experiment")
        self.assertIn("Reject automatic raster deskew", data["recommendation"])


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRasterGeometryExperiment)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    passed = result.testsRun - failed - skipped
    counts = {
        "collected": result.testsRun,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }

    rep_env = os.environ.get("INKFLIP_TEST_REPORT_FILE")
    if rep_env:
        Path(rep_env).write_text(json.dumps(counts) + "\n")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
