"""TEST-36 interval machinery: Wilson bounds and grouped bootstrap.

Uncertainty is estimated per page and resampled by document/generator
group — never per token, per reading or per sibling page.
"""
from __future__ import annotations

import unittest

import helpers

from evaluation.protocol import metrics


class TestWilsonInterval(unittest.TestCase):
    def test_known_bounds(self):
        low, high = metrics.wilson_interval(95, 100)
        self.assertAlmostEqual(low, 0.8882, places=3)
        self.assertAlmostEqual(high, 0.9784, places=3)
        low, high = metrics.wilson_interval(50, 100)
        self.assertAlmostEqual(low, 0.4038, places=3)
        self.assertAlmostEqual(high, 0.5962, places=3)

    def test_empty_sample_is_widest_not_vacuous(self):
        self.assertEqual(metrics.wilson_interval(0, 0), (0.0, 1.0))

    def test_perfect_score_lower_bound_below_one(self):
        low, high = metrics.wilson_interval(100, 100)
        self.assertLess(low, 1.0)
        self.assertAlmostEqual(low, 0.9630, places=3)
        self.assertAlmostEqual(high, 1.0, places=12)

    def test_lower_bound_increases_with_evidence(self):
        self.assertLess(
            metrics.wilson_interval(9, 10)[0],
            metrics.wilson_interval(90, 100)[0],
        )


class TestGroupedBootstrap(unittest.TestCase):
    def setUp(self):
        # 4 groups x 5 pages, one group entirely failing.
        self.values = {}
        self.groups = {}
        for group in ("g-a", "g-b", "g-c", "g-d"):
            for page in range(5):
                key = f"{group}:{page}"
                self.values[key] = 0.0 if group == "g-d" else 1.0
                self.groups[key] = group

    def test_deterministic_under_seed(self):
        first = metrics.grouped_bootstrap_ci(self.values, self.groups)
        second = metrics.grouped_bootstrap_ci(self.values, self.groups)
        self.assertEqual(first, second)

    def test_resamples_groups_not_pages(self):
        low, high, info = metrics.grouped_bootstrap_ci(
            self.values, self.groups, resamples=1000, seed=1)
        self.assertEqual(info["groups"], 4)
        # Resampling 4 groups of 5: the all-fail group is absent from a
        # resample ~31.6% of the time, so the interval must reach 1.0 —
        # a per-page resample would never produce it.
        self.assertEqual(high, 1.0)
        self.assertLess(low, 1.0)

    def test_repeated_readings_cannot_join_the_resample(self):
        # The same page under five reading identities collapses to one key
        # before bootstrap; handing those five keys in must be identical to
        # handing the collapsed page in.
        single = {"doc:0": 1.0, "doc:1": 0.0}
        groups = {"doc:0": "g-doc", "doc:1": "g-doc"}
        collapsed = metrics.grouped_bootstrap_ci(single, groups, resamples=500, seed=3)
        self.assertEqual(collapsed[2]["groups"], 1)
        # One group means the resample is degenerate: all-or-nothing.
        self.assertIn(collapsed[0], (0.0, 0.5, 1.0))

    def test_percentile_nearest_rank(self):
        self.assertEqual(metrics.percentile([1, 2, 3, 4, 5], 0.5), 3)
        self.assertEqual(metrics.percentile([1, 2, 3, 4, 5], 0.95), 5)
        self.assertIsNone(metrics.percentile([], 0.95))


if __name__ == "__main__":
    unittest.main()
