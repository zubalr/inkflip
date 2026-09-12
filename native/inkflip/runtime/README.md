# `inkflip.runtime` — native parent supervision (T29)

Disposable-reader process supervision and atomic partial results for the
local CLI/corpus path, implementing `planning/architecture/RUNTIME_LIFECYCLE.md`
"Native supervision" and the containment rows of
`planning/security/THREAT_MODEL.md`. POSIX only (process groups); no threads —
PDFium/engine calls stay inside child processes (s26).

## Model

Each `JobSpec` is spawned as a disposable child (`shell=False`, fixed argv) in
its **own process group** with a private scratch directory and a minimal
environment allowlist. The parent enforces:

- **wall deadline** — poll-loop kill of the whole group (SIGTERM → 0.5 s grace
  → SIGKILL); never SIGALRM;
- **memory bound** — `RLIMIT_AS` where the OS accepts it + live RSS probe
  (`/proc` on Linux, libproc `proc_pidinfo` on macOS) + post-exit `wait4`
  `ru_maxrss`; unsupported facilities are recorded in `index.json`
  (`rlimit_support`), never silently skipped;
- **output caps** — stdout/stderr drained and counted live, bounded sample
  only; over-cap → group kill, `output_limit`;
- **stray descendants** — after the leader is reaped the group is probed and
  leftover members killed;
- **Ctrl-C** — SIGINT/SIGTERM to the supervisor cancels: live groups die,
  queued jobs get terminal `cancelled` records, `index.json` + journal remain
  valid (partial artifact, I17);
- **one retry max** — transient kinds (`exit`, `crash`, `wall` timeout,
  `spawn_error`) retry once within the run deadline; `output_limit`,
  `memory_limit`, `missing_output`, `report_invalid`, `cancelled`, and any
  completed job (including empty success) are never retried;
- **jobs=1 default** — `Limits(jobs>1)` is refused without an explicit
  `ParallelAdmission(cpu_count=…, memory_bytes=…)` check.

## Artifacts

```
<out>/journal.jsonl        append-only, fsynced JSONL; torn tail tolerated on read
<out>/index.json           atomic tmp+rename terminal index of the last run
<out>/reports/<key>.json   per-file artifacts, exclusive tmp sibling → fsync → rename
<out>/scratch/             private per-attempt child dirs (removed after each job)
```

`resume=True` reuses a prior `completed` job only when its report file still
hashes to the recorded digest AND its config digest is identical — otherwise
the resume is refused (changed identity ⇒ new run directory), never silently
rerun.

## Example

```python
import sys
from pathlib import Path
from inkflip.runtime import JobSpec, Limits, Supervisor

sup = Supervisor(Path("runs/demo"), Limits(wall_seconds=30, memory_bytes=1 << 28))
result = sup.run([
    JobSpec("file-a", [sys.executable, "reader_worker.py", "a.pdf"], produces="report.json"),
    JobSpec("file-b", [sys.executable, "reader_worker.py", "b.pdf"], produces="report.json"),
])
print(result.status)                       # complete | partial | failed | cancelled
for key, rec in result.jobs.items():
    print(key, rec.status, rec.failure_kind, rec.reason)
```

The CLI task (T30+) maps `cancelled` to exit 130, `failed` to exit 4,
`partial` to exit 3, `complete` to exit 0 per `CLI_AND_REGRESSION.md`.

## Honest limits

- Memory bounding on macOS relies on the RSS poll + post-exit `ru_maxrss`
  (Darwin rejects `RLIMIT_AS`/`RLIMIT_DATA`/`RLIMIT_RSS` lowering); a child
  may transiently exceed the bound between probe ticks. Linux gets
  `RLIMIT_AS` prevention plus `/proc` polling. The hardened route remains a
  container (THREAT_MODEL).
- Process-group kill cannot reach a descendant that calls `setsid` itself;
  noted residual (container covers it).
- `preexec_fn` applies rlimits best-effort in the child; the parent's
  `rlimit_support` probe records what the platform actually accepted.
