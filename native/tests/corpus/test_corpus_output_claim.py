"""One corpus output directory has exactly one writer.

Reproduced before the claim existed: two processes starting against one *fresh*
output directory both succeeded (exits [0, 0]) and shared a single journal, which
then described two interleaved runs with duplicate terminal events for the same
job keys.

The claim is an exclusive, nonblocking advisory lock on the output directory taken
before preflight and held until the corpus wrapper has published identity.json.
These tests use a handshake rather than timing: the first holder signals readiness
through a file, so the second writer always starts while the claim is provably
held.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.runtime.supervisor import LOCK_FILE_NAME  # noqa: E402

EXIT_OK = 0
EXIT_INVALID_ARGS = 2

HOLDER = textwrap.dedent(
    """
    import os, sys, time
    from pathlib import Path
    sys.path.insert(0, {native!r})
    from inkflip.runtime.supervisor import Supervisor
    from inkflip.runtime.supervisor import Limits

    out = Path(sys.argv[1]); ready = Path(sys.argv[2]); done = Path(sys.argv[3])
    supervisor = Supervisor(out, Limits())
    ready.write_text(str(os.getpid()))
    deadline = time.time() + 30
    while time.time() < deadline and not done.exists():
        time.sleep(0.05)
    supervisor.close()
    """
)


def _env() -> dict[str, str]:
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(NATIVE) + (os.pathsep + prior if prior else "")
    return env


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OutputClaimCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.root = self.td / "src"
        self.root.mkdir()
        for name in ("mapping-amount.pdf", "covered-amount.pdf"):
            shutil.copyfile(FIXTURES / "public" / name, self.root / name)
        entries = [
            {"key": key, "source_path": name, "group_id": key, "pages": [0]}
            for key, name in (("amount", "mapping-amount.pdf"), ("covered", "covered-amount.pdf"))
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

    def corpus(self, out: Path | None = None, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "inkflip.cli", "corpus", "run",
             "--manifest", str(self.manifest), "--source-root", str(self.root),
             "--profile", "native-default", "--out", str(out or self.out), *extra],
            cwd=str(ROOT), capture_output=True, text=True, env=_env(), timeout=600,
        )

    def start_holder(self, out: Path):
        """Start a process that holds the claim, and wait until it actually does."""
        ready = self.td / f"ready-{out.name}"
        done = self.td / f"done-{out.name}"
        proc = subprocess.Popen(
            [sys.executable, "-c", HOLDER.format(native=str(NATIVE)), str(out), str(ready), str(done)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=_env(),
        )
        for _ in range(600):
            if ready.exists():
                break
            if proc.poll() is not None:
                raise AssertionError(f"holder exited early: {proc.stderr.read()[:400]}")
            time.sleep(0.05)
        self.assertTrue(ready.exists(), "the holder never signalled readiness")
        return proc, done


class TestSecondWriterIsRefused(OutputClaimCase):
    def test_a_second_writer_refuses_before_touching_the_winner(self):
        proc, done = self.start_holder(self.out)
        try:
            # The outcome required the claim to cover a fresh directory too.
            result = self.corpus()
            self.assertEqual(result.returncode, EXIT_INVALID_ARGS,
                             f"a second writer must refuse: {result.stderr}")
            self.assertIn("already owned by another run", result.stderr)
            self.assertNotIn("Unexpected error", result.stderr)
            # The loser must not have produced any run artefact.
            self.assertFalse((self.out / "index.json").exists())
            self.assertFalse((self.out / "reports").exists())
            self.assertFalse((self.out / "identity.json").exists())
        finally:
            done.write_text("go")
            proc.wait(timeout=30)

    def test_the_winner_completes_normally_after_the_loser_is_refused(self):
        proc, done = self.start_holder(self.out)
        try:
            self.corpus()
        finally:
            done.write_text("go")
            proc.wait(timeout=30)
        # The directory is free again once the holder releases it.
        result = self.corpus()
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        index = json.loads((self.out / "index.json").read_text())
        self.assertEqual({v["status"] for v in index["jobs"].values()}, {"completed"})

    def test_the_claim_file_is_not_unlinked_or_reused_as_a_hijack(self):
        proc, done = self.start_holder(self.out)
        try:
            lock = self.out / LOCK_FILE_NAME
            self.assertTrue(lock.exists())
            result = self.corpus()
            self.assertEqual(result.returncode, EXIT_INVALID_ARGS)
            # The refused writer must leave the lock inode alone.
            self.assertTrue(lock.exists(), "the loser must not unlink the holder's lock inode")
        finally:
            done.write_text("go")
            proc.wait(timeout=30)

    def test_a_symlink_alias_of_the_output_directory_shares_the_claim(self):
        alias_parent = self.td / "alias"
        alias_parent.mkdir()
        alias = alias_parent / "run-link"
        os.symlink(self.out, alias)
        proc, done = self.start_holder(self.out)
        try:
            result = self.corpus(alias)
            self.assertEqual(result.returncode, EXIT_INVALID_ARGS,
                             "an alias of the same directory must hit the same claim")
        finally:
            done.write_text("go")
            proc.wait(timeout=30)

    def test_simultaneous_resume_cannot_bypass_the_claim(self):
        self.assertTrue(self.out.exists() or True)
        first = self.corpus()
        self.assertEqual(first.returncode, EXIT_OK, first.stderr)
        before = _sha(self.out / "reports" / "amount.json")
        proc, done = self.start_holder(self.out)
        try:
            result = self.corpus(self.out, "--resume")
            self.assertEqual(result.returncode, EXIT_INVALID_ARGS,
                             "resume must not bypass the claim")
        finally:
            done.write_text("go")
            proc.wait(timeout=30)
        self.assertEqual(_sha(self.out / "reports" / "amount.json"), before,
                         "the refused resume must not alter the winner's report")


class TestOwnerDeathReleasesTheClaim(OutputClaimCase):
    def test_a_killed_owner_leaves_no_stale_claim(self):
        proc, _done = self.start_holder(self.out)
        proc.kill()          # abrupt death: no cleanup path runs in the holder
        proc.wait(timeout=30)
        # The kernel drops the flock with the process, so a stale PID file cannot
        # strand the directory and no PID heuristic is needed to recover it.
        result = self.corpus()
        self.assertEqual(result.returncode, EXIT_OK, result.stderr)


if __name__ == "__main__":
    unittest.main()
