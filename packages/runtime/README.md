# `@inkflip/runtime` — run lifecycle, backpressure and cancellation (T11)

The bounded local-run engine for the browser workspace. It owns the
explicit lifecycle state machine, per-check terminal bookkeeping, the
generation/document/run/job/sequence message authority, acknowledged
result-chunk windows, the retry taxonomy and owned-resource cleanup.
Dependency-free TypeScript; every contract shape (`WorkerMessage`,
`CheckPlan`, `CheckResult`, `Occurrence`) and `validate` comes from
`@inkflip/contracts` — nothing is redefined.

## Modules

| file | contents |
| --- | --- |
| `limits.ts` | `RUNTIME_LIMITS` mirrored from `planning/config/settings.json`; file/check/run state labels; failure `REASON` taxonomy + `retryKind` |
| `errors.ts` | `RuntimeError` with stable codes (`TRANSITION`, `STATE`, `PLAN`, `IDENTITY`, `BACKPRESSURE`, `SEQUENCE`) |
| `messages.ts` | `MessageFactory` (per-job strictly increasing `seq` + identity five-tuple), `emptyPayload`, `parseInbound` contract validation |
| `authority.ts` | `MessageAuthority` admission registry: generation → document → run → job → sequence; terminal jobs reject late chunks |
| `backpressure.ts` | `ChunkSender` producer window (≤256 occurrences/message, ≤2 unacked), `InboundWindow` receiver accounting |
| `checks.ts` | `CheckRecord` ledger, immutable plan, DAG `deriveDependencies`, exactly-once `terminalize`, `computeRunStatus` |
| `cleanup.ts` | `CleanupRegistry`: LIFO bounded teardown of owned resources (cancel/abort/terminate/destroy/close/revoke/disconnect/remove/unsubscribe) |
| `coordinator.ts` | `RunCoordinator`: the state machine, dispatch/terminate/ack intents, cancel/clear/replace, retry, watchdogs, `snapshot()` |
| `view.ts` | `SessionView` presentation snapshot + copy notice keys |
| `index.ts` | public surface |

## Lifecycle

```text
idle -> validating_file -> loading_metadata -> selecting
selecting -> preparing_assets -> running        (OCR assets needed)
selecting -> running                            (assets already ready)
running -> complete | partial | failed | cancelled
terminal -> selecting                           (new explicit run, same file)
any -> clearing -> idle | validating_file       (clear / replacement)
```

`RunCoordinator` drives transitions; the embedder supplies files,
metadata, plans and a worker host. The coordinator emits intents —
`dispatch` (spawn a fresh worker for a job id), `terminate`, `message`,
`ack` — via `drainOutbox()`; the host executes them on real transports.
The coordinator never spawns workers, fetches or touches the DOM.

## Identity and stale results (I07)

Every message must carry the active generation, document SHA-256, run
key, job id and a strictly increasing per-job `seq`; anything else is
rejected (`stale_generation` / `stale_document` / `stale_run` /
`unknown_job` / `terminal_job` / `sequence` / `malformed`) before it can
touch state. Generation increments before clear/replacement begins and
after cancellation teardown; a terminal job rejects late chunks. The
`snapshot()` view is built only from admitted bookkeeping.

## Backpressure

`ChunkSender` packs ≤256 occurrences per chunk and will not emit a third
chunk while two are unacknowledged; the coordinator's `InboundWindow`
counts accepted minus delivered acks and terminalizes a flooding sender
as `protocol_violation`. Acks carry the acked chunk's `seq` in
`payload.completed_units` and are capacity grants, never success
findings. Occurrence/raw-text caps end an over-producing check as
`resource_limit` with completed independent results retained (I17).

## Terminal bookkeeping (I05)

Every planned check reaches exactly one terminal result —
`completed`/`unsupported`/`timeout`/`cancelled`/`failed`/`skipped` —
with a non-null reason unless completed. Run status: `complete` only
when all checks completed; `cancelled` on user request; `failed` when
nothing completed and something failed/timed out; `partial` otherwise.
A completed check with zero occurrences is a completed check, never a
retry candidate.

## Cancellation and cleanup

`requestCancel()` updates the visible state first (≤100 ms target),
then marks pending checks `cancelled`, emits cancel+terminate intents,
tears down run resources and invalidates the registry (≤500 ms target,
old generation unreachable). `requestClear('idle' | 'replace')` bumps
the generation before teardown, runs both registries, nulls document
and run state. Neither claims forensic secure erasure.

## Retry taxonomy

One automatic retry for `worker_crash`/`init_crash` only — a fresh job
identity within remaining run budget (`plan.budget.timeout_ms`). Never
retried: `user_cancel`, `encrypted`, `unsupported`, `integrity_failure`;
timeouts and other failures settle terminally without an automatic
retry. A user-requested rerun is a new execution and run plan.

## Commands

```sh
# T11 acceptance (TEST-11)
node --test tests/runtime/*.test.mjs
python3 scripts/task_acceptance.py task T11
```
