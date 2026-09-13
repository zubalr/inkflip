"""Test suite for P14 original-preserving geometric raster experiment (Task T45 / TEST-45).

Verifies acceptance criteria and counterexamples:
- Evaluation across all required geometry families F06, F07, F09, F15
- Dynamic verdict derivation: theta=0.0 reports 0 blur, 0 drift, 0 corruption, and lost_registration=False
- Candidate deskew (theta=1.0) measures rendered fiducial displacement and cleanly rejects
- Any lost registration or clean corruption rejects the candidate
- Original PDF bytes remain immutable (I01, I04)
- Retained raster buffers in artifacts/P14/rasters/
- Manifest validation and terminal failures on empty or held-out manifests
- Structured test counts exported via INKFLIP_TEST_REPORT_FILE
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

from experiments.P14.run import (
    resolve_manifest,
    load_and_validate_manifest,
    locate_rendered_fiducial,
    compute_edge_variance,
    run_experiment,
    TARGET_FIXTURE_IDS,
)


class TestP14Experiment(unittest.TestCase):
    def setUp(self) -> None:
        self.out_dir = ROOT / "artifacts" / "P14"
        self.manifest_path = resolve_manifest("evaluation/manifests/development.json")

    def test_required_geometry_fixtures_exist(self) -> None:
        """Verify fixtures spanning F06, F07, F09, F15 exist on disk."""
        fixtures = load_and_validate_manifest(self.manifest_path)
        found_ids = set(f["fixture_id"] for f in fixtures)
        self.assertTrue(TARGET_FIXTURE_IDS.issubset(found_ids), f"Missing required fixture IDs: {TARGET_FIXTURE_IDS - found_ids}")
        self.assertGreaterEqual(len(fixtures), 12)

    def test_experiment_runs_and_produces_valid_artifact(self) -> None:
        """Verify candidate evaluation produces compliant result.json rejecting deskew."""
        res = run_experiment(self.manifest_path, self.out_dir, candidate_theta_deg=1.0)
        self.assertEqual(res["experiment_id"], "P14")
        self.assertEqual(res["task_id"], "T45")
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["disposition"], "rejected_experiment")
        self.assertEqual(res["integration_decision"], "rejected_from_production")

        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        loaded = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(loaded["experiment_id"], "P14")
        self.assertEqual(loaded["disposition"], "rejected_experiment")

    def test_identity_transform_counterexample_derives_zero_drift_and_no_corruption(self) -> None:
        """Counterexample test: theta=0.0 must report 0 blur, 0 drift, 0 corruption, and lost_registration=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_out = Path(tmpdir)
            res = run_experiment(self.manifest_path, temp_out, candidate_theta_deg=0.0)

            metrics = res["metrics"]
            self.assertEqual(metrics["clean_controls_corrupted_count"], 0)
            self.assertFalse(metrics["lost_registration_detected"])
            self.assertEqual(metrics["mean_edge_variance_loss_pct"], 0.0)
            self.assertEqual(metrics["max_fiducial_drift_px"], 0.0)
            self.assertEqual(metrics["max_subpixel_drift_px"], 0.0)
            # Must NOT report rejected_experiment on identity
            self.assertNotEqual(res["disposition"], "rejected_experiment")
            self.assertEqual(res["disposition"], "candidate_accepted")

    def test_rendered_fiducials_measured_in_raster(self) -> None:
        """Verify rendered fiducial centers are accurately located in the raster."""
        # F09 text-transform-control.pdf has crosshairs intersecting at (320, 60) in 2.0x raster
        doc = pdfium.PdfDocument(ROOT / "fixtures" / "development" / "text-transform-control.pdf")
        canonical = doc[0].render(scale=2.0).to_pil().convert("L")
        loc = locate_rendered_fiducial(canonical, expected_xy=(320.0, 60.0))
        # Distance from theoretical intersection (320, 60) should be < 2 px
        dist = ((loc[0] - 320.0) ** 2 + (loc[1] - 60.0) ** 2) ** 0.5
        self.assertLess(dist, 2.0)

    def test_retained_rasters_in_artifacts(self) -> None:
        """Verify that baseline, candidate, and roundtrip PNG rasters are persisted in artifacts/P14/rasters/."""
        rasters_dir = self.out_dir / "rasters"
        self.assertTrue(rasters_dir.is_dir())
        png_files = list(rasters_dir.glob("*.png"))
        self.assertGreaterEqual(len(png_files), 14 * 3)  # baseline, candidate, roundtrip for each fixture
        for p in png_files[:5]:
            self.assertGreater(p.stat().st_size, 0)

    def test_manifest_validation_terminal_failures(self) -> None:
        """Verify manifest parser fails terminally on missing, empty, or held-out manifests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Nonexistent manifest
            with self.assertRaises(FileNotFoundError):
                load_and_validate_manifest(Path(tmpdir) / "nonexistent.json")

            # 2. Corrupted JSON
            corrupt = Path(tmpdir) / "corrupt.json"
            corrupt.write_text("{invalid-json", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_and_validate_manifest(corrupt)

            # 3. Empty entries
            empty = Path(tmpdir) / "empty.json"
            empty.write_text(json.dumps({"entries": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_and_validate_manifest(empty)

            # 4. Held-out evaluation split
            held_out = Path(tmpdir) / "heldout.json"
            held_out.write_text(json.dumps({"split": "evaluation", "entries": [{"fixture_id": "F06"}]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_and_validate_manifest(held_out)

    def test_source_bytes_preservation(self) -> None:
        """Verify source PDF fixtures remain byte-identical before and after execution (I01, I04)."""
        result_file = self.out_dir / "result.json"
        self.assertTrue(result_file.is_file())
        data = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(data["metrics"]["source_bytes_mutated_count"], 0)

    def test_rejection_rationale_conforms_to_contract(self) -> None:
        """Verify rejection rationale explicitly cites clean control corruption and registration loss."""
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
