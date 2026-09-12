"""Native parent supervision and atomic partial results (T29).

Disposable-reader supervision for the local CLI/corpus path, per
``planning/architecture/RUNTIME_LIFECYCLE.md`` "Native supervision":

    from inkflip.runtime import JobSpec, Limits, Supervisor

    supervisor = Supervisor(Path("runs/corpus-1"), Limits(wall_seconds=30))
    result = supervisor.run([
        JobSpec(key="file-a", argv=[sys.executable, "worker.py", "a.pdf"],
                produces="report.json"),
        JobSpec(key="file-b", argv=[sys.executable, "worker.py", "b.pdf"],
                produces="report.json"),
    ])
    # result.status: complete | partial | failed | cancelled
    # <out>/reports/<key>.json committed atomically; journal.jsonl append-only.

Public surface: ``Limits``, ``JobSpec``, ``JobRecord``, ``RunResult``,
``ParallelAdmission``, ``Supervisor``, ``SupervisionError``, the terminal
status/failure-kind constants, ``atomic_write_bytes``, ``Journal`` and
``read_journal``. POSIX only (process groups); PDFium/engine calls stay
inside child processes, never in supervisor threads.
"""
from .artifacts import Journal, atomic_write_bytes, config_digest, read_journal, sha256_bytes, sha256_file
from .supervisor import (
    KIND_CRASH,
    KIND_EXIT,
    KIND_INTERRUPTED,
    KIND_MEMORY_LIMIT,
    KIND_MISSING_OUTPUT,
    KIND_OUTPUT_LIMIT,
    KIND_REPORT_INVALID,
    KIND_RUN_DEADLINE,
    KIND_SPAWN_ERROR,
    KIND_WALL,
    RETRYABLE_KINDS,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_TIMEOUT,
    JobRecord,
    JobSpec,
    Limits,
    ParallelAdmission,
    RunResult,
    SupervisionError,
    Supervisor,
    probe_rlimits,
)

__all__ = [
    "Journal",
    "JobRecord",
    "JobSpec",
    "Limits",
    "ParallelAdmission",
    "RETRYABLE_KINDS",
    "RunResult",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_SKIPPED",
    "STATUS_TIMEOUT",
    "KIND_CRASH",
    "KIND_EXIT",
    "KIND_INTERRUPTED",
    "KIND_MEMORY_LIMIT",
    "KIND_MISSING_OUTPUT",
    "KIND_OUTPUT_LIMIT",
    "KIND_REPORT_INVALID",
    "KIND_RUN_DEADLINE",
    "KIND_SPAWN_ERROR",
    "KIND_WALL",
    "SupervisionError",
    "Supervisor",
    "atomic_write_bytes",
    "config_digest",
    "probe_rlimits",
    "read_journal",
    "sha256_bytes",
    "sha256_file",
]
