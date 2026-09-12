/**
 * Failure taxonomy for the browser OCR adapter (T10).
 *
 * The public reason strings are the union of the RUNTIME_LIFECYCLE.md
 * failure taxonomy and the READER_ADAPTER_CONTRACT.md capability-error
 * list. A reason travels in `CheckResult.reason` and in the adapter's
 * own outcome records; the coordinator classifies it instead of
 * re-inferring from exceptions. Raw exceptions are local diagnostics
 * only — they are mapped to these stable codes at the boundary.
 */
import { REASON } from '../../runtime/src/index.ts';

/**
 * OCR adapter reason codes. `init_crash`, `worker_crash`, `timeout`,
 * `user_cancel`, `resource_limit` and `unsupported` come from the shared
 * runtime taxonomy (packages/runtime); the OCR-specific reasons below
 * are the READER_ADAPTER_CONTRACT "Capability negotiation and errors"
 * list plus the RUNTIME_LIFECYCLE asset states.
 */
export const OCR_REASON = {
  /** worker process/page died after initialization — transient. */
  WORKER_CRASH: REASON.WORKER_CRASH,
  /** worker failed to initialize — transient. */
  INIT_CRASH: REASON.INIT_CRASH,
  /** user asked to cancel — never retried automatically. */
  USER_CANCEL: REASON.USER_CANCEL,
  /** capability/clip/structure unsupported — never retried. */
  UNSUPPORTED: REASON.UNSUPPORTED,
  /** check/run deadline reached — not a transient crash. */
  TIMEOUT: REASON.TIMEOUT,
  /** output exceeded a declared bound (pixels, occurrences, bytes). */
  RESOURCE_LIMIT: REASON.RESOURCE_LIMIT,
  /** encrypted input — unsupported, never retried. */
  ENCRYPTED: REASON.ENCRYPTED,
  /** a dependency check did not complete, so this check never ran. */
  DEPENDENCY: REASON.DEPENDENCY,

  /** the requested OCR model is absent (fetch 404 / no cached copy). */
  MISSING_MODEL: 'missing_model',
  /** model bytes failed the manifest SHA-256 — never used. */
  MODEL_INTEGRITY: 'model_integrity',
  /**
   * The recognizer ran to completion but produced no usable text for
   * the pixels it was given. Informational outcome of a *completed*
   * check — never conflated with an initialization/model failure.
   */
  UNREADABLE_PIXELS: 'unreadable_pixels',
  /**
   * The model cannot be prepared because the machine cannot reach the
   * same-origin asset and no verified cached copy exists. Honest
   * asset state — distinct from an unreadable page.
   */
  UNAVAILABLE_OFFLINE: 'unavailable_offline',
  /** the raster source failed to produce the page raster. */
  RENDER_ERROR: 'render_error',
  /** region/page geometry could not be resolved into a crop. */
  GEOMETRY_UNAVAILABLE: 'geometry_unavailable',
  /** the engine returned a malformed/unverifiable result. */
  PARSER_ERROR: 'parser_error',
  /**
   * The engine produced no `blocks` hierarchy for a check that
   * requested it — a capability failure, never fabricated boxes.
   */
  BLOCKS_UNAVAILABLE: 'blocks_unavailable',
  /** a retried run disagreed in a way the adapter cannot reconcile. */
  NONDETERMINISM: 'nondeterminism',
} as const;

export type OcrReason = (typeof OCR_REASON)[keyof typeof OCR_REASON];

/** Reasons eligible for the single automatic transient retry. */
export const OCR_TRANSIENT_REASONS: ReadonlySet<string> = new Set([
  OCR_REASON.INIT_CRASH,
  OCR_REASON.WORKER_CRASH,
]);

/**
 * Reasons that must never be retried automatically: user cancellation,
 * unsupported features, integrity failures, offline/missing model.
 */
export const OCR_NO_RETRY_REASONS: ReadonlySet<string> = new Set([
  OCR_REASON.USER_CANCEL,
  OCR_REASON.ENCRYPTED,
  OCR_REASON.UNSUPPORTED,
  OCR_REASON.MISSING_MODEL,
  OCR_REASON.MODEL_INTEGRITY,
  OCR_REASON.UNAVAILABLE_OFFLINE,
]);

/** Classify an unknown thrown value into a stable reason code. */
export function classifyError(error: unknown, fallback: OcrReason): {
  reason: OcrReason;
  detail: string;
} {
  if (error instanceof OcrError) {
    return { reason: error.reason, detail: error.message };
  }
  const raw = error instanceof Error ? error.message : String(error);
  const text = raw.toLowerCase();
  if (/timeout|timed out/.test(text)) {
    return { reason: OCR_REASON.TIMEOUT, detail: raw };
  }
  if (/cancel/.test(text)) {
    return { reason: OCR_REASON.USER_CANCEL, detail: raw };
  }
  if (/integrity|sha256|hash/.test(text)) {
    return { reason: OCR_REASON.MODEL_INTEGRITY, detail: raw };
  }
  if (/fetch|network|offline|failed to fetch|load failed/.test(text)) {
    return { reason: OCR_REASON.UNAVAILABLE_OFFLINE, detail: raw };
  }
  return { reason: fallback, detail: raw };
}

/** An adapter failure carrying a stable machine-readable reason. */
export class OcrError extends Error {
  readonly reason: OcrReason;

  constructor(reason: OcrReason, message: string) {
    super(`${reason}: ${message}`);
    this.name = 'OcrError';
    this.reason = reason;
  }
}

export function requireOcr(
  condition: boolean,
  reason: OcrReason,
  message: string,
): asserts condition {
  if (!condition) throw new OcrError(reason, message);
}
