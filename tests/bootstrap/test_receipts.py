"""Acceptance must bind successful commands and review evidence to real Git state."""
import copy
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import acceptance_receipts as receipts
import coordination
import gate
import native_pass


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Acceptance test")
        self.git("config", "user.email", "acceptance@example.invalid")
        self.tasks, self.overrides = coordination.load_contracts()
        self.task = coordination.effective_task(self.tasks["T01"], self.overrides)
        (self.root / "package.json").write_text("{}\n")
        self.evaluated = self.commit()
        evidence = {}
        for name in self.task["evidence_artifacts"]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"worker": "worker-t01"}\n' if path.suffix == ".json" else "Observed evidence\n")
            evidence[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.path = "artifacts/tasks/T01/acceptance.json"
        self.data = dict(
            schema_version=1, task_id="T01", beads_id="pdf-t01", disposition="accepted",
            evaluated_commit=self.evaluated, evaluated_at="2026-09-11T00:00:00Z",
            contract_digest=receipts.contract_digest(self.task), worker="worker-t01",
            commands=[dict(segment=self.task["commands"][0], argv=shlex.split(self.task["commands"][0]),
                           cwd=".", checkout=str(self.root), exit=0,
                           tests=dict(collected=1, passed=1, failed=0, skipped=0))],
            evidence=evidence,
            criteria={c: ["artifacts/tasks/T01/review.md"] for c in self.task["acceptance_criteria"]},
            review=dict(disposition="approved", reviewers=["independent-reviewer"],
                        path="artifacts/tasks/T01/review.md"))
        self.issue = dict(status="closed", metadata=dict(disposition="accepted", accepted_receipt=self.path))
        self.patch = patch.object(receipts, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def git(self, *args):
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=self.root,
                                text=True, capture_output=True, check=True)
        return result.stdout.strip()

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-qm", "Synthetic acceptance test fixture")
        return self.git("rev-parse", "HEAD")

    def save(self, data=None):
        (self.root / self.path).write_text(json.dumps(self.data if data is None else data) + "\n")
        self.issue["metadata"]["accepted_commit"] = self.commit()

    def test_committed_review_and_real_results_pass(self):
        self.save()
        verified, errors = gate.check_prerequisites({"required_task_ids": ["T01"]}, {"pdf-t01": self.issue})
        self.assertFalse(errors)
        self.assertEqual(verified[0]["evaluated_commit"], self.evaluated)

    def test_native_admission_rejects_committed_empty_prerequisite_receipt(self):
        self.save({})
        with self.assertRaisesRegex(ValueError, "prerequisite acceptance invalid"):
            native_pass.check_fresh_predecessors({'dependencies': ['T01']},
                                                {'pdf-t01': self.issue}, 'HEAD')

    def test_native_admission_rejects_stale_predecessor_code(self):
        self.save()
        (self.root / "package.json").write_text('{"changed": true}\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, "stale receipt"):
            native_pass.check_fresh_predecessors({'dependencies': ['T01']},
                                                {'pdf-t01': self.issue}, 'HEAD')

    def test_native_admission_accepts_fresh_independently_reviewed_receipt(self):
        self.save()
        native_pass.check_fresh_predecessors({'dependencies': ['T01']},
                                            {'pdf-t01': self.issue}, 'HEAD')

    def test_empty_or_malformed_receipt_cannot_pass(self):
        for value in ({}, [], {"task_id": "T02"}):
            with self.subTest(value=value):
                self.save(value)
                with self.assertRaises(ValueError):
                    receipts.validate("T01", self.issue)

    def test_unsuccessful_or_incomplete_commands_cannot_pass(self):
        changes = [dict(exit=1), dict(tests=dict(collected=1, passed=0, failed=0, skipped=1)),
                   dict(tests=dict(collected=0, passed=0, failed=0, skipped=0)), dict(segment="echo success")]
        for change in changes:
            with self.subTest(change=change):
                data = copy.deepcopy(self.data)
                data["commands"][0].update(change)
                self.save(data)
                with self.assertRaises(ValueError):
                    receipts.validate("T01", self.issue)

    def test_a_matching_label_cannot_hide_a_different_executed_command(self):
        self.data["commands"][0]["argv"] = ["echo", "success"]
        self.save()
        with self.assertRaisesRegex(ValueError, "executed argv"):
            receipts.validate("T01", self.issue)

    def test_each_required_suite_needs_its_own_counts(self):
        task = coordination.effective_task(self.tasks["T17"], self.overrides)
        records = [dict(segment=s, argv=shlex.split(s), cwd=".", checkout=str(self.root), exit=0)
                   for s in receipts.segments(task)]
        records[0]["tests"] = dict(collected=1, passed=1, failed=0, skipped=0)
        with self.assertRaises(ValueError):
            receipts.validate_commands(records, task)

    def test_missing_manual_evidence_or_independent_review_cannot_pass(self):
        for field in ("criteria", "evidence", "review"):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data.pop(field)
                self.save(data)
                with self.assertRaises(ValueError):
                    receipts.validate("T01", self.issue)
        data = copy.deepcopy(self.data)
        data["review"]["reviewers"] = [data["worker"]]
        self.save(data)
        with self.assertRaisesRegex(ValueError, "own acceptance"):
            receipts.validate("T01", self.issue)

    def test_code_changes_invalidate_an_old_green_receipt(self):
        self.save()
        (self.root / "package.json").write_text('{"changed": true}\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, "stale receipt"):
            receipts.validate("T01", self.issue)

    def test_changed_evidence_invalidates_a_receipt(self):
        self.save()
        (self.root / "artifacts/tasks/T01/review.md").write_text("Rejected after further inspection\n")
        self.commit()
        with self.assertRaisesRegex(ValueError, "stale evidence"):
            receipts.validate("T01", self.issue)

    def test_unrelated_receipt_commit_does_not_invalidate_acceptance(self):
        self.save()
        other = self.root / "artifacts/tasks/T02/new-evidence.md"
        other.parent.mkdir()
        other.write_text("Independent later task evidence\n")
        self.commit()
        self.assertEqual(receipts.validate("T01", self.issue)["task"], "T01")

    def test_uncommitted_source_cannot_be_recorded_as_a_commit_result(self):
        self.save()
        (self.root / "new_source.py").write_text("raise RuntimeError('uncommitted')\n")
        with self.assertRaisesRegex(ValueError, "commit implementation"):
            receipts.require_clean_inputs()

    def run_fixture(self):
        path = self.root / "artifacts/tasks/T01/run.json"
        path.write_text(json.dumps(dict(task="T01", failures=[], evidence_errors=[],
            evaluated_commit=self.evaluated, evaluated_at="2026-09-12T00:00:00Z",
            tests=self.data["commands"][0]["tests"], records=self.data["commands"])))
        pending = dict(task_id="T01", acceptance_criteria_evidence={
            key: dict(status="executed", evidence=["artifacts/tasks/T01/commands.log"])
            for key in self.task["acceptance_criteria"]})
        (self.root / "artifacts/tasks/T01/receipt.json").write_text(json.dumps(pending))
        review_commit = self.commit()
        return path, review_commit

    def test_record_builder_produces_a_valid_bound_receipt_from_a_reviewed_run(self):
        path, review_commit = self.run_fixture()
        target = receipts.record_acceptance(self.task, path, "worker-t01", "independent-reviewer",
                                            review_commit, "artifacts/tasks/T01/review.md", "accepted")
        self.issue["metadata"]["accepted_commit"] = self.commit()
        self.assertEqual(target.name, "acceptance.json")
        self.assertEqual(receipts.validate("T01", self.issue)["task"], "T01")

    def test_record_builder_rejects_an_unexecuted_criterion(self):
        path, review_commit = self.run_fixture()
        pending = self.root / "artifacts/tasks/T01/receipt.json"
        data = json.loads(pending.read_text())
        data["acceptance_criteria_evidence"][self.task["acceptance_criteria"][0]]["status"] = "pending"
        pending.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "needs executed criterion"):
            receipts.record_acceptance(self.task, path, "worker-t01", "independent-reviewer",
                                       review_commit, "artifacts/tasks/T01/review.md", "accepted")

    def test_record_builder_rejects_code_that_changed_after_the_recorded_run(self):
        path, review_commit = self.run_fixture()
        (self.root / "package.json").write_text('{"new_code": true}\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, "stale receipt"):
            receipts.record_acceptance(self.task, path, "worker-t01", "independent-reviewer",
                                       review_commit, "artifacts/tasks/T01/review.md", "accepted")

    def test_record_builder_requires_real_criterion_specific_files(self):
        path, review_commit = self.run_fixture()
        pending = self.root / "artifacts/tasks/T01/receipt.json"
        data = json.loads(pending.read_text())
        proof = data["acceptance_criteria_evidence"][self.task["acceptance_criteria"][0]]
        for value in ("Manual check passed", ["artifacts/tasks/T01/missing-device-check.png"],
                      ["artifacts/tasks/T02/other.png"], ["artifacts/tasks/T01/empty.png"]):
            with self.subTest(evidence=value):
                (self.root / "artifacts/tasks/T01/empty.png").write_bytes(b"")
                proof["evidence"] = value
                pending.write_text(json.dumps(data))
                with self.assertRaises((ValueError, FileNotFoundError)):
                    receipts.record_acceptance(self.task, path, "worker-t01", "independent-reviewer",
                                               review_commit, "artifacts/tasks/T01/review.md", "accepted")

    def test_record_builder_binds_extra_manual_evidence_and_detects_later_changes(self):
        path, review_commit = self.run_fixture()
        manual = "artifacts/tasks/T01/device-check.md"
        (self.root / manual).write_text("Synthetic independently assessed device evidence\n")
        pending = self.root / "artifacts/tasks/T01/receipt.json"
        data = json.loads(pending.read_text())
        criterion = self.task["acceptance_criteria"][0]
        data["acceptance_criteria_evidence"][criterion]["evidence"] = [manual]
        pending.write_text(json.dumps(data))
        target = receipts.record_acceptance(self.task, path, "worker-t01", "independent-reviewer",
                                           review_commit, "artifacts/tasks/T01/review.md", "accepted")
        recorded = json.loads(target.read_text())
        self.assertEqual(recorded["criteria"][criterion], [manual])
        self.assertIn(manual, recorded["evidence"])
        self.issue["metadata"]["accepted_commit"] = self.commit()
        receipts.validate("T01", self.issue)
        (self.root / manual).write_text("Changed evidence\n")
        self.commit()
        with self.assertRaisesRegex(ValueError, "stale evidence"):
            receipts.validate("T01", self.issue)


if __name__ == "__main__":
    unittest.main()
