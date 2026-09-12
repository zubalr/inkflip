# T29 independent review — native parent supervision and atomic partial results

**Verdict: changes-required on exact candidate `3ae5cf9` (impl `607a0f7` + `e067442`, tests `07c6d24`, evidence `3ae5cf9`).**

All five written acceptance criteria were independently verified by execution
and hold on the default configuration. One blocking defect remains: output
overflow that is only observed after a child is reaped is never classified —
a flooding child that exits 0 while the parent loop is blocked is recorded
`completed` even though `stdout_bytes` in the same index entry exceeds the
cap. The defect is deterministically reachable under admitted `jobs>1`
concurrency, a tested public feature. One-line fix in `_classify_attempt`
plus a regression test.

Independent reviewer: Devin Local SWE-2 review subagent (this session), not
the writer (`devin-t29`; commits `607a0f7`–`e067442`). Reviewed in the
dedicated checkout `original/worktrees/review-devin/t29` on
`review/devin/t29` at `3ae5cf9`; never ran or wrote this code before this
review. Read `AGENTS.md`, `docs/ACCEPTANCE.md`, `docs/NATIVE_PASSES.md`,
`docs/HOMEBASE.md`, `planning/PROJECT_BRIEF.md`,
`planning/architecture/GLOSSARY_AND_INVARIANTS.md`, the effective contract
(`python3 scripts/coordination.py task T29`), all four evidence artifacts,
and the complete diff vs base `21be4c9`.

## Reproduced counts

| Executed command (this checkout) | Result |
| --- | --- |
| `uv run --project native python -m pytest native/tests/runtime -q` | **34 passed, 4 subtests passed**, exit 0, ~10.6 s |
| same + `-W error::DeprecationWarning` | **34 passed, 4 subtests**, exit 0 |
| `python3 scripts/task_acceptance.py task T29` | **collected 34 / passed 34 / 0 failed / 0 skipped**; run record matches contract argv+cwd |
| `uv run --project native python -m pytest native/tests -q` (whole suite) | **144 passed, 153 subtests, 1 failed** — the single failure is the claimed pre-existing T27 OCR test (below) |
| Independent probes (10 scripts, real children/drivers, `/tmp/t29-probe/`) | see per-criterion notes |

`run.json` binds `evaluated_commit e06744223f53a00975ae33b0b2da8e4ca3828420` —
verified equal to `git rev-parse e067442`. The `3ae5cf9` head adds only
task evidence; per `docs/ACCEPTANCE.md` an evidence-only commit does not
invalidate that evaluation.

## Scope verification

`git diff 21be4c9..3ae5cf9 --stat`: **11 new files, 0 modified** —
4 implementation (`native/inkflip/runtime/{__init__,artifacts,supervisor,README}`),
3 test (`native/tests/runtime/{fault_worker,supervisor_driver,test_supervision}`),
4 evidence (`artifacts/tasks/T29/*`). Zero bytes under `native/tests/ocr/`,
`native/inkflip/readers/`, `tests/fixtures/`, `fixtures/`, `planning/`,
`scripts/`. Within allowed scope.

## Criterion 1 — injected hang/crash/OOM/output-flood classified AND bounded

**Verified — and fault workers are real subprocesses, not supervisor mocks.**
`fault_worker.py` modes use real mechanisms: `os.kill(self, SIGSEGV)`, real
heap growth, real pipe floods, real `SIG_IGN`, real `Popen` grandchildren,
real `SIGINT` to `getppid()`. `supervisor_driver.py` runs the actual
`Supervisor` in a separate process for the Ctrl-C test. Tests touch only
the public API; the runtime contains **zero `os.environ`/`getenv` reads**
and no test knobs.

Beyond the suite, independently probed:

- **SIGTERM-ignoring child**: journaled SIGTERM→SIGKILL gap measured
  **0.508 s / 0.514 s** at default `kill_grace_seconds=0.5`; classified
  `timeout/wall`, `signal=SIGKILL`, retried once, whole run 1.96 s. The
  0.5 s→SIGKILL escalation is real.
- **Stray-descendant probe is real**: a grandchild that *also ignores
  SIGTERM*, orphaned by a leader that exits 0, is detected by the post-reap
  `killpg(pgid, 0)` probe, escalated to SIGKILL (`_cleanup_strays`,
  supervisor.py:782–809), journaled `descendants_reaped`, and flagged
  `stray_descendants=True`. Verified dead.
- **Bounded draining**: `_BoundedStream` counts every byte + sha256 while
  retaining only head 2048 + tail 2048 (supervisor.py:426–457); floods of
  3–4× cap on either stream are killed mid-run and classified
  `failed/output_limit`; journal records exact byte totals and digests.
