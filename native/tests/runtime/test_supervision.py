"""T29 native parent-supervision tests (TEST-29).

Real spawned fault-injection children (never mocks of the supervisor itself):
hang, native-like SIGSEGV crash, memory growth, stdout/stderr flood,
SIGTERM-ignoring workers, descendant leakers, empty/missing output, retry
exhaustion and the committed F20 ``worker-fault-*`` scenarios through
``tests/fixtures/fault_double.py``. Covers atomic per-file reports, the
append-only journal, bounded retry, byte-stable successes and Ctrl-C
termination with a valid partial artifact.

Invariants: I05 (every planned job reaches a terminal record), I17 (bounded
work; a failed/killed job never erases unrelated completed evidence).
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"
WORKER = Path(__file__).resolve().parent / "fault_worker.py"
DRIVER = Path(__file__).resolve().parent / "supervisor_driver.py"
FAULT_DOUBLE = ROOT / "tests" / "fixtures" / "fault_double.py"

sys.path.insert(0, str(NATIVE))

from inkflip.runtime import (  # noqa: E402
    JobSpec,
    Limits,
    ParallelAdmission,
    SupervisionError,
    Supervisor,
    read_journal,
)

BASE_ENV_KEYS = {
    "LANG", "LC_ALL", "TMPDIR",
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "PYTHONIOENCODING",
}
# Platform-injected keys that appear at exec regardless of the parent's
# environment (Darwin libSystem); not inherited ambient variables.
PLATFORM_ENV_KEYS = {
    "darwin": {"__CF_USER_TEXT_ENCODING"},
    "linux": set(),
}.get(sys.platform, set())


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def wait_pid_dead(pid: int, timeout: float = 4.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not pid_alive(pid):
            return True
        time.sleep(0.02)
    return not pid_alive(pid)


def spec(key: str, *worker_args: str, **kwargs) -> JobSpec:
    return JobSpec(key=key, argv=[sys.executable, str(WORKER), *worker_args], **kwargs)


def limits(**overrides) -> Limits:
    base = dict(
        wall_seconds=5.0,
        memory_bytes=256 << 20,
        max_stdout_bytes=64 << 10,
        max_stderr_bytes=64 << 10,
        max_report_bytes=1 << 20,
        scratch_bytes=8 << 20,
        retries=1,
        jobs=1,
        kill_grace_seconds=0.3,
        poll_interval_seconds=0.02,
        rss_probe_interval_seconds=0.05,
    )
    base.update(overrides)
    return Limits(**base)


def journal_events(path: Path, run_id: str | None = None) -> list[dict]:
    records = list(read_journal(path))
    if run_id is not None:
        records = [r for r in records if r.get("run_id") == run_id]
    return records


def job_pids(path: Path, run_id: str, job_key: str) -> list[int]:
    return [
        r["pid"]
        for r in journal_events(path, run_id)
        if r.get("event") == "child_spawned" and r.get("job") == job_key
    ]


class TestSpawnAndClassification(unittest.TestCase):
    """Injected hang/crash/OOM/flood is classified AND bounded."""

    def test_completed_job_commits_report_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Supervisor(Path(tmp) / "run", limits()).run(
                [spec("file-a", "report", "--text", "$100", produces="report.json")]
            )
            self.assertEqual(result.status, "complete")
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "completed")
            self.assertEqual(record.attempts, 1)
            self.assertEqual(record.exit_code, 0)
            committed = (Path(tmp) / "run" / "reports" / "file-a.json").read_bytes()
            self.assertEqual(
                committed,
                b'{"kind":"worker-report","text":"$100"}\n',
            )
            self.assertEqual(record.report_sha256, __import__("hashlib").sha256(committed).hexdigest())

    def test_hang_is_bounded_timeout_and_retried_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            started = time.monotonic()
            result = Supervisor(Path(tmp) / "run", limits(wall_seconds=0.4)).run(
                [spec("file-a", "hang")]
            )
            elapsed = time.monotonic() - started
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "timeout")
            self.assertEqual(record.failure_kind, "wall")
            self.assertEqual(record.attempts, 2)  # one retry, then terminal
            self.assertLess(elapsed, 4.0)  # bounded: 2 x (0.4 wall + grace)
            for pid in job_pids(Path(tmp) / "run" / "journal.jsonl", result.run_id, "file-a"):
                self.assertFalse(pid_alive(pid), f"stray child {pid}")

    def test_sigsegv_crash_classified_and_retried_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Supervisor(Path(tmp) / "run", limits()).run(
                [spec("file-a", "crash")]
            )
            record = result.jobs["file-a"]
            self.assertEqual(result.status, "failed")
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.failure_kind, "crash")
            self.assertEqual(record.signal, "SIGSEGV")
            self.assertEqual(record.attempts, 2)

    def test_nonzero_exit_classified_and_retried_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Supervisor(Path(tmp) / "run", limits()).run(
                [spec("file-a", "exit-fail", "--code", "17")]
            )
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.failure_kind, "exit")
            self.assertEqual(record.exit_code, 17)
            self.assertEqual(record.attempts, 2)

    def test_transient_failure_succeeds_on_single_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "attempt-marker"
            result = Supervisor(Path(tmp) / "run", limits()).run(
                [spec("file-a", "fail-once", "--state", str(state), produces="report.json")]
            )
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "completed")
            self.assertEqual(record.attempts, 2)  # exactly one retry
            self.assertEqual(
                json.loads((Path(tmp) / "run" / "reports" / "file-a.json").read_bytes())["text"],
                "second-attempt",
            )

    def test_retry_is_bounded_to_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Supervisor(Path(tmp) / "run", limits(retries=1)).run(
                [spec("file-a", "crash")]
            )
            journal = Path(tmp) / "run" / "journal.jsonl"
            spawns = [
                r for r in journal_events(journal, result.run_id)
                if r.get("event") == "child_spawned" and r.get("job") == "file-a"
            ]
            retries = [
                r for r in journal_events(journal, result.run_id)
                if r.get("event") == "job_retry" and r.get("job") == "file-a"
            ]
            self.assertEqual(len(spawns), 2)  # initial + exactly one retry
            self.assertEqual(len(retries), 1)

    def test_stdout_flood_is_bounded_and_classified(self):
        with tempfile.TemporaryDirectory() as tmp:
            started = time.monotonic()
            result = Supervisor(Path(tmp) / "run", limits(max_stdout_bytes=16 << 10)).run(
                [spec("file-a", "flood")]
            )
            elapsed = time.monotonic() - started
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.failure_kind, "output_limit")
            self.assertIn("stdout", record.reason)
            self.assertGreaterEqual(record.stdout_bytes, 16 << 10)
            self.assertLess(record.stdout_bytes, (16 << 10) + (256 << 10))  # bounded capture
            self.assertLess(elapsed, 4.0)
            for pid in job_pids(Path(tmp) / "run" / "journal.jsonl", result.run_id, "file-a"):
                self.assertFalse(pid_alive(pid), f"stray flooder {pid}")

    def test_stderr_flood_is_bounded_and_classified(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Supervisor(Path(tmp) / "run", limits(max_stderr_bytes=16 << 10)).run(
                [spec("file-a", "flood", "--stderr")]
            )
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.failure_kind, "output_limit")
            self.assertIn("stderr", record.reason)

    def test_post_reap_output_overflow_is_classified(self):
        # Regression for the post-reap drain hole (review F1): sibling A
        # leaves a SIGTERM-ignoring stray, so _cleanup_strays blocks the
        # parent loop for ~kill_grace while sibling B writes over-cap stdout
        # and exits 0. B's bytes are only drained by _drain_until_eof AFTER
        # B is reaped — killed_cause is never set — yet the cap violation
        # must still classify failed/output_limit, never "completed" with
        # recorded stdout_bytes over the cap.
        with tempfile.TemporaryDirectory() as tmp:
            pids_file = Path(tmp) / "pids.json"
            admission = ParallelAdmission(
                cpu_count=max(2, os.cpu_count() or 2), memory_bytes=64 << 30
            )
            result = Supervisor(
                Path(tmp) / "run",
                limits(jobs=2, max_stdout_bytes=8 << 10, kill_grace_seconds=0.8),
                parallel_admission=admission,
            ).run(
                [
                    spec(
                        "file-a", "leak-stubborn-grandchild",
                        "--pids-file", str(pids_file),
                        produces="report.json",
                    ),
                    # Delayed burst: writes land inside A's cleanup window
                    # and are drained only after B is reaped.
                    spec("file-b", "delayed-flood", "--seconds", "0.6", "--bytes", "12288"),
                    spec("file-c", "report", produces="report.json"),
                ]
            )
            a, b, c = result.jobs["file-a"], result.jobs["file-b"], result.jobs["file-c"]
            self.assertEqual(b.status, "failed")
            self.assertEqual(b.failure_kind, "output_limit")
            self.assertGreater(b.stdout_bytes, 8 << 10)
            self.assertEqual(b.attempts, 1)  # output violations are never retried
            self.assertEqual(a.status, "completed")
            self.assertTrue(a.stray_descendants)
            self.assertEqual(c.status, "completed")  # under-cap output unaffected
            pids = json.loads(pids_file.read_text())
            self.assertTrue(wait_pid_dead(pids["grandchild"]), "stubborn stray survived")

    def test_memory_growth_is_bounded_and_classified(self):
        with tempfile.TemporaryDirectory() as tmp:
            started = time.monotonic()
            result = Supervisor(Path(tmp) / "run", limits(memory_bytes=128 << 20)).run(
                [spec("file-a", "oom", "--chunk-mb", "8", "--hold")]
            )
            elapsed = time.monotonic() - started
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.failure_kind, "memory_limit")
            self.assertEqual(record.attempts, 1)  # resource violations are not retried
            self.assertLess(elapsed, 15.0)  # bounded, never the child's full hold
            for pid in job_pids(Path(tmp) / "run" / "journal.jsonl", result.run_id, "file-a"):
                self.assertFalse(pid_alive(pid), f"stray oom child {pid}")

    def test_sigterm_ignoring_child_is_killed(self):
        with tempfile.TemporaryDirectory() as tmp:
            started = time.monotonic()
            result = Supervisor(Path(tmp) / "run", limits(wall_seconds=0.4)).run(
                [spec("file-a", "term-ignorer")]
            )
            elapsed = time.monotonic() - started
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "timeout")
            self.assertEqual(record.signal, "SIGKILL")  # grace expired -> forced
            self.assertEqual(record.attempts, 2)
            self.assertLess(elapsed, 6.0)
            for pid in job_pids(Path(tmp) / "run" / "journal.jsonl", result.run_id, "file-a"):
                self.assertFalse(pid_alive(pid), f"unkillable child {pid}")

    def test_empty_success_is_completed_and_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Supervisor(Path(tmp) / "run", limits()).run([spec("file-a", "empty")])
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "completed")
            self.assertEqual(record.attempts, 1)
            self.assertIsNone(record.report_path)

    def test_missing_declared_output_fails_and_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Supervisor(Path(tmp) / "run", limits()).run(
                [spec("file-a", "empty", produces="report.json")]
            )
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.failure_kind, "missing_output")
            self.assertEqual(record.attempts, 1)

    def test_spawn_error_is_classified_and_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Supervisor(Path(tmp) / "run", limits()).run(
                [JobSpec(key="file-a", argv=["/nonexistent/inkflip-worker-xyz"])]
            )
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.failure_kind, "spawn_error")
            self.assertEqual(record.attempts, 2)  # transient: one bounded retry

    def test_leaked_descendant_is_reaped_after_completed_leader(self):
        with tempfile.TemporaryDirectory() as tmp:
            pids_file = Path(tmp) / "pids.json"
            result = Supervisor(Path(tmp) / "run", limits()).run(
                [spec("file-a", "leak-grandchild", "--pids-file", str(pids_file),
                       produces="report.json")]
            )
            record = result.jobs["file-a"]
            self.assertEqual(record.status, "completed")
            self.assertTrue(record.stray_descendants)
            pids = json.loads(pids_file.read_text())
            self.assertTrue(wait_pid_dead(pids["grandchild"]), "leaked grandchild survived")
            events = journal_events(Path(tmp) / "run" / "journal.jsonl", result.run_id)
            self.assertTrue(any(e.get("event") == "descendants_reaped" for e in events))

    def test_run_deadline_preempts_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Supervisor(
                Path(tmp) / "run",
                limits(wall_seconds=5.0, run_wall_seconds=0.5),
            ).run([spec("file-a", "hang"), spec("file-b", "report", produces="report.json")])
            a, b = result.jobs["file-a"], result.jobs["file-b"]
            self.assertEqual(a.status, "timeout")
            self.assertEqual(a.failure_kind, "run_deadline")
            self.assertEqual(a.attempts, 1)  # no room left for the retry
            self.assertEqual(b.status, "timeout")
            self.assertEqual(b.failure_kind, "run_deadline")


class TestArtifacts(unittest.TestCase):
    """Atomic per-file writes and the immutable journal."""

    def test_no_tmp_siblings_or_scratch_left_after_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            Supervisor(out, limits()).run(
                [
                    spec("file-a", "report", produces="report.json"),
                    spec("file-b", "crash"),
                ]
            )
            for path in out.rglob("*"):
                self.assertNotIn(".tmp-", path.name, f"temp sibling left: {path}")
            self.assertEqual(list((out / "scratch").iterdir()), [])
            for report in (out / "reports").iterdir():
                json.loads(report.read_bytes())  # every committed report is valid JSON

    def test_journal_is_complete_append_only_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            result = Supervisor(out, limits()).run(
                [spec("file-a", "report", produces="report.json"), spec("file-b", "crash")]
            )
            records = journal_events(out / "journal.jsonl")
            self.assertGreaterEqual(len(records), 8)
            kinds = {r["event"] for r in records}
            self.assertTrue(
                {"run_started", "job_queued", "child_spawned", "child_reaped",
                 "job_terminal", "report_committed", "job_retry", "run_terminal"} <= kinds
            )
            self.assertEqual(
                [r["seq"] for r in records], list(range(1, len(records) + 1))
            )
            run2 = Supervisor(out, limits(), resume=True).run(
                [spec("file-a", "report", produces="report.json"), spec("file-b", "crash")]
            )
            before = (out / "journal.jsonl").read_bytes()
            # run 2 must only have appended: journal from run 1 is a strict prefix.
            run1_bytes = b"".join(
                (json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n").encode()
                for r in records
            )
            self.assertTrue(before.startswith(run1_bytes))
            self.assertGreater(len(before), len(run1_bytes))
            self.assertNotEqual(run2.run_id, result.run_id)

    def test_index_covers_every_planned_job_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            Supervisor(out, limits()).run(
                [spec("file-a", "report", produces="report.json"), spec("file-b", "crash")]
            )
            index = json.loads((out / "index.json").read_bytes())
            self.assertEqual(index["kind"], "inkflip-run-index")
            self.assertEqual(index["status"], "partial")
            self.assertEqual(index["jobs"]["file-a"]["status"], "completed")
            self.assertEqual(index["jobs"]["file-b"]["status"], "failed")
            self.assertEqual(index["jobs"]["file-b"]["failure_kind"], "crash")
            self.assertIn("rlimit_support", index)
            self.assertIn(index["platform"], ("darwin", "linux"))


class TestByteStabilityAndResume(unittest.TestCase):
    """Successful files are byte-stable; resume never silently reruns them."""

    def test_identical_runs_produce_byte_identical_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [spec("file-a", "report", "--text", "$100", produces="report.json")]
            Supervisor(Path(tmp) / "run1", limits()).run(jobs)
            Supervisor(Path(tmp) / "run2", limits()).run(jobs)
            self.assertEqual(
                (Path(tmp) / "run1" / "reports" / "file-a.json").read_bytes(),
                (Path(tmp) / "run2" / "reports" / "file-a.json").read_bytes(),
            )

    def test_resume_skips_verified_completed_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            jobs = [
                spec("file-a", "report", "--text", "$100", produces="report.json"),
                spec("file-b", "crash"),
            ]
            first = Supervisor(out, limits()).run(jobs)
            self.assertEqual(first.status, "partial")
            report_before = (out / "reports" / "file-a.json").read_bytes()
            second = Supervisor(out, limits(), resume=True).run(jobs)
            a, b = second.jobs["file-a"], second.jobs["file-b"]
            self.assertEqual(a.status, "skipped")
            self.assertEqual(a.attempts, 0)
            self.assertEqual(b.status, "failed")
            self.assertEqual(b.attempts, 2)  # failed job reruns with its retry
            report_after = (out / "reports" / "file-a.json").read_bytes()
            self.assertEqual(report_before, report_after)  # byte-stable
            run2_events = journal_events(out / "journal.jsonl", second.run_id)
            self.assertFalse(
                any(e.get("event") == "child_spawned" and e.get("job") == "file-a" for e in run2_events),
                "resumed run silently respawned a completed job",
            )
            self.assertTrue(
                any(e.get("event") == "job_skipped" and e.get("job") == "file-a" for e in run2_events)
            )

    def test_resume_refuses_changed_config_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            Supervisor(out, limits()).run(
                [spec("file-a", "report", "--text", "$100", produces="report.json")]
            )
            index_before = (out / "index.json").read_bytes()
            journal_before = (out / "journal.jsonl").read_bytes()
            with self.assertRaises(SupervisionError):
                Supervisor(out, limits(), resume=True).run(
                    [spec("file-a", "report", "--text", "$200", produces="report.json")]
                )
            self.assertEqual((out / "index.json").read_bytes(), index_before)
            self.assertEqual((out / "journal.jsonl").read_bytes(), journal_before)

    def test_resume_binds_declared_env_values(self):
        # Review F3: the config digest must bind declared env names AND
        # values — a changed value under identical key names must not
        # silently reuse prior completed evidence (old code hashed only the
        # key names, so a changed value resumed as "skipped"). Identical
        # env still verifies and skips.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            jobs_one = [
                spec("file-a", "env-report", produces="report.json",
                     env={"INKFLIP_EXTRA": "value-one"})
            ]
            first = Supervisor(out, limits()).run(jobs_one)
            self.assertEqual(first.jobs["file-a"].status, "completed")
            index_before = (out / "index.json").read_bytes()
            journal_before = (out / "journal.jsonl").read_bytes()
            # Changed env VALUE, identical key names -> changed identity ->
            # refused BEFORE any writes (old code would have skipped).
            with self.assertRaises(SupervisionError):
                Supervisor(out, limits(), resume=True).run(
                    [
                        spec("file-a", "env-report", produces="report.json",
                             env={"INKFLIP_EXTRA": "value-two"})
                    ]
                )
            self.assertEqual((out / "index.json").read_bytes(), index_before)
            self.assertEqual((out / "journal.jsonl").read_bytes(), journal_before)
            second = Supervisor(out, limits(), resume=True).run(jobs_one)
            self.assertEqual(second.jobs["file-a"].status, "skipped")


class TestCancellation(unittest.TestCase):
    """Ctrl-C terminates descendants and leaves a valid partial artifact."""

    def test_sigint_to_driver_kills_process_group_and_keeps_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            pids_file = Path(tmp) / "pids.json"
            run_result_file = Path(tmp) / "run-result.json"
            spec_doc = {
                "limits": {"wall_seconds": 30.0, "kill_grace_seconds": 0.3},
                "run_result_file": str(run_result_file),
                "jobs": [
                    {"key": "file-a", "worker_args": ["report"], "produces": "report.json"},
                    {"key": "file-b", "worker_args": ["hang-grandchild", "--pids-file", str(pids_file)]},
                    {"key": "file-c", "worker_args": ["report"], "produces": "report.json"},
                ],
            }
            spec_file = Path(tmp) / "spec.json"
            spec_file.write_text(json.dumps(spec_doc))
            driver = subprocess.Popen(
                [sys.executable, str(DRIVER), str(spec_file), str(out)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # driver in own group; Ctrl-C hits only it
            )
            try:
                deadline = time.monotonic() + 10.0
                while not pids_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(pids_file.exists(), "worker never reported pids")
                os.killpg(driver.pid, signal.SIGINT)  # Ctrl-C to the supervisor
                out_pipe, err_pipe = driver.communicate(timeout=10)
            finally:
                if driver.poll() is None:
                    driver.kill()
                    driver.communicate()
            self.assertEqual(driver.returncode, 0, err_pipe.decode()[-500:])
            # descendants of BOTH the driver's direct child and its grandchild
            pids = json.loads(pids_file.read_text())
            self.assertTrue(wait_pid_dead(pids["child"]), "supervised child survived Ctrl-C")
            self.assertTrue(wait_pid_dead(pids["grandchild"]), "grandchild survived Ctrl-C")
            # a valid partial artifact exists and parses
            index = json.loads((out / "index.json").read_bytes())
            self.assertEqual(index["status"], "cancelled")
            self.assertEqual(index["jobs"]["file-a"]["status"], "completed")
            self.assertEqual(index["jobs"]["file-b"]["status"], "cancelled")
            self.assertEqual(index["jobs"]["file-c"]["status"], "cancelled")
            report = json.loads((out / "reports" / "file-a.json").read_bytes())
            self.assertEqual(report["kind"], "worker-report")
            records = journal_events(out / "journal.jsonl")
            self.assertTrue(any(r.get("event") == "cancel_requested" for r in records))
            self.assertEqual(records[-1]["event"], "run_terminal")
            result_doc = json.loads(run_result_file.read_text())
            self.assertEqual(result_doc["status"], "cancelled")

    def test_in_process_sigint_cancels_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Supervisor(Path(tmp) / "run", limits()).run(
                [
                    spec("file-a", "report", produces="report.json"),
                    spec("file-b", "sigint-parent"),
                    spec("file-c", "report", produces="report.json"),
                ]
            )
            self.assertEqual(result.status, "cancelled")
            self.assertEqual(result.jobs["file-a"].status, "completed")
            self.assertEqual(result.jobs["file-b"].status, "cancelled")
            self.assertEqual(result.jobs["file-c"].status, "cancelled")
            index = json.loads((Path(tmp) / "run" / "index.json").read_bytes())
            self.assertEqual(index["status"], "cancelled")


class TestJobsAdmission(unittest.TestCase):
    """Default jobs=1; concurrency requires explicit CPU/RAM-aware admission."""

    def test_default_jobs_is_one(self):
        self.assertEqual(Limits().jobs, 1)
        self.assertEqual(limits().jobs, 1)

    def test_jobs_two_requires_explicit_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SupervisionError):
                Supervisor(Path(tmp) / "run", limits(jobs=2))
            with self.assertRaises(SupervisionError):
                Supervisor(
                    Path(tmp) / "run",
                    limits(jobs=4, memory_bytes=1 << 30),
                    parallel_admission=ParallelAdmission(cpu_count=8, memory_bytes=2 << 30),
                )

    def test_admitted_parallel_jobs_run_concurrently(self):
        with tempfile.TemporaryDirectory() as tmp:
            admission = ParallelAdmission(
                cpu_count=max(2, os.cpu_count() or 2), memory_bytes=64 << 30
            )
            started = time.monotonic()
            result = Supervisor(
                Path(tmp) / "run", limits(jobs=2), parallel_admission=admission
            ).run(
                [
                    spec("file-a", "slow-report", "--seconds", "1.2", produces="report.json"),
                    spec("file-b", "slow-report", "--seconds", "1.2", produces="report.json"),
                ]
            )
            elapsed = time.monotonic() - started
            self.assertEqual(result.status, "complete")
            self.assertLess(elapsed, 2.2)  # sequential would exceed 2.4s

    def test_admitted_jobs_overlap_proven_by_handshake_not_by_timing(self):
        """Two admitted children are live at the same instant, proven by the
        children's own announcements rather than by a duration threshold.

        The budget is an explicit disposable test input: two child slots and 2 GiB
        of admitted RAM, with each child bounded to 64 MiB so both fit. It says
        nothing about this machine.
        """
        with tempfile.TemporaryDirectory() as tmp:
            markers = Path(tmp) / "markers"
            admission = ParallelAdmission(cpu_count=2, memory_bytes=2 << 30)
            supervisor = Supervisor(
                Path(tmp) / "run",
                limits(jobs=2, memory_bytes=64 << 20, wall_seconds=60.0),
                parallel_admission=admission,
            )
            jobs = [
                spec(
                    f"file-{key}",
                    "barrier-report",
                    "--key",
                    f"file-{key}",
                    "--markers",
                    str(markers),
                    produces="report.json",
                )
                for key in ("a", "b")
            ]
            errors: list[BaseException] = []

            def drive() -> None:
                try:
                    supervisor.run(jobs)
                except BaseException as exc:  # pragma: no cover - reported below
                    errors.append(exc)

            worker = threading.Thread(target=drive, daemon=True)
            worker.start()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if len(list(markers.glob("*.started"))) == 2:
                    break
                time.sleep(0.02)

            started = sorted(markers.glob("*.started"))
            released = sorted(markers.glob("*.released"))
            self.assertEqual(len(started), 2, "both admitted children must reach their handshake")
            self.assertEqual(
                released, [], "neither child had been released, so both were alive simultaneously"
            )

            for marker in started:
                marker.with_name(marker.name.replace(".started", ".release")).write_text("go")
            worker.join(60)
            supervisor.close()
            self.assertEqual(errors, [], f"the admitted run must complete: {errors}")
            self.assertEqual(sorted(p.name for p in (Path(tmp) / "run" / "reports").glob("*.json")),
                             ["file-a.json", "file-b.json"])

    def test_peak_admission_refuses_more_jobs_than_admitted_cpus(self):
        """Peak admission is the declared budget, not the requested job count."""
        with tempfile.TemporaryDirectory() as tmp:
            admission = ParallelAdmission(cpu_count=2, memory_bytes=2 << 30)
            with self.assertRaises(SupervisionError) as ctx:
                Supervisor(
                    Path(tmp) / "run", limits(jobs=3), parallel_admission=admission
                )
            self.assertIn("exceeds admitted CPU count", str(ctx.exception))

    def test_peak_admission_refuses_more_children_than_the_admitted_ram_allows(self):
        with tempfile.TemporaryDirectory() as tmp:
            admission = ParallelAdmission(cpu_count=8, memory_bytes=100 << 20)
            with self.assertRaises(SupervisionError) as ctx:
                Supervisor(
                    Path(tmp) / "run",
                    limits(jobs=2, memory_bytes=64 << 20),
                    parallel_admission=admission,
                )
            self.assertIn("exceeds admitted budget", str(ctx.exception))


class TestEnvironmentAndThreads(unittest.TestCase):
    """Minimal child env allowlist; supervision is process-based, no threads."""

    def test_child_environment_is_the_declared_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["INKFLIP_PARENT_SECRET"] = "must-not-leak"
            try:
                result = Supervisor(Path(tmp) / "run", limits()).run(
                    [
                        spec(
                            "file-a", "env-report",
                            produces="report.json",
                            env={"INKFLIP_EXTRA": "declared"},
                        )
                    ]
                )
            finally:
                del os.environ["INKFLIP_PARENT_SECRET"]
            self.assertEqual(result.status, "complete")
            report = json.loads((Path(tmp) / "run" / "reports" / "file-a.json").read_bytes())
            self.assertEqual(
                set(report["env_keys"]),
                BASE_ENV_KEYS | PLATFORM_ENV_KEYS | {"INKFLIP_EXTRA"},
            )
            self.assertNotIn("INKFLIP_PARENT_SECRET", report["env_keys"])
            spawn = next(
                r for r in journal_events(Path(tmp) / "run" / "journal.jsonl", result.run_id)
                if r.get("event") == "child_spawned"
            )
            self.assertIn("INKFLIP_EXTRA", spawn["env_keys"])
            self.assertNotIn("INKFLIP_PARENT_SECRET", spawn["env_keys"])

    def test_env_extra_cannot_redeclare_fixed_allowlist(self):
        # Review F2: a spec-level TMPDIR override would escape the scratch
        # bound and a *_NUM_THREADS override would defeat the thread pin,
        # invisibly (the journal records only key names). Refused outright.
        with tempfile.TemporaryDirectory() as tmp:
            for key in ("TMPDIR", "OMP_NUM_THREADS", "LANG"):
                with self.subTest(key=key):
                    with self.assertRaises(SupervisionError):
                        Supervisor(Path(tmp) / "run", limits()).run(
                            [
                                spec(
                                    "file-a", "env-report",
                                    produces="report.json",
                                    env={key: "override"},
                                )
                            ]
                        )
            # Adding a NEW name alongside the fixed set is still allowed.
            result = Supervisor(Path(tmp) / "run2", limits()).run(
                [spec("file-a", "env-report", produces="report.json", env={"INKFLIP_EXTRA": "ok"})]
            )
            self.assertEqual(result.jobs["file-a"].status, "completed")

    def test_supervision_uses_processes_not_threads(self):
        before = len(threading.enumerate())
        with tempfile.TemporaryDirectory() as tmp:
            Supervisor(Path(tmp) / "run", limits()).run(
                [spec("file-a", "report", produces="report.json")]
            )
        self.assertEqual(len(threading.enumerate()), before)


class TestWorkerFaultFixtures(unittest.TestCase):
    """F20 worker-fault-* scenarios (g78) driven under real supervision."""

    def run_double(self, variant: str, **overrides):
        scenario = FIXTURES / "development" / f"worker-fault-{variant}.json"
        self.assertTrue(scenario.is_file(), scenario)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result = Supervisor(Path(tmp.name) / "run", limits(**overrides)).run(
            [JobSpec(key=variant, argv=[sys.executable, str(FAULT_DOUBLE), str(scenario)])]
        )
        return result, Path(tmp.name) / "run"

    def test_control_scenario_completes(self):
        result, _ = self.run_double("control")
        self.assertEqual(result.jobs["control"].status, "completed")
        self.assertEqual(result.status, "complete")

    def test_crash_scenario_is_classified_and_retried_once(self):
        result, _ = self.run_double("crash")
        record = result.jobs["crash"]
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.failure_kind, "exit")  # double exits 17
        self.assertEqual(record.attempts, 2)

    def test_hang_and_cancel_scenarios_are_bounded(self):
        for variant in ("hang", "cancel"):
            with self.subTest(variant=variant):
                started = time.monotonic()
                result, run_dir = self.run_double(variant, wall_seconds=0.3)
                record = result.jobs[variant]
                self.assertEqual(record.status, "timeout")
                self.assertEqual(record.attempts, 2)
                self.assertLess(time.monotonic() - started, 4.0)
                for pid in job_pids(run_dir / "journal.jsonl", result.run_id, variant):
                    self.assertFalse(pid_alive(pid))

    def test_stale_and_model_failure_scenarios_terminate(self):
        # The doubles exit 0 after emitting their event streams; rejecting a
        # stale event semantically is the message coordinator's domain (T11),
        # while the process supervisor's contract here is a bounded terminal.
        for variant in ("stale", "model-failure"):
            with self.subTest(variant=variant):
                result, _ = self.run_double(variant)
                self.assertEqual(result.jobs[variant].status, "completed")


class TestValidation(unittest.TestCase):
    """Plan/spec refusals are loud, before any child spawns."""

    def test_invalid_specs_and_empty_plan_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SupervisionError):
                Supervisor(Path(tmp) / "run", limits()).run([])
            with self.assertRaises(SupervisionError):
                Supervisor(Path(tmp) / "run", limits()).run(
                    [JobSpec(key="bad key!", argv=["/bin/true"])]
                )
            with self.assertRaises(SupervisionError):
                Supervisor(Path(tmp) / "run", limits()).run(
                    [JobSpec(key="ok", argv=[])]
                )
            with self.assertRaises(SupervisionError):
                Supervisor(Path(tmp) / "run", limits()).run(
                    [spec("dup", "empty"), spec("dup", "empty")]
                )
            with self.assertRaises(SupervisionError):
                Supervisor(Path(tmp) / "run", limits()).run(
                    [JobSpec(key="file-a", argv=["/bin/true"], produces="../escape")]
                )

    def test_fresh_run_refuses_nonempty_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            Supervisor(out, limits()).run([spec("file-a", "empty")])
            with self.assertRaises(SupervisionError):
                Supervisor(out, limits()).run([spec("file-b", "empty")])


if __name__ == "__main__":
    unittest.main()
