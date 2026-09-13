"""Stored-run report keys must be unambiguous.

`_run_reports` derives a dict key from each report filename, stripping a
trailing `.inkflip`. `report.json` and `report.inkflip.json` therefore collapse
onto one key: before this guard the later file silently replaced the earlier
one, so a baseline could be built from fewer reports than the run directory
contains, with the outcome depending on glob order.

Reproduced here with two genuinely distinct reports on disk.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.baselines.engine import _run_reports, create_baseline  # noqa: E402
from inkflip.baselines.models import BaselineError  # noqa: E402
from inkflip.cli.main import EXIT_OK, main  # noqa: E402
from inkflip.contracts import core  # noqa: E402

AMOUNT = FIXTURES / "public" / "mapping-amount.pdf"


class RunReportAmbiguityCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.run = self.td / "run"
        (self.run / "reports").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def inspect(self, out: Path) -> dict:
        code = main(["inspect", str(AMOUNT), "--out", str(out)])
        self.assertEqual(code, EXIT_OK)
        data = json.loads(out.read_text())
        core.validate(data)
        return data

    def write_index(self, keys) -> None:
        (self.run / "index.json").write_text(
            json.dumps({"kind": "inkflip-run-index", "schema_version": "1.0.0", "status": "complete",
                        "jobs": {k: {"key": k, "status": "completed"} for k in keys}})
        )
        (self.run / "identity.json").write_text(
            json.dumps({"kind": "inkflip-corpus-identity", "corpus_manifest_sha256": "a" * 64,
                        "profile_sha256": "b" * 64, "profile_name": "native-default",
                        "algorithm_id": "inkflip-inspect-v1", "intended_keys": list(keys)})
        )


class TestCollisionIsRefused(RunReportAmbiguityCase):
    def test_two_files_normalising_to_one_key_are_refused(self):
        self.inspect(self.run / "reports" / "amount.json")
        self.inspect(self.run / "reports" / "amount.inkflip.json")
        on_disk = sorted(p.name for p in (self.run / "reports").glob("*.json"))
        self.assertEqual(on_disk, ["amount.inkflip.json", "amount.json"])
        with self.assertRaises(BaselineError) as ctx:
            _run_reports(self.run)
        message = str(ctx.exception)
        self.assertIn("Ambiguous stored-run reports", message)
        self.assertIn("amount.json", message)
        self.assertIn("amount.inkflip.json", message)

    def test_baseline_creation_refuses_the_ambiguous_run(self):
        self.inspect(self.run / "reports" / "amount.json")
        self.inspect(self.run / "reports" / "amount.inkflip.json")
        self.write_index(["amount"])
        out = self.td / "base.json"
        with self.assertRaises(BaselineError):
            create_baseline(self.run, None, out, "reviewer", "must not be built from partial evidence")
        self.assertFalse(out.exists(), "a refused ambiguous run must not produce a baseline")
        self.assertFalse(out.with_suffix(out.suffix + ".reports").exists())

    def test_distinct_keys_are_unaffected(self):
        self.inspect(self.run / "reports" / "amount.json")
        self.inspect(self.run / "reports" / "control.json")
        reports = _run_reports(self.run)
        self.assertEqual(sorted(reports), ["amount", "control"])

    def test_a_single_inkflip_suffixed_report_is_normalised_normally(self):
        self.inspect(self.run / "amount.inkflip.json")
        reports = _run_reports(self.run)
        self.assertEqual(sorted(reports), ["amount"])


if __name__ == "__main__":
    unittest.main()