- OOM is layered: `RLIMIT_AS` in-child where accepted, 100 ms RSS poll
  (libproc on macOS, `/proc` on Linux), post-exit `wait4` `ru_maxrss`;
  macOS `RLIMIT_AS` refusal is probed per run and recorded in
  `index.json.rlimit_support` — degradation is honest, not hidden.

**Blocking finding F1 (below)** is the one gap in this criterion: an
over-cap stream detected only *after* reap is never classified.

## Criterion 2 — successful files byte-stable

**Verified.** `atomic_write_bytes` (artifacts.py:64–88) does exclusive
`mkstemp` sibling → write → fsync → `os.replace` → directory fsync;
`index.json` uses the same path. Independent probe: 25 `SIGKILL`s of a
writer process at staggered mid-write offsets over a 4 MiB target →
**0 torn targets** (every read was either complete old or complete new
bytes). Suite asserts byte-identical reports across runs and verbatim
commit; resume re-verifies `report_sha256` and never rewrites (verified
end-to-end in the SIGINT-resume probe).

## Criterion 3 — one retry max within deadline

**Verified.** `RETRYABLE_KINDS = {exit, crash, wall, spawn_error}`
(supervisor.py:117); `_retryable` (1026–1035) requires transient kind AND
`attempts <= limits.retries` (default 1 = `native.max_retries`) AND
`time.monotonic() < run_deadline` AND not cancelled; the refill loop
re-checks the deadline before spawning. Probe: a retry admitted at
t≈0.4 s under `run_wall_seconds=0.7` is killed as
`timeout/run_deadline` — total run 0.79 s (deadline + kill grace only);
a slow retry cannot exceed the run deadline. `output_limit`,
`memory_limit`, `missing_output`, `report_invalid`, `cancelled` are
never retried (suite asserts `attempts=1` on each).

## Criterion 4 — empty success not retried

**Verified.** Exit 0 with `produces=None` → `completed`, `attempts=1`
(completed is not retryable). Exit 0 with a declared-but-absent output →
`failed/missing_output`, `attempts=1` — deterministic defect, also never
retried. A crashed child that wrote partial output never commits it
(`_commit_report` runs only for `completed`).

## Criterion 5 — Ctrl-C terminates descendants + valid partial artifact

**Verified end-to-end.** SIGINT/SIGTERM handlers only set a flag
(supervisor.py:578–584); the poll loop terminates every live process
group (`cancel` cause), queued jobs get terminal `cancelled` records,
and the `finally` still writes `run_terminal` + atomic `index.json`
(status `cancelled`). My driver-level probe then **resumed the same
out-dir**: prior `completed` job verified by sha256 + config digest →
`skipped` with bytes preserved; `cancelled` jobs rerun fresh; **journal
`seq` continued globally (15→29, strictly contiguous)** — the
seq-continuity claim is real. Journal torn-tail is tolerated on read
(verified with a truncated final line), while a corrupt middle line
raises — immutability is "ignore the tail", never repair.

Resume-after-kill hole check: `SIGKILL`ing the supervisor mid-run leaves
a readable journal (torn tail skipped) and intact committed reports but
no `index.json` → resume is honestly refused ("no index.json exists")
and a fresh run refuses the non-empty dir — no clobbering, no silent
reuse (see F4).

## Structural checks

- **jobs=1 default is structural**: `Limits.jobs=1` matches
  `planning/config/settings.json` `native.default_jobs=1`; `jobs>1` raises
  `SupervisionError` without an explicit `ParallelAdmission` whose
  CPU×RAM budget is checked. The supervisor uses **no threads** (no
  `threading` import; single selector loop) and no engine calls — PDFium
  can only run inside child processes, so the s26 exclusion is enforced
  by construction, not documentation.
- **`shell=False` + env allowlist enforced**: `Popen(shell=False, argv,
  env=_minimal_env+extras, start_new_session=True, cwd=scratch,
  stdin=DEVNULL)`. Verified via an env-echo child: no `PATH`, no `HOME`,
  no parent secret — only the fixed allowlist plus declared extras.
- `produces`/job-key patterns exclude `/` (no path traversal); produced
  file must be a non-symlink regular file; report size capped;
  `json.loads` validation default with a `validate_report` hook.
- Error reasons are safe templates (counts, signal names, caps) — no
  child stdout text or arbitrary paths leak into `reason`.
- All `Limits` defaults verified to mirror `settings.json.native`.

## T27 failure is genuinely unrelated

Reproduced exactly one whole-suite failure:
`native/tests/ocr/test_ocr.py::TestModelSelection::test_fallback_dir_is_probed_per_language`
— `PosixPath('/private/var/...tessdata') != PosixPath('/var/...tessdata')`
at `test_ocr.py:847`, a macOS `/var→/private/var` canonicalization issue
in T27-owned code. T29's diff touches **zero bytes** under
`native/tests/ocr/` and `native/inkflip/readers/` (the failing files are
byte-identical to base), so the failure is pre-existing/environmental on
this host, not introduced here. Recorded, not hidden — matches the
worker's claim precisely (144+153, 1 failed).

