"""Corpus failure isolation: an unreadable neighbour must not sink the run.

Measured first with a digest-correct but uninspectable PDF between two valid
neighbours. With jobs=1 the run isolates the failure: the two valid jobs complete
and their committed reports survive, the broken job reaches an honest terminal
state, and the run reports the partial outcome. Resume then reuses the two valid
reports byte-for-byte and re-attempts only the failure.

The jobs>1 request is covered too: the supervisor requires an explicit CPU/RAM
admission that no declared machine budget currently supplies, so the request must
surface as an actionable configuration error. It previously escaped as an
untranslated internal error with exit 4 because the Supervisor constructor was
outside the error translation.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
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

EXIT_INVALID_ARGS = 2
EXIT_PARTIAL_RUN = 3


def _env() -> dict[str, str]:
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(NATIVE) + (os.pathsep + prior if prior else "")
    return env


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CorpusFailureIsolationCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.root = self.td / "src"
        self.root.mkdir()
        for name, origin in (
            ("mapping-amount.pdf", FIXTURES / "public"),
            ("covered-amount.pdf", FIXTURES / "public"),
            ("bad-pdf-malformed.pdf", FIXTURES / "development"),
        ):
            shutil.copyfile(origin / name, self.root / name)
        entries = [
            {"key": "a-valid", "source_path": "mapping-amount.pdf", "group_id": "a", "pages": [0]},
            {"key": "b-corrupt", "source_path": "bad-pdf-malformed.pdf", "group_id": "b", "pages": [0]},
            {"key": "c-valid", "source_path": "covered-amount.pdf", "group_id": "c", "pages": [0]},
        ]
        for entry in entries:
            entry["sha256"] = _sha(self.root / entry["source_path"])
        self.manifest = self.td / "corpus.json"
        self.manifest.write_text(json.dumps({
            "kind": "corpus_manifest",
            "schema_version": "1.0.0",
            "split": "public_demo",
            "source_root_policy": "explicit_local_root_no_symlinks",
            "entries": entries,
        }))
        self.out = self.td / "run"

    def tearDown(self):
        self.tmp.cleanup()

    def corpus(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "inkflip.cli", "corpus", "run",
             "--manifest", str(self.manifest), "--source-root", str(self.root),
             "--profile", "native-default", "--out", str(self.out), *extra],
            cwd=str(ROOT), capture_output=True, text=True, env=_env(), timeout=900,
        )

    def states(self) -> dict:
        index = json.loads((self.out / "index.json").read_text())
        return {key: entry["status"] for key, entry in index["jobs"].items()}


class TestFailureIsolation(CorpusFailureIsolationCase):
    def test_a_broken_neighbour_leaves_valid_reports_and_an_honest_terminal_state(self):
        result = self.corpus()
        self.assertEqual(result.returncode, EXIT_PARTIAL_RUN, result.stderr)
        self.assertEqual(self.states(), {"a-valid": "completed", "b-corrupt": "failed", "c-valid": "completed"})
        self.assertTrue((self.out / "reports" / "a-valid.json").is_file())
        self.assertTrue((self.out / "reports" / "c-valid.json").is_file())
        self.assertFalse((self.out / "reports" / "b-corrupt.json").is_file(),
                         "a failed job must not leave a success-looking report")

    def test_resume_reuses_the_valid_reports_verbatim_and_retries_only_the_failure(self):
        self.corpus()
        before = {name: _sha(self.out / "reports" / name)
                  for name in ("a-valid.json", "c-valid.json")}
        result = self.corpus("--resume")
        self.assertEqual(result.returncode, EXIT_PARTIAL_RUN, result.stderr)
        self.assertEqual(self.states(), {"a-valid": "skipped", "b-corrupt": "failed", "c-valid": "skipped"})
        after = {name: _sha(self.out / "reports" / name)
                 for name in ("a-valid.json", "c-valid.json")}
        self.assertEqual(before, after, "resumed reports must be reused byte-for-byte")

    def test_no_orphan_temp_files_survive_a_completed_run(self):
        """The scratch root may persist; nothing may be left inside it.

        Measured: `out/scratch` remains as an empty directory after a completed
        run while every per-job directory is cleaned, so the invariant worth
        pinning is the absence of leftover files, not the absence of the root.
        """
        result = self.corpus()
        self.assertEqual(result.returncode, EXIT_PARTIAL_RUN)
        leftover = [p for p in (self.out / "scratch").rglob("*") if p.is_file()] if (self.out / "scratch").is_dir() else []
        self.assertEqual(leftover, [], f"orphan temp files: {leftover}")


class TestUnsupportedConcurrencyIsAConfigurationError(CorpusFailureIsolationCase):
    def test_jobs_above_one_reports_an_actionable_configuration_error(self):
        result = self.corpus("--jobs", "3")
        self.assertEqual(result.returncode, EXIT_INVALID_ARGS,
                         f"expected a configuration error, got {result.returncode}: {result.stderr}")
        self.assertNotIn("Unexpected error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("ParallelAdmission", result.stderr)
        self.assertFalse((self.out / "index.json").exists(),
                         "a refused concurrency request must not start a run")

    def test_jobs_equal_to_one_is_accepted(self):
        self.assertEqual(self.corpus("--jobs", "1").returncode, EXIT_PARTIAL_RUN)


if __name__ == "__main__":
    unittest.main()
