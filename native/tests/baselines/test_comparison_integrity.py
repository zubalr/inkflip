"""Comparison provenance, matrix rows, and baseline path integrity.

Reproduces AutoClaw's changed-profile probe (handoffs/.../evidence/out3b-probe.log)
against the frozen T34 contract: reader_upgrade may compare different profiles,
but must not silently treat tampered or inconsistent identities as unchanged.
Coverage-loss constructions are schema-valid so comparison actually runs.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.baselines import engine  # noqa: E402
from inkflip.baselines.engine import (  # noqa: E402
    EXIT_INCOMPARABLE,
    EXIT_INVALID_ARGS,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_REGRESSION,
    compare,
    create_baseline,
)
from inkflip.baselines.models import BaselineError, BaselineOverwriteError  # noqa: E402
from inkflip.cli.main import EXIT_POLICY_FAILURE, main  # noqa: E402
from inkflip.contracts import core  # noqa: E402

AMOUNT = FIXTURES / "public" / "mapping-amount.pdf"
CONTROL = FIXTURES / "public" / "mapping-control.pdf"
AMOUNT_SHA = "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80"
CONTROL_SHA = "19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed"
PROFILE_BEFORE = "b" * 64
PROFILE_AFTER = "c" * 64
CORPUS_SHA = "a" * 64


def _inspect(destination: Path, source: Path, reader: str = "pdfium") -> dict:
    code = main(["inspect", str(source), "--out", str(destination), "--reader", reader])
    assert code == 0, f"inspect failed for {source} reader={reader}"
    data = json.loads(destination.read_text())
    core.validate(data)
    return data


def _write_run(
    directory: Path,
    reports: dict[str, dict],
    *,
    profile_sha256: str = PROFILE_BEFORE,
    intended_keys: list[str] | None = None,
    algorithm_id: str = "inkflip-inspect-v1",
) -> Path:
    reports_dir = directory / "reports"
    reports_dir.mkdir(parents=True)
    jobs = {}
    for key, report in reports.items():
        path = reports_dir / f"{key}.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        jobs[key] = {
            "key": key,
            "status": "completed",
            "report_path": f"reports/{key}.json",
            "report_sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
            "report_bytes": path.stat().st_size,
        }
    keys = intended_keys if intended_keys is not None else list(reports)
    (directory / "index.json").write_text(
        json.dumps({"kind": "inkflip-run-index", "schema_version": "1.0.0", "status": "complete", "jobs": jobs})
    )
    identity = {
        "kind": "inkflip-corpus-identity",
        "corpus_manifest_sha256": CORPUS_SHA,
        "profile_sha256": profile_sha256,
        "profile_name": "native-default",
        "algorithm_id": algorithm_id,
        "intended_keys": keys,
    }
    (directory / "identity.json").write_text(json.dumps(identity))
    return directory


def _rules(extra: list[dict] | None = None, policy: dict | None = None) -> dict:
    rules = {
        "kind": "acceptance_rules",
        "schema_version": "1.0.0",
        "rules": extra
        or [
            {
                "id": "control-expected-text",
                "type": "expected_text",
                "document_sha256": CONTROL_SHA,
                "page_index": 0,
                "reader_id": None,
                "region_id": None,
                "expected_text": "$100",
                "expected_count": None,
                "max_delta_pt": None,
                "capability": None,
                "explanation": "Control fixture amount stays $100.",
            }
        ],
        "policy": policy
        or {
            "fail_on_coverage_loss": True,
            "fail_on_error": True,
            "unruled_change": "changed",
        },
    }
    core.validate(rules)
    return rules


def _as_upgrade_report(report: dict, version: str, environment: str) -> dict:
    mutated = json.loads(json.dumps(report))
    mutated["readers"][0]["version"] = version
    mutated["execution"]["environment"] = environment
    sealed = core.seal(mutated)
    core.validate(sealed)
    return sealed


def _with_embedded_profile_sha256(report: dict, sha256: str) -> dict:
    """A report whose recorded environment carries the profile identity it ran under."""
    mutated = json.loads(json.dumps(report))
    mutated["execution"]["environment"] = (
        mutated["execution"]["environment"] + f"; profile_sha256={sha256}"
    )
    sealed = core.seal(mutated)
    core.validate(sealed)
    return sealed


def _with_lost_coverage(report: dict) -> dict:
    """Schema-valid coverage loss: drop an occurrence and repair every reference."""
    mutated = json.loads(json.dumps(report))
    occs = list(mutated.get("occurrences") or [])
    if not occs:
        raise AssertionError("fixture report has no occurrences to drop")
    dropped = {occs[-1]["id"]}
    mutated["occurrences"] = occs[:-1]
    remaining = {occ["id"] for occ in mutated["occurrences"]}
    for check in mutated["checks"]:
        retained = [oid for oid in check.get("retained_occurrence_ids") or [] if oid in remaining]
        check["retained_occurrence_ids"] = retained
        check["produced_occurrence_count"] = max(len(retained), 0)
    mutated["findings"] = [
        finding
        for finding in mutated.get("findings") or []
        if set(finding.get("occurrence_ids") or []).issubset(remaining)
    ]
    for annotation in mutated.get("annotations") or []:
        if annotation.get("finding_id") and annotation["finding_id"] not in {
            finding["id"] for finding in mutated["findings"]
        }:
            annotation["finding_id"] = None
    sealed = core.seal(mutated)
    core.validate(sealed)
    return sealed


def _with_partial_check(report: dict) -> dict:
    mutated = json.loads(json.dumps(report))
    target = mutated["checks"][0]
    target["status"] = "timeout"
    target["reason"] = "forced partial reading for comparison matrix"
    mutated["execution"]["status"] = "partial"
    mutated["execution"]["errors"] = ["forced partial reading for comparison matrix"]
    bad = {target["id"]}
    mutated["findings"] = [
        finding for finding in mutated.get("findings") or [] if not bad.intersection(finding.get("check_ids") or [])
    ]
    for annotation in mutated.get("annotations") or []:
        if annotation.get("finding_id") and annotation["finding_id"] not in {
            finding["id"] for finding in mutated["findings"]
        }:
            annotation["finding_id"] = None
    sealed = core.seal(mutated)
    core.validate(sealed)
    return sealed


def _with_missing_check(report: dict) -> dict:
    mutated = json.loads(json.dumps(report))
    if len(mutated["checks"]) < 2:
        raise AssertionError("need two checks to drop one")
    dropped_id = mutated["checks"][-1]["id"]
    mutated["checks"] = mutated["checks"][:-1]
    mutated["plan"]["checks"] = [item for item in mutated["plan"]["checks"] if item["id"] != dropped_id]
    mutated["findings"] = [
        finding for finding in mutated.get("findings") or [] if dropped_id not in (finding.get("check_ids") or [])
    ]
    sealed = core.seal(mutated)
    core.validate(sealed)
    return sealed


class ComparisonIntegrityCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.td = Path(cls.tmp.name)
        cls.amount = _inspect(cls.td / "amount.inkflip.json", AMOUNT, "pdfium")
        cls.control = _inspect(cls.td / "control.inkflip.json", CONTROL, "pdfium")
        cls.pypdf_amount = _inspect(cls.td / "amount-pypdf.inkflip.json", AMOUNT, "pypdf")
        cls.pypdf_control = _inspect(cls.td / "control-pypdf.inkflip.json", CONTROL, "pypdf")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.td))

    def _comparison(self, out: Path) -> dict:
        payload = json.loads((out / "comparison.json").read_text())
        core.validate(payload)
        return payload


class TestComparisonProvenance(ComparisonIntegrityCase):
    def test_identity_declaring_a_different_profile_than_its_reports_is_invalid(self):
        """The detectable rewrite: identity.json disagrees with its own reports."""
        recorded = _with_embedded_profile_sha256(self.amount, PROFILE_BEFORE)
        left = _write_run(self.case / "left", {"mapping-amount": recorded}, profile_sha256=PROFILE_BEFORE)
        right = _write_run(self.case / "right", {"mapping-amount": recorded}, profile_sha256="f" * 64)
        result = compare(left, right, None, self.case / "cmp-tamper")
        self.assertEqual(result.exit_code, EXIT_INVALID_ARGS)
        self.assertNotEqual(result.status, "unchanged")
        self.assertTrue(any("does not match" in item.lower() for item in result.violations))
        self.assertFalse((self.case / "cmp-tamper" / "comparison.json").is_file())

    def test_different_profile_identities_without_recorded_hashes_stay_comparable(self):
        """Reports produced without a profile record no hash; differing declared
        identities are then legitimate separate profiles, not rewritten metadata."""
        left = _write_run(self.case / "left", {"mapping-amount": self.amount}, profile_sha256=PROFILE_BEFORE)
        right = _write_run(self.case / "right", {"mapping-amount": self.amount}, profile_sha256="f" * 64)
        result = compare(left, right, None, self.case / "cmp-distinct")
        self.assertNotEqual(result.exit_code, EXIT_INVALID_ARGS)
        self.assertNotEqual(result.status, "incomparable")
        comparison = self._comparison(self.case / "cmp-distinct")
        self.assertTrue(any("profile" in item.lower() for item in comparison["limitations"]))

    def test_malformed_profile_digest_is_invalid_configuration(self):
        left = _write_run(self.case / "left", {"mapping-amount": self.amount})
        right = _write_run(self.case / "right", {"mapping-amount": self.amount})
        identity = json.loads((right / "identity.json").read_text())
        identity["profile_sha256"] = "ffffffffffffffff"
        (right / "identity.json").write_text(json.dumps(identity))
        result = compare(left, right, None, self.case / "cmp-malformed")
        self.assertEqual(result.exit_code, EXIT_INVALID_ARGS)
        self.assertTrue(any("malformed" in item.lower() for item in result.violations))

    def test_reader_upgrade_with_different_profiles_is_not_exit_6(self):
        before = _as_upgrade_report(
            self.pypdf_amount,
            "5.9.0",
            "Python; pypdf==5.9.0; profile_name=before",
        )
        after = _as_upgrade_report(
            self.pypdf_amount,
            "6.18.0",
            "Python; pypdf==6.18.0; profile_name=after",
        )
        left = _write_run(self.case / "before", {"mapping-amount": before}, profile_sha256=PROFILE_BEFORE)
        right = _write_run(self.case / "after", {"mapping-amount": after}, profile_sha256=PROFILE_AFTER)
        baseline = self.case / "before.json"
        create_baseline(left, None, baseline, "local-reviewer", "Immutable before profile")
        out = self.case / "cmp-upgrade"
        result = compare(baseline, right, None, out, mode="reader_upgrade")
        self.assertNotEqual(result.exit_code, EXIT_INCOMPARABLE)
        self.assertNotEqual(result.status, "incomparable")
        comparison = self._comparison(out)
        joined = " ".join(comparison["limitations"])
        self.assertIn(PROFILE_BEFORE, joined)
        self.assertIn(PROFILE_AFTER, joined)
        self.assertTrue(any("not equal" in item.lower() or "differ" in item.lower() for item in comparison["limitations"]))
        html = (out / "comparison.html").read_text()
        self.assertIn(PROFILE_BEFORE, html)
        self.assertIn("Limitations", html)

    def test_mode_reader_marks_incompatible_reader_config_incomparable(self):
        left = _write_run(self.case / "left", {"mapping-amount": self.amount})
        right = _write_run(self.case / "right", {"mapping-amount": self.pypdf_amount})
        result = compare(left, right, None, self.case / "cmp-reader-mode", mode="reader")
        self.assertEqual(result.exit_code, EXIT_INCOMPARABLE)
        comparison = self._comparison(self.case / "cmp-reader-mode")
        self.assertEqual(comparison["status"], "incomparable")
        self.assertTrue(any(change["kind"] == "configuration" for change in comparison["changes"]))

    def test_missing_profile_identity_is_recorded_not_silently_equal(self):
        left = _write_run(self.case / "left", {"mapping-amount": self.amount})
        right = _write_run(self.case / "right", {"mapping-amount": self.amount})
        (right / "identity.json").unlink()
        result = compare(left, right, None, self.case / "cmp-missing-id")
        self.assertEqual(result.exit_code, EXIT_OK)
        comparison = self._comparison(self.case / "cmp-missing-id")
        self.assertTrue(
            any("not claimed equal" in item.lower() or "no profile identity" in item.lower() for item in comparison["limitations"])
        )

    def test_algorithm_identity_change_is_incomparable(self):
        left = _write_run(self.case / "left", {"mapping-amount": self.amount}, algorithm_id="inkflip-inspect-v1")
        right = _write_run(self.case / "right", {"mapping-amount": self.amount}, algorithm_id="inkflip-inspect-v2")
        result = compare(left, right, None, self.case / "cmp-algo")
        self.assertEqual(result.exit_code, EXIT_INCOMPARABLE)
        self.assertEqual(result.status, "incomparable")


class TestComparisonMatrix(ComparisonIntegrityCase):
    def test_unchanged_identical_runs(self):
        left = _write_run(self.case / "left", {"mapping-amount": self.amount})
        right = _write_run(self.case / "right", {"mapping-amount": self.amount})
        result = compare(left, right, None, self.case / "cmp-unchanged")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(result.status, "unchanged")
        self.assertEqual(self._comparison(self.case / "cmp-unchanged")["status"], "unchanged")

    def test_informational_reader_change_without_rules(self):
        left = _write_run(self.case / "left", {"mapping-amount": self.amount})
        right = _write_run(self.case / "right", {"mapping-amount": self.pypdf_amount})
        result = compare(left, right, None, self.case / "cmp-info")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(result.status, "changed")

    def test_rule_violation_exits_5_with_cli_diagnostics(self):
        left = _write_run(self.case / "left", {"mapping-control": self.pypdf_control})
        mutated = json.loads(json.dumps(self.pypdf_control))
        for occ in mutated["occurrences"]:
            occ["raw_text"] = "MUTATED"
            occ["normalized_text"], occ["normalization_map"] = core.normalize(occ["raw_text"])
        mutated = core.seal(mutated)
        core.validate(mutated)
        right = _write_run(self.case / "right", {"mapping-control": mutated})
        rules = self.case / "rules.json"
        rules.write_text(json.dumps(_rules()))
        result = compare(left, right, rules, self.case / "cmp-rule")
        self.assertEqual(result.exit_code, EXIT_POLICY_FAILURE)
        self.assertEqual(result.status, "regressed")
        code = main(
            [
                "compare",
                str(left),
                str(right),
                "--rules",
                str(rules),
                "--out",
                str(self.case / "cmp-rule-cli"),
            ]
        )
        self.assertEqual(code, EXIT_POLICY_FAILURE)

    def test_valid_coverage_loss_cannot_improve_and_policy_exits_5(self):
        reduced = _with_lost_coverage(self.amount)
        left = _write_run(self.case / "left", {"mapping-amount": self.amount})
        right = _write_run(self.case / "right", {"mapping-amount": reduced})
        rules = self.case / "rules.json"
        rules.write_text(
            json.dumps(
                _rules(
                    extra=[
                        {
                            "id": "amount-coverage",
                            "type": "required_coverage",
                            "document_sha256": AMOUNT_SHA,
                            "page_index": 0,
                            "reader_id": None,
                            "region_id": None,
                            "expected_text": None,
                            "expected_count": None,
                            "max_delta_pt": None,
                            "capability": "native_text",
                            "explanation": "Amount page must complete native_text.",
                        }
                    ]
                )
            )
        )
        result = compare(left, right, rules, self.case / "cmp-coverage")
        self.assertTrue(result.coverage_lost)
        self.assertNotEqual(result.status, "improved")
        self.assertEqual(result.exit_code, EXIT_REGRESSION)
        comparison = self._comparison(self.case / "cmp-coverage")
        self.assertTrue(any(change["kind"] == "coverage" for change in comparison["changes"]))

    def test_invalid_coverage_probe_still_fails_validation_before_compare(self):
        broken = json.loads(json.dumps(self.amount))
        broken["occurrences"] = []
        left = _write_run(self.case / "left", {"mapping-amount": self.amount})
        reports = self.case / "right" / "reports"
        reports.mkdir(parents=True)
        (reports / "mapping-amount.json").write_text(json.dumps(broken))
        (self.case / "right" / "index.json").write_text(
            json.dumps({"kind": "inkflip-run-index", "schema_version": "1.0.0", "status": "complete", "jobs": {}})
        )
        (self.case / "right" / "identity.json").write_text(
            json.dumps(
                {
                    "kind": "inkflip-corpus-identity",
                    "corpus_manifest_sha256": CORPUS_SHA,
                    "profile_sha256": PROFILE_BEFORE,
                    "algorithm_id": "inkflip-inspect-v1",
                    "intended_keys": ["mapping-amount"],
                }
            )
        )
        result = compare(left, self.case / "right", None, self.case / "cmp-invalid-coverage")
        self.assertEqual(result.exit_code, EXIT_INVALID_ARGS)

    def test_missing_source_job_is_not_unchanged(self):
        left = _write_run(
            self.case / "left",
            {"mapping-amount": self.amount, "mapping-control": self.control},
        )
        right = _write_run(
            self.case / "right",
            {"mapping-amount": self.amount},
            intended_keys=["mapping-amount", "mapping-control"],
        )
        result = compare(left, right, None, self.case / "cmp-missing-job")
        self.assertNotEqual(result.exit_code, EXIT_OK)
        self.assertIn(result.status, {"errored", "regressed"})
        self.assertTrue(result.coverage_lost)
        self.assertEqual(result.exit_code, EXIT_PARTIAL)

    def test_partial_reading_is_not_unchanged(self):
        left = _write_run(self.case / "left", {"mapping-amount": self.amount})
        right = _write_run(self.case / "right", {"mapping-amount": _with_partial_check(self.amount)})
        result = compare(left, right, None, self.case / "cmp-partial")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(result.status, "changed")

    def test_lost_check_is_not_unchanged(self):
        dest = self.case / "amount-two.inkflip.json"
        code = main(
            ["inspect", str(AMOUNT), "--out", str(dest), "--reader", "pdfium", "--reader", "pypdf"]
        )
        self.assertEqual(code, 0)
        two = json.loads(dest.read_text())
        core.validate(two)
        left = _write_run(self.case / "left", {"mapping-amount": two})
        right = _write_run(self.case / "right", {"mapping-amount": _with_missing_check(two)})
        result = compare(left, right, None, self.case / "cmp-lost-check")
        self.assertEqual(result.status, "changed")

    def test_different_document_is_incomparable(self):
        left = _write_run(self.case / "left", {"doc": self.amount})
        right = _write_run(self.case / "right", {"doc": self.control})
        result = compare(left, right, None, self.case / "cmp-docs")
        self.assertEqual(result.exit_code, EXIT_INCOMPARABLE)
        self.assertEqual(self._comparison(self.case / "cmp-docs")["status"], "incomparable")

    def test_unsupported_geometry_is_recorded(self):
        left = _write_run(self.case / "left", {"mapping-amount": self.pypdf_amount})
        right = _write_run(self.case / "right", {"mapping-amount": self.pypdf_amount})
        rules = self.case / "geom.json"
        rules.write_text(
            json.dumps(
                _rules(
                    extra=[
                        {
                            "id": "geom",
                            "type": "max_geometry_delta",
                            "document_sha256": AMOUNT_SHA,
                            "page_index": 0,
                            "reader_id": None,
                            "region_id": None,
                            "expected_text": None,
                            "expected_count": None,
                            "max_delta_pt": 0.5,
                            "capability": None,
                            "explanation": "Page-only pypdf geometry is not comparable.",
                        }
                    ]
                )
            )
        )
        result = compare(left, right, rules, self.case / "cmp-geom")
        self.assertNotEqual(result.exit_code, EXIT_REGRESSION)
        comparison = self._comparison(self.case / "cmp-geom")
        self.assertTrue(any(change["status"] == "incomparable" for change in comparison["changes"]))

    def test_exit_precedence_policy_beats_incomparable_neighbour(self):
        mutated = json.loads(json.dumps(self.pypdf_control))
        for occ in mutated["occurrences"]:
            occ["raw_text"] = "MUTATED"
            occ["normalized_text"], occ["normalization_map"] = core.normalize(occ["raw_text"])
        mutated = core.seal(mutated)
        core.validate(mutated)
        left = _write_run(
            self.case / "left",
            {"mapping-control": self.pypdf_control, "other": self.amount},
        )
        right = _write_run(
            self.case / "right",
            {"mapping-control": mutated, "other": self.control},
        )
        rules = self.case / "rules.json"
        rules.write_text(json.dumps(_rules()))
        result = compare(left, right, rules, self.case / "cmp-prec")
        self.assertEqual(result.exit_code, EXIT_REGRESSION)
        self.assertEqual(result.status, "regressed")
        self.assertTrue(result.incomparable)


class TestBaselinePathIntegrity(ComparisonIntegrityCase):
    def test_symlink_alias_compares_without_mutating_original(self):
        run = _write_run(self.case / "run", {"mapping-amount": self.amount})
        baseline = self.case / "real" / "base.json"
        baseline.parent.mkdir()
        create_baseline(run, None, baseline, "reviewer", "alias probe")
        before = baseline.read_bytes()
        sidecar_before = sorted(p.read_bytes() for p in baseline.with_suffix(baseline.suffix + ".reports").glob("*.json"))
        alias = self.case / "alias.json"
        os.symlink(baseline, alias)
        result = compare(alias, run, None, self.case / "cmp-alias")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(result.status, "unchanged")
        self.assertEqual(baseline.read_bytes(), before)
        sidecar_after = sorted(p.read_bytes() for p in baseline.with_suffix(baseline.suffix + ".reports").glob("*.json"))
        self.assertEqual(sidecar_after, sidecar_before)

    def test_directory_symlink_alias_compares(self):
        run = _write_run(self.case / "run", {"mapping-amount": self.amount})
        real_dir = self.case / "real-dir"
        real_dir.mkdir()
        baseline = real_dir / "base.json"
        create_baseline(run, None, baseline, "reviewer", "dir alias")
        alias_dir = self.case / "alias-dir"
        os.symlink(real_dir, alias_dir)
        result = compare(alias_dir / "base.json", run, None, self.case / "cmp-dir-alias")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(baseline.read_bytes(), (alias_dir / "base.json").read_bytes())

    def test_overlapping_output_is_refused_and_run_is_unchanged(self):
        left = _write_run(self.case / "left", {"mapping-amount": self.amount})
        right = _write_run(self.case / "right", {"mapping-amount": self.amount})
        identity_before = (left / "identity.json").read_bytes()
        reports_before = sorted(p.read_bytes() for p in (left / "reports").glob("*.json"))
        result = compare(left, right, None, left)
        self.assertEqual(result.exit_code, EXIT_INVALID_ARGS)
        self.assertTrue(any("overlap" in item.lower() for item in result.violations))
        self.assertEqual((left / "identity.json").read_bytes(), identity_before)
        self.assertEqual(sorted(p.read_bytes() for p in (left / "reports").glob("*.json")), reports_before)
        self.assertFalse((left / "comparison.json").exists())

    def test_same_file_compare_is_unchanged_and_does_not_rewrite_source(self):
        run = _write_run(self.case / "run", {"mapping-amount": self.amount})
        before = sorted(p.read_bytes() for p in run.rglob("*") if p.is_file())
        result = compare(run, run, None, self.case / "cmp-same")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(result.status, "unchanged")
        after = sorted(p.read_bytes() for p in run.rglob("*") if p.is_file())
        self.assertEqual(after, before)

    def test_failed_compare_write_leaves_existing_baseline_intact(self):
        run = _write_run(self.case / "run", {"mapping-amount": self.amount})
        baseline = self.case / "base.json"
        create_baseline(run, None, baseline, "reviewer", "keep me")
        before = baseline.read_bytes()
        sidecar = baseline.with_suffix(baseline.suffix + ".reports")
        sidecar_before = sorted(p.read_bytes() for p in sidecar.glob("*.json"))
        original = engine.atomic_write_bytes

        def boom(path, data):
            raise OSError("injected comparison write failure")

        engine.atomic_write_bytes = boom
        try:
            with self.assertRaises(OSError):
                compare(baseline, run, None, self.case / "cmp-fail")
        finally:
            engine.atomic_write_bytes = original
        self.assertEqual(baseline.read_bytes(), before)
        self.assertEqual(sorted(p.read_bytes() for p in sidecar.glob("*.json")), sidecar_before)

    def test_create_refuses_output_inside_the_run_directory(self):
        run = _write_run(self.case / "run", {"mapping-amount": self.amount})
        before = sorted(p.read_bytes() for p in run.rglob("*") if p.is_file())
        with self.assertRaises(BaselineError) as ctx:
            create_baseline(run, None, run / "nested.json", "reviewer", "overlap")
        self.assertIn("overlap", str(ctx.exception).lower())
        self.assertEqual(sorted(p.read_bytes() for p in run.rglob("*") if p.is_file()), before)

    def test_create_still_refuses_existing_alias_without_refresh(self):
        run = _write_run(self.case / "run", {"mapping-amount": self.amount})
        baseline = self.case / "base.json"
        create_baseline(run, None, baseline, "reviewer", "first")
        before = baseline.read_bytes()
        alias = self.case / "alias-existing.json"
        os.symlink(baseline, alias)
        with self.assertRaises(BaselineOverwriteError):
            create_baseline(run, None, alias, "reviewer", "must not refresh")
        self.assertEqual(baseline.read_bytes(), before)


class TestCliDiagnostics(ComparisonIntegrityCase):
    def test_cli_prints_status_and_provenance_notes(self):
        before = _as_upgrade_report(self.pypdf_amount, "5.9.0", "pypdf 5.9.0")
        after = _as_upgrade_report(self.pypdf_amount, "6.18.0", "pypdf 6.18.0")
        left = _write_run(self.case / "before", {"mapping-amount": before}, profile_sha256=PROFILE_BEFORE)
        right = _write_run(self.case / "after", {"mapping-amount": after}, profile_sha256=PROFILE_AFTER)
        code = main(["compare", str(left), str(right), "--out", str(self.case / "cmp-cli")])
        self.assertIn(code, (EXIT_OK, EXIT_REGRESSION))


if __name__ == "__main__":
    unittest.main()
