"""Test suite for P09 paint-order and ink-counterexample experiment (T41, TEST-41).

Verifies acceptance criteria:
- Zero hard-control false visibility
- precision/coverage/runtime recorded
- candidate gain measured without held-out leakage
- negative result is complete
- source bytes preserved immutable (I01)
- empty or held-out manifests fail terminal
- 2D geometric occlusion distinguishes full vs partial coverage
- distinct execution runtimes recorded per method
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P09_DIR = ROOT / "experiments" / "P09"
sys.path.insert(0, str(P09_DIR))

# Ensure native venv dependencies (pypdf, pypdfium2, Pillow) are loaded or re-exec via uv
try:
    import pypdf
    import pypdfium2 as pdfium
    from PIL import Image
except (ImportError, ModuleNotFoundError):
    uv = shutil.which("uv")
    if uv and not os.environ.get("_INKFLIP_P09_TEST_REEXEC"):
        os.environ["_INKFLIP_P09_TEST_REEXEC"] = "1"
        os.execv(uv, [uv, "run", "--project", "native", "python", *sys.argv])
    raise

import run as p09_runner


class TestPaintOrderExperiment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest_path = p09_runner.resolve_manifest("evaluation/manifests/development.json")
        cls.out_dir = ROOT / "artifacts" / "P09"
        cls.result = p09_runner.run_experiment(cls.manifest_path, cls.out_dir)

    def test_zero_hard_control_false_visibility(self):
        """Criterion: Zero hard-control false visibility."""
        metrics = self.result["metrics"]["bounded_paint_order_candidate"]
        self.assertEqual(metrics["false_visibility_count"], 0)
        self.assertTrue(metrics["zero_hard_control_false_visibility"])
        self.assertEqual(metrics["precision"], 1.0)

    def test_precision_coverage_runtime_recorded(self):
        """Criterion: precision/coverage/runtime recorded."""
        self.assertIn("runtime_seconds", self.result)
        self.assertGreater(self.result["runtime_seconds"], 0.0)
        self.assertIn("metrics", self.result)
        self.assertIn("method_runtimes_seconds", self.result)
        for key in ("metadata_baseline", "rectangular_ink_heuristic", "bounded_paint_order_candidate"):
            m = self.result["metrics"][key]
            self.assertIn("precision", m)
            self.assertIn("coverage", m)
            self.assertIn("false_visibility_count", m)
            self.assertIn("runtime_seconds", m)
            self.assertGreater(m["runtime_seconds"], 0.0)

    def test_ink_counterexample_triggered(self):
        """Criterion: negative result / counterexample complete."""
        ink_metrics = self.result["metrics"]["rectangular_ink_heuristic"]
        self.assertTrue(ink_metrics["counterexample_triggered"])
        self.assertGreater(ink_metrics["false_visibility_count"], 0)

    def test_no_held_out_leakage(self):
        """Criterion: candidate gain measured without held-out leakage."""
        for ev in self.result["fixture_evaluations"]:
            self.assertTrue(ev["path"].startswith("fixtures/development/"))

    def test_source_bytes_immutable(self):
        """Invariant I01: source fixture bytes remain immutable."""
        for ev in self.result["fixture_evaluations"]:
            p = ROOT / ev["path"]
            actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(actual_sha, ev["sha256"], f"Source fixture mutated: {ev['path']}")

    def test_empty_manifest_fails_terminal(self):
        """Review counterexample: empty manifest must fail terminal."""
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            json.dump({"entries": []}, f)
            f.flush()
            with self.assertRaises(ValueError):
                p09_runner.run_experiment(Path(f.name), self.out_dir)

    def test_held_out_manifest_fails_terminal(self):
        """Review counterexample: held-out evaluation manifest must fail terminal."""
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            json.dump({"split": "evaluation", "entries": [{"path": "fixtures/development/paint-order-control.pdf"}]}, f)
            f.flush()
            with self.assertRaises(ValueError):
                p09_runner.run_experiment(Path(f.name), self.out_dir)

    def test_occlusion_geometry_computation(self):
        """Geometric occlusion accurately computes full, partial, and zero intersection."""
        text_box = [50.0, 100.0, 150.0, 120.0]  # width 100, height 20, area 2000
        # Fully enclosing rectangle
        full_rect = [40.0, 90.0, 160.0, 130.0]
        self.assertEqual(p09_runner.compute_rect_intersection(text_box, full_rect), 2000.0)

        # Half covering rectangle
        half_rect = [50.0, 100.0, 100.0, 120.0]  # width 50, height 20, area 1000
        self.assertEqual(p09_runner.compute_rect_intersection(text_box, half_rect), 1000.0)

        # Disjoint rectangle (corner of page)
        disjoint_rect = [0.0, 0.0, 20.0, 20.0]
        self.assertEqual(p09_runner.compute_rect_intersection(text_box, disjoint_rect), 0.0)

    def test_resolve_manifest_explicit_missing_fails(self):
        """Verify resolve_manifest raises FileNotFoundError on explicitly missing manifests."""
        with self.assertRaises(FileNotFoundError):
            p09_runner.resolve_manifest("/tmp/nonexistent_p09_dir/development.json")
        with self.assertRaises(FileNotFoundError):
            p09_runner.resolve_manifest("nonexistent_p09.json")
        # Documented defaults resolve
        self.assertTrue(p09_runner.resolve_manifest(None).is_file())
        self.assertTrue(p09_runner.resolve_manifest("evaluation/manifests/development.json").is_file())


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPaintOrderExperiment)
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
