"""TEST-36 criterion 4: targets reported as unmet until real run.

A manifest declaring targets shows them UNMET until an actual bound
evaluation run produces real counts. No green-by-default, no self-attested
pass, no vacuous metrics.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import MANIFESTS

from evaluation.protocol import custody, manifest, report


class TestStatusIsUnmetByDefault(unittest.TestCase):
    def test_committed_plan_reports_every_target_unmet(self):
        plan = manifest.load_manifest(MANIFESTS / "evaluation.plan.json")
        result = report.status_report(plan)
        self.assertEqual(result["summary"]["unmet"], len(plan["targets"]))
        self.assertEqual(result["summary"]["met"], 0)
        self.assertFalse(result["summary"]["all_met"])
        for verdict in result["targets"]:
            self.assertEqual(verdict["verdict"], "UNMET")
            self.assertEqual(verdict["reason"], "no_evaluation_run")
            self.assertIsNone(verdict["observed"])

    def test_plan_format_cannot_carry_a_verdict(self):
        plan = helpers.make_plan()
        plan["targets"][0]["verdict"] = "met"
        with self.assertRaises(manifest.ManifestError):
            manifest.validate_evaluation_plan(plan)
        plan2 = helpers.make_plan()
        plan2["targets_met"] = True
        with self.assertRaises(manifest.ManifestError):
            manifest.validate_evaluation_plan(plan2)
        plan3 = helpers.make_plan()
        plan3["status"] = "passed"
        with self.assertRaises(manifest.ManifestError):
            manifest.validate_evaluation_plan(plan3)


class TestRunValidation(unittest.TestCase):
    def _corpus_and_labels(self):
        entries = [helpers.corpus_entry("d0"), helpers.corpus_entry("d1"),
                   helpers.corpus_entry("c0")]
        corpus = helpers.corpus_manifest("evaluation", entries)
        labels = helpers.labels_file({
            helpers.page_key("d0"): {"truth": "supported_failure"},
            helpers.page_key("d1"): {"truth": "supported_failure"},
            helpers.page_key("c0"): {"truth": "clean"},
        })
        return corpus, labels

    def test_run_without_frozen_candidate_rejected(self):
        run = helpers.make_run([], "f" * 64)
        run["candidate"]["commit"] = None
        with self.assertRaises(report.RunError):
            report.validate_run(run)
        run2 = helpers.make_run([], "f" * 64)
        del run2["candidate"]["lock_sha256"]
        with self.assertRaises(report.RunError):
            report.validate_run(run2)

    def test_self_attested_run_rejected(self):
        run = helpers.make_run([], "f" * 64)
        run["targets_met"] = True
        with self.assertRaises(report.RunError):
            report.validate_run(run)
        run2 = helpers.make_run([], "f" * 64)
        run2["readings"] = [{"document_sha256": "a" * 64, "page_index": 0,
                             "check_id": "c-1", "status": "completed",
                             "verdict": "pass"}]
        with self.assertRaises(report.RunError):
            report.validate_run(run2)

    def test_self_attested_resolution_rejected(self):
        # A "useful finding" with no findings is exactly the inflated
        # resolution a dishonest run would emit.
        bad = helpers.reading("d0", resolution="useful_finding", finding_ids=[])
        with self.assertRaises(report.RunError):
            report.validate_run(helpers.make_run([bad], "f" * 64))
        bad2 = helpers.reading("d0", status="failed",
                               resolution="actionable_comparison",
                               comparison_ref="cmp-1")
        with self.assertRaises(report.RunError):
            report.validate_run(helpers.make_run([bad2], "f" * 64))

    def test_nonterminal_status_rejected(self):
        bad = helpers.reading("d0", status="reading")  # not a terminal state
        with self.assertRaises(report.RunError):
            report.validate_run(helpers.make_run([bad], "f" * 64))


class TestVerdictsFromRealRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        entries = [helpers.corpus_entry("d0"), helpers.corpus_entry("d1"),
                   helpers.corpus_entry("c0")]
        self.corpus = helpers.corpus_manifest("evaluation", entries)
        self.corpus_path = helpers.write_manifest(root / "eval.corpus.json", self.corpus)
        self.corpus_sha = manifest.file_digest(self.corpus_path)
        self.labels = helpers.labels_file({
            helpers.page_key("d0"): {"truth": "supported_failure"},
            helpers.page_key("d1"): {"truth": "supported_failure"},
            helpers.page_key("c0"): {"truth": "clean"},
        })
        store, payload = helpers.make_label_store(self.labels)
        self.plan = helpers.make_plan(label_store=store)
        (root / "labels").mkdir()
        (root / "labels" / "eval-labels.json").write_bytes(payload)
        self.label_root = root / "labels"
        self.labels_sha = store["sha256"]

    def tearDown(self):
        self.tmp.cleanup()

    def _evaluate(self, readings, plan=None, **run_extra):
        run = helpers.make_run(readings, self.corpus_sha, **run_extra)
        labels, labels_sha = custody.resolve_labels(
            self.plan["label_store"], helpers.ROOT, self.label_root)
        return report.evaluate(
            plan or self.plan, self.corpus, run, labels, labels_sha,
            self.corpus_sha)

    def test_real_run_produces_met_verdicts(self):
        readings = [
            helpers.reading("d0", resolution="useful_finding", finding_ids=["f0"]),
            helpers.reading("d1", resolution="useful_finding", finding_ids=["f1"]),
            helpers.reading("c0"),  # clean, no alerts
        ]
        result = self._evaluate(readings)
        for verdict in result["targets"]:
            self.assertEqual(verdict["verdict"], "MET", verdict)
            self.assertEqual(verdict["reason"], "measured")
        self.assertTrue(result["summary"]["all_met"])

    def test_below_target_is_unmet_with_observed(self):
        readings = [
            helpers.reading("d0", resolution="useful_finding", finding_ids=["f0"]),
            helpers.reading("d1", status="skipped"),
            helpers.reading("c0"),
        ]
        result = self._evaluate(readings)
        coverage = next(v for v in result["targets"]
                        if v["metric"] == "supported_coverage")
        self.assertEqual(coverage["verdict"], "UNMET")
        self.assertEqual(coverage["reason"], "below_target")
        self.assertAlmostEqual(coverage["observed"], 0.5)

    def test_zero_findings_is_not_a_vacuous_precision_pass(self):
        plan = helpers.make_plan(
            label_store=self.plan["label_store"],
            targets=[{"id": "t_p", "metric": "useful_precision_point",
                      "comparator": ">=", "threshold": 0.95, "min_samples": 100}])
        # No adjudication -> not measured; adjudication of 3 items ->
        # measured but below min_samples. Neither can pass.
        result_none = self._evaluate([], plan=plan)
        self.assertEqual(result_none["targets"][0]["verdict"], "UNMET")
        self.assertEqual(result_none["targets"][0]["reason"], "not_measured")
        adjudication = {"useful": 3, "evaluated": 3,
                        "decisions": {}, "disagreements": []}
        result_few = report.evaluate(
            plan, self.corpus, helpers.make_run([], self.corpus_sha),
            *custody.resolve_labels(self.plan["label_store"], helpers.ROOT,
                                    self.label_root),
            self.corpus_sha, adjudication=adjudication)
        verdict = result_few["targets"][0]
        self.assertEqual(verdict["verdict"], "UNMET")
        self.assertIn("insufficient_evidence", verdict["reason"])

    def test_run_bound_to_other_corpus_rejected(self):
        run = helpers.make_run([], "b" * 64)  # wrong corpus digest
        labels, labels_sha = custody.resolve_labels(
            self.plan["label_store"], helpers.ROOT, self.label_root)
        with self.assertRaises(report.RunError):
            report.evaluate(self.plan, self.corpus, run, labels, labels_sha,
                            self.corpus_sha)

    def test_missing_label_or_stray_label_fails_closed(self):
        # Denominator protection: an unlabeled corpus page or a stray label
        # is a hard failure, not a silently dropped sample.
        readings = [helpers.reading("d0", resolution="useful_finding",
                                    finding_ids=["f0"])]
        run = helpers.make_run(readings, self.corpus_sha)
        short = helpers.labels_file({
            helpers.page_key("d0"): {"truth": "supported_failure"}})
        with self.assertRaises(custody.CustodyError):
            custody.check_labels_cover_corpus(
                short, manifest.corpus_page_keys(self.corpus))


if __name__ == "__main__":
    unittest.main()
