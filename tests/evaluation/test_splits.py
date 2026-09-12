"""TEST-36 criterion 1: no sibling leakage.

Splits group by generator family/document lineage. A fixture and its
siblings — same source, transformed variants, control twins — can never
straddle dev/eval boundaries. These tests build a corpus that *would* leak
under naive random splitting and prove the grouped protocol prevents it.
"""
from __future__ import annotations

import json
import unittest

import helpers
from helpers import MANIFESTS, ROOT

from evaluation.protocol import lineage, manifest


def sibling_family(prefix: str, count: int, sha_seed: str | None = None) -> list[dict]:
    """One generator family: a control plus transformed variant siblings."""
    entries = []
    for index in range(count):
        variant = "control" if index == 0 else f"v{index}"
        key = f"{prefix}-{variant}"
        entries.append(helpers.corpus_entry(
            key, sha256=helpers.sha(sha_seed or key), group_id=f"g-{prefix}"))
    return entries


class TestNaiveVsGroupedAssignment(unittest.TestCase):
    """The case that leaks under naive random split, and why grouping holds."""

    def setUp(self):
        # Two families of five siblings each: the realistic eval-corpus shape.
        self.entries = sibling_family("alpha", 5) + sibling_family("beta", 5)
        self.groups = lineage.sibling_groups(self.entries)
        self.keys = [e["key"] for e in self.entries]

    def test_sibling_groups_collapse_each_family_to_one_cluster(self):
        self.assertEqual(len(self.groups), 2)
        for members in self.groups.values():
            self.assertEqual(len(members), 5)
            self.assertEqual(len({m.split("-")[0] for m in members}), 1)

    def test_naive_random_split_straddles_siblings(self):
        # There must exist a seed where per-entry draws split a family —
        # otherwise the naive baseline could not demonstrate leakage at all.
        straddled = []
        for seed in range(50):
            naive = lineage.assign_naive(self.keys, ["development", "evaluation"], seed)
            by_split = {"development": [], "evaluation": []}
            for entry in self.entries:
                by_split[naive[entry["key"]]].append(entry)
            if lineage.split_violations(by_split):
                straddled.append(seed)
        self.assertTrue(straddled, "no seed straddled siblings; naive test is vacuous")
        # And the audit must catch every one of those straddles.
        for seed in straddled:
            naive = lineage.assign_naive(self.keys, ["development", "evaluation"], seed)
            by_split = {"development": [], "evaluation": []}
            for entry in self.entries:
                by_split[naive[entry["key"]]].append(entry)
            violations = lineage.split_violations(by_split)
            self.assertTrue(violations, f"seed {seed} straddled but audit missed it")

    def test_grouped_assignment_never_straddles(self):
        for seed in range(200):
            assigned = lineage.assign_grouped(
                self.groups, ["development", "evaluation"], seed)
            by_split = {"development": [], "evaluation": []}
            for entry in self.entries:
                by_split[assigned[entry["key"]]].append(entry)
            self.assertEqual(lineage.split_violations(by_split), [], f"seed {seed}")

    def test_grouped_assignment_is_deterministic(self):
        first = lineage.assign_grouped(self.groups, ["development", "evaluation"], 7)
        second = lineage.assign_grouped(self.groups, ["development", "evaluation"], 7)
        self.assertEqual(first, second)


class TestLineageEdges(unittest.TestCase):
    """All three lineage edges: declared group, control twin, identical bytes."""

    def test_control_edges_union_across_declared_groups(self):
        # A variant and its named control share lineage even if a worker
        # mislabeled their group_ids — the edge, not the label, decides.
        control = helpers.corpus_entry("fam-control", group_id="g-wrong-a")
        variant = dict(helpers.corpus_entry("fam-variant", group_id="g-wrong-b"))
        variant["controls"] = ["fam-control"]
        groups = lineage.sibling_groups([control, variant])
        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(next(iter(groups.values()))), ["fam-control", "fam-variant"])

    def test_identical_bytes_share_lineage_across_families(self):
        # The real T05 case: F17 unreadable-control is literally the F03
        # raster-only file — identical sha256, different fixture families.
        fixture_manifest = json.loads((ROOT / "fixtures/manifest.json").read_text())
        groups = lineage.sibling_groups(fixture_manifest["entries"])
        scan = next(m for m in groups.values()
                    if "development/scan-raster-only.pdf" in m)
        self.assertIn("development/unreadable-control.pdf", scan)
        self.assertIn("development/scan-correct.pdf", scan)
        self.assertIn("development/scan-shifted.pdf", scan)

    def test_fixture_family_variants_cluster_with_controls(self):
        fixture_manifest = json.loads((ROOT / "fixtures/manifest.json").read_text())
        groups = lineage.sibling_groups(fixture_manifest["entries"])
        units = next(m for m in groups.values()
                     if "development/userunit-1.pdf" in m)
        self.assertEqual(
            set(units),
            {f"development/userunit-{u}.pdf" for u in ("0.5", "1", "2", "10")},
        )


class TestSplitAudit(unittest.TestCase):
    """The leakage audit over frozen manifests."""

    def test_moved_sibling_is_flagged(self):
        entries = sibling_family("gamma", 4) + sibling_family("delta", 4)
        by_split = {"development": entries[:-1], "evaluation": entries[-1:]}
        violations = lineage.split_violations(by_split)
        self.assertEqual(len(violations), 1)
        self.assertIn("straddles", violations[0])
        self.assertIn("delta", violations[0])

    def test_identical_bytes_in_two_splits_is_flagged(self):
        # Same bytes, different key and group: a copy cannot launder lineage.
        leaked = dict(helpers.corpus_entry("echo", sha256=helpers.doc_sha("original"),
                                           group_id="g-echo"))
        original = dict(helpers.corpus_entry("original", sha256=helpers.doc_sha("original"),
                                             group_id="g-original"))
        by_split = {"development": [original], "evaluation": [leaked]}
        violations = lineage.split_violations(by_split)
        self.assertTrue(violations)

    def test_committed_corpus_manifests_have_no_leakage(self):
        dev = manifest.load_manifest(MANIFESTS / "development.corpus.json")
        pub = manifest.load_manifest(MANIFESTS / "public.corpus.json")
        violations = lineage.split_violations(
            {"development": dev["entries"], "public_demo": pub["entries"]})
        self.assertEqual(violations, [])

    def test_public_siblings_cannot_enter_evaluation_denominator(self):
        # Take a real public group and redeclare one sibling as evaluation:
        # the audit must refuse, whichever edge carries the lineage.
        pub = manifest.load_manifest(MANIFESTS / "public.corpus.json")
        group = sorted({e["group_id"] for e in pub["entries"]})[0]
        members = [e for e in pub["entries"] if e["group_id"] == group]
        by_split = {
            "public_demo": members[:-1],
            "evaluation": members[-1:],
        }
        violations = lineage.split_violations(by_split)
        self.assertTrue(violations, "a public sibling reached the evaluation split")

    def test_evaluation_group_may_not_reuse_a_claim_split_group(self):
        dev = manifest.load_manifest(MANIFESTS / "development.corpus.json")
        member = dev["entries"][0]
        renamed = dict(member, key="eval-renamed", source_path="heldout/eval-renamed.pdf")
        violations = lineage.split_violations(
            {"development": [member], "evaluation": [renamed]})
        self.assertTrue(violations, "identical bytes under a new key passed the audit")

    def test_unknown_split_is_rejected(self):
        entry = helpers.corpus_entry("x")
        with self.assertRaises(lineage.LeakageError):
            lineage.split_violations({"staging": [entry]})


if __name__ == "__main__":
    unittest.main()
