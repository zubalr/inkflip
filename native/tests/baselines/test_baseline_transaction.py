"""Baseline creation must be a transaction, not a half-visible bundle.

Before this guard `create_baseline` created the `.reports` sidecar, wrote every
backing report into it, and only then wrote the baseline manifest. A failure
between those steps left a partial sidecar with no manifest — and because the
overwrite guard refuses an existing sidecar, the operator could not retry and
could not cleanly recover.

The failure is injected at the real write boundary, so the test exercises the
actual commit order rather than a description of it.
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

from inkflip.baselines import engine  # noqa: E402
from inkflip.baselines.engine import create_baseline  # noqa: E402
from inkflip.baselines.models import BaselineError  # noqa: E402
from inkflip.cli.main import EXIT_OK, main  # noqa: E402
from inkflip.contracts import core  # noqa: E402

AMOUNT = FIXTURES / "public" / "mapping-amount.pdf"


class BaselineTransactionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.run = self._make_run(self.td / "run", ("amount", "control"))

    def tearDown(self):
        self.tmp.cleanup()

    def _make_run(self, directory: Path, keys) -> Path:
        reports = directory / "reports"
        reports.mkdir(parents=True)
        for key in keys:
            out = reports / f"{key}.json"
            self.assertEqual(main(["inspect", str(AMOUNT), "--out", str(out)]), EXIT_OK)
        (directory / "index.json").write_text(json.dumps(
            {"kind": "inkflip-run-index", "schema_version": "1.0.0", "status": "complete",
             "jobs": {k: {"key": k, "status": "completed"} for k in keys}}))
        (directory / "identity.json").write_text(json.dumps(
            {"kind": "inkflip-corpus-identity", "corpus_manifest_sha256": "a" * 64,
             "profile_sha256": "b" * 64, "profile_name": "native-default",
             "algorithm_id": "inkflip-inspect-v1", "intended_keys": list(keys)}))
        return directory

    def _bundle(self, out: Path):
        sidecar = out.with_suffix(out.suffix + ".reports")
        staging = out.with_name(out.name + ".staging")
        return out, sidecar, staging


class TestInterruptedCreationLeavesNothing(TransactionCase := BaselineTransactionCase):
    def _fail_on_nth_write(self, n: int):
        original = engine.atomic_write_bytes
        calls = {"n": 0}

        def flaky(path, data):
            calls["n"] += 1
            if calls["n"] == n:
                raise OSError("injected write failure")
            return original(path, data)

        return original, flaky

    def test_failure_during_backing_report_writes_leaves_no_bundle(self):
        out, sidecar, staging = self._bundle(self.td / "base.json")
        original, flaky = self._fail_on_nth_write(2)
        engine.atomic_write_bytes = flaky
        try:
            with self.assertRaises(OSError):
                create_baseline(self.run, None, out, "reviewer", "injected")
        finally:
            engine.atomic_write_bytes = original
        self.assertFalse(out.exists(), "no baseline manifest may survive a failed attempt")
        self.assertFalse(sidecar.exists(), "no sidecar may survive a failed attempt")
        self.assertFalse(staging.exists(), "no staging directory may survive a failed attempt")

    def test_failure_at_the_manifest_write_removes_the_promoted_sidecar(self):
        out, sidecar, staging = self._bundle(self.td / "base.json")
        original, flaky = self._fail_on_nth_write(3)  # 2 reports, then the manifest
        engine.atomic_write_bytes = flaky
        try:
            with self.assertRaises(OSError):
                create_baseline(self.run, None, out, "reviewer", "injected")
        finally:
            engine.atomic_write_bytes = original
        self.assertFalse(out.exists())
        self.assertFalse(sidecar.exists(), "a half-valid bundle must not survive")
        self.assertFalse(staging.exists())

    def test_a_retry_after_a_failed_attempt_succeeds(self):
        out, sidecar, staging = self._bundle(self.td / "base.json")
        original, flaky = self._fail_on_nth_write(1)
        engine.atomic_write_bytes = flaky
        try:
            with self.assertRaises(OSError):
                create_baseline(self.run, None, out, "reviewer", "injected")
        finally:
            engine.atomic_write_bytes = original
        record = create_baseline(self.run, None, out, "reviewer", "retry after recovery")
        core.validate(record)
        self.assertTrue(out.is_file())
        self.assertTrue(sidecar.is_dir())
        self.assertEqual(len(list(sidecar.glob("*.json"))), 2)


class TestSuccessfulCreationIsUnchanged(BaselineTransactionCase):
    def test_valid_creation_commits_both_parts_and_no_staging(self):
        out, sidecar, staging = self._bundle(self.td / "ok.json")
        record = create_baseline(self.run, None, out, "reviewer", "approved")
        core.validate(record)
        self.assertTrue(out.is_file())
        self.assertTrue(sidecar.is_dir())
        self.assertFalse(staging.exists(), "staging must not outlive a successful commit")
        self.assertEqual(len(list(sidecar.glob("*.json"))), 2)

    def test_existing_baseline_is_still_never_overwritten(self):
        out, _sidecar, _staging = self._bundle(self.td / "keep.json")
        create_baseline(self.run, None, out, "reviewer", "first")
        before = out.read_bytes()
        with self.assertRaises(BaselineError):
            create_baseline(self.run, None, out, "reviewer", "second")
        self.assertEqual(out.read_bytes(), before)

    def test_a_leftover_staging_directory_is_refused_with_a_clear_reason(self):
        out, _sidecar, staging = self._bundle(self.td / "stuck.json")
        staging.mkdir()
        with self.assertRaises(BaselineError) as ctx:
            create_baseline(self.run, None, out, "reviewer", "third")
        self.assertIn("staging directory already exists", str(ctx.exception))
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
