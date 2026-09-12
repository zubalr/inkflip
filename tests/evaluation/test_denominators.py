"""TEST-36 criteria 2+3: precise denominators and deduplicated samples.

Coverage denominators are corpus-declared, never reader-chosen: skipped,
failed, timed-out and never-attempted pages stay visible in every ratio.
And repeated OCR readings of one page are one sample — a duplicated-reading
corpus cannot inflate n or narrow an interval.
"""
from __future__ import annotations

import unittest

import helpers

from evaluation.protocol import metrics


def supported_labels(*names: str) -> dict:
    return helpers.labels_file({
        helpers.page_key(name): {"truth": "supported_failure"} for name in names
    })


class TestCoverageDenominator(unittest.TestCase):
    """Criterion 2: skipped/failed pages remain the coverage denominator."""

    def test_nine_skipped_of_ten_scores_tenth_not_perfect(self):
        docs = [f"doc{i}" for i in range(10)]
        labels = supported_labels(*docs)
        readings = [
            helpers.reading("doc0", resolution="useful_finding", finding_ids=["f0"]),
            *[helpers.reading(d, status="skipped") for d in docs[1:]],
        ]
        pages = metrics.collapse_readings(readings)
        result = metrics.supported_coverage(pages, labels)
        self.assertEqual(result["total"], 10)
        self.assertEqual(result["covered"], 1)
        self.assertAlmostEqual(result["rate"], 0.1)
        self.assertEqual(len(result["uncovered_pages"]), 9)
        self.assertEqual(result["uncovered_statuses"], {"skipped": 9})

    def test_failed_timeout_cancelled_stay_in_denominator(self):
        labels = supported_labels("a", "b", "c", "d", "e")
        readings = [
            helpers.reading("a", resolution="useful_finding", finding_ids=["f"]),
            helpers.reading("b", status="failed"),
            helpers.reading("c", status="timeout"),
            helpers.reading("d", status="cancelled"),
            # "e" was never attempted at all — still a denominator member.
        ]
        pages = metrics.collapse_readings(readings)
        result = metrics.supported_coverage(pages, labels)
        self.assertEqual(result["covered"], 1)
        self.assertAlmostEqual(result["rate"], 0.2)
        self.assertIn(helpers.page_key("e"), result["never_attempted"])
        self.assertEqual(result["uncovered_statuses"],
                         {"failed": 1, "timeout": 1, "cancelled": 1, "never_attempted": 1})

    def test_abstain_everywhere_is_zero_not_precision_by_silence(self):
        labels = supported_labels("a", "b", "c")
        readings = [helpers.reading(d, status="unsupported") for d in ("a", "b", "c")]
        result = metrics.supported_coverage(metrics.collapse_readings(readings), labels)
        self.assertEqual(result["rate"], 0.0)
        self.assertEqual(result["uncovered_statuses"], {"unsupported": 3})

    def test_unsupported_mechanism_outside_supported_recall_inside_full(self):
        labels = helpers.labels_file({
            helpers.page_key("s1"): {"truth": "supported_failure"},
            helpers.page_key("s2"): {"truth": "supported_failure"},
            helpers.page_key("u1"): {"truth": "unsupported"},
            helpers.page_key("c1"): {"truth": "clean"},
        })
        readings = [
            helpers.reading("s1", resolution="useful_finding", finding_ids=["f"]),
            helpers.reading("s2", status="failed"),
            helpers.reading("u1", status="unsupported"),
        ]
        pages = metrics.collapse_readings(readings)
        supported = metrics.supported_coverage(pages, labels)
        self.assertEqual(supported["total"], 2)
        self.assertAlmostEqual(supported["rate"], 0.5)
        full = metrics.full_coverage(pages, labels)
        self.assertEqual(full["total"], 4)  # unsupported + clean stay visible
        self.assertAlmostEqual(full["rate"], 0.25)

    def test_clean_false_alert_denominator_counts_every_clean_page(self):
        labels = helpers.labels_file({
            **{helpers.page_key(f"c{i}"): {"truth": "clean"} for i in range(100)},
            helpers.page_key("s0"): {"truth": "supported_failure"},
        })
        readings = [
            helpers.reading("c0", finding_ids=["noise-1", "noise-2"]),
            helpers.reading("c1", finding_ids=["noise-3"]),
            # 98 clean pages never read: they contribute no alerts but stay
            # in the denominator and are counted in pages_read honestly.
        ]
        result = metrics.clean_false_alerts(metrics.collapse_readings(readings), labels)
        self.assertEqual(result["alerts"], 3)
        self.assertEqual(result["clean_pages"], 100)
        self.assertAlmostEqual(result["per_page"], 0.03)
        self.assertEqual(result["pages_read"], 2)
        self.assertEqual(result["max_per_page"], 2)

    def test_check_accounting_missing_result_is_violation_not_agreement(self):
        readings = [
            helpers.reading("a", check_id="c-ok", status="completed"),
            helpers.reading("a", check_id="c-dup", status="failed", run_id="r1"),
            helpers.reading("a", check_id="c-dup", status="completed", run_id="r2"),
        ]
        result = metrics.check_accounting(readings, ["c-ok", "c-dup", "c-missing"])
        self.assertEqual(result["planned"], 3)
        self.assertEqual(result["terminal"], 2)
        self.assertEqual(result["missing"], ["c-missing"])
        # The retried c-dup counts once as one planned unit of work.
        self.assertEqual(result["attempts"], 3)


