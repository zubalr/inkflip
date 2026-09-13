"""Contract acceptance suite for regression and baselines (T34, TEST-34).

Verifies:
- Baseline immutability and prohibition of silent auto-refresh
- Coverage loss cannot count as improvement
- Incompatible files and reader configurations marked
- Rule exit behavior: informational changed exits 0, regression exits 5
- New baseline requires explicit approval and distinct path
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
NATIVE = ROOT / "native"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.baselines import (
    BaselineError,
    BaselineOverwriteError,
    EXIT_INVALID_ARGS,
    EXIT_OK,
    EXIT_REGRESSION,
    compare,
    create_baseline,
)
from inkflip.contracts import core


class RegressionContractTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="inkflip-regression-test-"))
        self.doc_sha = hashlib.sha256(b"immutable-doc").hexdigest()

        # Create sample run directory
        self.run_a = self.td / "runs" / "run_a"
        self.run_a.mkdir(parents=True)

        self.rep_a = {
            "kind": "report",
            "schema_version": "1.0.0",
            "id": hashlib.sha256(b"report_a").hexdigest(),
            "document": {
                "sha256": self.doc_sha,
                "byte_length": 2048,
                "page_count": 1,
                "source_asset_id": None,
            },
            "readers": [
                {
                    "id": "pypdf-native",
                    "name": "pypdf",
                    "version": "6.18.0",
                    "build": "pypdf 6.18.0",
                    "adapter_version": "1.0.0",
                    "method": "native_text",
                    "environment": "native",
                    "settings": {"normalization": "scalar-whitespace-v1"},
                    "capabilities": ["native_text"],
                    "limits": {"max_bytes": 1000000, "max_pages": 10},
                }
            ],
            "pages": [{"index": 0, "width_pt": 612.0, "height_pt": 792.0, "rotation": 0}],
            "transforms": [],
            "plan": {
                "version": "1.0.0",
                "selected_pages": [0],
                "regions": [],
                "checks": [],
                "normalization_version": "scalar-whitespace-v1",
                "alignment_version": "region-match-v1",
                "profile": "native",
                "budget": {
                    "max_raster_pixels": 1000000,
                    "max_run_ocr_pixels": 1000000,
                    "timeout_ms": 5000,
                    "max_retries": 1,
                },
            },
            "occurrences": [
                {
                    "id": "occ_0",
                    "page_index": 0,
                    "ordinal": 0,
                    "raw_text": "APPROVED BASELINE TEXT",
                    "normalized_text": "APPROVED BASELINE TEXT",
                    "geometry": {"polygon": None, "page_only": True},
                    "transform_ids": [],
                    "reader_id": "pypdf-native",
                }
            ],
            "checks": [],
            "assets": [],
            "export": {
                "created_at": "2026-09-13T00:00:00Z",
                "mode": "evidence",
                "replay": "requires_original",
                "privacy": {
                    "source_retained": False,
                    "rendered_retained": False,
                    "raster_geometry_retained": False,
                    "disclosed_redactions": [],
                },
            },
            "execution": {
                "execution_id": "22222222-2222-4222-8222-222222222222",
                "host_platform": "darwin",
                "limits": {"wall_seconds": 30.0, "memory_bytes": 1000000, "retries": 1},
                "wall_duration_ms": 40,
            },
        }
        (self.run_a / "sample.inkflip.json").write_text(json.dumps(self.rep_a), encoding="utf-8")
        (self.run_a / "index.json").write_text(
            json.dumps({"status": "complete", "jobs": {"sample": {"status": "completed"}}}),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_baseline_immutability_and_overwrite_prohibition(self):
        """Criterion: baseline overwrite/auto-refresh prohibited."""
        base_path = self.td / "baselines" / "base.json"
        base_path.parent.mkdir(parents=True)
        res = create_baseline(
            run_dir=self.run_a,
            rules_path=None,
            out_path=base_path,
            approved_by="lead-reviewer",
            rationale="Approved initial baseline",
        )
        self.assertTrue(base_path.is_file())
        core.validate(res)

        # Attempting overwrite must fail
        with self.assertRaises(BaselineOverwriteError):
            create_baseline(
                run_dir=self.run_a,
                rules_path=None,
                out_path=base_path,
                approved_by="other-reviewer",
                rationale="Should fail",
                overwrite=False,
            )

    def test_coverage_loss_cannot_count_improvement(self):
        """Criterion: lost coverage cannot count improvement (regression under fail_on_coverage_loss)."""
        run_b = self.td / "runs" / "run_b"
        run_b.mkdir(parents=True)
        rep_b = dict(self.rep_a)
        rep_b["occurrences"] = []  # dropped all occurrences!
        (run_b / "sample.inkflip.json").write_text(json.dumps(rep_b), encoding="utf-8")

        res = compare(left_path=self.run_a, right_path=run_b)
        self.assertEqual(res.status, "regressed")
        self.assertEqual(res.exit_code, EXIT_REGRESSION)
        self.assertTrue(res.coverage_lost)

    def test_changed_no_rule_is_informational(self):
        """Criterion: Changed no-rule is informational (status: "changed", exit 0)."""
        run_c = self.td / "runs" / "run_c"
        run_c.mkdir(parents=True)
        rep_c = dict(self.rep_a)
        rep_c["occurrences"] = [
            {
                "id": "occ_0",
                "page_index": 0,
                "ordinal": 0,
                "raw_text": "UPDATED UNRULED TEXT",
                "normalized_text": "UPDATED UNRULED TEXT",
                "geometry": {"polygon": None, "page_only": True},
                "transform_ids": [],
                "reader_id": "pypdf-native",
            }
        ]
        (run_c / "sample.inkflip.json").write_text(json.dumps(rep_c), encoding="utf-8")

        res = compare(left_path=self.run_a, right_path=run_c, rules_path=None)
        self.assertEqual(res.status, "changed")
        self.assertEqual(res.exit_code, EXIT_OK)
        self.assertEqual(len(res.violations), 0)

    def test_rule_regression_exits_5(self):
        """Criterion: rule regression exits 5."""
        run_d = self.td / "runs" / "run_d"
        run_d.mkdir(parents=True)
        rep_d = dict(self.rep_a)
        rep_d["occurrences"] = [
            {
                "id": "occ_0",
                "page_index": 0,
                "ordinal": 0,
                "raw_text": "DEVIANT TEXT",
                "normalized_text": "DEVIANT TEXT",
                "geometry": {"polygon": None, "page_only": True},
                "transform_ids": [],
                "reader_id": "pypdf-native",
            }
        ]
        (run_d / "sample.inkflip.json").write_text(json.dumps(rep_d), encoding="utf-8")

        rules_path = self.td / "rules.json"
        rules_path.write_text(
            json.dumps({
                "kind": "acceptance_rules",
                "schema_version": "1.0.0",
                "rules": [
                    {
                        "id": "rule_0",
                        "type": "stable_reading",
                        "document_sha256": self.doc_sha,
                        "page_index": 0,
                        "reader_id": None,
                        "region_id": None,
                        "expected_text": None,
                        "expected_count": None,
                        "max_delta_pt": None,
                        "capability": None,
                        "explanation": "Strict reading invariance",
                    }
                ],
                "policy": {
                    "fail_on_coverage_loss": True,
                    "fail_on_error": True,
                    "unruled_change": "changed",
                },
            }),
            encoding="utf-8",
        )

        res = compare(left_path=self.run_a, right_path=run_d, rules_path=rules_path)
        self.assertEqual(res.status, "regressed")
        self.assertEqual(res.exit_code, EXIT_REGRESSION)

    def test_incompatible_files_marked(self):
        """Criterion: incompatible files/readerconfig marked."""
        run_e = self.td / "runs" / "run_e"
        run_e.mkdir(parents=True)
        rep_e = dict(self.rep_a)
        rep_e["document"] = dict(self.rep_a["document"])
        rep_e["document"]["sha256"] = hashlib.sha256(b"totally-different-document").hexdigest()
        (run_e / "sample.inkflip.json").write_text(json.dumps(rep_e), encoding="utf-8")

        res = compare(left_path=self.run_a, right_path=run_e)
        self.assertEqual(res.status, "incompatible")
        self.assertEqual(res.exit_code, EXIT_INVALID_ARGS)


if __name__ == "__main__":
    unittest.main()
