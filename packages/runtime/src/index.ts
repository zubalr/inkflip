/**
 * @inkflip/runtime — run lifecycle, backpressure and cancellation (T11).
 *
 * Explicit file/run state machine, per-check terminal bookkeeping,
 * generation/digest/run/job/sequence message authority, bounded
 * acknowledged result chunks, retry taxonomy and owned-resource cleanup.
 * Contract shapes (`WorkerMessage`, `CheckPlan`, `CheckResult`,
 * `Occurrence`) and `validate` come from `@inkflip/contracts` — nothing
 * is redefined here.
 */
export {
  ADMIT_CODES,
  MessageAuthority,
  type ActiveRun,
  type Admission,
  type AdmitCode,
} from './authority.ts';
export {
  ChunkSender,
  DEFAULT_CHUNK_LIMITS,
  InboundWindow,
  TransferLedger,
  type ChunkLimits,
} from './backpressure.ts';
export {
  buildRecords,
  checkResults,
  commitChunk,
  computeRunStatus,
  deriveDependencies,
  freezePlan,
  propagateSkips,
  runnableChecks,
  terminalize,
  validateDependencies,
  type AttemptRecord,
  type CheckRecord,
  type DependencyMap,
} from './checks.ts';
export {
  CleanupRegistry,
  TEARDOWN_VERBS,
  type CleanupFailure,
  type TeardownFn,
  type TeardownVerb,
} from './cleanup.ts';
export {
  RunCoordinator,
  TRANSITIONS,
  deriveRunKey,
  type CancelReceipt,
  type CoordinatorIntent,
  type CoordinatorOptions,
  type StartRunOptions,
} from './coordinator.ts';
export { RuntimeError, requireRuntime } from './errors.ts';
export {
  CHECK_PHASES,
  FILE_STATES,
  NO_RETRY_REASONS,
  REASON,
  RUNTIME_LIMITS,
  TERMINAL_CHECK_STATUSES,
  TERMINAL_RUN_STATUSES,
  TRANSIENT_REASONS,
  retryKind,
  type CheckPhase,
  type FileState,
  type Reason,
  type RuntimeLimits,
  type TerminalCheckStatus,
  type TerminalRunStatus,
} from './limits.ts';
export {
  JOB_ID_PATTERN,
  MessageFactory,
  RUN_KEY_PATTERN,
  emptyPayload,
  parseInbound,
  type MessageEvent,
  type MessageIdentity,
  type MessagePayload,
} from './messages.ts';
export {
  NOTICE_KEYS,
  type CheckView,
  type NoticeKey,
  type RunView,
  type SessionView,
} from './view.ts';
