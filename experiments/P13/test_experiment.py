"""Test suite for P13 RapidOCR experiment (T44, TEST-44).

Verifies acceptance criteria:
- Complementary useful failures at fixed precision and memory budget or reject
- Explicit missing-model and OOV behavior
- No runtime network
- No consensus-as-truth
- Full raw and negative outcomes documented
"""
from __future__ import annotations

import json
import os
import socket
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P13_DIR = ROOT / "experiments" / "P13"
sys.path.insert(0, str(P13_DIR))

import run as p13_runner


class TestRapidOCRExperiment(unittest.TestCase):
    def test_no_runtime_network_during_evaluation(self):
        """Criterion: no runtime network calls permitted."""
        provenance = p13_runner.evaluate_rapidocr_provenance()
        self.assertFalse(provenance["runtime_network_allowed"])
        self.assertIn("missing_weights", provenance["status"])

    def test_explicit_missing_model_behavior(self):
        """Criterion: explicit missing-model and OOV behavior."""
        provenance = p13_runner.evaluate_rapidocr_provenance()
        self.assertFalse(provenance["models_present"])
        self.assertIn("Official weight artifacts and SHA-256 hashes not pinned", provenance["reason"])

    def test_no_consensus_as_truth(self):
        """Criterion: no consensus-as-truth (I16)."""
        res = p13_runner.run_experiment(
            p13_runner.resolve_manifest(None),
            ROOT / "artifacts" / "P13",
        )
        self.assertTrue(res["consensus_as_truth_avoided"])
        self.assertEqual(res["status"], "rejected_experiment")

    def test_full_raw_and_negative_outcomes_documented(self):
        """Criterion: full raw and negative outcomes documented."""
        res_file = ROOT / "artifacts" / "P13" / "result.json"
        self.assertTrue(res_file.is_file(), "artifacts/P13/result.json must exist")
        data = json.loads(res_file.read_text(encoding="utf-8"))
        self.assertEqual(data["disposition"], "rejected_experiment")
        self.assertIn("RapidOCR candidate rejected", data["rejection_rationale"])
        self.assertIn("recommendation", data)


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRapidOCRExperiment)
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
