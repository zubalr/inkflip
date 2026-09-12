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

    def test_pinned_candidate_freeze_enforced(self):
        # A plan that pins the freeze refuses any other candidate; a plan
        # that leaves fields null stays advisory only.
        pinned = dict(self.plan["candidate_freeze"])
        pinned.update({"commit": "b" * 40, "lock_sha256": "c" * 64,
                       "config_sha256": "d" * 64})
        plan = helpers.make_plan(label_store=self.plan["label_store"],
                                 candidate_freeze=pinned)
        readings = [helpers.reading(d, resolution="useful_finding",
                                    finding_ids=["f"])
                    for d in ("d0", "d1")] + [helpers.reading("c0")]
        with self.assertRaises(report.RunError):
            self._evaluate(readings, plan=plan)  # run commits "aa..", plan pins "bb.."
        run = helpers.make_run(readings, self.corpus_sha,
                               commit="b" * 40)
        run["candidate"]["lock_sha256"] = "c" * 64
        run["candidate"]["config_sha256"] = "d" * 64
        labels, labels_sha = custody.resolve_labels(
            self.plan["label_store"], helpers.ROOT, self.label_root)
        result = report.evaluate(plan, self.corpus, run, labels, labels_sha,
                                 self.corpus_sha)
        self.assertTrue(result["summary"]["all_met"])
        # Partial pin (commit only): mismatched lock is advisory, wrong
        # commit still refused.
        partial = helpers.make_plan(
            label_store=self.plan["label_store"],
            candidate_freeze={"commit": "b" * 40, "lock_sha256": None,
                              "config_sha256": None})
        result = report.evaluate(partial, self.corpus, run, labels, labels_sha,
                                 self.corpus_sha)
        self.assertTrue(result["summary"]["all_met"])
        run["candidate"]["commit"] = "a" * 40
        with self.assertRaises(report.RunError):
            report.evaluate(partial, self.corpus, run, labels, labels_sha,
                            self.corpus_sha)


class TestAlignmentSamplingUnit(unittest.TestCase):
    """Regression for review P2-1: alignment pools pages, not readings.

    The reviewer's exact demonstrated flip: 5 pages at 0.1px + 5 pages at
    3.9px is honestly p95=3.9 (UNMET); re-reading ONLY the good pages 30x
    must not turn it into p95=0.1 (MET) — the sampling unit is the page.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.docs = [f"good{i}" for i in range(5)] + [f"bad{i}" for i in range(5)]
        entries = [helpers.corpus_entry(d) for d in self.docs]
        self.corpus = helpers.corpus_manifest("evaluation", entries)
        self.corpus_path = helpers.write_manifest(root / "eval.corpus.json",
                                                  self.corpus)
        self.corpus_sha = manifest.file_digest(self.corpus_path)
        self.labels = helpers.labels_file({
            helpers.page_key(d): {"truth": "supported_failure"}
            for d in self.docs})
        store, payload = helpers.make_label_store(self.labels)
        self.plan = helpers.make_plan(
            label_store=store,
            targets=[{"id": "t_alignment_p95", "metric": "alignment_p95_px",
                      "comparator": "<=", "threshold": 2.0},
                     {"id": "t_cov", "metric": "supported_coverage",
                      "comparator": ">=", "threshold": 0.5}])
        (root / "labels").mkdir()
        (root / "labels" / "eval-labels.json").write_bytes(payload)
        self.label_root = root / "labels"

    def tearDown(self):
        self.tmp.cleanup()

    def _evaluate(self, readings):
        labels, labels_sha = custody.resolve_labels(
            self.plan["label_store"], helpers.ROOT, self.label_root)
        return report.evaluate(
            self.plan, self.corpus, helpers.make_run(readings, self.corpus_sha),
            labels, labels_sha, self.corpus_sha)

    def _verdict(self, result):
        return next(v for v in result["targets"]
                    if v["metric"] == "alignment_p95_px")

    def test_rereading_good_pages_cannot_flip_verdict(self):
        def one_pass():
            return [helpers.reading(d, resolution="useful_finding",
                                    finding_ids=["f"],
                                    alignment_errors_px=[0.1])
                    for d in self.docs[:5]] + \
                   [helpers.reading(d, resolution="useful_finding",
                                    finding_ids=["f"],
                                    alignment_errors_px=[3.9])
                    for d in self.docs[5:]]
        single = self._evaluate(one_pass())
        self.assertEqual(single["metrics"]["alignment_px"]["n"], 10)
        self.assertAlmostEqual(single["metrics"]["alignment_px"]["p95"], 3.9)
        self.assertEqual(self._verdict(single)["verdict"], "UNMET")
        # 30x re-reads of ONLY the good pages: n and p95 must not move.
        inflated = one_pass() + [
            helpers.reading(d, run_id=f"re-{k}", resolution="useful_finding",
                            finding_ids=["f"], alignment_errors_px=[0.1])
            for k in range(29) for d in self.docs[:5]]
        self.assertEqual(len(inflated), 155)  # the reviewer's exact corpus
        result = self._evaluate(inflated)
        self.assertEqual(result["samples"]["unique_pages"], 10)
        self.assertEqual(result["metrics"]["alignment_px"]["n"], 10)
        self.assertAlmostEqual(result["metrics"]["alignment_px"]["p95"], 3.9)
        verdict = self._verdict(result)
        self.assertEqual(verdict["verdict"], "UNMET")
        self.assertAlmostEqual(verdict["observed"], 3.9)

    def test_alignment_sample_count_is_pages_not_readings(self):
        from evaluation.protocol.report import _metric_samples
        readings = [
            helpers.reading("good0", run_id=f"r{k}", resolution="useful_finding",
                            finding_ids=["f"], alignment_errors_px=[0.1])
            for k in range(30)]
        result = self._evaluate(readings)
        self.assertEqual(result["metrics"]["alignment_px"]["n"], 1)
        self.assertEqual(_metric_samples(result["metrics"])
                         ["alignment_p95_px"], 1)


if __name__ == "__main__":
    unittest.main()
