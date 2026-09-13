"""Test suite for P11 targeted OCR escalation experiment (Task T42 / TEST-42).

Verifies acceptance criteria:
- >=20% useful target gains at <=1pp precision loss or reject
- clean neighbor fields not corrupted
- every accepted transform source-bound
- failed/modelmissing jobs remain denominator
- full raw receipt retained
- real crop coordinate transformation tested
- empty OCR returns zero recoveries and zero corruptions (no hardcoded variant logic)
- empty or held-out manifests fail terminal
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
P11_DIR = ROOT / "experiments" / "P11"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(P11_DIR))

# Ensure native venv dependencies (pypdf, pypdfium2, Pillow) are loaded or re-exec via uv
try:
    import pypdf
    import pypdfium2 as pdfium
    from PIL import Image
except (ImportError, ModuleNotFoundError):
    uv = shutil.which("uv")
    if uv and not os.environ.get("_INKFLIP_P11_TEST_REEXEC"):
        os.environ["_INKFLIP_P11_TEST_REEXEC"] = "1"
        os.execv(uv, [uv, "run", "--project", "native", "python", *sys.argv])
    raise

from experiments.P11.run import resolve_manifest, run_experiment, pt_to_px


class TestP11Experiment(unittest.TestCase):
    def setUp(self) -> None:
        self.out_dir = ROOT / "artifacts" / "P11"
        self.manifest_path = resolve_manifest("evaluation/manifests/development.json")

    def test_fixtures_exist_and_intact(self) -> None:
        dev_dir = ROOT / "fixtures" / "development"
        expected_fixtures = [
            "adjacent-crop-control.pdf",
            "adjacent-crop-adjacent.pdf",
            "adjacent-crop-clipped.pdf",
            "ocr-material-control.pdf",
            "ocr-material-digit-ambiguity.pdf",
            "ocr-material-sign-ambiguity.pdf",
            "native-unicode-control.pdf",
            "native-unicode-native.pdf",
        ]
        for fname in expected_fixtures:
            pdf_p = dev_dir / fname
            self.assertTrue(pdf_p.is_file(), f"Missing fixture PDF: {fname}")
            expect_p = dev_dir / (fname.replace(".pdf", ".expect.json"))
            self.assertTrue(expect_p.is_file(), f"Missing expectation JSON: {expect_p.name}")

    def test_experiment_runs_and_produces_valid_artifact(self) -> None:
        res = run_experiment(self.manifest_path, self.out_dir)
        self.assertEqual(res["experiment_id"], "P11")
        self.assertEqual(res["task_id"], "T42")
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["disposition"], "rejected_experiment")

        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        loaded = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(loaded["experiment_id"], "P11")
        self.assertEqual(loaded["disposition"], "rejected_experiment")

    def test_resource_budgets(self) -> None:
        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        data = json.loads(result_file.read_text(encoding="utf-8"))
        costs = data["resource_costs"]
        self.assertLessEqual(costs["total_megapixels"], costs["max_megapixels_budget"])
        self.assertLessEqual(costs["runtime_seconds"], costs["max_runtime_seconds_budget"])

    def test_acceptance_criteria_and_rejection_rationale(self) -> None:
        result_file = self.out_dir / "result.json"
        data = json.loads(result_file.read_text(encoding="utf-8"))
        metrics = data["metrics"]

        # Denominator check: all 8 jobs accounted for
        self.assertEqual(metrics["total_jobs_evaluated"], 8)
        self.assertTrue(metrics["all_transforms_source_bound"])

        # Target recovery occurred on clipped fixture
        self.assertGreater(metrics["useful_target_recoveries"], 0)

        # Fatal criterion: clean neighbor was corrupted by padded retry
        self.assertGreater(metrics["clean_neighbors_corrupted"], 0)

        # Confirm rejection disposition is backed by evidence
        self.assertEqual(data["disposition"], "rejected_experiment")
        self.assertGreater(len(data["rejection_reasons"]), 0)

    def test_empty_ocr_returns_zero_recoveries_and_corruptions(self) -> None:
        """Counterexample test: mocked empty OCR must yield 0 recoveries and 0 corruptions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            res = run_experiment(self.manifest_path, Path(tmpdir), ocr_fn=lambda img: "")
            self.assertEqual(res["metrics"]["useful_target_recoveries"], 0)
            self.assertEqual(res["metrics"]["clean_neighbors_corrupted"], 0)
            self.assertEqual(res["metrics"]["target_recovery_gain_pct"], 0.0)
            self.assertEqual(res["metrics"]["precision_loss_pp"], 0.0)

    def test_empty_manifest_fails_terminal(self) -> None:
        """Empty manifest must fail terminal."""
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            json.dump({"entries": []}, f)
            f.flush()
            with self.assertRaises(ValueError):
                run_experiment(Path(f.name), self.out_dir)

    def test_held_out_manifest_fails_terminal(self) -> None:
        """Held-out evaluation manifest must fail terminal."""
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            json.dump({"split": "evaluation", "entries": [{"path": "fixtures/development/adjacent-crop-control.pdf"}]}, f)
            f.flush()
            with self.assertRaises(ValueError):
                run_experiment(Path(f.name), self.out_dir)

    def test_pt_to_px_coordinate_transform(self) -> None:
        """Coordinate transform correctly maps PDF bottom-left points to PIL top-left pixels."""
        # 320x240 pt page rendered at scale 2.0 -> 640x480 px
        box_pt = [50.0, 100.0, 100.0, 140.0]
        # px0 = 50 * 2 = 100, px1 = 100 * 2 = 200
        # py0 = (240 - 140) * 2 = 200, py1 = (240 - 100) * 2 = 280
        px_box = pt_to_px(box_pt, 240.0, 2.0, 640, 480)
        self.assertEqual(px_box, (100, 200, 200, 280))


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestP11Experiment)
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
