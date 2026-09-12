/**
 * Runtime limits, state labels and failure/retry taxonomy (T11).
 *
 * `RUNTIME_LIMITS` mirrors the browser profile of the canonical
 * `planning/config/settings.json`; the values are safety limits, not
 * development budgets. State and status spellings are shared with
 * `planning/architecture/RUNTIME_LIFECYCLE.md`, the inkflip schema
 * (`packages/contracts`), and `planning/product/copy.json`.
 */

export const RUNTIME_LIMITS = {
  /** schema WorkerMessage payload.occurrences maxItems. */
  maxResultChunkOccurrences: 256,
  /** acknowledged-window bound: chunks in flight without an ack. */
  maxUnackedChunks: 2,
  /** live raster buffers held at once. */
  maxLiveRasters: 2,
  /** OCR workers admitted at once. */
  maxOcrWorkers: 1,
  /** active page renders admitted at once. */
  maxActiveRenders: 1,
  /** per-page produced-occurrence cap before resource_limit. */
  maxOccurrencesPerPage: 20000,
  /** per-run produced-occurrence cap before resource_limit. */
  maxOccurrencesPerRun: 100000,
  /** per-run raw-text byte cap before resource_limit. */
  maxRawTextBytesPerRun: 8388608,
  /** automatic retries for transient initialization/worker crashes. */
  maxTransientRetries: 1,
  /** cancel -> UI-visible update target. */
  cancelUiTargetMs: 100,
  /** cancel -> generation unreachable / teardown target. */
  terminateTargetMs: 500,
  /** default per-check deadline when the plan does not set one. */
  checkTimeoutMs: 30000,
} as const;

export type RuntimeLimits = typeof RUNTIME_LIMITS;

/** File/run lifecycle states (RUNTIME_LIFECYCLE.md state machine). */
export const FILE_STATES = [
  'idle',
  'validating_file',
  'loading_metadata',
  'selecting',
  'preparing_assets',
  'running',
  'complete',
  'partial',
  'failed',
  'cancelled',
  'clearing',
] as const;
export type FileState = (typeof FILE_STATES)[number];

/** Terminal run states only; `clearing` is transient, never a result. */
export const TERMINAL_RUN_STATUSES = [
  'complete',
  'partial',
  'failed',
  'cancelled',
] as const;
export type TerminalRunStatus = (typeof TERMINAL_RUN_STATUSES)[number];

/** Per-check phases; `terminal` is reached exactly once (I05). */
export const CHECK_PHASES = ['queued', 'running', 'terminal'] as const;
export type CheckPhase = (typeof CHECK_PHASES)[number];

/** Terminal check values — the schema CheckResult.status enum. */
export const TERMINAL_CHECK_STATUSES = [
  'completed',
  'unsupported',
  'timeout',
  'cancelled',
  'failed',
  'skipped',
] as const;
export type TerminalCheckStatus = (typeof TERMINAL_CHECK_STATUSES)[number];

/**
 * Failure/retry taxonomy (RUNTIME_LIFECYCLE.md "Failure taxonomy and
 * retry"). A reason string travels in CheckResult.reason; the coordinator
 * classifies it instead of re-inferring from errors.
 */
export const REASON = {
  /** worker process/page died after initialization — transient. */
  WORKER_CRASH: 'worker_crash',
  /** worker failed to initialize — transient. */
  INIT_CRASH: 'init_crash',
  /** user asked to cancel — never retried automatically. */
  USER_CANCEL: 'user_cancel',
  /** encrypted input — unsupported, never retried. */
  ENCRYPTED: 'encrypted',
  /** capability/clip/structure unsupported — never retried. */
  UNSUPPORTED: 'unsupported',
  /** known integrity mismatch (model/cache) — never retried. */
  INTEGRITY: 'integrity_failure',
  /** check/run deadline reached — not a transient crash. */
  TIMEOUT: 'timeout',
  /** output exceeded a declared bound. */
  RESOURCE_LIMIT: 'resource_limit',
  /** sender violated the acknowledged-chunk bound or identity rules. */
  PROTOCOL: 'protocol_violation',
  /** a dependency check did not complete, so this check never ran. */
  DEPENDENCY: 'dependency_unmet',
  /** inbound bytes failed contract validation. */
  MALFORMED: 'malformed_message',
} as const;
export type Reason = (typeof REASON)[keyof typeof REASON];

/** Reasons eligible for the single automatic transient retry. */
export const TRANSIENT_REASONS: ReadonlySet<string> = new Set([
  REASON.WORKER_CRASH,
  REASON.INIT_CRASH,
]);

/**
 * Reasons that must never be retried automatically: user cancellation,
 * encrypted input, unsupported features, known integrity failures.
 */
export const NO_RETRY_REASONS: ReadonlySet<string> = new Set([
  REASON.USER_CANCEL,
  REASON.ENCRYPTED,
  REASON.UNSUPPORTED,
  REASON.INTEGRITY,
]);

/** Classify a terminal reason for the retry decision. */
export function retryKind(
  reason: string | null,
): 'transient' | 'never' | 'other' {
  if (reason === null) return 'other';
  if (TRANSIENT_REASONS.has(reason)) return 'transient';
  if (NO_RETRY_REASONS.has(reason)) return 'never';
  return 'other';
}
