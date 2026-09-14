"""Committed fixture facts asserted through the real CLI.

The family tests read fixture bytes; these run the shipped CLI over the same
fixtures and assert that the produced report carries the fixture's declared facts.
Probed first, then pinned. One observation is recorded rather than repaired: the
native reader emits character-level occurrences where the browser capture emitted
word-level ones, so assertions here are stated in a granularity-independent way.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
PUBLIC = FIXTURES / "public"
DEVELOPMENT = FIXTURES / "development"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.contracts import core  # noqa: E402

EXIT_OK = 0


def _env() -> dict[str, str]:
    import os
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(NATIVE) + (os.pathsep + prior if prior else "")
    return env


class FixtureThroughCliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def inspect(self, source: Path, *extra: str) -> dict:
        out = self.td / f"{source.stem}-{' '.join(extra) if extra else 'default'}.inkflip.json"
        result = subprocess.run(
            [sys.executable, "-m", "inkflip.cli", "inspect", str(source), "--out", str(out), *extra],
            cwd=str(ROOT), capture_output=True, text=True, env=_env(), timeout=180,
        )
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        payload = json.loads(out.read_text())
        core.validate(payload)
        return payload


class TestGeometryFactsSurviveTheCli(FixtureThroughCliCase):
    def test_rotation_and_userunit_match_the_fixture_declaration(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotate=rotation):
                source = PUBLIC / f"geometry-{rotation}.pdf"
                declared = int(re.search(rb"/Rotate (-?\d+)", source.read_bytes()).group(1))
                payload = self.inspect(source, "--pages", "1")
                page = payload["pages"][0]
                self.assertEqual(declared, rotation)
                self.assertEqual(page["rotation"], declared, "the report must carry the page rotation")
                self.assertEqual(page["user_unit"], 2.0, "the fixture declares /UserUnit 2")
                box = page["effective_view_box"]
                expected = [2.0 * (box[2] - box[0]), 2.0 * (box[3] - box[1])]
                self.assertAlmostEqual(page["canonical_size_pt"][0], expected[0], places=4)
                self.assertAlmostEqual(page["canonical_size_pt"][1], expected[1], places=4)

    def test_zero_origin_control_differs_from_the_rotated_family(self):
        control = self.inspect(PUBLIC / "geometry-control.pdf")["pages"][0]
        rotated = self.inspect(PUBLIC / "geometry-90.pdf")["pages"][0]
        self.assertEqual(control["user_unit"], 1.0)
        self.assertEqual(control["effective_view_box"], [0.0, 0.0, 520.0, 400.0])
        self.assertEqual(rotated["effective_view_box"][0], 20.0)
        self.assertEqual(rotated["rotation"], 90)


class TestDuplicatesRemainAddressableThroughTheCli(FixtureThroughCliCase):
    def test_four_amounts_survive_as_separate_addressable_runs(self):
        payload = self.inspect(DEVELOPMENT / "duplicates-four.pdf")
        occurrences = payload["occurrences"]
        ids = [o["id"] for o in occurrences]
        self.assertEqual(len(ids), len(set(ids)), "occurrence ids must stay unique")

        # Granularity-independent: the emitted runs, read in order, must contain the
        # four amounts, and each amount's leading run must have its own anchor.
        joined = "".join(o["raw_text"] for o in occurrences)
        self.assertEqual(joined.count("$100"), 4, f"four amounts must survive extraction, got {joined!r}")
        anchors = {
            (round(o["geometry"]["polygon"][0][0], 2), round(o["geometry"]["polygon"][0][1], 2))
            for o in occurrences
            if o["raw_text"].startswith("$")
        }
        self.assertEqual(len(anchors), 4, "each amount keeps a distinct anchor")

    def test_native_reader_granularity_is_recorded_not_assumed(self):
        """Observation, recorded: the native reader emits character-level runs here
        where the browser capture emitted word-level ones. Assertions above are
        therefore granularity-independent, and this pins the actual shape so a future
        change in reader granularity is visible rather than silently absorbed."""
        payload = self.inspect(DEVELOPMENT / "duplicates-four.pdf")
        texts = [o["raw_text"] for o in payload["occurrences"]]
        self.assertGreater(len(texts), 4, "the native reader is character-granular for this fixture")
        self.assertTrue(all(len(t) <= 2 for t in texts), f"unexpected run widths: {texts}")
        self.assertEqual(payload["readers"][0]["method"], "native_text")


class TestWhitespaceAndCapabilityAreDeclared(FixtureThroughCliCase):
    def test_whitespace_runs_keep_their_normalization_map(self):
        payload = self.inspect(DEVELOPMENT / "duplicates-four.pdf")
        runs = [o for o in payload["occurrences"] if o["raw_text"] != o["raw_text"].strip()]
        self.assertTrue(runs, "this fixture produces runs carrying whitespace")
        for run in runs:
            normalized, mapping = core.normalize(run["raw_text"])
            self.assertEqual(run["normalized_text"], normalized)
            self.assertEqual(run["normalization_map"], mapping)
            self.assertIn("whitespace", {m["operation"] for m in mapping})

    def test_unsupported_capability_is_declared_by_the_reader(self):
        payload = self.inspect(PUBLIC / "mapping-amount.pdf", "--reader", "pypdf")
        capabilities = {c["name"]: c["support"] for reader in payload["readers"] for c in reader["capabilities"]}
        self.assertEqual(capabilities.get("native_text"), "supported")
        self.assertNotIn("ocr", capabilities, "a text-only reader must not claim OCR")
        self.assertIn(capabilities.get("crop_metadata"), {"approximate", "supported", "unavailable"})

    def test_report_declares_its_limitations_rather_than_implying_completeness(self):
        payload = self.inspect(PUBLIC / "mapping-amount.pdf")
        self.assertTrue(payload["limitations"], "a report must state its limitations")
        for reader in payload["readers"]:
            for capability in reader["capabilities"]:
                if capability["support"] != "unavailable":
                    self.assertTrue(
                        capability["limits"], "a supported capability must state its limits"
                    )


if __name__ == "__main__":
    unittest.main()
