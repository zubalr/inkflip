"""Native parent supervision over disposable reader processes (T29).

Implements the "Native supervision" section of
``planning/architecture/RUNTIME_LIFECYCLE.md`` plus the containment rows of
``planning/security/THREAT_MODEL.md`` ("Process hang/orphan", "Local path
abuse", "Resource exhaustion") for the local corpus/CLI path:

* Each job runs in a disposable child process in its **own process group**
  (``start_new_session`` → ``setsid``). Termination targets the whole group
  with SIGTERM, a bounded grace, then SIGKILL; after the leader is reaped the
  group is probed again and leftover descendants are killed too — a child that
  spawned a subprocess cannot strand it under the supervisor's watch.
* **Wall deadline** is enforced by the parent's poll loop, never by SIGALRM —
  a stuck native call cannot rely on in-process signals. A CPU-second rlimit
  is only a backstop.
* **Output caps** on stdout/stderr are enforced live: the parent drains the
  pipes through a ``selectors`` loop, counts every byte, keeps only a bounded
  head+tail sample, and kills the group when a stream exceeds its cap. A
  post-reap mirror covers the hole where the excess was only drained in
  ``_drain_until_eof`` after the leader exited (e.g. while the loop was
  blocked in a sibling's stray-descendant cleanup): recorded stream bytes
  over cap classify ``output_limit``, never ``completed``.
* **Memory bound** is layered and honest: ``RLIMIT_AS`` where the platform
  accepts it (Linux), ``RLIMIT_FSIZE``/``RLIMIT_CORE``/``RLIMIT_CPU`` where
  available, a parent-side RSS probe (``/proc`` on Linux, ``libproc``
  ``proc_pidinfo`` on macOS) that kills the group past the limit mid-run, and
  a post-exit ``wait4`` ``ru_maxrss`` check. Where a facility is unavailable
  the supervisor degrades and records it — see ``rlimit_support`` in the run
  index. A container remains the hardened route (THREAT_MODEL).
* **Minimal environment**: the child receives a fixed allowlist (locale,
  thread-count pins at 1, TMPDIR into its private scratch) plus explicitly
  declared per-job extras whose *names* are journaled and which may not
  redeclare fixed keys. No proxy tokens, cloud credentials or inherited
  ambient variables reach a parse child.
* **One bounded retry**: failures classified as transient (nonzero exit,
  signal crash, wall timeout, spawn error) get at most ``limits.retries``
  extra attempt (default 1) with a fresh worker and fresh scratch, and only
  while the run deadline leaves room. Cancellation, output/memory violations
  and missing/invalid output are never retried; neither is a completed job —
  including an "empty success" that produced nothing.
* **Ctrl-C** = SIGINT to the supervisor process: it is forwarded as a cancel —
  live process groups are terminated, queued jobs receive terminal
  ``cancelled`` records, and the run still writes its index and journal tail,
  so the partial artifact stays valid. Queued work cancelled this way is a
  terminal result, not a skip (I05).
* **jobs=1 default**; ``limits.jobs > 1`` requires an explicit
  :class:`ParallelAdmission` (CPU/RAM-aware). All reader engine calls (e.g.
  pypdfium2) run inside child processes — the supervisor itself uses no
  threads, so PDFium is never invoked from concurrent threads (s26).

Classification (per job, journaled and indexed): ``completed`` | ``failed``
(``failure_kind`` in ``exit``, ``crash``, ``output_limit``, ``memory_limit``,
``spawn_error``, ``missing_output``, ``report_invalid``, ``interrupted``) |
``timeout`` (``failure_kind`` ``wall``/``run_deadline``) | ``cancelled`` |
``skipped`` (resume only: a previously completed job whose report bytes and
config digest still verify is never silently rerun — CLI_AND_REGRESSION).

Error surface discipline: job ``reason`` strings are safe templates (counts,
signal names, cap sizes) — never child stdout text or arbitrary paths, per
RUNTIME_LIFECYCLE "errors disclose type and safe reason".
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import re
import resource
import selectors
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .artifacts import (
    Journal,
    atomic_write_bytes,
    config_digest,
    sha256_bytes,
    sha256_file,
)

POSIX = os.name == "posix"
HAS_WAIT4 = hasattr(os, "wait4")

JOB_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
PRODUCES_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,255}$")

# Fixed child-environment values (THREAT_MODEL: no ambient variables reach a
# parse child; thread libraries pinned to one thread). TMPDIR is also fixed
# but bound per attempt to the private scratch, so it is set dynamically.
_FIXED_ENV_VALUES = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "PYTHONIOENCODING": "utf-8",
}
# Per-job env extras may add names but may NEVER redeclare these — a TMPDIR
# override would escape the scratch bound and a *_NUM_THREADS override would
# defeat the single-thread pin silently (the journal records only key names).
FIXED_ENV_KEYS = frozenset(_FIXED_ENV_VALUES) | {"TMPDIR"}

# Terminal job statuses (aligned with RUNTIME_LIFECYCLE check terminals).
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"
STATUS_SKIPPED = "skipped"  # resume: already-completed evidence reused verbatim

# failure_kind values (status failed unless noted).
KIND_EXIT = "exit"  # nonzero exit code
KIND_CRASH = "crash"  # died on a signal (not one we sent for another cause)
KIND_OUTPUT_LIMIT = "output_limit"  # stdout/stderr/report/scratch cap
KIND_MEMORY_LIMIT = "memory_limit"  # rlimit trip, RSS-probe kill or post-exit peak
KIND_SPAWN_ERROR = "spawn_error"  # exec/preexec/OSError at spawn
KIND_MISSING_OUTPUT = "missing_output"  # exit 0 but declared output absent
KIND_REPORT_INVALID = "report_invalid"  # output exists but fails validation
KIND_INTERRUPTED = "interrupted"  # run aborted before the job reached terminal
KIND_WALL = "wall"  # status timeout: per-file wall deadline
KIND_RUN_DEADLINE = "run_deadline"  # status timeout: whole-run deadline

# Transient failures that may be retried once within the run deadline
# (RUNTIME_LIFECYCLE: "one transient retry for initialization/worker crash").
# Resource violations, invalid/missing output and cancellation are
# deterministic and never retried; neither is a completed job — including an
# "empty success" that produced nothing to commit.
RETRYABLE_KINDS = frozenset({KIND_EXIT, KIND_CRASH, KIND_WALL, KIND_SPAWN_ERROR})

SAMPLE_HEAD_BYTES = 2048
SAMPLE_TAIL_BYTES = 2048

_RUN_INDEX_KIND = "inkflip-run-index"
_RUN_INDEX_VERSION = "1.0.0"

_OOM_MARKERS = (
    b"MemoryError",
    b"std::bad_alloc",
    b"cannot allocate memory",
    b"Cannot allocate memory",
    b"Out of memory",
    b"out of memory",
)


class SupervisionError(Exception):
    """Setup/configuration violation (bad spec, clobbered output dir, missing
    parallel admission, resume identity change). Job failures never raise —
    they are classified."""


@dataclass(frozen=True)
class ParallelAdmission:
    """Explicit CPU/RAM-aware admission required for ``limits.jobs > 1``.

    The caller declares the machine's real resources; the supervisor refuses
    concurrency when ``jobs * child memory`` exceeds the declared budget or
    jobs exceed the declared CPU count — the "explicit CPU/RAM-aware
    admission" of RUNTIME_LIFECYCLE, not an autotuner.
    """

    cpu_count: int
    memory_bytes: int


@dataclass(frozen=True)
class Limits:
    """Runtime bounds; defaults mirror planning/config/settings.json "native"."""

    wall_seconds: float = 180.0  # native.file_timeout_ms
    run_wall_seconds: float | None = None  # optional whole-run deadline
    memory_bytes: int = 1 << 30  # native.child_memory_bytes
    max_stdout_bytes: int = 1 << 20  # native.max_stdout_message_bytes
    max_stderr_bytes: int = 1 << 20
    max_report_bytes: int = 64 << 20  # native.max_output_bytes_per_file
    scratch_bytes: int = 512 << 20  # native.scratch_bytes
    retries: int = 1  # native.max_retries — at most ONE extra attempt
    jobs: int = 1  # native.default_jobs
    kill_grace_seconds: float = 0.5
    poll_interval_seconds: float = 0.05
    rss_probe_interval_seconds: float = 0.1


@dataclass(frozen=True)
class JobSpec:
    """One disposable unit of work.

    ``argv`` is executed with ``shell=False``; ``produces`` names a file the
    child writes inside its private scratch that the parent validates and
    commits atomically under ``<out>/reports/<key>.json``. ``env`` is an
    explicit per-job allowlist of extra variables merged over the minimal
    base environment; it may add names only — redeclaring a fixed key
    (FIXED_ENV_KEYS: locale, TMPDIR, the *_NUM_THREADS pins,
    PYTHONIOENCODING) is refused, since an override would silently defeat
    the scratch/thread bounds while the journaled key set looked identical.
    Only key names are journaled; the resume config digest binds names and
    values (a hash — values are never persisted).
    """

    key: str
    argv: tuple | list
    produces: str | None = None
    env: dict = field(default_factory=dict)
    wall_seconds: float | None = None
    memory_bytes: int | None = None

    def validate(self) -> None:
        if not JOB_KEY_PATTERN.match(self.key):
            raise SupervisionError(f"invalid job key: {self.key!r}")
        if (
            not isinstance(self.argv, (tuple, list))
            or not self.argv
            or not all(isinstance(a, str) and a for a in self.argv)
        ):
            raise SupervisionError(f"job {self.key}: argv must be a nonempty string list")
        if self.produces is not None and not PRODUCES_PATTERN.match(self.produces):
            raise SupervisionError(f"job {self.key}: invalid produces name {self.produces!r}")
        if not isinstance(self.env, dict) or not all(
            isinstance(k, str) and k and "=" not in k and isinstance(v, str)
            for k, v in self.env.items()
        ):
            raise SupervisionError(f"job {self.key}: env must be a flat string dict")
        collisions = sorted(set(self.env) & FIXED_ENV_KEYS)
        if collisions:
            raise SupervisionError(
                f"job {self.key}: env extras cannot redeclare fixed "
                f"child-env keys {collisions}"
            )
        for name, value in (
            ("wall_seconds", self.wall_seconds),
            ("memory_bytes", self.memory_bytes),
        ):
            if value is not None and (not isinstance(value, (int, float)) or value <= 0):
                raise SupervisionError(f"job {self.key}: {name} must be positive")


@dataclass
class JobRecord:
    """Terminal record for one job (index.json + RunResult)."""

    key: str
    status: str
    failure_kind: str | None = None
    reason: str | None = None
    attempts: int = 0
    report_path: str | None = None
    report_sha256: str | None = None
    report_bytes: int | None = None
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    peak_rss_bytes: int | None = None
    wall_ms: int = 0
    exit_code: int | None = None
    signal: str | None = None
    stray_descendants: bool = False
    resumed: bool = False
    config_digest: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class RunResult:
    status: str  # complete | partial | failed | cancelled
    run_id: str
    run_dir: str
    jobs: dict  # key -> JobRecord
    index_path: str
    journal_path: str
    started_at: str
    ended_at: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "index_path": self.index_path,
            "journal_path": self.journal_path,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "jobs": {k: j.to_dict() for k, j in self.jobs.items()},
        }


# ---------------------------------------------------------------------------
# Platform capability probes (recorded honestly; degrade where unavailable)
# ---------------------------------------------------------------------------

_RLIMIT_PROBE = {
    "RLIMIT_AS": 256 << 20,
    "RLIMIT_FSIZE": 1 << 20,
    "RLIMIT_CPU": 3600,
    "RLIMIT_CORE": 0,
    "RLIMIT_NOFILE": 256,
}

# Probe script run in a fresh subprocess (never os.fork: the parent may hold
# threads, and forking a threaded process risks deadlocks). The child tries
# each limit and exits a bitmask.
_PROBE_SCRIPT = """
import resource, sys
names = sys.argv[1:]
probes = %r
code = 0
for index, name in enumerate(names):
    try:
        resource.setrlimit(getattr(resource, name), (probes[name], probes[name]))
        code |= 1 << index
    except BaseException:
        pass
