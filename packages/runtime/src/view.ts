/**
 * Presentation snapshot (T11).
 *
 * The coordinator's `snapshot()` is the ONLY state the UI may render:
 * it is rebuilt from accepted, committed bookkeeping — never from a
 * rejected or in-flight message — so a stale event can never reach the
 * screen (I07). `revision` increments on every accepted mutation, which
 * lets a view layer cheaply detect that nothing changed.
 *
 * Progress stays stage-specific (per check: completed/total units; a
 * null total is an indeterminate engine with no denominator). There is
 * deliberately no unified percentage field: mixed units must not be
 * averaged into an exact-looking number.
 */
import type { Occurrence } from '../../contracts/src/index.ts';
import type {
  CheckPhase,
  FileState,
  TerminalCheckStatus,
  TerminalRunStatus,
} from './limits.ts';

/** Copy keys from planning/product/copy.json used for run notices. */
export const NOTICE_KEYS = {
  cancelled: 'progress.cancelled',
  partial: 'progress.partial',
  failed: 'progress.failed',
  complete: 'progress.complete',
  timeout: 'progress.timeout',
  resource: 'progress.resource',
} as const;
export type NoticeKey = (typeof NOTICE_KEYS)[keyof typeof NOTICE_KEYS];

export interface CheckView {
  readonly id: string;
  readonly capability: string;
  readonly pageIndex: number;
  readonly phase: CheckPhase;
  /** terminal status; null while queued/running. */
  readonly status: TerminalCheckStatus | null;
  readonly reason: string | null;
  readonly producedOccurrences: number;
  readonly retainedOccurrenceIds: readonly string[];
  readonly attempts: number;
  readonly progress: { completed: number; total: number | null } | null;
}

export interface RunView {
  readonly runKey: string;
  readonly status: TerminalRunStatus | null;
  readonly cancelRequested: boolean;
  readonly startedAt: number;
  readonly deadlineAt: number | null;
  readonly selectedPagesTotal: number;
  readonly checks: readonly CheckView[];
}

export interface SessionView {
  readonly fileState: FileState;
  readonly generation: number;
  readonly documentSha256: string | null;
  readonly run: RunView | null;
  /** Retained committed occurrences in plan order — the renderable evidence. */
  readonly occurrences: readonly Occurrence[];
  /** Copy key for the current user-facing run notice, if any. */
  readonly notice: NoticeKey | null;
  /** Monotonic mutation counter; equal revisions mean identical content. */
  readonly revision: number;
}