class TestRepeatedReadingsDedup(unittest.TestCase):
    """Criterion 3: repeated OCR readings are not independent samples."""

    def setUp(self):
        self.docs = [f"doc{i}" for i in range(20)]
        self.labels = supported_labels(*self.docs)
        self.single = [
            helpers.reading(d, resolution="useful_finding", finding_ids=[f"f-{d}"])
            for d in self.docs
        ]
        self.duplicated = [
            helpers.reading(d, resolution="useful_finding",
                            finding_ids=[f"f-{d}"], run_id=f"attempt-{k}")
            for d in self.docs for k in range(5)
        ]

    def test_five_rereads_of_twenty_pages_is_twenty_samples(self):
        pages = metrics.collapse_readings(self.duplicated)
        self.assertEqual(len(pages), 20)
        self.assertTrue(all(p["readings"] == 5 for p in pages.values()))
        result = metrics.supported_coverage(pages, self.labels)
        self.assertEqual(result["total"], 20)  # not 100
        self.assertEqual(result["covered"], 20)

    def test_duplicated_corpus_matches_single_read_metrics(self):
        single_pages = metrics.collapse_readings(self.single)
        dup_pages = metrics.collapse_readings(self.duplicated)
        single_cov = metrics.supported_coverage(single_pages, self.labels)
        dup_cov = metrics.supported_coverage(dup_pages, self.labels)
        self.assertEqual(single_cov["rate"], dup_cov["rate"])
        self.assertEqual(single_cov["wilson"], dup_cov["wilson"])
        self.assertEqual(single_cov["total"], dup_cov["total"])

    def test_wilson_uses_pages_not_readings(self):
        # If re-reads counted, n would be 100 and the interval would narrow
        # dishonestly. It must equal the 20-page interval.
        dup_pages = metrics.collapse_readings(self.duplicated)
        result = metrics.supported_coverage(dup_pages, self.labels)
        expected = metrics.wilson_interval(20, 20)
        inflated = metrics.wilson_interval(100, 100)
        self.assertEqual(result["wilson"], [expected[0], expected[1]])
        self.assertGreater(expected[0], 0)  # sanity
        self.assertGreater(inflated[0], expected[0],
                           "sanity: 100-sample bound is narrower; we must not emit it")

    def test_rereads_cannot_erase_a_failed_first_attempt(self):
        labels = supported_labels("a")
        readings = [
            helpers.reading("a", status="failed", run_id="r1"),
            helpers.reading("a", status="completed", resolution="useful_finding",
                            finding_ids=["f"], run_id="r2"),
        ]
        pages = metrics.collapse_readings(readings)
        page = pages[helpers.page_key("a")]
        self.assertTrue(page["resolved"])
        self.assertEqual(page["statuses"], {"failed": 1, "completed": 1})
        # Coverage resolves the page, but the failure stays reported.

    def test_same_alert_reread_counts_once_distinct_alerts_count(self):
        labels = helpers.labels_file({helpers.page_key("a"): {"truth": "clean"}})
        readings = [
            helpers.reading("a", finding_ids=["dup-alert"], run_id="r1"),
            helpers.reading("a", finding_ids=["dup-alert", "new-alert"], run_id="r2"),
        ]
        result = metrics.clean_false_alerts(metrics.collapse_readings(readings), labels)
        self.assertEqual(result["alerts"], 2)  # dup-alert once + new-alert
        self.assertEqual(result["max_per_page"], 2)


