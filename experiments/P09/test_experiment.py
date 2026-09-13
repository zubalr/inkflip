"""Test suite for P09 paint-order and ink-counterexample experiment (T41, TEST-41).

Verifies acceptance criteria:
- Zero hard-control false visibility
- precision/coverage/runtime recorded
- candidate gain measured without held-out leakage
- negative result is complete
- source bytes preserved immutable (I01)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
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
        for key in ("metadata_baseline", "rectangular_ink_heuristic", "bounded_paint_order_candidate"):
            m = self.result["metrics"][key]
            self.assertIn("precision", m)
            self.assertIn("coverage", m)
            self.assertIn("false_visibility_count", m)

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
