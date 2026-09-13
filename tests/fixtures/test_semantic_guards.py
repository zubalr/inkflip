"""Data-level semantic guards over the shipped examples (implementation wave 2026-09-13).

Four properties the gallery and the report contract depend on, checked against
the real committed example reports and the real staged PDFs rather than against
any presentation text:

1. individually addressable duplicate occurrences;
2. order-only changes (same content multiset, different emission order);
3. honest geometry - no report claims a polygon it does not have, and page size
   always agrees with UserUnit * effective view box;
4. source/report identity - every report binds the staged PDF bytes and its own
   sealed identity recomputes.

The last class is a static guard that keeps the corrected clean-checkout repair
intact: nothing under tests/fixtures may reach into an untracked working-record
directory, which is exactly the fault that made `test:fixtures` fail on a fresh
checkout. The guard is pure text inspection - it needs no git and no audit
artifacts.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native"
EXAMPLES = ROOT / "apps" / "web" / "public" / "examples"

if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.contracts import core  # noqa: E402


def cards() -> list[dict]:
    return json.loads((EXAMPLES / "index.json").read_text())["cards"]


def card(card_id: str) -> dict:
    return json.loads((EXAMPLES / card_id / "manifest.json").read_text())


def report(card_id: str, role: str = "source") -> dict:
    manifest = card(card_id)
    return json.loads((EXAMPLES / card_id / manifest["files"][role]["report_file"]).read_text())


def all_reports():
    for entry in cards():
        manifest = card(entry["example_id"])
        for role, spec in manifest["files"].items():
            path = EXAMPLES / entry["example_id"] / spec["report_file"]
            if path.is_file():
                yield entry["example_id"], role, json.loads(path.read_text()), spec


class TestDuplicateOccurrencesAreIndividuallyAddressable(unittest.TestCase):
    def test_duplicates_card_keeps_four_separate_occurrences(self):
        payload = report("duplicates")
        amounts = [occ for occ in payload["occurrences"] if occ["raw_text"] == "$100"]
        self.assertGreaterEqual(len(amounts), 4, "every repeated amount must stay its own occurrence")
        ids = [occ["id"] for occ in amounts]
        self.assertEqual(len(ids), len(set(ids)), "duplicate readings may not share an occurrence id")

    def test_duplicate_occurrences_keep_distinct_geometry(self):
        payload = report("duplicates")
        amounts = [occ for occ in payload["occurrences"] if occ["raw_text"] == "$100"]
        anchors = {(round(occ["geometry"]["polygon"][0][0], 3), round(occ["geometry"]["polygon"][0][1], 3)) for occ in amounts}
        self.assertGreaterEqual(len(anchors), 2, "repeated amounts must remain spatially distinguishable")

    def test_a_string_match_cannot_collapse_them(self):
        """A naive text index collapses duplicates; occurrence ids must not."""
        payload = report("duplicates")
        by_text = Counter(occ["raw_text"] for occ in payload["occurrences"])
        self.assertGreaterEqual(by_text["$100"], 4)
        self.assertEqual(len({occ["id"] for occ in payload["occurrences"]}), len(payload["occurrences"]))

    def test_duplicate_occurrences_validate(self):
        payload = report("duplicates")
        core.validate(payload)

    def test_collapsing_occurrence_ids_is_rejected(self):
        """Counterfactual: the validator must refuse a collapsed duplicate set."""
        payload = json.loads(json.dumps(report("duplicates")))
        payload["occurrences"].append(json.loads(json.dumps(payload["occurrences"][0])))
        with self.assertRaises(core.ContractError) as ctx:
            core.validate(payload)
        self.assertEqual(ctx.exception.code, "ID")


class TestOrderOnlyChange(unittest.TestCase):
    def test_reading_order_card_changes_order_but_not_content(self):
        control = report("reading-order", "source")
        reordered = report("reading-order", "control")
        left = [occ["normalized_text"] for occ in control["occurrences"] if occ["normalized_text"].strip()]
        right = [occ["normalized_text"] for occ in reordered["occurrences"] if occ["normalized_text"].strip()]
        self.assertEqual(Counter(left), Counter(right), "the content multiset must be identical")
        self.assertNotEqual(left, right, "the emitted order must differ")

    def test_order_change_is_reported_without_a_correctness_verdict(self):
        payload = report("reading-order", "source")
        kinds = {finding["kind"] for finding in payload["findings"]}
        self.assertTrue(kinds, "the order change must be surfaced as a finding")
        self.assertNotIn("safe", json.dumps(payload).lower())
        for finding in payload["findings"]:
            self.assertTrue(finding["limitations"], "a finding must carry its limitation")


class TestGeometryHonesty(unittest.TestCase):
    def test_every_shipped_report_states_geometry_it_actually_has(self):
        checked = 0
        for card_id, role, payload, _spec in all_reports():
            with self.subTest(card=card_id, role=role):
                core.validate(payload)
                for page in payload["pages"]:
                    box = page["effective_view_box"]
                    self.assertIsNotNone(box)
                    expected = [page["user_unit"] * (box[2] - box[0]), page["user_unit"] * (box[3] - box[1])]
                    for actual, want in zip(page["canonical_size_pt"], expected):
                        self.assertAlmostEqual(actual, want, places=4)
                    if page["media_box"] is None or page["crop_box"] is None:
                        self.assertTrue(
                            any("media_box" in text or "crop_box" in text for text in page["limitations"]),
                            "an absent page box must be declared as a limitation",
                        )
                checked += 1
        self.assertGreater(checked, 0)

    def test_precision_and_polygon_never_disagree(self):
        for card_id, role, payload, _spec in all_reports():
            for collection in ("occurrences",):
                for item in payload.get(collection, []):
                    geometry = item["geometry"]
                    with self.subTest(card=card_id, role=role, item=item["id"]):
                        if geometry["precision"] in ("unknown", "page_only"):
                            self.assertIsNone(geometry["polygon"])
                        else:
                            self.assertIsNotNone(geometry["polygon"])

    def test_page_only_geometry_is_accepted_but_not_invented(self):
        """The contract permits page-level geometry; it forbids a fake polygon."""
        payload = json.loads(json.dumps(report("amount")))
        payload["occurrences"][0]["geometry"] = {
            "precision": "page_only",
            "space": payload["occurrences"][0]["geometry"]["space"],
            "polygon": None,
            "transform_ids": [],
            "basis": "reader reported page-level location only",
        }
        core.validate(core.seal(payload))
        payload["occurrences"][0]["geometry"]["polygon"] = [[0, 0], [1, 0], [1, 1]]
        with self.assertRaises(core.ContractError) as ctx:
            core.validate(payload)
        self.assertEqual(ctx.exception.code, "GEOMETRY")


class TestSourceAndReportIdentity(unittest.TestCase):
    def test_every_report_binds_the_staged_source_bytes(self):
        checked = 0
        for card_id, role, payload, spec in all_reports():
            with self.subTest(card=card_id, role=role):
                staged = EXAMPLES / card_id / spec["filename"]
                self.assertTrue(staged.is_file(), f"{staged} must be staged")
                digest = hashlib.sha256(staged.read_bytes()).hexdigest()
                self.assertEqual(payload["document"]["sha256"], digest)
                self.assertEqual(payload["document"]["byte_length"], staged.stat().st_size)
                checked += 1
        self.assertEqual(checked, 22, "all six cards' captured reports must be checked")

    def test_every_report_seal_recomputes(self):
        for card_id, role, payload, _spec in all_reports():
            with self.subTest(card=card_id, role=role):
                self.assertEqual(payload["report_id"], core.report_digest(json.loads(json.dumps(payload))))
                self.assertEqual(payload["execution"]["run_key"], core.run_key(json.loads(json.dumps(payload))))

    def test_a_tampered_document_digest_is_rejected(self):
        """Counterfactual: source identity is enforced, not decorative."""
        payload = json.loads(json.dumps(report("amount")))
        payload["document"]["sha256"] = "b" * 64
        with self.assertRaises(core.ContractError):
            core.validate(payload)


class TestCleanCheckoutGuard(unittest.TestCase):
    """Static guard keeping the FND-001 clean-checkout repair intact."""

    FORBIDDEN = ("artifacts/tasks", "artifacts/", "handoffs/", "dsfa-")

    def sources(self) -> list[Path]:
        return sorted(
            path for path in (ROOT / "tests" / "fixtures").glob("*.py")
            if path.name != Path(__file__).name
        )

    def test_no_fixture_test_reads_a_working_records_directory(self):
        offenders = []
        for path in self.sources():
            text = "\n".join(
                line.split("#", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
            )
            for needle in self.FORBIDDEN:
                if needle in text:
                    offenders.append(f"{path.name}: {needle}")
        self.assertEqual(offenders, [], "fixture tests must not depend on untracked working records")

    def test_no_fixture_test_hardcodes_an_absolute_audit_path(self):
        offenders = []
        for path in self.sources():
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    continue
                if "openclaw-autoclaw" in stripped or "/Code/Projects/" in stripped:
                    offenders.append(f"{path.name}: {stripped[:80]}")
        self.assertEqual(offenders, [])

    def test_the_restored_baseline_lives_under_tracked_test_data(self):
        baseline = ROOT / "tests" / "fixtures" / "data" / "baseline-hashes.json"
        self.assertTrue(baseline.is_file(), "the priority-catalog baseline must live under tests/fixtures/data")
        self.assertEqual(ROOT / "tests" / "fixtures" / "data", baseline.parent)
        self.assertEqual(len(json.loads(baseline.read_text())), 32)


if __name__ == "__main__":
    unittest.main()
