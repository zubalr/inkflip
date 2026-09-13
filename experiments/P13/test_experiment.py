"""Test suite for P13 native RapidOCR complement experiment (Task T44 / TEST-44).

Verifies:
- Baseline native Tesseract execution over manifest fixtures with persisted rasters
- Real RapidOCR candidate execution when candidate environment is available
- Terminal failure and denominator accounting on OCR errors, timeouts, and missing binaries
- Strict rejection of corrupted ONNX models including junk-ONNX counterexample (b'\x08' + b'\x00' * 127)
- Official PP-OCRv5 mobile English provenance and exact version auditing against trusted digests
- Manifest validation: explicit missing manifest fails (no silent fallback), empty/held-out fail
- Peak RSS measurement accurately labeled and bounded within 1 GiB memory budget
- Independent ground truth preservation: no consensus-as-truth (Invariant I17)
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

# Re-exec via experiment-local virtual environment if available
P13_VENV_PYTHON = ROOT / "experiments" / "P13" / ".venv" / "bin" / "python"


def maybe_reexec_venv() -> None:
    if P13_VENV_PYTHON.is_file() and sys.executable != str(P13_VENV_PYTHON):
        if "-c" not in sys.argv and not os.environ.get("_INKFLIP_P13_TEST_VENV_REEXEC"):
            os.environ["_INKFLIP_P13_TEST_VENV_REEXEC"] = "1"
            os.execv(str(P13_VENV_PYTHON), [str(P13_VENV_PYTHON), *sys.argv])

# Ensure native dependencies are available
try:
    import pypdf
    import pypdfium2 as pdfium
    from PIL import Image
except (ImportError, ModuleNotFoundError):
    uv = shutil.which("uv")
    if uv and "-c" not in sys.argv and not os.environ.get("_INKFLIP_P13_TEST_REEXEC"):
        os.environ["_INKFLIP_P13_TEST_REEXEC"] = "1"
        os.execv(uv, [uv, "run", "--project", "native", "python", *sys.argv])
    raise

from experiments.P13.run import (
    resolve_manifest,
    load_and_validate_manifest,
    is_valid_onnx_model,
    audit_rapidocr_environment,
    run_tesseract_ocr,
    run_rapidocr,
    run_experiment,
    REQUIRED_RAPIDOCR_VERSION,
    OFFICIAL_MODEL_DIGESTS,
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
        """Verify experiment execution produces compliant result.json."""
        res = run_experiment(self.manifest_path, self.out_dir)
        self.assertEqual(res["experiment_id"], "P13")
        self.assertEqual(res["task_id"], "T44")
        self.assertIn(res["status"], ("completed", "blocked"))
        self.assertEqual(res["integration_decision"], "default_not_installed")

        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        loaded = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(loaded["experiment_id"], "P13")
        self.assertIn(loaded["status"], ("completed", "blocked"))

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

    def test_candidate_rapidocr_execution_when_available(self) -> None:
        """Verify candidate RapidOCR outputs boxes, texts, scores when environment is available."""
        audit = audit_rapidocr_environment()
        if audit["status"] == "available":
            result_file = self.out_dir / "result.json"
            data = json.loads(result_file.read_text(encoding="utf-8"))
            for f in data["fixtures"]:
                cand = f["candidate_rapidocr"]
                self.assertEqual(cand["status"], "completed")
                self.assertIsInstance(cand["boxes"], list)
                self.assertIsInstance(cand["scores"], list)
                self.assertGreater(cand["runtime_seconds"], 0.0)
            self.assertEqual(data["metrics"]["candidate_completed_count"], 8)
            self.assertEqual(data["metrics"]["candidate_blocked_count"], 0)

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

    def test_junk_onnx_counterexample_rejected_strictly(self) -> None:
        """Reproduce and verify rejection of junk-ONNX counterexample b'\\x08' + b'\\x00' * 127."""
        junk_payload = b"\x08" + b"\x00" * 127
        valid, reason = is_valid_onnx_model(junk_payload)
        self.assertFalse(valid, f"Junk-ONNX payload was falsely accepted! Reason: {reason}")

        # Text dummy placeholder rejection
        valid_dummy, reason_dummy = is_valid_onnx_model(b"not an ONNX model - dummy weights placeholder")
        self.assertFalse(valid_dummy)
        self.assertIn("dummy", reason_dummy)

        # Empty / too short payload rejection
        valid_short, _ = is_valid_onnx_model(b"\x08\x01\x02")
        self.assertFalse(valid_short)

        # Expected digest mismatch rejection
        valid_mismatch, reason_mismatch = is_valid_onnx_model(
            b"\x08" * 100,
            expected_sha256="0000000000000000000000000000000000000000000000000000000000000000",
        )
        self.assertFalse(valid_mismatch)
        self.assertIn("mismatch", reason_mismatch)

    def test_pp_ocrv5_mobile_english_provenance_and_version(self) -> None:
        """Verify candidate audit targets PP-OCRv5 mobile English, pinned version 3.8.1, and official digests."""
        audit = audit_rapidocr_environment()
        self.assertIn("PP-OCRv5 mobile English", audit["candidate_name"])
        self.assertEqual(audit["source_id"], "S47")
        self.assertEqual(audit["required_package"], f"rapidocr=={REQUIRED_RAPIDOCR_VERSION}")
        self.assertFalse(audit["runtime_network_allowed"])
        self.assertIn("attempted_preparation", audit)
        self.assertIn("rapidocr==3.8.1", audit["attempted_preparation"]["package_command"])
        from experiments.P13.run import DEFAULT_WEIGHT_SEARCH_DIRS

        for search_dir in DEFAULT_WEIGHT_SEARCH_DIRS:
            self.assertNotIn("site-packages", str(search_dir))

        # RapidOCR v3.8.1 default_models.yaml: cls_mobile is e47acedf…, not 54379ae5…
        # (54379ae5… is ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx).
        self.assertEqual(
            OFFICIAL_MODEL_DIGESTS["ch_ppocr_mobile_v2.0_cls_mobile.onnx"],
            "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
        )
        self.assertEqual(
            OFFICIAL_MODEL_DIGESTS["ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx"],
            "54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7",
        )

        if audit["status"] == "available":
            self.assertEqual(audit["disposition"], "candidate_ready")
            self.assertTrue(audit["package_installed"])
            self.assertTrue(audit["version_valid"])
            self.assertTrue(audit["weights_present"])
            self.assertFalse(audit["weights_corrupt"])
            self.assertIsNotNone(audit["detector_model"])
            self.assertIsNotNone(audit["recognizer_model"])
            self.assertIsNotNone(audit["classifier_model"])
            self.assertEqual(
                audit["detector_model"]["sha256"],
                OFFICIAL_MODEL_DIGESTS["ch_PP-OCRv5_det_mobile.onnx"],
            )
            self.assertEqual(
                audit["recognizer_model"]["sha256"],
                OFFICIAL_MODEL_DIGESTS["en_PP-OCRv5_rec_mobile.onnx"],
            )
            self.assertEqual(
                audit["classifier_model"]["sha256"],
                OFFICIAL_MODEL_DIGESTS["ch_ppocr_mobile_v2.0_cls_mobile.onnx"],
            )
            self.assertNotIn("site-packages", audit["classifier_model"]["path"])

    def test_classifier_digest_mismatch_fails_closed(self) -> None:
        """A present classifier whose digest does not match its filename pin is corrupt, not official."""
        models = ROOT / "experiments" / "P13" / "models"
        det = models / "ch_PP-OCRv5_det_mobile.onnx"
        rec = models / "en_PP-OCRv5_rec_mobile.onnx"
        if not (det.is_file() and rec.is_file()):
            self.skipTest("matching det/rec weights are not staged in this worktree")
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            shutil.copyfile(det, d / det.name)
            shutil.copyfile(rec, d / rec.name)
            (d / "ch_ppocr_mobile_v2.0_cls_mobile.onnx").write_bytes(b"not-official-classifier" * 8)
            audit = audit_rapidocr_environment(custom_search_dirs=[d])
            self.assertTrue(audit["weights_corrupt"])
            self.assertEqual(audit["status"], "blocked")
            self.assertEqual(audit["disposition"], "candidate_rejected_corrupted_weights")
            self.assertIsNotNone(audit["classifier_model"])
            self.assertFalse(audit["classifier_model"]["valid"])
            self.assertIn("mismatch", audit["classifier_model"]["reason"].lower())
            self.assertNotEqual(audit["status"], "available")

    def test_resolve_manifest_explicit_missing_fails(self) -> None:
        """Verify resolve_manifest raises FileNotFoundError on explicitly missing manifests without fallback."""
        # 1. Nonexistent explicit path must fail immediately
        with self.assertRaises(FileNotFoundError):
            resolve_manifest("/tmp/nonexistent_dir_xyz/development.json")

        with self.assertRaises(FileNotFoundError):
            resolve_manifest("nonexistent_manifest_file.json")

        # 2. Documented default must resolve to existing manifest
        default_path = resolve_manifest(None)
        self.assertTrue(default_path.is_file())

        contract_default = resolve_manifest("evaluation/manifests/development.json")
        self.assertTrue(contract_default.is_file())

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
        """Verify peak RSS is measured and strictly within 1 GiB memory budget."""
        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        data = json.loads(result_file.read_text(encoding="utf-8"))
        costs = data["resource_costs"]

        self.assertGreater(costs["process_max_rss_bytes"], 0)
        self.assertGreater(costs["process_max_rss_mb"], 0.0)
        self.assertTrue(costs["memory_budget_satisfied"])
        self.assertLess(costs["process_max_rss_bytes"], costs["memory_budget_bytes"])
        self.assertEqual(costs["memory_budget_bytes"], 1024 * 1024 * 1024)
        self.assertIn("host_containment", costs)
        self.assertEqual(costs["runtime_network_isolation"]["network_calls_attempted"], 0)

    def test_no_consensus_as_truth(self) -> None:
        """Verify that candidate and baseline outputs are kept separate without consensus-as-truth (Invariant I17)."""
        result_file = self.out_dir / "result.json"
        data = json.loads(result_file.read_text(encoding="utf-8"))
        for f in data["fixtures"]:
            self.assertIn("baseline_tesseract", f)
            self.assertIn("candidate_rapidocr", f)
            # Ground truth must not be synthetic consensus of candidate and baseline
            self.assertNotIn("consensus_ground_truth", f)

    def test_runtime_network_isolation_blocks_network(self) -> None:
        """Verify enforce_network_isolation intercepts and blocks outbound network calls during inference."""
        from experiments.P13.run import enforce_network_isolation
        import socket

        with enforce_network_isolation():
            # Outbound connection attempt must be blocked
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with self.assertRaises(RuntimeError) as cm:
                s.connect(("1.1.1.1", 80))
            self.assertIn("prohibited by Invariant I14", str(cm.exception))

            with self.assertRaises(RuntimeError) as cm:
                socket.create_connection(("example.com", 80))
            self.assertIn("prohibited by Invariant I14", str(cm.exception))

            with self.assertRaises(RuntimeError) as cm:
                socket.getaddrinfo("example.com", 80)
            self.assertIn("prohibited by Invariant I14", str(cm.exception))

    def test_explicit_missing_model_and_oov_behavior(self) -> None:
        """Verify explicit missing-model audit triggers blocked status and preserves failure accounting in denominator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Audit with empty search directory (missing models)
            audit = audit_rapidocr_environment(custom_search_dirs=[Path(tmpdir)])
            self.assertEqual(audit["status"], "blocked")
            self.assertFalse(audit["weights_present"])
            self.assertEqual(audit["disposition"], "blocked_missing_dependency_and_weights")
            self.assertIn("attempted_preparation", audit)

            # Evaluate fixture with missing model audit must produce blocked candidate record
            rasters_dir = Path(tmpdir) / "rasters"
            rasters_dir.mkdir()
            dev_dir = ROOT / "fixtures" / "development"
            fix_path = dev_dir / "ocr-material-control.pdf"
            from experiments.P13.run import evaluate_fixture
            res = evaluate_fixture(fix_path, rasters_dir, audit)
            self.assertEqual(res["baseline_tesseract"]["status"], "completed")
            self.assertEqual(res["candidate_rapidocr"]["status"], "blocked")
            self.assertEqual(res["candidate_rapidocr"]["exit_code"], -1)
            self.assertIn("blocked", res["candidate_rapidocr"]["error"])

            # Verify OOV character handling: RapidOCR inference with unusual/OOV Unicode string
            audit_real = audit_rapidocr_environment()
            if audit_real["status"] == "available":
                from PIL import ImageDraw
                oov_img = Path(tmpdir) / "oov_test.png"
                img = Image.new("RGB", (300, 100), color="white")
                draw = ImageDraw.Draw(img)
                draw.text((10, 30), "§¶•€¥ 12345", fill="black")
                img.save(oov_img)
                res_oov = run_rapidocr(
                    oov_img,
                    Path(audit_real["det_path"]),
                    Path(audit_real["rec_path"]),
                    Path(audit_real["cls_path"]) if audit_real.get("cls_path") else None,
                )
                self.assertIn(res_oov["status"], ("completed", "failed"))
                self.assertIsInstance(res_oov["boxes"], list)


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
    maybe_reexec_venv()
    sys.exit(run_tests())
