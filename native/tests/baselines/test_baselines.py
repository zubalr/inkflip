"""Tests for stored-run comparison, rules, and immutable baselines (T34, TEST-34).

Acceptance criteria:
- Changed no-rule is informational (status: "changed", exit 0)
- Rule regression exits 5 (status: "regressed")
- Lost coverage cannot count improvement (regression under fail_on_coverage_loss)
- Incompatible files/readerconfig marked (status: "incompatible")
- Baseline overwrite/auto-refresh prohibited (BaselineOverwriteError)
- New baseline requires explicit approval and new path
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

ROOT = Path(__file__).resolve().parents[3]
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
from inkflip.cli.main import main as cli_main
from inkflip.contracts import core


class TestBaselinesAndRegression(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="test-baselines-"))
        self.run_dir = self.td / "runs" / "run1"
        self.run_dir.mkdir(parents=True)

        self.doc_sha = hashlib.sha256(b"fake-pdf-content").hexdigest()

        # Write a sample report
        self.report1 = {
            "kind": "report",
            "schema_version": "1.0.0",
            "id": hashlib.sha256(b"rep1").hexdigest(),
            "document": {
                "sha256": self.doc_sha,
                "byte_length": 1024,
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
                    "id": "occ_1",
                    "page_index": 0,
                    "ordinal": 0,
                    "raw_text": "Baseline Text Content",
                    "normalized_text": "Baseline Text Content",
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
                "execution_id": "11111111-1111-4111-8111-111111111111",
                "host_platform": "darwin",
                "limits": {"wall_seconds": 30.0, "memory_bytes": 1000000, "retries": 1},
                "wall_duration_ms": 50,
            },
        }

        self.rep_file = self.run_dir / "doc1.inkflip.json"
        self.rep_file.write_text(json.dumps(self.report1, indent=2), encoding="utf-8")

        # Write index.json
        self.index_data = {
            "kind": "run_index",
            "schema_version": "1.0.0",
            "run_id": "run-001",
            "status": "complete",
            "started_at": "2026-09-13T00:00:00Z",
            "ended_at": "2026-09-13T00:00:01Z",
            "platform": "darwin",
            "rlimit_support": True,
            "limits": {"wall_seconds": 30.0, "memory_bytes": 1000000, "retries": 1, "jobs": 1},
            "jobs": {
                "doc1": {
                    "key": "doc1",
                    "status": "completed",
                    "attempts": 1,
                    "config_digest": "cfg-1",
                }
            },
        }
        (self.run_dir / "index.json").write_text(json.dumps(self.index_data, indent=2), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_baseline_creation_and_schema_validation(self):
        """Criterion: new baseline requires explicit approval and new path."""
        baseline_out = self.td / "baselines" / "base1.json"
        res = create_baseline(
            run_dir=self.run_dir,
            rules_path=None,
            out_path=baseline_out,
            approved_by="local-reviewer",
            rationale="Approved standard baseline for pypdf 6.18.0",
        )
        self.assertTrue(baseline_out.is_file())
        self.assertEqual(res["kind"], "baseline")
        self.assertEqual(res["approved_by"], "local-reviewer")
        self.assertEqual(len(res["report_ids"]), 1)
        # Verify schema validity
        core.validate(res)

    def test_baseline_overwrite_prohibited(self):
        """Criterion: baseline overwrite/auto-refresh prohibited."""
        baseline_out = self.td / "base_existing.json"
        baseline_out.write_text("{}", encoding="utf-8")

        with self.assertRaises(BaselineOverwriteError):
            create_baseline(
                run_dir=self.run_dir,
                rules_path=None,
                out_path=baseline_out,
                approved_by="reviewer",
                rationale="Rationale",
                overwrite=False,
            )

    def test_baseline_requires_explicit_approval_and_rationale(self):
        """Missing approved_by or rationale raises BaselineError."""
        out = self.td / "base_missing_auth.json"
        with self.assertRaises(BaselineError):
            create_baseline(
                run_dir=self.run_dir,
                rules_path=None,
                out_path=out,
                approved_by="",
                rationale="Some rationale",
            )
        with self.assertRaises(BaselineError):
            create_baseline(
                run_dir=self.run_dir,
                rules_path=None,
                out_path=out,
                approved_by="reviewer",
                rationale="",
            )

    def test_baseline_rejects_incomplete_run(self):
        """Incomplete or invalid runs rejected unless explicit diagnostic override."""
        incomplete_dir = self.td / "incomplete_run"
        incomplete_dir.mkdir()
        (incomplete_dir / "index.json").write_text(
            json.dumps({"status": "partial", "jobs": {}}), encoding="utf-8"
        )
        (incomplete_dir / "doc1.inkflip.json").write_text(json.dumps(self.report1), encoding="utf-8")

        with self.assertRaises(BaselineError):
            create_baseline(
                run_dir=incomplete_dir,
                rules_path=None,
                out_path=self.td / "base_fail.json",
                approved_by="reviewer",
                rationale="Should fail",
            )

    def test_changed_no_rule_is_informational(self):
        """Criterion: Changed no-rule is informational (status: "changed", exit 0)."""
        run2_dir = self.td / "runs" / "run2"
        run2_dir.mkdir(parents=True)
        rep2 = dict(self.report1)
        rep2["occurrences"] = [
            {
                "id": "occ_1",
                "page_index": 0,
                "ordinal": 0,
                "raw_text": "Different Text Without Rules",
                "normalized_text": "Different Text Without Rules",
                "geometry": {"polygon": None, "page_only": True},
                "transform_ids": [],
                "reader_id": "pypdf-native",
            }
        ]
        (run2_dir / "doc1.inkflip.json").write_text(json.dumps(rep2), encoding="utf-8")

        result = compare(left_path=self.run_dir, right_path=run2_dir, rules_path=None)
        self.assertEqual(result.status, "changed")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(len(result.changes), 1)
        self.assertEqual(len(result.violations), 0)

    def test_rule_regression_exits_5(self):
        """Criterion: rule regression exits 5."""
        run2_dir = self.td / "runs" / "run_regressed"
        run2_dir.mkdir(parents=True)
        rep2 = dict(self.report1)
        rep2["occurrences"] = [
            {
                "id": "occ_1",
                "page_index": 0,
                "ordinal": 0,
                "raw_text": "Candidate Changed Text",
                "normalized_text": "Candidate Changed Text",
                "geometry": {"polygon": None, "page_only": True},
                "transform_ids": [],
                "reader_id": "pypdf-native",
            }
        ]
        (run2_dir / "doc1.inkflip.json").write_text(json.dumps(rep2), encoding="utf-8")

        rules_file = self.td / "upgrade_rules.json"
        rules_data = {
            "kind": "acceptance_rules",
            "schema_version": "1.0.0",
            "rules": [
                {
                    "id": "rule_stable_0",
                    "type": "stable_reading",
                    "document_sha256": self.doc_sha,
                    "page_index": 0,
                    "reader_id": None,
                    "region_id": None,
                    "expected_text": None,
                    "expected_count": None,
                    "max_delta_pt": None,
                    "capability": None,
                    "explanation": "Do not allow reading to change on page 0",
                }
            ],
            "policy": {
                "fail_on_coverage_loss": True,
                "fail_on_error": True,
                "unruled_change": "changed",
            },
        }
        rules_file.write_text(json.dumps(rules_data, indent=2), encoding="utf-8")

        result = compare(left_path=self.run_dir, right_path=run2_dir, rules_path=rules_file)
        self.assertEqual(result.status, "regressed")
        self.assertEqual(result.exit_code, EXIT_REGRESSION)
        self.assertTrue(len(result.violations) > 0)
        self.assertIn("stable_reading", result.violations[0])

    def test_lost_coverage_cannot_count_improvement(self):
        """Criterion: lost coverage cannot count improvement (regression under fail_on_coverage_loss)."""
        run_empty_dir = self.td / "runs" / "run_empty"
        run_empty_dir.mkdir(parents=True)
        rep_empty = dict(self.report1)
        rep_empty["occurrences"] = []  # 0 occurrences, coverage lost!
        (run_empty_dir / "doc1.inkflip.json").write_text(json.dumps(rep_empty), encoding="utf-8")

        result = compare(left_path=self.run_dir, right_path=run_empty_dir, rules_path=None)
        self.assertEqual(result.status, "regressed")
        self.assertEqual(result.exit_code, EXIT_REGRESSION)
        self.assertTrue(result.coverage_lost)

    def test_incompatible_files_or_readerconfig_marked(self):
        """Criterion: incompatible files/readerconfig marked (status: "incompatible")."""
        run_diff_doc = self.td / "runs" / "diff_doc"
        run_diff_doc.mkdir(parents=True)
        rep_diff = dict(self.report1)
        rep_diff["document"] = dict(self.report1["document"])
        rep_diff["document"]["sha256"] = hashlib.sha256(b"different-doc").hexdigest()
        (run_diff_doc / "doc1.inkflip.json").write_text(json.dumps(rep_diff), encoding="utf-8")

        result = compare(left_path=self.run_dir, right_path=run_diff_doc)
        self.assertEqual(result.status, "incompatible")
        self.assertEqual(result.exit_code, EXIT_INVALID_ARGS)

    def test_cli_baseline_create_and_compare(self):
        """Test full CLI baseline create and compare invocations."""
        base_path = self.td / "baselines" / "run1.json"
        code = cli_main([
            "baseline", "create",
            "--run", str(self.run_dir),
            "--out", str(base_path),
            "--approved-by", "cli-tester",
            "--rationale", "Testing CLI baseline creation",
        ])
        self.assertEqual(code, 0)
        self.assertTrue(base_path.is_file())

        # Test CLI compare (identical runs -> unchanged, exit 0)
        comp_code = cli_main([
            "compare",
            str(base_path),
            str(self.run_dir),
        ])
        self.assertEqual(comp_code, 0)


if __name__ == "__main__":
    unittest.main()
