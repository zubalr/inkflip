/**
 * Adapter error taxonomy (READER_ADAPTER_CONTRACT.md "Capability
 * negotiation and errors"). A `ReaderError` carries a public-safe reason
 * string from the shared runtime taxonomy; raw exception text is a local
 * diagnostic and is never propagated into check results unfiltered.
 */
import { REASON } from '../../runtime/src/index.ts';

/** Terminal check statuses this adapter can produce. */
export type AdapterFailure =
  | 'unsupported'
  | 'timeout'
  | 'cancelled'
  | 'failed'
  | 'resource_limit';

export class ReaderError extends Error {
  readonly failure: AdapterFailure;
  /** Public reason code suitable for CheckResult.reason. */
  readonly reason: string;

  constructor(failure: AdapterFailure, reason: string, message?: string) {
    super(message ?? reason);
    this.name = 'ReaderError';
    this.failure = failure;
    this.reason = reason;
  }
}

export function unsupportedReason(detail: string): string {
  return `${REASON.UNSUPPORTED}:${detail}`;
}

export function resourceLimitReason(detail: string): string {
  return `${REASON.RESOURCE_LIMIT}:${detail}`;
}

export function parserErrorReason(detail: string): string {
  return `parser_error:${detail}`;
}

export function renderErrorReason(detail: string): string {
  return `render_error:${detail}`;
}

export const CANCEL_REASON = REASON.USER_CANCEL;
export const TIMEOUT_REASON = REASON.TIMEOUT;
export const ENCRYPTED_REASON = REASON.ENCRYPTED;

/** Map an arbitrary thrown value to a ReaderError without leaking internals. */
export function classifyError(
  error: unknown,
  renderPhase = false,
): ReaderError {
  if (error instanceof ReaderError) return error;
  const name =
    typeof error === 'object' && error !== null
      ? String((error as { name?: unknown }).name ?? '')
      : '';
  const message = error instanceof Error ? error.message : String(error);
  if (name === 'PasswordException') {
    return new ReaderError(
      'unsupported',
      `${ENCRYPTED_REASON}:password-protected documents are unsupported`,
      'Password-protected PDF rejected',
    );
  }
  if (name === 'RenderingCancelledException') {
    return new ReaderError(
      'cancelled',
      CANCEL_REASON,
      'Render task cancelled',
    );
  }
  if (name === 'AbortException' || name === 'AbortError') {
    return new ReaderError('cancelled', CANCEL_REASON, 'Operation aborted');
  }
  const safe = `${name || 'Error'}`.slice(0, 120);
  return new ReaderError(
    'failed',
    renderPhase ? renderErrorReason(safe) : parserErrorReason(safe),
    message.slice(0, 500),
  );
}