class TestOccurrencePreservation(unittest.TestCase):
    """Repeated-occurrence preservation over label-declared expectations."""

    def labels(self) -> dict:
        return helpers.labels_file({
            helpers.page_key("dup3"): {"truth": "supported_failure",
                                       "expected_occurrences": 3},
            helpers.page_key("dup2"): {"truth": "supported_failure",
                                       "expected_occurrences": 2},
            helpers.page_key("plain"): {"truth": "supported_failure"},
        })

    def test_dropped_duplicate_is_lost_not_averaged(self):
        readings = [
            helpers.reading("dup3", occurrence_count=3),
            helpers.reading("dup2", occurrence_count=1),  # lost one duplicate
            helpers.reading("plain"),
        ]
        result = metrics.occurrence_preservation(
            metrics.collapse_readings(readings), self.labels())
        self.assertEqual(result["pages"], 2)  # "plain" declares no expectation
        self.assertEqual(result["preserved"], 1)
        self.assertAlmostEqual(result["fraction"], 0.5)
        self.assertEqual(result["lost"], [helpers.page_key("dup2")])

    def test_unread_declared_page_counts_as_lost(self):
        result = metrics.occurrence_preservation(
            metrics.collapse_readings([]), self.labels())
        self.assertEqual(result["fraction"], 0.0)
        self.assertEqual(len(result["lost"]), 2)

    def test_flaky_rereads_use_minimum_not_best(self):
        readings = [
            helpers.reading("dup3", occurrence_count=3, run_id="r1"),
            helpers.reading("dup3", occurrence_count=2, run_id="r2"),  # flaky
            helpers.reading("dup2", occurrence_count=2),
        ]
        result = metrics.occurrence_preservation(
            metrics.collapse_readings(readings), self.labels())
        self.assertEqual(result["preserved"], 1)
        self.assertEqual(result["lost"], [helpers.page_key("dup3")])

    def test_zero_expected_still_needs_a_measurement(self):
        # Review P3: silence cannot confirm preservation even when the
        # declared expectation is zero — an unread page is lost, while a
        # completed reading reporting 0 is measured evidence.
        labels = helpers.labels_file({
            helpers.page_key("empty0"): {"truth": "supported_failure",
                                         "expected_occurrences": 0},
        })
        unread = metrics.occurrence_preservation(
            metrics.collapse_readings([]), labels)
        self.assertEqual(unread["fraction"], 0.0)
        self.assertEqual(unread["lost"], [helpers.page_key("empty0")])
        # A completed read that reports no count is still silence.
        silent = metrics.occurrence_preservation(
            metrics.collapse_readings([helpers.reading("empty0")]), labels)
        self.assertEqual(silent["fraction"], 0.0)
        measured = metrics.occurrence_preservation(
            metrics.collapse_readings(
                [helpers.reading("empty0", occurrence_count=0)]), labels)
        self.assertEqual(measured["fraction"], 1.0)


if __name__ == "__main__":
    unittest.main()
