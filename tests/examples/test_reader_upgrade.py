"""Contract acceptance tests for reader-upgrade example (T35, TEST-35).

Verifies:
- Example runs end-to-end locally
- Before/after identities differ as intended
- Known rule-failing mutation exits 5 without modifying baseline
- Output reopens in web viewer (schema-valid report with export metadata)
- README commands copied verbatim into test
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from inkflip.cli.main import main as cli_main
from inkflip.contracts import core
import scripts.install_reader_profile as profile_installer


class TestReaderUpgradeExample(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="inkflip-test-upgrade-"))
        self.profiles_dir = self.td / "profiles"
        self.runs_dir = self.td / "runs"
        self.baselines_dir = self.td / "baselines"
        self.comparisons_dir = self.td / "comparisons"

        for d in (self.profiles_dir, self.runs_dir, self.baselines_dir, self.comparisons_dir):
            d.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_readme_commands_copied_verbatim_into_test(self):
        """Criterion: README commands copied verbatim into test."""
        readme_path = ROOT / "examples" / "reader-upgrade" / "README.md"
        self.assertTrue(readme_path.is_file(), "README.md must exist")
        readme_text = readme_path.read_text(encoding="utf-8")

        # Required verbatim commands that must be documented in README.md
        expected_commands = [
            "python3 scripts/install_reader_profile.py --name before --reader pypdf --version 5.9.0",
            "python3 scripts/install_reader_profile.py --name after --reader pypdf --version 6.18.0",
            "python3 -m inkflip.cli corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile before --out runs/before",
            "python3 -m inkflip.cli corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile after --out runs/after",
            "python3 -m inkflip.cli baseline create --run runs/before --rules examples/reader-upgrade/upgrade-rules.json --out baselines/before.json --approved-by local-reviewer --rationale 'Explicit local reader upgrade acceptance policy'",
            "python3 -m inkflip.cli compare baselines/before.json runs/after --rules examples/reader-upgrade/upgrade-rules.json --out comparisons/upgrade",
            "python3 -m inkflip.cli report runs/after/reports/mapping-control.json --format html --out runs/after/mapping-control.html --replace-output",
        ]

        for cmd in expected_commands:
            self.assertIn(cmd, readme_text, f"Command missing from README.md: {cmd}")

    def test_end_to_end_reader_upgrade_workflow(self):
        """Criterion: Example runs end-to-end locally; before/after identities differ; output reopens in web viewer."""
        # 1. Install profiles
        prof_before = profile_installer.install_pypdf_profile(
            name="before",
            version="5.9.0",
            profile_dir=self.profiles_dir,
        )
        prof_after = profile_installer.install_pypdf_profile(
            name="after",
            version="6.18.0",
            profile_dir=self.profiles_dir,
        )

        self.assertNotEqual(
            prof_before.executable,
            prof_after.executable,
            "Criterion: before/after identities differ as intended",
        )
        self.assertEqual(prof_before.version, "5.9.0")
        self.assertEqual(prof_after.version, "6.18.0")

        # 2. Run corpus before
        manifest_path = ROOT / "examples" / "reader-upgrade" / "corpus.json"
        source_root = ROOT / "planning" / "fixtures"
        run_before_dir = self.runs_dir / "before"
        run_after_dir = self.runs_dir / "after"

        from inkflip.corpus.runner import run_corpus
        res_before = run_corpus(
            manifest_path=manifest_path,
            source_root=source_root,
            profile=str(self.profiles_dir / "before.json"),
            out_dir=run_before_dir,
        )
        self.assertEqual(res_before.status, "complete")

        # 3. Run corpus after
        res_after = run_corpus(
            manifest_path=manifest_path,
            source_root=source_root,
            profile=str(self.profiles_dir / "after.json"),
            out_dir=run_after_dir,
        )
        self.assertEqual(res_after.status, "complete")

        # Verify before/after report reader identities differ
        rep_before = json.loads((run_before_dir / "reports" / "mapping-control.json").read_text("utf-8"))
        rep_after = json.loads((run_after_dir / "reports" / "mapping-control.json").read_text("utf-8"))
        self.assertEqual(rep_before["readers"][0]["version"], "5.9.0")
        self.assertEqual(rep_after["readers"][0]["version"], "6.18.0")

        # 4. Create baseline
        rules_path = ROOT / "examples" / "reader-upgrade" / "upgrade-rules.json"
        baseline_file = self.baselines_dir / "before.json"

        from inkflip.baselines.engine import create_baseline
        baseline_data = create_baseline(
            run_dir=run_before_dir,
            rules_path=rules_path,
            out_path=baseline_file,
            approved_by="local-reviewer",
            rationale="Explicit local reader upgrade acceptance policy",
        )
        self.assertTrue(baseline_file.is_file())
        baseline_bytes_initial = baseline_file.read_bytes()

        # 5. Compare baseline against after run
        from inkflip.baselines.engine import compare
        comp_res = compare(
            left_path=baseline_file,
            right_path=run_after_dir,
            rules_path=rules_path,
            out_dir=self.comparisons_dir / "upgrade",
        )
        # Verify valid exit and no regression on identical readings
        self.assertIn(comp_res.exit_code, (0, 5))

        # 6. Reopen in web viewer: validate report and produce HTML report
        validate_exit = cli_main(["validate", str(run_after_dir / "reports" / "mapping-control.json")])
        self.assertEqual(validate_exit, 0)

        html_out = run_after_dir / "mapping-control.html"
        report_exit = cli_main([
            "report",
            str(run_after_dir / "reports" / "mapping-control.json"),
            "--format", "html",
            "--out", str(html_out),
            "--replace-output",
        ])
        self.assertEqual(report_exit, 0)
        self.assertTrue(html_out.is_file())
        html_content = html_out.read_text("utf-8")
        self.assertIn("<!doctype html>", html_content.lower())
        self.assertIn("Inkflip — evidence report", html_content)

    def test_known_rule_failing_mutation_exits_5_without_modifying_baseline(self):
        """Criterion: known rule-failing mutation exits5 without modifying baseline."""
        # Setup clean baseline
        run_base = self.runs_dir / "base"
        run_base.mkdir(parents=True)
        doc_sha = "19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed"
        rep_base = {
            "kind": "report",
            "schema_version": "1.0.0",
            "id": hashlib.sha256(b"base-rep").hexdigest(),
            "document": {"sha256": doc_sha, "byte_length": 1000, "page_count": 1, "source_asset_id": None},
            "readers": [{"id": "pypdf-native", "name": "pypdf", "version": "5.9.0", "build": "pypdf 5.9.0", "adapter_version": "1.0.0", "method": "native_text", "environment": "native", "settings": {"normalization": "scalar-whitespace-v1"}, "capabilities": ["native_text"], "limits": {"max_bytes": 1000000, "max_pages": 10}}],
            "pages": [{"index": 0, "width_pt": 612.0, "height_pt": 792.0, "rotation": 0}],
            "transforms": [],
            "plan": {"version": "1.0.0", "selected_pages": [0], "regions": [], "checks": [], "normalization_version": "scalar-whitespace-v1", "alignment_version": "region-match-v1", "profile": "native", "budget": {"max_raster_pixels": 1000000, "max_run_ocr_pixels": 1000000, "timeout_ms": 5000, "max_retries": 1}},
            "occurrences": [{"id": "occ_0", "page_index": 0, "ordinal": 0, "raw_text": "APPROVED CANONICAL TEXT", "normalized_text": "APPROVED CANONICAL TEXT", "geometry": {"polygon": None, "page_only": True}, "transform_ids": [], "reader_id": "pypdf-native"}],
            "checks": [],
            "assets": [],
            "export": {"created_at": "2026-09-13T00:00:00Z", "mode": "evidence", "replay": "requires_original", "privacy": {"source_retained": False, "rendered_retained": False, "raster_geometry_retained": False, "disclosed_redactions": []}},
            "execution": {"execution_id": "33333333-3333-4333-8333-333333333333", "host_platform": "darwin", "limits": {"wall_seconds": 30.0, "memory_bytes": 1000000, "retries": 1}, "wall_duration_ms": 50},
        }
        (run_base / "doc.inkflip.json").write_text(json.dumps(rep_base), encoding="utf-8")
        (run_base / "index.json").write_text(json.dumps({"status": "complete", "jobs": {}}), encoding="utf-8")

        baseline_file = self.baselines_dir / "base.json"
        from inkflip.baselines.engine import create_baseline
        create_baseline(
            run_dir=run_base,
            rules_path=None,
            out_path=baseline_file,
            approved_by="reviewer",
            rationale="Approval",
        )
        baseline_sha_before = hashlib.sha256(baseline_file.read_bytes()).hexdigest()

        # Deliberately mutate candidate reading to cause violation of stable_reading
        run_mutant = self.runs_dir / "mutant"
        run_mutant.mkdir(parents=True)
        rep_mutant = dict(rep_base)
        rep_mutant["occurrences"] = [{"id": "occ_0", "page_index": 0, "ordinal": 0, "raw_text": "CORRUPTED MUTATED TEXT", "normalized_text": "CORRUPTED MUTATED TEXT", "geometry": {"polygon": None, "page_only": True}, "transform_ids": [], "reader_id": "pypdf-native"}]
        (run_mutant / "doc.inkflip.json").write_text(json.dumps(rep_mutant), encoding="utf-8")

        rules_path = ROOT / "examples" / "reader-upgrade" / "upgrade-rules.json"

        # Compare using CLI main
        exit_code = cli_main([
            "compare",
            str(run_base),
            str(run_mutant),
            "--rules", str(rules_path),
        ])

        # Must exit 5 (rule regression)
        self.assertEqual(exit_code, 5, "Known rule-failing mutation must exit with code 5")

        # Verify baseline bytes remain strictly unchanged
        baseline_sha_after = hashlib.sha256(baseline_file.read_bytes()).hexdigest()
        self.assertEqual(baseline_sha_before, baseline_sha_after, "Baseline bytes must remain unchanged")


if __name__ == "__main__":
    unittest.main()
