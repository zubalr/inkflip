"""Test suite for P13 native RapidOCR complement experiment (Task T44 / TEST-44).

Verifies:
- Baseline native Tesseract execution over manifest fixtures with persisted rasters
- Terminal failure and denominator accounting on OCR errors, timeouts, and missing binaries
- Rejection of corrupt/dummy ONNX models and unchecked candidate claims (counterexample verification)
- PP-OCRv5 mobile English provenance and exact version auditing
- Honest blocked status and disposition when dependencies/weights are missing under offline containment
- Manifest validation and terminal failure on empty or held-out manifests
- Peak RSS measurement and memory budget auditing
- Structured test counts exported via INKFLIP_TEST_REPORT_FILE
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

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

from experiments.P13.run import (
    resolve_manifest,
    load_and_validate_manifest,
    is_valid_onnx_model,
    audit_rapidocr_environment,
    run_tesseract_ocr,
    run_experiment,
    REQUIRED_RAPIDOCR_VERSION,
    PP_OCRV5_DET_NAMES,
    PP_OCRV5_REC_NAMES,
)


class TestP13Experiment(unittest.TestCase):
    def setUp(self) -> None:
        self.out_dir = ROOT / "artifacts" / "P13"
        self.manifest_path = resolve_manifest("evaluation/manifests/development.json")

    def test_fixtures_exist_and_intact(self) -> None:
        """Verify all target F14, F15, F16 development fixtures exist."""
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
        """Verify experiment execution produces compliant result.json with blocked status."""
        res = run_experiment(self.manifest_path, self.out_dir)
        self.assertEqual(res["experiment_id"], "P13")
        self.assertEqual(res["task_id"], "T44")
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res["disposition"], "blocked_missing_dependency_and_weights")
        self.assertEqual(res["integration_decision"], "default_not_installed")

        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        loaded = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(loaded["experiment_id"], "P13")
        self.assertEqual(loaded["status"], "blocked")

    def test_baseline_real_measurements_and_persisted_rasters(self) -> None:
        """Verify baseline runs real Tesseract and retains PNG rasters in artifacts/P13/rasters/."""
        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        data = json.loads(result_file.read_text(encoding="utf-8"))

        fixtures = data["fixtures"]
        self.assertEqual(len(fixtures), 8)
        rasters_dir = self.out_dir / "rasters"
        self.assertTrue(rasters_dir.is_dir())

        for f in fixtures:
            baseline = f["baseline_tesseract"]
            self.assertEqual(baseline["status"], "completed")
            self.assertGreater(baseline["runtime_seconds"], 0.0)
            self.assertGreater(f["pixels"], 0)
            self.assertIsNotNone(f.get("raster_path"))

            raster_file = ROOT / f["raster_path"]
            self.assertTrue(raster_file.is_file(), f"Persisted raster missing: {raster_file}")
            self.assertGreater(raster_file.stat().st_size, 0)

    def test_ocr_failures_counted_in_denominator_not_empty_success(self) -> None:
        """Counterexample test: verify Tesseract failure/timeout/error is never treated as completed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_img = Path(tmpdir) / "dummy.png"
            Image.new("RGB", (100, 100), color="white").save(dummy_img)

            # 1. Nonzero exit code
            mock_res_fail = MagicMock()
            mock_res_fail.returncode = 1
            mock_res_fail.stdout = ""
            mock_res_fail.stderr = "Error: unhandled exception in leptonica"
            with patch("subprocess.run", return_value=mock_res_fail):
                outcome = run_tesseract_ocr(dummy_img)
                self.assertEqual(outcome["status"], "failed")
                self.assertEqual(outcome["exit_code"], 1)
                self.assertIn("leptonica", outcome["error"])

            # 2. Timeout
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["tesseract"], timeout=15)):
                outcome = run_tesseract_ocr(dummy_img)
                self.assertEqual(outcome["status"], "timeout")
                self.assertEqual(outcome["exit_code"], -1)
                self.assertIn("timed out", outcome["error"])

            # 3. Missing binary
            with patch("shutil.which", return_value=None), patch("os.path.exists", return_value=False):
                outcome = run_tesseract_ocr(dummy_img)
                self.assertEqual(outcome["status"], "missing_executable")
                self.assertEqual(outcome["exit_code"], -1)

    def test_corrupted_model_counterexample_rejected_never_available(self) -> None:
        """Counterexample test: dummy files containing 'not an ONNX model' must fail validation and reject."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            det_file = model_dir / PP_OCRV5_DET_NAMES[0]
            rec_file = model_dir / PP_OCRV5_REC_NAMES[0]

            # Write dummy non-ONNX text counterexample
            det_file.write_bytes(b"not an ONNX model - dummy weights placeholder")
            rec_file.write_bytes(b"not an ONNX model - dummy weights placeholder")

            # Validate header helper directly
            valid, reason = is_valid_onnx_model(det_file.read_bytes())
            self.assertFalse(valid)
            self.assertIn("dummy", reason)

            # Audit environment with dummy models in search path
            audit = audit_rapidocr_environment(custom_search_dirs=[model_dir])
            self.assertEqual(audit["status"], "blocked")
            self.assertEqual(audit["disposition"], "candidate_rejected_corrupted_weights")
            self.assertTrue(audit["weights_corrupt"])
            self.assertNotEqual(audit["status"], "available")

    def test_pp_ocrv5_mobile_english_provenance_and_version(self) -> None:
        """Verify candidate audit targets PP-OCRv5 mobile English and pinned version 3.8.1."""
        audit = audit_rapidocr_environment()
        self.assertIn("PP-OCRv5 mobile English", audit["candidate_name"])
        self.assertEqual(audit["source_id"], "S47")
        self.assertEqual(audit["required_package"], f"rapidocr=={REQUIRED_RAPIDOCR_VERSION}")
        self.assertEqual(audit["status"], "blocked")
        self.assertEqual(audit["disposition"], "blocked_missing_dependency_and_weights")
        self.assertFalse(audit["runtime_network_allowed"])
        self.assertIn("attempted_preparation", audit)
        self.assertIn("uv pip install", audit["attempted_preparation"]["package_command"])

    def test_manifest_validation_terminal_failures(self) -> None:
        """Verify manifest loader fails terminally on missing, empty, or held-out manifests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Nonexistent manifest
            with self.assertRaises(FileNotFoundError):
                load_and_validate_manifest(Path(tmpdir) / "nonexistent.json")

            # 2. Corrupted JSON
            corrupt = Path(tmpdir) / "corrupt.json"
            corrupt.write_text("{bad-json", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_and_validate_manifest(corrupt)

            # 3. Empty entries
            empty = Path(tmpdir) / "empty.json"
            empty.write_text(json.dumps({"entries": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_and_validate_manifest(empty)

            # 4. Held-out evaluation split
            held_out = Path(tmpdir) / "heldout.json"
            held_out.write_text(json.dumps({"split": "evaluation", "entries": [{"fixture_id": "F14"}]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_and_validate_manifest(held_out)

    def test_resource_costs_and_rss_measurement(self) -> None:
        """Verify peak RSS is measured and within 1 GiB memory budget."""
        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        data = json.loads(result_file.read_text(encoding="utf-8"))
        costs = data["resource_costs"]

        self.assertGreater(costs["measured_peak_rss_bytes"], 0)
        self.assertGreater(costs["measured_peak_rss_mb"], 0.0)
        self.assertTrue(costs["memory_budget_satisfied"])
        self.assertEqual(costs["memory_budget_bytes"], 1024 * 1024 * 1024)
        self.assertIn("host_containment", costs)
        self.assertEqual(costs["runtime_network_isolation"]["network_calls_attempted"], 0)


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
