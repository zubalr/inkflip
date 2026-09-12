"""TEST-36 diagnosis test forms and useful-finding adjudication.

Blinded reviewers label surfaced findings independently; disagreements
stay reported and are adjudicated with rationale — never hidden as
correct. Diagnosis sessions use counterbalanced tool order and per-tester
deterministic task shuffles.
"""
from __future__ import annotations

import unittest

import helpers

from evaluation.protocol import diagnosis


def sample_findings(count: int = 6) -> list[dict]:
    return [
        {"finding_sha256": helpers.sha(f"finding-{i}"),
         "page_ref": f"{helpers.sha('d')[:12]}:{i}"}
        for i in range(count)
    ]


def responses_for(form: dict, votes: dict[str, str]) -> dict:
    """Reviewer response file: {item_id: {useful, noise, rationale}}."""
    return {
        item["item_id"]: {
            "useful": votes.get(item["item_id"]) == "useful",
            "noise": votes.get(item["item_id"]) == "noise",
            "rationale": f"rationale for {votes.get(item['item_id'], 'none')}",
        }
        for item in form["items"]
    }


class TestCounterbalancing(unittest.TestCase):
    def test_two_conditions_are_balanced_and_deterministic(self):
        testers = [f"tester-{i}" for i in range(4)]
        assignments = diagnosis.counterbalanced_assignments(testers)
        orders = list(assignments.values())
        self.assertEqual(orders.count(["baseline_viewer_dump", "inspector"]), 2)
        self.assertEqual(orders.count(["inspector", "baseline_viewer_dump"]), 2)
        self.assertEqual(assignments, diagnosis.counterbalanced_assignments(testers))

    def test_task_order_shuffles_per_tester_deterministically(self):
        tasks = [f"task-{i}" for i in range(6)]
        first = diagnosis.task_order("t-a", tasks)
        self.assertEqual(sorted(first), sorted(tasks))
        self.assertEqual(first, diagnosis.task_order("t-a", tasks))
        self.assertNotEqual(first, diagnosis.task_order("t-b", tasks))


class TestBlindedForm(unittest.TestCase):
    def test_items_carry_no_truth_or_verdict(self):
        form = diagnosis.blinded_review_form(sample_findings())
        self.assertEqual(len(form["items"]), 6)
        for item in form["items"]:
            self.assertEqual(
                item["labels"], {"useful": None, "noise": None, "rationale": None})
            self.assertNotIn("truth", item)
            self.assertNotIn("verdict", item)

    def test_sampling_is_deterministic_and_bounded(self):
        form_a = diagnosis.blinded_review_form(sample_findings(10), sample_size=4)
        form_b = diagnosis.blinded_review_form(sample_findings(10), sample_size=4)
        self.assertEqual(form_a["items"], form_b["items"])
        self.assertEqual(len(form_a["items"]), 4)


class TestAdjudication(unittest.TestCase):
    def setUp(self):
        self.form = diagnosis.blinded_review_form(sample_findings(4), seed=7)
        self.items = [i["item_id"] for i in self.form["items"]]

    def _adjudicate(self, votes_a, votes_b, adjudications=None):
        return diagnosis.adjudicate(
            self.form,
            {"rev-a": responses_for(self.form, votes_a),
             "rev-b": responses_for(self.form, votes_b)},
            adjudications=adjudications)

    def test_agreement_decides_disagreement_stays_visible(self):
        votes_a = dict(zip(self.items, ["useful", "noise", "useful", "useful"]))
        votes_b = dict(zip(self.items, ["useful", "noise", "noise", "useful"]))
        result = self._adjudicate(votes_a, votes_b)
        self.assertEqual(result["decisions"][self.items[2]], "disputed_unresolved")
        self.assertEqual(len(result["disagreements"]), 1)
        dispute = result["disagreements"][0]
        self.assertEqual(dispute["labels"], {"rev-a": "useful", "rev-b": "noise"})
        self.assertIn("rev-a", dispute["rationales"])
        self.assertIn("rev-b", dispute["rationales"])
        # The unresolved dispute counts in the denominator, not numerator.
        self.assertEqual(result["evaluated"], 4)
        self.assertEqual(result["useful"], 2)
        self.assertAlmostEqual(result["precision"], 0.5)

    def test_adjudicated_dispute_uses_recorded_rationale(self):
        votes_a = dict(zip(self.items, ["useful"] * 4))
        votes_b = dict(zip(self.items, ["noise", "useful", "useful", "useful"]))
        result = self._adjudicate(
            votes_a, votes_b,
            adjudications={self.items[0]: {
                "decision": "noise",
                "rationale": "duplicate card for one issue is review burden",
                "adjudicator": "rev-chief"}})
        self.assertEqual(result["decisions"][self.items[0]], "noise")
        self.assertEqual(result["useful"], 3)
        self.assertEqual(len(result["disagreements"]), 1)  # still visible
        self.assertEqual(
            result["disagreements"][0]["adjudicated"]["adjudicator"], "rev-chief")

    def test_adjudication_without_rationale_rejected(self):
        votes = dict(zip(self.items, ["useful", "useful", "useful", "useful"]))
        votes_b = dict(zip(self.items, ["noise", "useful", "useful", "useful"]))
        with self.assertRaises(ValueError):
            self._adjudicate(votes, votes_b,
                             adjudications={self.items[0]: {"decision": "useful"}})

    def test_one_reviewer_is_not_independent(self):
        with self.assertRaises(ValueError):
            diagnosis.adjudicate(
                self.form, {"rev-a": responses_for(self.form, {})})

    def test_precision_metric_wilson_uses_adjudicated_counts(self):
        votes_a = dict(zip(self.items, ["useful"] * 4))
        result = self._adjudicate(votes_a, votes_a)
        metric = diagnosis.useful_precision_metric(result)
        self.assertEqual(metric["evaluated"], 4)
        self.assertEqual(metric["useful"], 4)
        self.assertAlmostEqual(metric["point"], 1.0)
        self.assertLess(metric["wilson_lower"], 1.0)


class TestDiagnosisSummary(unittest.TestCase):
    def test_understanding_and_median_improvement(self):
        sessions = []
        for i in range(5):
            tester = f"tester-{i}"
            sessions.append({"tester": tester, "condition": "baseline_viewer_dump",
                             "task": "t1", "seconds": 100.0, "understood": True})
            sessions.append({"tester": tester, "condition": "inspector",
                             "task": "t1", "seconds": 60.0 if i != 4 else 70.0,
                             "understood": i != 4})
        summary = diagnosis.diagnosis_summary(sessions)
        self.assertEqual(summary["testers"], 5)
        self.assertEqual(summary["understood"], 4)
        self.assertAlmostEqual(summary["understanding_rate"], 0.8)
        self.assertAlmostEqual(summary["median_improvement"], 0.4, places=5)

    def test_improvement_requires_both_conditions(self):
        sessions = [{"tester": "t", "condition": "inspector", "task": "x",
                     "seconds": 10.0, "understood": True}]
        summary = diagnosis.diagnosis_summary(sessions)
        self.assertIsNone(summary["median_improvement"])
        self.assertEqual(summary["understanding_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