sys.exit(code & 0x7F)
""" % repr(_RLIMIT_PROBE)


def probe_rlimits() -> dict:
    """Best-effort probe of which rlimits this platform actually accepts.

    macOS reports RLIMIT_AS/DATA/RSS as infinity yet rejects lowering them;
    Linux accepts AS and ignores RSS. A fresh interpreter child tries each
    limit and reports a bitmask; any failure degrades to an empty map."""
    if not POSIX:
        return {}
    names = sorted(_RLIMIT_PROBE)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE_SCRIPT, *names],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    code = proc.returncode
    if code < 0 or code > 0x7F:
        return {}
    return {name: bool(code & (1 << index)) for index, name in enumerate(names)}


def _rss_bytes(pid: int) -> int | None:
    """Resident bytes of a live child, or None when unavailable (the parent
    then degrades to post-exit wait4 classification only)."""
    if sys.platform.startswith("linux"):
        try:
            with open(f"/proc/{pid}/status", "rb") as handle:
                for line in handle:
                    if line.startswith(b"VmRSS:"):
                        return int(line.split()[1]) << 10
        except (OSError, ValueError, IndexError):
            return None
        return None
    if sys.platform == "darwin":
        try:
            lib = ctypes.CDLL("libproc.dylib")
            proc_pidinfo = lib.proc_pidinfo
            proc_pidinfo.restype = ctypes.c_int
            proc_pidinfo.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint64,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            buffer = ctypes.create_string_buffer(96)
            written = proc_pidinfo(pid, 4, 0, buffer, 96)  # PROC_PIDTASKINFO
            if written <= 0:
                return None
            _, resident = struct.unpack_from("QQ", buffer, 0)
            return int(resident)
        except (OSError, AttributeError, ValueError, struct.error):
            return None
    return None


def _rusage_maxrss_bytes(rusage) -> int | None:
    """Normalize wait4 ru_maxrss: bytes on macOS, KiB on Linux."""
    if rusage is None:
        return None
    value = getattr(rusage, "ru_maxrss", None)
    if not isinstance(value, int) or value < 0:
        return None
    return value if sys.platform == "darwin" else value << 10


def _minimal_env(scratch: Path, extra: dict) -> dict:
    """Fixed child environment allowlist + declared per-job extras.

    Parse-only jobs must not inherit proxy tokens, cloud credentials or broad
    ambient variables (THREAT_MODEL). Thread libraries are pinned to one
    thread per child; TMPDIR is the private scratch. ``extra`` is validated
    upstream (JobSpec.validate refuses collisions with FIXED_ENV_KEYS), so
    the update below can only add names, never silently redeclare them."""
    env = dict(_FIXED_ENV_VALUES)
    env["TMPDIR"] = str(scratch)
    env.update(extra)
    return env


def _child_rlimits(wall_seconds: float, memory_bytes: int, file_cap: int):
    """preexec best-effort rlimit application. Runs in the child after setsid
    and before exec; each call is individually optional — unsupported limits
    are skipped silently (the parent's probe records what this platform
    honors). Must never raise."""

    def apply() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except BaseException:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except BaseException:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_cap, file_cap))
        except BaseException:
            pass
        try:
            cpu = int(math.ceil(wall_seconds)) + 60
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 60))
        except BaseException:
            pass

    return apply


def _sig_name(signo: int) -> str:
    try:
        return signal.Signals(signo).name
    except (ValueError, KeyError):
        return f"SIG{signo}"


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class _BoundedStream:
    """Counts every byte of one child stream, keeping only a bounded head+tail
    sample — the parent never retains unbounded child output."""

    __slots__ = ("fd", "name", "cap", "total", "sha", "head", "tail", "overflow")

    def __init__(self, fd: int, name: str, cap: int):
        self.fd = fd
        self.name = name
        self.cap = cap
        self.total = 0
        self.sha = hashlib.sha256()
        self.head = bytearray()
        self.tail = bytearray()
        self.overflow = False

    def consume(self, data: bytes) -> None:
        self.total += len(data)
        self.sha.update(data)
        if len(self.head) < SAMPLE_HEAD_BYTES:
            self.head += data[: SAMPLE_HEAD_BYTES - len(self.head)]
        self.tail += data
        if len(self.tail) > SAMPLE_TAIL_BYTES:
            del self.tail[: len(self.tail) - SAMPLE_TAIL_BYTES]
        if self.total > self.cap:
            self.overflow = True

    def digest(self) -> str:
        return self.sha.hexdigest()

    def sample(self) -> bytes:
        return bytes(self.head) + bytes(self.tail)


class _ActiveChild:
    """One spawned attempt: process handles, stream counters, kill state."""

    __slots__ = (
        "job", "attempt", "proc", "pgid", "scratch", "deadline", "wall_limit",
        "memory_limit", "stdout", "stderr", "reaped", "exit_code", "signal",
        "rusage", "peak_rss", "killed_cause", "started_mono", "last_rss_probe",
        "stray", "abandoned",
    )

    def __init__(self, job, attempt, proc, pgid, scratch, wall_limit, memory_limit, stdout, stderr):
        self.job = job
        self.attempt = attempt
        self.proc = proc
        self.pgid = pgid
        self.scratch = scratch
        self.wall_limit = wall_limit
        self.deadline = time.monotonic() + wall_limit
        self.memory_limit = memory_limit
        self.stdout = stdout
        self.stderr = stderr
        self.reaped = False
        self.exit_code = None
        self.signal = None
        self.rusage = None
        self.peak_rss = None
        self.killed_cause = None
        self.started_mono = time.monotonic()
        self.last_rss_probe = 0.0
        self.stray = False
        self.abandoned = False


class Supervisor:
    """Parent supervisor over a queue of disposable per-file jobs.

    ``out_dir`` layout::

        journal.jsonl     append-only run journal (all runs share it)
        index.json        atomically-written terminal index of the LAST run
        reports/<key>.json  committed per-file artifacts (atomic writes only)
        scratch/<key>-a<n>-XXXXXX/  private per-attempt scratch (removed)

    ``resume=True`` reads the previous index: a job recorded ``completed``
    whose report file still hashes to the recorded digest AND whose config
    digest is unchanged is marked ``skipped`` — never silently rerun or
    rewritten (byte-stability, I17). A changed config digest refuses the
    resume BEFORE anything is written: changed identities require a new run
    directory.
    """

    def __init__(
        self,
        out_dir: Path,
        limits: Limits | None = None,
        *,
        resume: bool = False,
        parallel_admission: ParallelAdmission | None = None,
        validate_report: Callable[[bytes], None] | None = None,
    ):
        if not POSIX:
            raise SupervisionError("native supervision requires POSIX process groups")
        self.out_dir = Path(out_dir)
        self.limits = limits or Limits()
        if self.limits.retries < 0:
            raise SupervisionError("retries must be >= 0")
        if self.limits.jobs < 1:
            raise SupervisionError("jobs must be >= 1")
        if self.limits.jobs > 1:
            if parallel_admission is None:
                raise SupervisionError(
                    "jobs > 1 requires explicit CPU/RAM-aware ParallelAdmission"
                )
            if self.limits.jobs > parallel_admission.cpu_count:
                raise SupervisionError(
                    f"jobs {self.limits.jobs} exceeds admitted CPU count "
                    f"{parallel_admission.cpu_count}"
                )
            if self.limits.jobs * self.limits.memory_bytes > parallel_admission.memory_bytes:
                raise SupervisionError(
                    f"jobs {self.limits.jobs} x child memory "
                    f"{self.limits.memory_bytes} exceeds admitted budget "
                    f"{parallel_admission.memory_bytes}"
                )
        self.resume = resume
        self.validate_report = validate_report
        self.reports_dir = self.out_dir / "reports"
        self.scratch_root = self.out_dir / "scratch"
        self.journal_path = self.out_dir / "journal.jsonl"
        self.index_path = self.out_dir / "index.json"
        self._cancel_requested = False
        self._cancel_signal = None
        self._previous_handlers: dict = {}
        self._prior_index: dict | None = None
        self.rlimit_support: dict = {}

    # -- signal handling ----------------------------------------------------

    def _install_handlers(self) -> None:
        """Forward SIGINT/SIGTERM to the cancel flag. Only the main thread may
        install handlers; elsewhere request_cancel() remains the path."""
        self._cancel_requested = False
        self._cancel_signal = None
        try:
            for signo in (signal.SIGINT, signal.SIGTERM):
                self._previous_handlers[signo] = signal.getsignal(signo)
                signal.signal(signo, self._on_signal)
        except ValueError:
            self._previous_handlers = {}

    def _restore_handlers(self) -> None:
        for signo, previous in self._previous_handlers.items():
            try:
                signal.signal(signo, previous)
            except (ValueError, OSError):
                pass
        self._previous_handlers = {}

    def _on_signal(self, signo, _frame) -> None:
        self._cancel_requested = True
        self._cancel_signal = _sig_name(signo)

    def request_cancel(self) -> None:
        self._cancel_requested = True
        self._cancel_signal = self._cancel_signal or "request_cancel"

    # -- filesystem setup ----------------------------------------------------

    def _setup_dirs(self) -> None:
        if self.resume:
            if not self.index_path.is_file():
                raise SupervisionError("resume requested but no index.json exists")
            try:
                self._prior_index = json.loads(self.index_path.read_bytes())
            except (ValueError, UnicodeDecodeError) as error:
                raise SupervisionError(f"resume refused: unreadable index.json ({error})")
            if self._prior_index.get("kind") != _RUN_INDEX_KIND:
                raise SupervisionError("resume refused: index.json is not a run index")
        else:
            if self.journal_path.exists() or self.index_path.exists():
                raise SupervisionError(
                    "output directory already holds a run; use resume=True or a fresh directory"
                )
            if self.out_dir.exists() and any(self.out_dir.iterdir()):
                raise SupervisionError("output directory is not empty")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.scratch_root.mkdir(parents=True, exist_ok=True)

    # -- job config / spawn -----------------------------------------------------

    def _job_config(self, job: JobSpec) -> dict:
        return {
            "key": job.key,
            "argv": list(job.argv),
            # Names AND values: only the digest is persisted, so binding the
            # declared values costs nothing and a changed env value can no
            # longer silently reuse prior evidence on resume.
            "env": dict(sorted(job.env.items())),
            "produces": job.produces,
            "wall_seconds": job.wall_seconds or self.limits.wall_seconds,
            "memory_bytes": job.memory_bytes or self.limits.memory_bytes,
        }

    def _spawn(self, job: JobSpec, attempt: int, journal: Journal) -> _ActiveChild:
        wall = job.wall_seconds or self.limits.wall_seconds
        memory = job.memory_bytes or self.limits.memory_bytes
        argv = [str(a) for a in job.argv]
        # Resolve a bare executable name against the parent's PATH so the child
        # never needs an environment PATH for exec itself.
        if "/" not in argv[0]:
            resolved = shutil.which(argv[0])
            if resolved is None:
                raise FileNotFoundError(f"executable not found: {argv[0]}")
            argv[0] = resolved
        scratch = Path(tempfile.mkdtemp(prefix=f"{job.key}-a{attempt}-", dir=self.scratch_root))
        env = _minimal_env(scratch, job.env)
        try:
            proc = subprocess.Popen(
                argv,
                shell=False,
                cwd=str(scratch),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True,  # own process group; pgid == pid
                preexec_fn=_child_rlimits(wall, memory, self.limits.max_report_bytes),
                close_fds=True,
            )
        except BaseException:
            shutil.rmtree(scratch, ignore_errors=True)
            raise
        for stream in (proc.stdout, proc.stderr):
            os.set_blocking(stream.fileno(), False)
        stdout = _BoundedStream(proc.stdout.fileno(), "stdout", self.limits.max_stdout_bytes)
        stderr = _BoundedStream(proc.stderr.fileno(), "stderr", self.limits.max_stderr_bytes)
        journal.record(
            "child_spawned",
            job=job.key,
            attempt=attempt,
            pid=proc.pid,
            pgid=proc.pid,
            argv=argv,
            env_keys=sorted(env),
            scratch=str(scratch),
            wall_seconds=wall,
            memory_bytes=memory,
        )
        return _ActiveChild(
            job=job, attempt=attempt, proc=proc, pgid=proc.pid, scratch=scratch,
            wall_limit=wall, memory_limit=memory, stdout=stdout, stderr=stderr,
        )

    # -- signals / termination ---------------------------------------------------

    def _signal_group(self, child: _ActiveChild, signo: int) -> None:
        """Signal the child's whole group; race-tolerant fallback to the leader
        if its setsid has not completed yet."""
        try:
            os.killpg(child.pgid, signo)
        except (ProcessLookupError, PermissionError):
            try:
                child.proc.send_signal(signo)
            except (ProcessLookupError, OSError):
                pass
        except OSError:
            pass

    def _reap(self, child: _ActiveChild) -> bool:
        """wait4/waitpid WNOHANG; on reap decode status + per-child rusage."""
        if child.reaped:
            return True
        code = None
        if HAS_WAIT4:
            try:
                pid, status, rusage = os.wait4(child.proc.pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pid, status, rusage = child.proc.pid, None, None
            if pid == 0:
                return False
            child.rusage = rusage
            if status is not None:
                code = os.waitstatus_to_exitcode(status)
        else:  # no wait4: degrade to waitpid (no per-child rusage)
            try:
                pid, status = os.waitpid(child.proc.pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pid, status = child.proc.pid, None
            if pid == 0:
                return False
            if status is not None:
                code = os.waitstatus_to_exitcode(status)
        if code is None:
            code = child.proc.returncode  # may still be None -> "status unavailable"
        child.reaped = True
        if code is not None and code < 0:
            child.signal = _sig_name(-code)
            child.exit_code = None
        else:
            child.exit_code = code
            child.signal = None
        if code is not None:
            child.proc.returncode = code  # keep Popen consistent; it never waits
        child.peak_rss = _rusage_maxrss_bytes(child.rusage)
        return True

    def _terminate_group(self, child: _ActiveChild, journal: Journal, cause: str) -> None:
        """SIGTERM the group, bounded grace, SIGKILL; then reap the leader."""
        if child.reaped:
            return
        if cause == "cancel" or child.killed_cause is None:
            child.killed_cause = cause
        journal.record("child_killed", job=child.job.key, attempt=child.attempt,
                       pgid=child.pgid, signal="SIGTERM", cause=cause)
        self._signal_group(child, signal.SIGTERM)
        grace_end = time.monotonic() + self.limits.kill_grace_seconds
        while time.monotonic() < grace_end:
            if self._reap(child):
                return
            self._drain_once(child)
            time.sleep(0.01)
        journal.record("child_killed", job=child.job.key, attempt=child.attempt,
                       pgid=child.pgid, signal="SIGKILL", cause=f"{cause}:grace_expired")
        self._signal_group(child, signal.SIGKILL)
        deadline = time.monotonic() + 5.0
        while not self._reap(child) and time.monotonic() < deadline:
            self._drain_once(child)
            time.sleep(0.01)
        if not child.reaped:
            # Uninterruptible-sleep (D-state) children survive even SIGKILL;
            # the kernel cannot reap them. Give up honestly: record it and
            # move on rather than hanging the run forever.
            child.abandoned = True
            child.stray = True
            journal.record("child_unreaped", job=child.job.key, attempt=child.attempt,
                           pgid=child.pgid, cause=cause)

    def _drain_once(self, child: _ActiveChild) -> None:
        """One nonblocking pass over both pipes into the bounded counters."""
        for stream in (child.stdout, child.stderr):
            if stream.fd is None:
                continue
            while True:
                try:
                    data = os.read(stream.fd, 65536)
                except BlockingIOError:
                    break
                except OSError:
                    data = b""
                if not data:
                    stream.fd = None
                    break
                stream.consume(data)

    def _drain_until_eof(self, child: _ActiveChild, budget: float = 1.0) -> None:
        """After all writers are dead, drain remaining pipe data until EOF."""
        end = time.monotonic() + budget
        while time.monotonic() < end:
            if child.stdout.fd is None and child.stderr.fd is None:
                return
            self._drain_once(child)
            if child.stdout.fd is None and child.stderr.fd is None:
                return
            time.sleep(0.01)

    def _cleanup_strays(self, child: _ActiveChild, journal: Journal) -> bool:
        """After the leader is reaped, probe the group: leftover descendants
        get SIGTERM then SIGKILL. Returns True if strays were found."""
        if not child.reaped:
            return False
        try:
            os.killpg(child.pgid, 0)
        except OSError:
            return False
        journal.record("descendants_reaped", job=child.job.key, attempt=child.attempt,
                       pgid=child.pgid)
        self._signal_group(child, signal.SIGTERM)
        end = time.monotonic() + self.limits.kill_grace_seconds
        while time.monotonic() < end:
            try:
                os.killpg(child.pgid, 0)
            except OSError:
                return True
            time.sleep(0.02)
        self._signal_group(child, signal.SIGKILL)
        end = time.monotonic() + 2.0
        while time.monotonic() < end:
            try:
                os.killpg(child.pgid, 0)
            except OSError:
                return True
            time.sleep(0.02)
        return True

    def _close_pipes(self, child: _ActiveChild) -> None:
        for stream in (child.proc.stdout, child.proc.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    # -- classification ------------------------------------------------------------

    def _classify_attempt(self, child: _ActiveChild) -> tuple:
        """(status, failure_kind, safe reason) for a reaped attempt."""
        if child.killed_cause == "cancel":
            return STATUS_CANCELLED, None, "cancelled by request"
        if child.killed_cause == "run_deadline":
            return STATUS_TIMEOUT, KIND_RUN_DEADLINE, "run deadline exceeded"
        if child.killed_cause == "wall":
            return STATUS_TIMEOUT, KIND_WALL, f"exceeded {child.wall_limit}s wall budget"
        if child.killed_cause == "output_limit":
            over = "stdout" if child.stdout.overflow else "stderr"
            cap = child.stdout.cap if child.stdout.overflow else child.stderr.cap
            return STATUS_FAILED, KIND_OUTPUT_LIMIT, f"{over} exceeded {cap}-byte cap"
        if child.killed_cause == "memory_limit":
            return (
                STATUS_FAILED,
                KIND_MEMORY_LIMIT,
                f"resident memory exceeded {child.memory_limit}-byte bound",
            )
        # Post-reap mirror of the live overflow kill (the memory bound has the
        # same shape via peak_rss below): a stream can cross its cap through
        # bytes drained only in _drain_until_eof — e.g. while the loop was
        # blocked in a sibling's stray-descendant cleanup — so the verdict
        # must not depend on killed_cause having been set in time. A job
        # whose recorded stream total exceeds the cap is never "completed".
        if child.stdout.overflow or child.stderr.overflow:
            over = "stdout" if child.stdout.overflow else "stderr"
            cap = child.stdout.cap if child.stdout.overflow else child.stderr.cap
            return STATUS_FAILED, KIND_OUTPUT_LIMIT, f"{over} exceeded {cap}-byte cap"
        stderr_sample = bytes(child.stderr.tail[-256:]) + bytes(child.stderr.head[:256])
        if child.signal is not None:
            if child.signal == "SIGXFSZ":
                return STATUS_FAILED, KIND_OUTPUT_LIMIT, "child file write exceeded the byte cap"
            if child.signal == "SIGXCPU":
                return STATUS_TIMEOUT, KIND_WALL, "child CPU budget exhausted"
            if any(marker in stderr_sample for marker in _OOM_MARKERS):
                return STATUS_FAILED, KIND_MEMORY_LIMIT, "child reported out-of-memory"
            return STATUS_FAILED, KIND_CRASH, f"killed by {child.signal}"
        if child.peak_rss is not None and child.peak_rss >= child.memory_limit:
            return (
                STATUS_FAILED,
                KIND_MEMORY_LIMIT,
                f"peak resident {child.peak_rss} reached {child.memory_limit}-byte bound",
            )
        if child.exit_code is None:
            return STATUS_FAILED, KIND_CRASH, "child reaped without an exit status"
        if child.exit_code != 0:
            if any(marker in stderr_sample for marker in _OOM_MARKERS):
                return STATUS_FAILED, KIND_MEMORY_LIMIT, "child reported out-of-memory"
            return STATUS_FAILED, KIND_EXIT, f"exited {child.exit_code}"
        # exit 0: a declared output must exist, or this "empty success" failed.
        if child.job.produces is not None:
            produced = child.scratch / child.job.produces
            if not produced.is_file() or produced.is_symlink():
                return (
                    STATUS_FAILED,
                    KIND_MISSING_OUTPUT,
                    "child exited 0 without its declared output",
                )
        return STATUS_COMPLETED, None, "completed"

    # -- per-tick poll loop -------------------------------------------------------

    def _run_children(self, active: list, finished: list, journal: Journal,
                      run_deadline: float | None) -> None:
        """Poll all active children until each is reaped and moved to
        ``finished``. Single parent thread; selector-driven."""
        selector = selectors.DefaultSelector()
        fd_to_stream: dict = {}
        for child in active:
            for stream in (child.stdout, child.stderr):
                if stream.fd is not None:
                    try:
                        selector.register(stream.fd, selectors.EVENT_READ)
                        fd_to_stream[stream.fd] = stream
                    except (KeyError, ValueError, OSError):
                        pass
        try:
            while active:
                now = time.monotonic()
                if self._cancel_requested:
                    for child in active:
                        if not child.reaped and not child.abandoned and child.killed_cause != "cancel":
                            self._terminate_group(child, journal, "cancel")
                for child in active:
                    if child.reaped or child.abandoned or child.killed_cause is not None:
                        continue
                    if run_deadline is not None and now >= run_deadline:
                        self._terminate_group(child, journal, "run_deadline")
                    elif now >= child.deadline:
                        self._terminate_group(child, journal, "wall")
                    elif child.stdout.overflow or child.stderr.overflow:
                        self._terminate_group(child, journal, "output_limit")
                    elif (
                        self.limits.rss_probe_interval_seconds > 0
                        and now - child.last_rss_probe >= self.limits.rss_probe_interval_seconds
                    ):
                        child.last_rss_probe = now
                        rss = _rss_bytes(child.proc.pid)
                        if rss is not None:
                            child.peak_rss = max(child.peak_rss or 0, rss)
                            if rss >= child.memory_limit:
                                self._terminate_group(child, journal, "memory_limit")
                for child in active:
                    if not child.reaped and not child.abandoned:
                        self._reap(child)
                live = [c for c in active if not c.reaped and not c.abandoned]
                if live:
                    events = selector.select(self.limits.poll_interval_seconds)
                    for key, _mask in events:
                        stream = fd_to_stream.get(key.fd)
                        if stream is None or stream.fd is None:
                            continue
                        try:
                            data = os.read(key.fd, 65536)
                        except (BlockingIOError, OSError):
                            data = b""
                        if not data:
                            stream.fd = None
                            try:
                                selector.unregister(key.fd)
                            except (KeyError, ValueError, OSError):
                                pass
                        else:
                            stream.consume(data)
                else:
                    time.sleep(min(self.limits.poll_interval_seconds, 0.02))
                for child in list(active):
                    if child.reaped or child.abandoned:
                        if (
                            child.reaped
                            and child.killed_cause is None
                            and not self._cancel_requested
                            and self._cleanup_strays(child, journal)
                        ):
                            child.stray = True
                        self._drain_until_eof(child)
                        self._close_pipes(child)
                        active.remove(child)
                        finished.append(child)
        finally:
            selector.close()

    # -- report commit ---------------------------------------------------------

    def _commit_report(self, child: _ActiveChild, journal: Journal) -> tuple:
        """Validate and atomically commit the child's declared output.
        Returns (rel_path, sha256, bytes, error_kind)."""
        job = child.job
        if job.produces is None:
            return None, None, None, None
        produced = child.scratch / job.produces
        try:
            if produced.is_symlink() or not produced.is_file():
                return None, None, None, KIND_MISSING_OUTPUT
            if produced.stat().st_size > self.limits.max_report_bytes:
                return None, None, None, KIND_OUTPUT_LIMIT
            data = produced.read_bytes()
        except OSError:
            return None, None, None, KIND_MISSING_OUTPUT
        try:
            if self.validate_report is not None:
                self.validate_report(data)
            else:
                json.loads(data.decode("utf-8"))
        except Exception:
            return None, None, None, KIND_REPORT_INVALID
        target = self.reports_dir / f"{job.key}.json"
        atomic_write_bytes(target, data)
        digest = sha256_bytes(data)
        rel = str(target.relative_to(self.out_dir))
        journal.record("report_committed", job=job.key, path=rel,
                       sha256=digest, bytes=len(data))
        return rel, digest, len(data), None

    def _scratch_bytes(self, scratch: Path) -> int:
        total = 0
        try:
            for entry in scratch.rglob("*"):
                if entry.is_file() and not entry.is_symlink():
                    total += entry.stat().st_size
        except OSError:
            pass
        return total

    # -- resume -------------------------------------------------------------------

    def _resume_lookup(self, job: JobSpec, digest: str) -> JobRecord | None:
        prior = (self._prior_index.get("jobs") or {}).get(job.key)
        if not prior or prior.get("status") != STATUS_COMPLETED:
            return None
        if prior.get("config_digest") != digest:
            raise SupervisionError(
                f"job {job.key}: config identity changed since last run; "
                "a changed identity requires a new run directory"
            )
        report_rel = prior.get("report_path")
        recorded_sha = prior.get("report_sha256")
        if report_rel is None or recorded_sha is None:
            return None
        report_abs = self.out_dir / report_rel
        if not report_abs.is_file() or sha256_file(report_abs) != recorded_sha:
            return None  # missing/changed evidence is never reused silently
        return JobRecord(
            key=job.key,
            status=STATUS_SKIPPED,
            reason="resumed: prior completed report verified by hash/config",
            attempts=0,
            report_path=report_rel,
            report_sha256=recorded_sha,
            report_bytes=prior.get("report_bytes"),
            config_digest=digest,
            resumed=True,
        )

    # -- retry ---------------------------------------------------------------------

    def _retryable(self, record: JobRecord, attempts: int, run_deadline: float | None) -> bool:
        """At most `limits.retries` extra attempts, transient kinds only, and
        only while the run deadline leaves room."""
        return (
            record.status in (STATUS_FAILED, STATUS_TIMEOUT)
            and record.failure_kind in RETRYABLE_KINDS
            and attempts <= self.limits.retries
            and (run_deadline is None or time.monotonic() < run_deadline)
            and not self._cancel_requested
        )

    # -- main loop -------------------------------------------------------------------

    def run(self, jobs: Iterable[JobSpec]) -> RunResult:
        jobs = list(jobs)
        if not jobs:
            raise SupervisionError("an empty job plan is refused (no vacuous run)")
        keys = [j.key for j in jobs]
        if len(set(keys)) != len(keys):
            raise SupervisionError("duplicate job keys are refused")
        for job in jobs:
            job.validate()
        self._setup_dirs()
        self.rlimit_support = probe_rlimits()
        digests = {j.key: config_digest(self._job_config(j)) for j in jobs}
        # Resume pre-pass BEFORE any writes: a refused identity change leaves
        # the prior index/journal byte-identical.
        presumed: dict = {}
        if self.resume:
            for job in jobs:
                record = self._resume_lookup(job, digests[job.key])  # may refuse
                if record is not None:
                    presumed[job.key] = record
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        started_at = _utcnow()
        started_mono = time.monotonic()
        run_deadline = (
            started_mono + self.limits.run_wall_seconds
            if self.limits.run_wall_seconds is not None
            else None
        )
        records: dict = {}
        attempts: dict = {j.key: 0 for j in jobs}
        journal = Journal(self.journal_path, run_id)
        self._install_handlers()
        pending = list(jobs)
        active: list = []
        finished: list = []
        try:
            journal.record(
                "run_started",
                resume=self.resume,
                platform=sys.platform,
                limits={
                    "wall_seconds": self.limits.wall_seconds,
                    "run_wall_seconds": self.limits.run_wall_seconds,
                    "memory_bytes": self.limits.memory_bytes,
                    "max_stdout_bytes": self.limits.max_stdout_bytes,
                    "max_stderr_bytes": self.limits.max_stderr_bytes,
                    "max_report_bytes": self.limits.max_report_bytes,
                    "scratch_bytes": self.limits.scratch_bytes,
                    "retries": self.limits.retries,
                    "jobs": self.limits.jobs,
                },
                rlimit_support=self.rlimit_support,
                jobs=keys,
            )
            for job in jobs:
                journal.record("job_queued", job=job.key)
            while pending or active:
                while (
                    pending
                    and len(active) < self.limits.jobs
                    and not self._cancel_requested
                    and (run_deadline is None or time.monotonic() < run_deadline)
                ):
                    job = pending.pop(0)
                    resumed = presumed.get(job.key)
                    if resumed is not None:
                        journal.record("job_skipped", job=job.key, reason="resume_verified")
                        records[job.key] = resumed
                        continue
                    attempts[job.key] += 1
                    try:
                        child = self._spawn(job, attempts[job.key], journal)
                    except (OSError, subprocess.SubprocessError) as error:
                        record = JobRecord(
                            key=job.key, status=STATUS_FAILED, failure_kind=KIND_SPAWN_ERROR,
                            reason=f"spawn failed: {type(error).__name__}",
                            attempts=attempts[job.key], config_digest=digests[job.key],
                        )
                        journal.record("job_terminal", job=job.key, attempt=attempts[job.key],
                                       status=record.status, failure_kind=record.failure_kind,
                                       reason=record.reason)
                        records[job.key] = record
                        if self._retryable(record, attempts[job.key], run_deadline):
                            journal.record("job_retry", job=job.key,
                                           attempt=attempts[job.key] + 1,
                                           reason=f"{record.failure_kind} is transient")
                            pending.insert(0, job)
                        continue
                    active.append(child)
                if not active:
                    break  # refill blocked by cancel/deadline or queue drained
                self._run_children(active, finished, journal, run_deadline)
                for child in finished:
                    job = child.job
                    status, kind, reason = self._classify_attempt(child)
                    wall_ms = int((time.monotonic() - child.started_mono) * 1000)
                    journal.record(
                        "child_reaped", job=job.key, attempt=child.attempt,
                        exit_code=child.exit_code, signal=child.signal,
                        peak_rss_bytes=child.peak_rss, wall_ms=wall_ms,
                        stdout_bytes=child.stdout.total, stderr_bytes=child.stderr.total,
                        stdout_sha256=child.stdout.digest(),
                        stderr_sha256=child.stderr.digest(),
                    )
                    report_path = report_sha = None
                    report_bytes = None
                    if status == STATUS_COMPLETED:
                        report_path, report_sha, report_bytes, commit_error = (
                            self._commit_report(child, journal)
                        )
                        if commit_error is not None:
                            status, kind = STATUS_FAILED, commit_error
                            reason = {
                                KIND_OUTPUT_LIMIT: f"report exceeded {self.limits.max_report_bytes}-byte cap",
                                KIND_REPORT_INVALID: "child output failed validation",
                                KIND_MISSING_OUTPUT: "child exited 0 without its declared output",
                            }[commit_error]
                    if status == STATUS_COMPLETED and self._scratch_bytes(child.scratch) > self.limits.scratch_bytes:
                        status, kind = STATUS_FAILED, KIND_OUTPUT_LIMIT
                        reason = f"scratch exceeded {self.limits.scratch_bytes}-byte cap"
                    journal.record("job_terminal", job=job.key, attempt=child.attempt,
                                   status=status, failure_kind=kind, reason=reason)
                    record = JobRecord(
                        key=job.key, status=status, failure_kind=kind, reason=reason,
                        attempts=child.attempt,
                        report_path=report_path, report_sha256=report_sha,
                        report_bytes=report_bytes,
                        stdout_bytes=child.stdout.total, stderr_bytes=child.stderr.total,
                        peak_rss_bytes=child.peak_rss, wall_ms=wall_ms,
                        exit_code=child.exit_code, signal=child.signal,
                        stray_descendants=child.stray,
                        config_digest=digests[job.key],
                    )
                    records[job.key] = record
                    shutil.rmtree(child.scratch, ignore_errors=True)
                    if self._retryable(record, attempts[job.key], run_deadline):
                        journal.record("job_retry", job=job.key, attempt=attempts[job.key] + 1,
                                       reason=f"{record.failure_kind} is transient")
                        pending.insert(0, job)
                finished.clear()
            # Sweep: children still in `active` (shouldn't happen) and queued
            # jobs receive terminal records — every planned job ends terminal.
            for child in active:
                self._terminate_group(child, journal, "cancel")
                records[child.job.key] = JobRecord(
                    key=child.job.key, status=STATUS_CANCELLED, reason="cancelled by request",
                    attempts=child.attempt, config_digest=digests[child.job.key],
                    stdout_bytes=child.stdout.total, stderr_bytes=child.stderr.total,
                )
                journal.record("job_terminal", job=child.job.key, attempt=child.attempt,
                               status=STATUS_CANCELLED, reason="cancelled by request")
                self._close_pipes(child)
                shutil.rmtree(child.scratch, ignore_errors=True)
            for job in pending:
                cancelled = self._cancel_requested
                record = JobRecord(
                    key=job.key,
                    status=STATUS_CANCELLED if cancelled else STATUS_TIMEOUT,
                    failure_kind=None if cancelled else KIND_RUN_DEADLINE,
                    reason="cancelled by request" if cancelled else "run deadline exceeded",
                    attempts=0, config_digest=digests[job.key],
                )
                journal.record("job_terminal", job=job.key, attempt=0,
                               status=record.status, failure_kind=record.failure_kind,
                               reason=record.reason)
                records[job.key] = record
            if self._cancel_requested:
                journal.record("cancel_requested", signal=self._cancel_signal)
            for job in jobs:  # I05: no planned job may lack a terminal record
                if job.key not in records:
                    records[job.key] = JobRecord(
                        key=job.key, status=STATUS_FAILED, failure_kind=KIND_INTERRUPTED,
                        reason="run interrupted before a terminal result",
                        attempts=attempts[job.key], config_digest=digests[job.key],
                    )
        finally:
            status = self._run_status(records, jobs)
            journal.record(
                "run_terminal", status=status,
                counts={s: sum(1 for r in records.values() if r.status == s)
                        for s in (STATUS_COMPLETED, STATUS_FAILED, STATUS_TIMEOUT,
                                  STATUS_CANCELLED, STATUS_SKIPPED)},
            )
            index = {
                "kind": _RUN_INDEX_KIND,
                "schema_version": _RUN_INDEX_VERSION,
                "run_id": run_id,
                "status": status,
                "started_at": started_at,
                "ended_at": _utcnow(),
                "platform": sys.platform,
                "rlimit_support": self.rlimit_support,
                "limits": {
                    "wall_seconds": self.limits.wall_seconds,
                    "run_wall_seconds": self.limits.run_wall_seconds,
                    "memory_bytes": self.limits.memory_bytes,
                    "max_stdout_bytes": self.limits.max_stdout_bytes,
                    "max_stderr_bytes": self.limits.max_stderr_bytes,
                    "max_report_bytes": self.limits.max_report_bytes,
                    "scratch_bytes": self.limits.scratch_bytes,
                    "retries": self.limits.retries,
                    "jobs": self.limits.jobs,
                },
                "jobs": {k: r.to_dict() for k, r in records.items()},
            }
            try:
                atomic_write_bytes(
                    self.index_path,
                    (json.dumps(index, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                )
            finally:
                journal.close()
                self._restore_handlers()
        return RunResult(
            status=status,
            run_id=run_id,
            run_dir=str(self.out_dir),
            jobs=records,
            index_path=str(self.index_path),
            journal_path=str(self.journal_path),
            started_at=started_at,
            ended_at=_utcnow(),
        )

    def _run_status(self, records: dict, jobs: list) -> str:
        if self._cancel_requested:
            return "cancelled"
        values = [records[j.key].status for j in jobs if j.key in records]
        ok = sum(1 for s in values if s in (STATUS_COMPLETED, STATUS_SKIPPED))
        bad = sum(1 for s in values if s in (STATUS_FAILED, STATUS_TIMEOUT))
        if ok == len(jobs):
            return "complete"
        if ok == 0 and bad > 0:
            return "failed"
        return "partial"
