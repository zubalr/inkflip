"""TEST-36 criterion 5: held-out labels stay permissioned and out of logs.

Held-out labels and small real incident data are custodian-only artifacts:
they resolve only from an explicit label root outside every checkout, must
match the plan's pinned digest, and their content can never reach reports,
logs or task artifacts — only digests and aggregate counts may.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import helpers
from helpers import EVALUATOR, ROOT

from evaluation.protocol import custody, manifest, report

SENTINEL_EXPECTED = "$4,210.55"
SENTINEL_INCIDENT = "ACME-INCIDENT-9X"
SENTINEL_CONSENT = "consent/2026-081-jdoe"


def make_eval_fixture(root: Path, pages: dict[str, dict]) -> tuple[dict, dict, Path, dict]:
    """Corpus + labels + plan + label root in a tmp dir outside the repo.

    Label page keys are ``<doc_sha256>:<page_index>``; the corpus manifest
    declares one entry per document sha so every page binds by content.
    """
    docs: dict[str, list[int]] = {}
    for key in pages:
        sha, index = key.rsplit(":", 1)
        docs.setdefault(sha, []).append(int(index))
    entries = [
        helpers.corpus_entry(f"doc{index}", sha256=sha,
                             group_id=f"g-doc{index}", pages=sorted(pages_idx))
        for index, (sha, pages_idx) in enumerate(sorted(docs.items()))
    ]
    corpus = helpers.corpus_manifest("evaluation", entries)
    corpus_path = helpers.write_manifest(root / "eval.corpus.json", corpus)
    labels = helpers.labels_file(pages)
    store, payload = helpers.make_label_store(labels)
    label_root = root / "custodian-labels"
    label_root.mkdir(parents=True)
    (label_root / "eval-labels.json").write_bytes(payload)
    plan = helpers.make_plan(label_store=store)
    return corpus, corpus_path, label_root, plan


class TestLabelGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_labels_outside_repo_resolve_with_pinned_digest(self):
        pages = {helpers.page_key("d0"): {"truth": "supported_failure"},
                 helpers.page_key("c0"): {"truth": "clean"}}
        _, _, label_root, plan = make_eval_fixture(self.root, pages)
        labels, digest = custody.resolve_labels(
            plan["label_store"], ROOT, label_root)
        self.assertEqual(sorted(labels["pages"]), sorted(pages))
        self.assertEqual(digest, plan["label_store"]["sha256"])

    def test_missing_label_root_fails_closed(self):
        store = {"schema": helpers.LABEL_SCHEMA, "labels_file": "eval-labels.json",
                 "sha256": "a" * 64, "label_count": 1, "permissioned": True}
        with self.assertRaises(custody.CustodyError):
            custody.resolve_labels(store, ROOT, None)

    def test_label_root_inside_repository_refused(self):
        # A different folder in the same tree is not custody: pointing the
        # gate at the repo itself or a subdir must fail before any file read.
        store = {"schema": helpers.LABEL_SCHEMA, "labels_file": "eval-labels.json",
                 "sha256": "a" * 64, "label_count": 1, "permissioned": True}
        for inside in (ROOT, ROOT / "evaluation", ROOT / "tests/evaluation"):
            with self.assertRaises(custody.CustodyError, msg=str(inside)):
                custody.resolve_labels(store, ROOT, inside)

    def test_label_root_inside_worktree_sibling_refused(self):
        # Even an unrelated directory nested under the checkout is refused.
        store = {"schema": helpers.LABEL_SCHEMA, "labels_file": "eval-labels.json",
                 "sha256": "a" * 64, "label_count": 1, "permissioned": True}
        nested = ROOT / "artifacts"
        with self.assertRaises(custody.CustodyError):
            custody.resolve_labels(store, ROOT, nested)

    def test_digest_mismatch_refused(self):
        pages = {helpers.page_key("d0"): {"truth": "supported_failure"}}
        _, _, label_root, plan = make_eval_fixture(self.root, pages)
        plan["label_store"]["sha256"] = "0" * 64
        with self.assertRaises(custody.CustodyError):
            custody.resolve_labels(plan["label_store"], ROOT, label_root)

    def test_unpinned_label_store_fails_closed(self):
        pages = {helpers.page_key("d0"): {"truth": "supported_failure"}}
        _, _, label_root, plan = make_eval_fixture(self.root, pages)
        plan["label_store"]["sha256"] = None
        with self.assertRaises(custody.CustodyError):
            custody.resolve_labels(plan["label_store"], ROOT, label_root)

    def test_label_file_traversal_refused(self):
        store = {"schema": helpers.LABEL_SCHEMA, "labels_file": "../escape.json",
                 "sha256": "a" * 64, "label_count": 1, "permissioned": True}
        label_root = self.root / "labels"
        label_root.mkdir()
        (self.root / "escape.json").write_text("{}")
        with self.assertRaises(custody.CustodyError):
            custody.resolve_labels(store, ROOT, label_root)

    def test_label_count_mismatch_refused(self):
        pages = {helpers.page_key("d0"): {"truth": "supported_failure"}}
        _, _, label_root, plan = make_eval_fixture(self.root, pages)
        plan["label_store"]["label_count"] = 99
        with self.assertRaises(custody.CustodyError):
            custody.resolve_labels(plan["label_store"], ROOT, label_root)

    def test_permissioned_labels_require_consent_ref(self):
        pages = {helpers.page_key("d0"): {
            "truth": "supported_failure", "incident_ref": SENTINEL_INCIDENT}}
        _, _, label_root, plan = make_eval_fixture(self.root, pages)
        labels, _ = custody.resolve_labels(plan["label_store"], ROOT, label_root)
        with self.assertRaises(custody.CustodyError):
            custody.validate_permissioned_labels(labels)
        # With consent recorded, the same labels pass.
        labels["pages"][helpers.page_key("d0")]["consent_ref"] = SENTINEL_CONSENT
        custody.validate_permissioned_labels(labels)


class TestNoLabelContentInArtifacts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        pages = {
            helpers.page_key("d0"): {
                "truth": "supported_failure",
                "expected_finding": SENTINEL_EXPECTED,
                "incident_ref": SENTINEL_INCIDENT,
                "consent_ref": SENTINEL_CONSENT,
            },
            helpers.page_key("c0"): {"truth": "clean"},
        }
        self.corpus, self.corpus_path, self.label_root, self.plan = \
            make_eval_fixture(self.root, pages)
        self.labels, self.labels_sha = custody.resolve_labels(
            self.plan["label_store"], ROOT, self.label_root)
        self.corpus_sha = manifest.file_digest(self.corpus_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _run_eval(self, out_path: Path | None = None) -> tuple[dict, str]:
        readings = [
            helpers.reading("d0", resolution="useful_finding", finding_ids=["f0"]),
            helpers.reading("c0"),
        ]
        run = helpers.make_run(readings, self.corpus_sha)
        result = report.evaluate(
            self.plan, self.corpus, run, self.labels, self.labels_sha,
            self.corpus_sha)
        serialized = report.serialize_report(result, self.labels)
        if out_path:
            out_path.write_bytes(serialized)
        return result, serialized.decode()

    def test_report_contains_no_label_values(self):
        _, serialized = self._run_eval()
        for sentinel in (SENTINEL_EXPECTED, SENTINEL_INCIDENT, SENTINEL_CONSENT):
            self.assertNotIn(sentinel, serialized)
        self.assertIn(self.labels_sha, serialized)  # digest is allowed

    def test_report_has_no_per_page_truth_or_label_keys(self):
        result, _ = self._run_eval()
        self.assertEqual(custody.scan_forbidden_keys(result), [])
        # Per-page outcomes carry status/resolution only — never truth.
        encoded = json.dumps(result)
        self.assertNotIn('"truth"', encoded)
        self.assertNotIn('"expected_finding"', encoded)
        self.assertNotIn('"consent_ref"', encoded)

    def test_serializer_refuses_label_content(self):
        result, _ = self._run_eval()
        result["metrics"]["leak"] = SENTINEL_EXPECTED
        with self.assertRaises(custody.CustodyError):
            report.serialize_report(result, self.labels)
        result2, _ = self._run_eval()
        result2["per_page_truth"] = {"x": "clean"}
        with self.assertRaises(custody.CustodyError):
            report.serialize_report(result2, self.labels)

    def test_label_secrets_collection_catches_nested_content(self):
        secrets = custody.label_secret_values(self.labels)
        for sentinel in (SENTINEL_EXPECTED, SENTINEL_INCIDENT, SENTINEL_CONSENT):
            self.assertIn(sentinel, secrets)
        self.assertNotIn("clean", secrets)
        self.assertNotIn("supported_failure", secrets)


class TestCliCustody(unittest.TestCase):
    """End-to-end: the evaluator never prints or writes label content."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        pages = {
            helpers.page_key("d0"): {
                "truth": "supported_failure",
                "expected_finding": SENTINEL_EXPECTED,
                "incident_ref": SENTINEL_INCIDENT,
            },
            helpers.page_key("d1"): {"truth": "supported_failure"},
            helpers.page_key("c0"): {"truth": "clean"},
        }
        self.corpus, self.corpus_path, self.label_root, self.plan = \
            make_eval_fixture(self.root, pages)
        self.plan_path = helpers.write_json(self.root / "plan.json", self.plan)

    def tearDown(self):
        self.tmp.cleanup()

    def _cli(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(EVALUATOR), *argv],
            capture_output=True, text=True, cwd=ROOT, timeout=60)

    def test_evaluate_stdout_and_report_carry_no_label_content(self):
        corpus_sha = manifest.file_digest(self.corpus_path)
        readings = [
            helpers.reading("d0", resolution="useful_finding", finding_ids=["f0"]),
            helpers.reading("d1", resolution="useful_finding", finding_ids=["f1"]),
            helpers.reading("c0"),
        ]
        run_path = helpers.write_json(
            self.root / "run.json", helpers.make_run(readings, corpus_sha))
        out_path = self.root / "report.json"
        result = self._cli(
            "evaluate", "--plan", str(self.plan_path),
            "--corpus", str(self.corpus_path), "--run", str(run_path),
            "--label-root", str(self.label_root), "--out", str(out_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        emitted = result.stdout + result.stderr + out_path.read_text()
        for sentinel in (SENTINEL_EXPECTED, SENTINEL_INCIDENT):
            self.assertNotIn(sentinel, emitted)
        data = json.loads(out_path.read_text())
        self.assertTrue(data["summary"]["all_met"])
        self.assertEqual(data["samples"]["unique_pages"], 3)

    def test_evaluate_without_label_root_fails_closed(self):
        run_path = helpers.write_json(
            self.root / "run.json",
            helpers.make_run([], manifest.file_digest(self.corpus_path)))
        result = self._cli(
            "evaluate", "--plan", str(self.plan_path),
            "--corpus", str(self.corpus_path), "--run", str(run_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("label root", result.stderr)
        self.assertFalse((self.root / "report.json").exists())

    def test_status_is_unmet_and_exit_nonzero(self):
        result = self._cli("status", "--plan", str(self.plan_path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("UNMET", result.stdout)
        self.assertIn("no_evaluation_run", result.stdout)


if __name__ == "__main__":
    unittest.main()
