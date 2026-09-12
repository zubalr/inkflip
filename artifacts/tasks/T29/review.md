# T29 independent review — native parent supervision and atomic partial results

## Round 2 verdict: **approved** on exact revision `93b75ca`

(impl `057430e` + tests `601b370`, evidence `93b75ca`; merged into local
`review/devin/t29` — candidate state verified is exactly `93b75ca`'s tree.)

All four round-1 findings (F1 P2 blocking; F2–F4 P3) are **resolved** with
fixes and regression tests that were independently red/green-verified by
this reviewer against the actual old code, not only the worker's claim.
37 tests + 7 subtests reproduced; `task_acceptance` binds `601b370`. No
new findings. Test additions are purely additive (0 removed lines vs
`07c6d24`); nothing was weakened.

Independent reviewer: Devin Local SWE-2 review subagent (this session), not
the writer (`devin-t29`). Round 2 performed in the same dedicated checkout
`original/worktrees/review-devin/t29` on `review/devin/t29`: merged
`93b75ca` locally (merge `b75ef60`), no pushes, review branch stays local.

## Round-2 reproduced counts

| Executed command (this checkout, `93b75ca` state) | Result |
| --- | --- |
| `uv run --project native python -m pytest native/tests/runtime -q` | **37 passed, 7 subtests passed**, exit 0, ~11.7 s |
| `python3 scripts/task_acceptance.py task T29` | **collected 37 / passed 37 / 0 failed / 0 skipped** |
| `uv run --project native python -m pytest native/tests -q` | **147 passed, 156 subtests, 1 failed** — same single pre-existing T27 OCR failure (`test_ocr.py:847`, `/private/var` vs `/var`), diff still disjoint |
| Independent probes (old-code shadow package + new scenarios) | see below |

`run.json` binds `evaluated_commit 601b3707be61d2f78060299da7df5683cb52c10c`
— verified equal to `git rev-parse 601b370`.

## Finding resolution

### F1 [P2] — RESOLVED (verified red AND green)

`_classify_attempt` now checks `child.stdout.overflow or
child.stderr.overflow` after the `killed_cause` block and before the
signal/exit-code path (supervisor.py:~868–878) — the exact post-reap
mirror the memory bound already had via `peak_rss`. Precedence is
correct: cancel/wall/output kill causes still win (checked first), so a
wall-killed flooder stays `timeout/wall` and a cancelled flooder stays
`cancelled`; only previously-invisible post-reap overflow newly
classifies `failed/output_limit`.

- **Independent red**: built a shadow package from `e067442`'s
  supervisor.py and ran the new test's exact scenario
  (`leak-stubborn-grandchild` + `delayed-flood` 12288 B > 8192 B cap,
  jobs=2) → `file-b: completed, stdout_bytes=12288` — the new test would
  have failed on the old code, matching the worker's claimed red.
- **Independent green**: same scenario on `93b75ca` → `file-b:
  failed/output_limit, stdout_bytes=12288`; `file-c` (under-cap)
  `completed`; `file-a` `completed` + `stray_descendants`. Stderr mirror
  also verified (`--stderr` variant → `failed/output_limit`). `completed`
  is still only for under-cap output.
- The regression test genuinely exercises the sibling-blocked drain path:
  A's SIG_IGN stray holds `_cleanup_strays` for ~kill_grace while B's
  delayed burst lands and is drained only by `_drain_until_eof` after
  reap — `killed_cause` is never set on that path, so only the new mirror
  catches it. Timing margin (~0.5 s each side of the grace window) is
  comfortable on this host.

### F2 [P3] — RESOLVED

`FIXED_ENV_KEYS` (frozenset: locale, `TMPDIR`, all `*_NUM_THREADS` pins,
`PYTHONIOENCODING`) is exported; `JobSpec.validate` refuses redeclaration
with a clear error listing the collided names. Independently probed:
**all 9 fixed keys refused**, refusal happens before `_setup_dirs` (no
out-dir, journal or scratch created — early/honest), and additive extras
still reach the child (`EXTRA_OK` seen; `TMPDIR` remains the private
scratch). No production callers pass env extras today, so nothing
existing can regress.

### F3 [P3] — RESOLVED

`_job_config` now binds `"env": dict(sorted(job.env.items()))` — names
AND values — into `config_digest`; only the hash is persisted (values
never journaled or stored). Independently probed: resume with a changed
env VALUE under identical key names → `SupervisionError("config identity
changed…")` **before any writes** (index.json and journal.jsonl verified
byte-identical after refusal); identical env → `skipped`.

### F4 [P3] — RESOLVED

README "Honest limits" now documents the hard-killed-supervisor end
state: intact `journal.jsonl`/`reports/`, absent `index.json` → resume
honestly refused, fresh run refuses non-empty dir, recovery = new run
directory, orphaned setsid'd children out of scope (container route).
Matches the behavior my round-1 probe observed.

## Residual observations (unchanged, non-blocking)

- `Limits.retries` remains caller-configurable; default 1 matches
  `native.max_retries` — sanctioned config surface.
- macOS `RLIMIT_AS` refusal remains honestly recorded per run
  (`rlimit_support`); RSS-probe + `ru_maxrss` layering unchanged.
- Post-reap overflow fix means a flooding child that exits NONZERO now
  reports `output_limit` rather than `exit` — deliberate precedence,
  consistent with the live-kill path.

## Round-1 record (context, fully re-verified then)

Round 1 (`8c479d2`, changes-required on `3ae5cf9`) had verified:
34+4 suite; real-subprocess fault workers (no mocks/knobs);
SIGTERM→0.5 s→SIGKILL measured 0.508/0.514 s; stray-descendant probe
reaps a SIGTERM-ignoring grandchild; atomic write survives 25 mid-write
SIGKILLs with 0 torn targets; retry bounded to transient kinds within the
run deadline (0.79 s vs 0.7 s); empty success `completed`/attempts 1;
Ctrl-C → `cancelled` index + journal, resume with contiguous seq
(15→29), sha256+config-digest skip; SIGKILLed supervisor → honest
refusals; scope 11 new/0 modified; jobs=1 + no-threading structural;
env allowlist enforced (no PATH/HOME leak); T27 OCR failure pre-existing
and disjoint; `run.json` bound `e067442`.

## Process hygiene

No stray `fault_worker`/`probe_worker` processes after round 2 (`pgrep`
clean). Probes live under `/tmp/t29-probe` outside the repo; worktree is
clean except this review update.
