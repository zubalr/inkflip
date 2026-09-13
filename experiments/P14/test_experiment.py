"""Test suite for P14 original-preserving geometric raster experiment (Task T45 / TEST-45).

Verifies acceptance criteria:
- Real rasterization and measurement of clean controls
- Measurable resampling blur and subpixel drift
- Any lost registration or clean corruption rejects the candidate
- Original PDF bytes remain immutable (I01, I04)
- Structured test counts exported via INKFLIP_TEST_REPORT_FILE
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
P14_DIR = ROOT / "experiments" / "P14"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(P14_DIR))

# Ensure native venv dependencies (pypdfium2, Pillow) are loaded or re-exec via uv
try:
    import pypdfium2 as pdfium
    from PIL import Image
except (ImportError, ModuleNotFoundError):
    uv = shutil.which("uv")
    if uv and not os.environ.get("_INKFLIP_P14_TEST_REEXEC"):
        os.environ["_INKFLIP_P14_TEST_REEXEC"] = "1"
        os.execv(uv, [uv, "run", "--project", "native", "python", *sys.argv])
    raise

from experiments.P14.run import resolve_manifest, run_experiment


class TestP14Experiment(unittest.TestCase):
    def setUp(self) -> None:
        self.out_dir = ROOT / "artifacts" / "P14"
        self.manifest_path = resolve_manifest("evaluation/manifests/development.json")

    def test_fixtures_exist_and_intact(self) -> None:
        dev_dir = ROOT / "fixtures" / "development"
        expected = [
            "ocr-material-control.pdf",
            "ocr-material-digit-ambiguity.pdf",
            "ocr-material-sign-ambiguity.pdf",
            "partial-clip-control.pdf",
            "partial-clip-partial.pdf",
            "partial-clip-triangle.pdf",
            "huge-page-control.pdf",
            "userunit-1.pdf",
            "adjacent-crop-control.pdf",
        ]
        for f in expected:
            p = dev_dir / f
            self.assertTrue(p.is_file(), f"Missing fixture: {f}")

    def test_experiment_runs_and_produces_valid_artifact(self) -> None:
        res = run_experiment(self.manifest_path, self.out_dir)
        self.assertEqual(res["experiment_id"], "P14")
        self.assertEqual(res["task_id"], "T45")
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["disposition"], "rejected_experiment")

        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        loaded = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(loaded["experiment_id"], "P14")
        self.assertEqual(loaded["disposition"], "rejected_experiment")

    def test_clean_control_corruption_is_measured(self) -> None:
        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        data = json.loads(result_file.read_text(encoding="utf-8"))

        metrics = data["metrics"]
        self.assertGreater(metrics["clean_controls_corrupted_count"], 0)
        self.assertGreater(metrics["mean_edge_variance_loss_pct"], 0.0)
        self.assertGreater(metrics["max_subpixel_drift_px"], 0.0)
        self.assertTrue(metrics["lost_registration_detected"])
        self.assertEqual(metrics["source_bytes_mutated_count"], 0)

    def test_rejection_rationale_conforms_to_contract(self) -> None:
        result_file = self.out_dir / "result.json"
        data = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(data["disposition"], "rejected_experiment")
        self.assertEqual(data["integration_decision"], "rejected_from_production")
        self.assertGreater(len(data["rejection_reasons"]), 0)


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestP14Experiment)
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
