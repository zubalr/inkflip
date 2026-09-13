"""Resume integrity: stale success and same-output contention (Section B).

`test_corpus.py` already covers "resume skips an unchanged completed report" and
"resume refuses a changed source or manifest". These are the two behaviours it
did not pin, both exercised as real corpus runs against the pinned interpreter:

* a completed job whose committed report bytes no longer verify must be re-run,
  never reported as `skipped` — a stale success file is not current evidence;
* a second non-resume run into a directory that already holds a run must refuse
  clearly rather than interleave a success-looking index.

The tamper cases are the counterfactual: they take a genuinely completed run and
break exactly the thing resume relies on.
"""
from __future__ import annotations

import hashlib
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

from inkflip.corpus.manifest import CorpusError  # noqa: E402
from inkflip.corpus.runner import run_corpus  # noqa: E402

AMOUNT = FIXTURES / "public" / "mapping-amount.pdf"
CONTROL = FIXTURES / "public" / "mapping-control.pdf"


class CorpusResumeIntegrityCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.source_root = FIXTURES / "public"
        self.manifest = self._manifest("mapping-amount.pdf", "amount")
        self.out = self.td / "run"

    def tearDown(self):
        self.tmp.cleanup()

    def _manifest(self, filename: str, key: str) -> Path:
        payload = {
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "split": "public_demo",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "entries": [
                {
                    "key": key,
                    "source_path": filename,
                    "sha256": hashlib.sha256((self.source_root / filename).read_bytes()).hexdigest(),
                    "group_id": key,
                    "pages": [0],
                }
            ],
        }
        path = self.td / f"manifest-{key}.json"
        path.write_text(json.dumps(payload))
        return path

    def run_once(self, *, resume: bool = False, manifest: Path | None = None):
        return run_corpus(
            manifest_path=manifest or self.manifest,
            source_root=self.source_root,
            profile="native-default",
            out_dir=self.out,
            jobs=1,
            resume=resume,
        )

    def job_states(self) -> dict:
        index = json.loads((self.out / "index.json").read_text())
        return {key: entry.get("status") for key, entry in index["jobs"].items()}

    def report_path(self, key: str = "amount") -> Path:
        return self.out / "reports" / f"{key}.json"


class TestStaleSuccessIsNeverReused(CorpusResumeIntegrityCase):
    def test_an_intact_result_is_skipped_not_rerun(self):
        self.run_once()
        self.assertEqual(self.job_states(), {"amount": "completed"})
        before = self.report_path().read_bytes()
        self.run_once(resume=True)
        self.assertEqual(self.job_states(), {"amount": "skipped"})
        self.assertEqual(self.report_path().read_bytes(), before, "a skip must reuse bytes verbatim")

    def test_a_tampered_result_is_rerun_not_skipped(self):
        self.run_once()
        report = self.report_path()
        payload = json.loads(report.read_bytes())
        payload["report_id"] = "0" * 64
        report.write_text(json.dumps(payload))
        self.run_once(resume=True)
        states = self.job_states()
        self.assertNotIn("skipped", states.values(), "a stale success file must not count as current")
        self.assertEqual(states, {"amount": "completed"})
        index = json.loads((self.out / "index.json").read_text())
        self.assertEqual(
            index["jobs"]["amount"]["report_sha256"],
            hashlib.sha256(report.read_bytes()).hexdigest(),
            "the index must record the bytes actually on disk",
        )

    def test_a_truncated_result_is_rerun_not_skipped(self):
        self.run_once()
        report = self.report_path()
        report.write_bytes(report.read_bytes()[: len(report.read_bytes()) // 2])
        self.run_once(resume=True)
        self.assertEqual(self.job_states(), {"amount": "completed"})
        json.loads(report.read_text())  # the re-run must leave a parseable report


class TestSameOutputContention(CorpusResumeIntegrityCase):
    def test_a_second_non_resume_run_is_refused(self):
        self.run_once()
        before = self.report_path().read_bytes()
        with self.assertRaises(CorpusError) as ctx:
            self.run_once(resume=False)
        self.assertIn("already holds a run", str(ctx.exception))
        self.assertEqual(self.report_path().read_bytes(), before, "a refused run must not touch evidence")

    def test_a_changed_identity_on_resume_is_refused(self):
        self.run_once()
        other = self._manifest("mapping-control.pdf", "amount")
        with self.assertRaises(CorpusError) as ctx:
            self.run_once(resume=True, manifest=other)
        self.assertIn("identity changed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
