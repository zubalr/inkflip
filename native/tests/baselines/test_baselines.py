"""T34 baseline and stored-run comparison tests (TEST-34)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.baselines.engine import compare, create_baseline  # noqa: E402
from inkflip.baselines.models import BaselineOverwriteError  # noqa: E402
from inkflip.cli.main import EXIT_INVALID_ARGS, EXIT_OK, EXIT_POLICY_FAILURE, main  # noqa: E402
from inkflip.contracts import core  # noqa: E402

AMOUNT = FIXTURES / "public" / "mapping-amount.pdf"
CONTROL = FIXTURES / "public" / "mapping-control.pdf"
AMOUNT_SHA = "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80"
CONTROL_SHA = "19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed"


def _inspect(destination: Path, source: Path, reader: str = "pdfium") -> dict:
    code = main(["inspect", str(source), "--out", str(destination), "--reader", reader])
    assert code == EXIT_OK, f"inspect failed for {source} reader={reader}"
    data = json.loads(destination.read_text())
    core.validate(data)
    return data


def _write_run(directory: Path, reports: dict[str, dict]) -> Path:
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
    (directory / "index.json").write_text(
        json.dumps({"kind": "inkflip-run-index", "schema_version": "1.0.0", "status": "complete", "jobs": jobs})
    )
    (directory / "identity.json").write_text(
        json.dumps(
            {
                "kind": "inkflip-corpus-identity",
                "corpus_manifest_sha256": "a" * 64,
                "profile_sha256": "b" * 64,
                "profile_name": "native-default",
                "algorithm_id": "inkflip-inspect-v1",
                "intended_keys": list(reports),
            }
        )
    )
    return directory


def _rules(extra: list[dict] | None = None) -> dict:
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
            },
            {
                "id": "control-coverage",
                "type": "required_coverage",
                "document_sha256": CONTROL_SHA,
                "page_index": 0,
                "reader_id": None,
                "region_id": None,
                "expected_text": None,
                "expected_count": None,
                "max_delta_pt": None,
                "capability": "native_text",
                "explanation": "Control page must complete native_text.",
            },
        ],
        "policy": {
            "fail_on_coverage_loss": True,
            "fail_on_error": True,
            "unruled_change": "changed",
        },
    }
    core.validate(rules)
    return rules


class TestBaselines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.amount = _inspect(self.td / "amount.inkflip.json", AMOUNT, "pdfium")
        self.control = _inspect(self.td / "control.inkflip.json", CONTROL, "pdfium")
        self.pypdf_amount = _inspect(self.td / "amount-pypdf.inkflip.json", AMOUNT, "pypdf")
        self.pypdf_control = _inspect(self.td / "control-pypdf.inkflip.json", CONTROL, "pypdf")

    def tearDown(self):
        self.tmp.cleanup()

    def test_overwrite_prohibited_and_new_path_required(self):
        run = _write_run(self.td / "run-a", {"mapping-amount": self.amount, "mapping-control": self.control})
        rules = self.td / "rules.json"
        rules.write_text(json.dumps(_rules()))
        out = self.td / "base.json"
        create_baseline(run, rules, out, "local-reviewer", "Create the first approved baseline")
        first = out.read_bytes()
        with self.assertRaises(BaselineOverwriteError):
            create_baseline(run, rules, out, "local-reviewer", "Must not refresh")
        self.assertEqual(out.read_bytes(), first)
        code = main(
            [
                "baseline",
                "create",
                "--run",
                str(run),
                "--rules",
                str(rules),
                "--out",
                str(out),
                "--approved-by",
                "local-reviewer",
                "--rationale",
                "second attempt",
            ]
        )
        self.assertEqual(code, EXIT_INVALID_ARGS)
        other = self.td / "base-2.json"
        create_baseline(run, rules, other, "local-reviewer", "A new path is a new baseline")
        self.assertTrue(other.is_file())
        self.assertNotEqual(other.read_bytes(), first)

    def test_no_rule_difference_is_informational(self):
        left = _write_run(self.td / "left", {"mapping-amount": self.amount})
        right = _write_run(self.td / "right", {"mapping-amount": self.pypdf_amount})
        result = compare(left, right, None, self.td / "cmp-info")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(result.status, "changed")
        comparison = json.loads((self.td / "cmp-info" / "comparison.json").read_text())
        core.validate(comparison)
        self.assertEqual(comparison["status"], "changed")
        self.assertTrue((self.td / "cmp-info" / "comparison.html").is_file())

    def test_rule_regression_exits_5(self):
        left = _write_run(self.td / "left-r", {"mapping-control": self.pypdf_control})
        mutated = json.loads(json.dumps(self.pypdf_control))
        for occ in mutated["occurrences"]:
            occ["raw_text"] = "MUTATED"
            occ["normalized_text"], occ["normalization_map"] = core.normalize(occ["raw_text"])
        mutated = core.seal(mutated)
        core.validate(mutated)
        right = _write_run(self.td / "right-r", {"mapping-control": mutated})
        rules = self.td / "rules.json"
        rules.write_text(json.dumps(_rules()))
        result = compare(left, rules_path=rules, right_path=right, out_dir=self.td / "cmp-reg")
        self.assertEqual(result.exit_code, EXIT_POLICY_FAILURE)
        self.assertEqual(result.status, "regressed")

    def test_lost_file_is_retained_not_unchanged(self):
        left = _write_run(self.td / "left-lost", {"mapping-amount": self.amount, "mapping-control": self.control})
        right = _write_run(self.td / "right-lost", {"mapping-amount": self.amount})
        result = compare(left, right, None, self.td / "cmp-lost")
        self.assertNotEqual(result.exit_code, EXIT_OK)
        self.assertTrue(result.coverage_lost)
        self.assertIn(result.status, {"errored", "regressed"})
        rules = self.td / "rules.json"
        rules.write_text(json.dumps(_rules()))
        with_rules = compare(left, right, rules, self.td / "cmp-lost-rules")
        self.assertEqual(with_rules.exit_code, EXIT_POLICY_FAILURE)

    def test_malformed_inputs_exit_2(self):
        bad_left = self.td / "bad-left.json"
        bad_right = self.td / "bad-right.json"
        bad_left.write_text(json.dumps({"kind": "report"}))
        bad_right.write_text(json.dumps({"kind": "report"}))
        result = compare(bad_left, bad_right, None, self.td / "cmp-bad")
        self.assertEqual(result.exit_code, EXIT_INVALID_ARGS)
        code = main(["compare", str(bad_left), str(bad_right), "--out", str(self.td / "cmp-bad-cli")])
        self.assertEqual(code, EXIT_INVALID_ARGS)

    def test_tampered_backing_reports_exit_2(self):
        run = _write_run(self.td / "run-t", {"mapping-control": self.control})
        baseline = self.td / "tamper.json"
        create_baseline(run, None, baseline, "reviewer", "Approved for tamper test")
        sidecar = baseline.with_suffix(baseline.suffix + ".reports")
        target = next(sidecar.glob("*.json"))
        payload = json.loads(target.read_text())
        payload["occurrences"][0]["raw_text"] = "tampered"
        target.write_text(json.dumps(payload))
        result = compare(baseline, run, None, self.td / "cmp-tamper")
        self.assertEqual(result.exit_code, EXIT_INVALID_ARGS)

    def test_unrelated_document_rule_does_not_fire(self):
        left = _write_run(self.td / "left-u", {"mapping-amount": self.amount})
        right = _write_run(self.td / "right-u", {"mapping-amount": self.amount})
        rules = _rules(
            [
                {
                    "id": "wrong-document",
                    "type": "expected_text",
                    "document_sha256": CONTROL_SHA,
                    "page_index": 0,
                    "reader_id": None,
                    "region_id": None,
                    "expected_text": "this-string-is-not-in-the-amount-fixture",
                    "expected_count": None,
                    "max_delta_pt": None,
                    "capability": None,
                    "explanation": "Scoped to a different document; must not fail amount.",
                }
            ]
        )
        rules_path = self.td / "unrelated.json"
        rules_path.write_text(json.dumps(rules))
        result = compare(left, right, rules_path, self.td / "cmp-unrelated")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(result.status, "unchanged")

    def test_check_status_change_is_not_unchanged(self):
        left = _write_run(self.td / "left-c", {"mapping-amount": self.amount})
        mutated = json.loads(json.dumps(self.amount))
        mutated["checks"][0]["status"] = "failed"
        mutated["checks"][0]["reason"] = "forced terminal status change"
        mutated["execution"]["status"] = "failed"
        mutated = core.seal(mutated)
        core.validate(mutated)
        right = _write_run(self.td / "right-c", {"mapping-amount": mutated})
        result = compare(left, right, None, self.td / "cmp-status")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(result.status, "changed")

    def test_geometry_rule_incomparable_for_page_only(self):
        left = _write_run(self.td / "left-g", {"mapping-amount": self.pypdf_amount})
        right = _write_run(self.td / "right-g", {"mapping-amount": self.pypdf_amount})
        rules = _rules(
            [
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
        path = self.td / "geom.json"
        path.write_text(json.dumps(rules))
        result = compare(left, right, path, self.td / "cmp-geom")
        self.assertNotEqual(result.exit_code, EXIT_POLICY_FAILURE)
        comparison = json.loads((self.td / "cmp-geom" / "comparison.json").read_text())
        self.assertTrue(any(change["status"] == "incomparable" for change in comparison["changes"]))


if __name__ == "__main__":
    unittest.main()
