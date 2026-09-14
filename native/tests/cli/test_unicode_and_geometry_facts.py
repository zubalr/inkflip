"""Normalisation and geometry honesty through the real CLI.

Probed first, then pinned. Two properties matter to a consumer of a stored report:

* the normalised view is declared, not improvised - every run's `normalized_text`
  and `normalization_map` must be exactly what the shared normaliser produces, so a
  reader's raw text survives verbatim while the normalised view stays auditable;
* geometry is honest - a page-only reading must carry no polygon, and an absent
  page box must be declared rather than silently fabricated.

Reader granularity differs between engines (the native readers emit character-level
runs where a browser capture emits word-level ones), so assertions here are written
to hold at any granularity.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.contracts import core  # noqa: E402

MIXED_SCRIPT = FIXTURES / "development" / "native-unicode-control.pdf"
NATIVE_TEXT = FIXTURES / "development" / "native-unicode-native.pdf"
CONTROL = FIXTURES / "public" / "mapping-amount.pdf"
EXIT_OK = 0


def _env() -> dict[str, str]:
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(NATIVE) + (os.pathsep + prior if prior else "")
    return env


class UnicodeAndGeometryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def inspect(self, source: Path, *extra: str) -> dict:
        out = self.td / f"{source.stem}-{'-'.join(extra) or 'default'}.json"
        result = subprocess.run(
            [sys.executable, "-m", "inkflip.cli", "inspect", str(source), "--out", str(out), *extra],
            cwd=str(ROOT), capture_output=True, text=True, env=_env(), timeout=300,
        )
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        payload = json.loads(out.read_text())
        core.validate(payload)
        return payload


class TestNormalisationIsDeclared(UnicodeAndGeometryCase):
    def test_every_run_reports_the_shared_normalised_view(self):
        for source in (MIXED_SCRIPT, NATIVE_TEXT, CONTROL):
            with self.subTest(fixture=source.name):
                payload = self.inspect(source)
                self.assertTrue(payload["occurrences"])
                for run in payload["occurrences"]:
                    normalized, mapping = core.normalize(run["raw_text"])
                    self.assertEqual(run["normalized_text"], normalized)
                    self.assertEqual(run["normalization_map"], mapping)

    def test_raw_text_is_preserved_verbatim(self):
        """The raw view is the reader's own output; normalisation never rewrites it."""
        payload = self.inspect(MIXED_SCRIPT)
        joined = "".join(run["raw_text"] for run in payload["occurrences"])
        self.assertIn("LATIN", joined)
        # The map must cover the raw text exactly, so the verbatim view stays
        # reconstructible from the declared mapping rather than being lost.
        for run in payload["occurrences"]:
            mapping = run["normalization_map"]
            self.assertTrue(mapping, "every run must declare its normalization map")
            cursor = 0
            for entry in sorted(mapping, key=lambda e: e["raw_start"]):
                self.assertEqual(entry["raw_start"], cursor, "the map must cover raw text without gaps")
                self.assertGreater(entry["raw_end"], entry["raw_start"])
                cursor = entry["raw_end"]
            self.assertEqual(cursor, len(run["raw_text"]), "the map must cover the whole raw text")

    def test_runs_are_not_reshaped_into_words(self):
        """Granularity is the reader's, not the contract's: the native readers emit
        character-level runs here, and nothing may silently regroup them."""
        payload = self.inspect(NATIVE_TEXT)
        widths = {len(run["raw_text"]) for run in payload["occurrences"]}
        self.assertTrue(max(widths) <= 2, f"unexpected regrouped runs: {widths}")

    def test_currency_and_sign_survive_extraction(self):
        payload = self.inspect(CONTROL)
        joined = "".join(run["raw_text"] for run in payload["occurrences"])
        self.assertIn("$", joined, "the currency sign must survive extraction")
        normalized_joined = "".join(run["normalized_text"] for run in payload["occurrences"])
        self.assertIn("$", normalized_joined)


class TestGeometryHonesty(UnicodeAndGeometryCase):
    def test_page_only_readings_carry_no_polygon(self):
        payload = self.inspect(CONTROL, "--reader", "pypdf")
        for run in payload["occurrences"]:
            geometry = run["geometry"]
            if geometry["precision"] in ("page_only", "unknown"):
                self.assertIsNone(geometry["polygon"], "a page-only reading must not carry a polygon")

    def test_a_declared_page_box_is_reported_not_nulled(self):
        payload = self.inspect(CONTROL)
        page = payload["pages"][0]
        self.assertEqual(page["media_box"], [0.0, 0.0, 520.0, 400.0])
        self.assertEqual(page["effective_view_box"], [0.0, 0.0, 520.0, 400.0])

    def test_an_absent_page_box_is_declared_as_a_limitation(self):
        """Where the selected API cannot expose the original box, the report says so
        instead of inventing one."""
        for fixture in sorted((FIXTURES / "public").glob("mapping-*.pdf")):
            payload = self.inspect(fixture, "--reader", "pypdf")
            page = payload["pages"][0]
            if page["media_box"] is None or page["crop_box"] is None:
                self.assertTrue(
                    any("media_box" in text or "crop_box" in text for text in page["limitations"]),
                    f"{fixture.name} hides an absent page box without declaring it",
                )


if __name__ == "__main__":
    unittest.main()