## Findings

### F1 — [P2, blocking] Post-reap stdout/stderr overflow is never classified

`_classify_attempt` (supervisor.py:820–868) maps `output_limit` only via
`killed_cause`, which is set only when the poll loop catches
`stream.overflow` while the child is still unreaped. Output consumed by
`_drain_until_eof` (771–780) *after* `_reap` succeeds — i.e., when the
child wrote past the cap and exited before its bytes were drained — sets
`overflow` too late: classification falls through to `exit 0 → completed`.

Reproduced deterministically (4/4) at admitted `jobs=2`: child A exits
leaving a SIGTERM-ignoring stray, so `_cleanup_strays` blocks the parent
loop ~2.4 s while child B writes 16384 B against an 8192 B cap and exits
0 → **B recorded `completed` with `stdout_bytes=16384 > cap` in the same
index entry** — a self-contradictory record: bounded retention and
journaling are intact, but the flood is classified as success. Any
sibling-blocking path can trigger it (`_terminate_group`'s ≤5.5 s reap
budget, a sibling's 1 s `_drain_until_eof` budget); at `jobs=1` the
window shrinks to a sub-millisecond race since the parent is
select-blocked whenever the child is live, so the demonstrated trigger
needs admitted concurrency. Memory has the correct post-exit mirror
(`peak_rss >= limit → memory_limit`, :847) — output is the only bound
lacking a post-reap check, which marks this an oversight rather than a
design choice.

Fix: in `_classify_attempt`, return `failed/output_limit` when
`child.stdout.overflow or child.stderr.overflow` (before the exit-code
path), and add a regression test (e.g., flood-then-exit-0 alongside a
stray-blocking sibling, or a cap smaller than the pipe buffer).

### F2 — [P3] Per-job env extras silently override the fixed allowlist

`_minimal_env` does `env.update(extra)` (supervisor.py:383), so a JobSpec
can overwrite `TMPDIR` (moving the child's temp writes outside the
scratch-capped directory, partially evading `scratch_bytes`) and the
`*_NUM_THREADS=1` pins; the journal records only key **names**
(`env_keys`), so the override is invisible in evidence — the journaled
key set is identical either way. Verified: child saw `TMPDIR=/tmp`,
`OMP_NUM_THREADS=99`. Spec-author footgun, not child-exploitable, but it
defeats documented bounds silently. Consider refusing collisions with
fixed keys or journaling which declared keys overrode allowlist keys.

### F3 — [P3] Config digest covers env key names but not values

`_job_config` includes `"env_keys": sorted(job.env)` (supervisor.py:613)
but not values. Verified: run 1 with `EXTRA=value-one` completed; resume
with `EXTRA=value-two` → **`skipped`** — prior evidence silently reused
under a changed environment. Hashing declared env *values* into
`config_digest` fixes it without leaking them (digest output is a hash).

### F4 — [P3] Hard-killed supervisor leaves the out-dir a dead end

After `SIGKILL` of the supervisor: `index.json` absent → `resume`
refused; fresh run refused (non-empty dir). Honest and clobber-free —
correct failure behavior — but the only recovery is a new run directory
even though `journal.jsonl` + committed `reports/` are intact, and the
leftover `scratch/` and orphaned (setsid'd) children persist, which is
inherent: a dead supervisor cannot kill. Worth one line in
README "Honest limits" / limitations so it reads as designed, not lost.

### Observations (non-blocking)

- `Limits.retries` is caller-configurable; a caller could set >1 and
  exceed "one retry max". Default 1 matches `native.max_retries`; the
  bound is enforced relative to the configured value. Sanctioned config
  surface — noted only.
- `_cleanup_strays` returns True even when strays outlive SIGKILL (2 s
  probe timeout) — flagged honestly via `stray_descendants`, not hidden.
- D-state/unreapable children degrade to `abandoned` + `child_unreaped`
  journal rather than hanging the run — good honest degradation.
- `probe_rlimits` correctly moved from `os.fork` to a fresh interpreter
  subprocess in `e067442`; `-W error::DeprecationWarning` is clean.
- macOS injects `__CF_USER_TEXT_ENCODING` at exec regardless of parent
  env — the suite's platform-allowlist handling of this is correct
  (OS-injected, not inherited).

## Process hygiene

Post-probe check found one leftover `fault_worker hang-grandchild` —
traced to my own probe 6 (`SIGKILL`ed supervisor cannot reap its
setsid'd children; inherent, not a defect). Killed; `pgrep` now clean.
No probe files were written inside the repository; `git status` clean
except this review.
