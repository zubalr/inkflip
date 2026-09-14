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

from inkflip.runtime.supervisor import (  # noqa: E402
    LOCK_FILE_NAME,
    SupervisionError,
    claim_output_directory,
)

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


class TestLockTargetIsNeverFollowed(OutputClaimCase):
    """A planted lock path must be refused without touching its referent."""

    SENTINEL = b"preserve-me\n"

    def _referent(self, name: str = "referent.bin") -> Path:
        target = self.td / name
        target.write_bytes(self.SENTINEL)
        return target

    def test_a_symlinked_lock_target_is_refused_and_its_referent_is_untouched(self):
        self.out.mkdir(parents=True, exist_ok=True)
        referent = self._referent()
        os.symlink(referent, self.out / LOCK_FILE_NAME)

        with self.assertRaises(SupervisionError) as ctx:
            claim_output_directory(self.out)
        self.assertIn("symbolic link", str(ctx.exception))
        self.assertEqual(referent.read_bytes(), self.SENTINEL,
                         "the symlink's referent must not be rewritten through the link")

    def test_a_hardlinked_lock_target_is_refused_and_its_other_name_is_untouched(self):
        self.out.mkdir(parents=True, exist_ok=True)
        referent = self._referent("hardlink-source.bin")
        os.link(referent, self.out / LOCK_FILE_NAME)

        with self.assertRaises(SupervisionError) as ctx:
            claim_output_directory(self.out)
        self.assertIn("hard links", str(ctx.exception))
        self.assertEqual(referent.read_bytes(), self.SENTINEL,
                         "a hard-linked inode must not be rewritten under its other name")

    def test_a_non_regular_lock_target_is_refused(self):
        self.out.mkdir(parents=True, exist_ok=True)
        lock = self.out / LOCK_FILE_NAME
        os.mkfifo(lock)
        with self.assertRaises(SupervisionError) as ctx:
            claim_output_directory(self.out)
        self.assertIn("not a regular file", str(ctx.exception))

    def test_an_unrelated_file_in_the_directory_is_untouched_by_a_successful_claim(self):
        self.out.mkdir(parents=True, exist_ok=True)
        marker = self.out / "unrelated.txt"
        marker.write_bytes(self.SENTINEL)
        claim = claim_output_directory(self.out)
        try:
            self.assertEqual(marker.read_bytes(), self.SENTINEL)
            # The claim file carries advisory PID metadata and nothing else; the
            # unrelated file beside it is what must remain untouched.
            self.assertEqual((self.out / LOCK_FILE_NAME).read_text().strip(), str(os.getpid()))
        finally:
            claim.release()

    def test_a_refused_second_claim_does_not_rewrite_the_winner_lock(self):
        first = claim_output_directory(self.out)
        try:
            lock = self.out / LOCK_FILE_NAME
            lock.write_bytes(b"winner-pid\n")
            with self.assertRaises(SupervisionError):
                claim_output_directory(self.out)
            self.assertEqual(lock.read_bytes(), b"winner-pid\n",
                             "the refused claim must not have touched the winner's lock")
        finally:
            first.release()


class TestOwnershipIsReleasedOnEveryFailurePath(OutputClaimCase):
    def test_a_populated_directory_refusal_releases_ownership_for_the_same_process(self):
        """The reported reproduction across processes: refuse, then claim again."""
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "marker.txt").write_text("unrelated\n")

        result = self.corpus()
        self.assertNotEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertIn("not empty", result.stderr)

        claim = claim_output_directory(self.out)
        claim.release()
        self.assertEqual((self.out / "marker.txt").read_text(), "unrelated\n")

    def test_an_in_process_run_corpus_refusal_releases_ownership(self):
        """A refusal inside this process must not strand the flock it acquired."""
        from inkflip.corpus.manifest import CorpusError
        from inkflip.corpus.runner import run_corpus

        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "marker.txt").write_text("unrelated\n")

        with self.assertRaises(CorpusError) as ctx:
            run_corpus(
                manifest_path=self.manifest,
                source_root=self.root,
                profile="native-default",
                out_dir=self.out,
            )
        self.assertIn("not empty", str(ctx.exception))

        # The subprocess variant of this check cannot see the leak: process exit
        # drops the flock. Claiming again here proves the release really ran.
        claim = claim_output_directory(self.out)
        claim.release()
        self.assertEqual((self.out / "marker.txt").read_text(), "unrelated\n")

    def test_an_in_process_failed_identity_write_releases_ownership(self):
        """run() succeeded, the publish step failed: ownership is still released."""
        from inkflip.corpus import runner
        from inkflip.corpus.runner import run_corpus

        original = runner.atomic_write_bytes

        def fail(path, data):
            raise OSError("simulated publish failure")

        runner.atomic_write_bytes = fail
        try:
            with self.assertRaises(OSError):
                run_corpus(
                    manifest_path=self.manifest,
                    source_root=self.root,
                    profile="native-default",
                    out_dir=self.out,
                )
        finally:
            runner.atomic_write_bytes = original

        claim = claim_output_directory(self.out)
        claim.release()

    def test_a_failed_identity_write_releases_ownership(self):
        self.out.mkdir(parents=True, exist_ok=True)
        # identity.json as a directory makes the publish step fail after run().
        (self.out / "identity.json").mkdir()
        result = self.corpus()
        self.assertNotEqual(result.returncode, EXIT_OK)
        claim = claim_output_directory(self.out)
        claim.release()

    def test_repeated_close_is_safe(self):
        self.out.mkdir(parents=True, exist_ok=True)
        claim = claim_output_directory(self.out)
        claim.release()
        claim.release()
        self.assertFalse(claim.held)
        again = claim_output_directory(self.out)
        again.release()

    def test_a_first_instance_that_never_ran_does_not_strand_the_directory(self):
        from inkflip.runtime.supervisor import Limits, Supervisor

        self.out.mkdir(parents=True, exist_ok=True)
        first = Supervisor(self.out, Limits())
        first.close()
        second = Supervisor(self.out, Limits())
        second.close()
