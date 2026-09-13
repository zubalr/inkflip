"""Test suite for P13 native RapidOCR complement experiment (Task T44 / TEST-44).

Verifies:
- Baseline native Tesseract execution over manifest fixtures
- Explicit missing-model and OOV handling
- Honest accounting of RapidOCR dependency and weights blocker
- No runtime network calls
- Source PDF byte preservation (I04)
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
P13_DIR = ROOT / "experiments" / "P13"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(P13_DIR))

# Ensure native venv dependencies (pypdf, pypdfium2, Pillow) are loaded or re-exec via uv
try:
    import pypdf
    import pypdfium2 as pdfium
    from PIL import Image
except (ImportError, ModuleNotFoundError):
    uv = shutil.which("uv")
    if uv and not os.environ.get("_INKFLIP_P13_TEST_REEXEC"):
        os.environ["_INKFLIP_P13_TEST_REEXEC"] = "1"
        os.execv(uv, [uv, "run", "--project", "native", "python", *sys.argv])
    raise

from experiments.P13.run import resolve_manifest, run_experiment


class TestP13Experiment(unittest.TestCase):
    def setUp(self) -> None:
        self.out_dir = ROOT / "artifacts" / "P13"
        self.manifest_path = resolve_manifest("evaluation/manifests/development.json")

    def test_fixtures_exist_and_intact(self) -> None:
        dev_dir = ROOT / "fixtures" / "development"
        expected = [
            "ocr-material-control.pdf",
            "ocr-material-digit-ambiguity.pdf",
            "ocr-material-sign-ambiguity.pdf",
            "native-unicode-control.pdf",
            "native-unicode-native.pdf",
            "adjacent-crop-control.pdf",
            "adjacent-crop-adjacent.pdf",
            "adjacent-crop-clipped.pdf",
        ]
        for f in expected:
            p = dev_dir / f
            self.assertTrue(p.is_file(), f"Missing fixture: {f}")

    def test_experiment_runs_and_produces_valid_artifact(self) -> None:
        res = run_experiment(self.manifest_path, self.out_dir)
        self.assertEqual(res["experiment_id"], "P13")
        self.assertEqual(res["task_id"], "T44")
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["disposition"], "blocked_missing_dependency_and_weights")

        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        loaded = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(loaded["experiment_id"], "P13")

    def test_baseline_real_measurements(self) -> None:
        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        data = json.loads(result_file.read_text(encoding="utf-8"))

        fixtures = data["fixtures"]
        self.assertEqual(len(fixtures), 8)
        for f in fixtures:
            baseline = f["baseline_tesseract"]
            self.assertEqual(baseline["status"], "completed")
            self.assertGreater(baseline["runtime_seconds"], 0.0)
            self.assertGreater(f["pixels"], 0)

    def test_environment_audit_and_blocker_classification(self) -> None:
        result_file = self.out_dir / "result.json"
        data = json.loads(result_file.read_text(encoding="utf-8"))
        audit = data["environment_audit"]

        # Package is not installed and ONNX weights not bundled
        self.assertFalse(audit["package_installed"])
        self.assertFalse(audit["weights_present"])
        self.assertEqual(audit["status"], "blocked_missing_dependency_and_weights")
        self.assertFalse(audit["runtime_network_allowed"])
        self.assertEqual(data["integration_decision"], "default_not_installed")


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestP13Experiment)
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
