/**
 * Per-check terminal bookkeeping (T11; invariant I05).
 *
 * The immutable plan enumerates intended checks before work starts; each
 * check is `queued`, then `running`, then `terminal` exactly once, with a
 * schema-shaped `CheckResult` (completed / unsupported / timeout /
 * cancelled / failed / skipped). Queued work cancelled by the user
 * receives a terminal `cancelled` result; a check whose dependencies did
 * not complete receives a terminal `skipped` result that names them. A
 * completed read returning zero occurrences is a completed read — never
 * a skipped one and never a retry candidate.
 *
 * Terminal run status (RUNTIME_LIFECYCLE.md): `complete` only when every
 * planned check completed; `cancelled` when the user asked; `failed`
 * when nothing completed and at least one check failed or timed out;
 * `partial` otherwise. Successfully completed independent results are
 * preserved through every outcome (I17).
 */
import type {
  CheckPlan,
  CheckResult,
  Occurrence,
} from '../../contracts/src/index.ts';
import { requireRuntime } from './errors.ts';
import { InboundWindow, type ChunkLimits } from './backpressure.ts';
import {
  REASON,
  TERMINAL_CHECK_STATUSES,
  type CheckPhase,
  type Reason,
  type TerminalCheckStatus,
  type TerminalRunStatus,
} from './limits.ts';

const CHECK_ID_PATTERN = /^[a-z][a-z0-9_-]{0,95}$/;

/** One attempt's outcome, kept for audit — retries are new executions. */
export interface AttemptRecord {
  readonly jobId: string;
  readonly status: TerminalCheckStatus;
  readonly reason: string | null;
}

export interface CheckRecord {
  readonly plan: CheckPlan;
  phase: CheckPhase;
  result: CheckResult | null;
  /** Job currently serving the check; null while queued. */
  jobId: string | null;
  attempts: AttemptRecord[];
  /** Retained occurrence ids in commit order (the check's evidence). */
  retainedIds: string[];
  produced: number;
  rawTextBytes: number;
  readonly inbound: InboundWindow;
  progress: { completed: number; total: number | null } | null;
}

/**
 * Dependencies of one check as other planned check ids. A check becomes
 * runnable only when every dependency completed; a dependency that ends
 * non-completed terminalizes the dependent as `skipped` (OCR cannot run
 * without its raster, alignment cannot run without its readings).
 */
export type DependencyMap = ReadonlyMap<string, readonly string[]>;

/**
 * The documented check DAG: metadata → extraction/render → OCR →
 * alignment. OCR on a page needs the render check for the same page;
 * alignment needs the readings it compares (native_text and OCR checks
 * on the same page).
 */
export function deriveDependencies(checks: readonly CheckPlan[]): DependencyMap {
  const deps = new Map<string, string[]>();
  for (const check of checks) {
    const needs: string[] = [];
    if (check.capability === 'ocr') {
      for (const other of checks) {
        if (other.capability === 'render' && other.page_index === check.page_index) {
          needs.push(other.id);
        }
      }
    } else if (check.capability === 'alignment') {
      for (const other of checks) {
        if (
          other.page_index === check.page_index &&
          (other.capability === 'native_text' || other.capability === 'ocr')
        ) {
          needs.push(other.id);
        }
      }
    }
    deps.set(check.id, needs);
  }
  return deps;
}

/** Validate and deeply freeze the plan — it is immutable once issued. */
export function freezePlan(checks: readonly CheckPlan[]): CheckPlan[] {
  const ids = new Set<string>();
  const frozen = checks.map((check) => {
    requireRuntime(
      CHECK_ID_PATTERN.test(check.id),
      'PLAN',
      `check id ${JSON.stringify(check.id)} fails the schema pattern`,
    );
    requireRuntime(!ids.has(check.id), 'PLAN', `duplicate check id ${check.id}`);
    ids.add(check.id);
    return Object.freeze({ ...check, reader_ids: Object.freeze([...check.reader_ids]) });
  });
  return Object.freeze(frozen) as unknown as CheckPlan[];
}

/**
 * Validate the dependency map against the plan: every prerequisite id
 * must be a planned check and the graph must be acyclic — otherwise a
 * check could wait forever, which would violate I05.
 */
export function validateDependencies(
  deps: DependencyMap,
  checkIds: ReadonlySet<string>,
): void {
  for (const [id, needs] of deps) {
    requireRuntime(
      checkIds.has(id),
      'PLAN',
      `dependency entry for unknown check ${id}`,
    );
    for (const dep of needs) {
      requireRuntime(
        checkIds.has(dep),
        'PLAN',
        `check ${id} depends on unknown check ${dep}`,
      );
      requireRuntime(dep !== id, 'PLAN', `check ${id} depends on itself`);
    }
  }
  // Cycle check via repeated propagation over the frozen graph.
  const settled = new Set<string>();
  for (;;) {
    let progressed = false;
    for (const [id, needs] of deps) {
      if (settled.has(id)) continue;
      if (needs.every((dep) => settled.has(dep))) {
        settled.add(id);
        progressed = true;
      }
    }
    if (!progressed) break;
  }
  for (const id of checkIds) {
    if ((deps.get(id) ?? []).length === 0) settled.add(id);
  }
  requireRuntime(
    settled.size >= checkIds.size,
    'PLAN',
    'check dependency cycle detected',
  );
}

export function buildRecords(
  plan: readonly CheckPlan[],
  chunkLimits: ChunkLimits,
): Map<string, CheckRecord> {
  const records = new Map<string, CheckRecord>();
  for (const check of plan) {
    records.set(check.id, {
      plan: check,
      phase: 'queued',
      result: null,
      jobId: null,
      attempts: [],
      retainedIds: [],
      produced: 0,
      rawTextBytes: 0,
      inbound: new InboundWindow(chunkLimits),
      progress: null,
    });
  }
  return records;
}

const STATUS_SET: ReadonlySet<string> = new Set(TERMINAL_CHECK_STATUSES);

/**
 * Write the check's single terminal result. Terminal is final: a second
 * terminalization — by a late event, a retry of different settings, or a
 * coordinator bug — is rejected, so failure can never become agreement
 * and completed output is never retroactively overwritten.
 */
export function terminalize(
  record: CheckRecord,
  status: TerminalCheckStatus,
  reason: string | null,
): CheckResult {
  requireRuntime(
    record.phase !== 'terminal',
    'STATE',
    `check ${record.plan.id} is already terminal (${record.result?.status})`,
  );
  requireRuntime(
    STATUS_SET.has(status),
    'PLAN',
    `unknown terminal status ${JSON.stringify(status)}`,
  );
  requireRuntime(
    status === 'completed' || reason !== null,
    'PLAN',
    `incomplete check ${record.plan.id} requires a reason`,
  );
  record.phase = 'terminal';
  record.result = {
    id: record.plan.id,
    status,
    reason,
    produced_occurrence_count: record.produced,
    retained_occurrence_ids: [...record.retainedIds],
  };
  if (record.jobId !== null) {
    record.attempts.push({ jobId: record.jobId, status, reason });
    record.jobId = null;
  }
  return record.result;
}

/**
 * After a check reaches a non-completed terminal state, every queued
 * dependent that needed it is terminalized `skipped` with a reason that
 * names the unmet dependency. Returns the ids newly skipped (the caller
 * cascades the propagation).
 */
export function propagateSkips(
  records: ReadonlyMap<string, CheckRecord>,
  deps: DependencyMap,
): string[] {
  const skipped: string[] = [];
  for (const [id, record] of records) {
    if (record.phase !== 'queued') continue;
    const unmet = (deps.get(id) ?? []).find((depId) => {
      const dep = records.get(depId);
      return dep?.phase === 'terminal' && dep.result?.status !== 'completed';
    });
    if (unmet !== undefined) {
      const dep = records.get(unmet)!;
      terminalize(
        record,
        'skipped',
        `${REASON.DEPENDENCY}:${unmet}:${dep.result?.status}`,
      );
      skipped.push(id);
    }
  }
  return skipped;
}

/** Queued checks whose dependencies have all completed. */
export function runnableChecks(
  records: ReadonlyMap<string, CheckRecord>,
  deps: DependencyMap,
): CheckRecord[] {
  const out: CheckRecord[] = [];
  for (const [id, record] of records) {
    if (record.phase !== 'queued') continue;
    const ready = (deps.get(id) ?? []).every(
      (depId) => records.get(depId)?.result?.status === 'completed',
    );
    if (ready) out.push(record);
  }
  return out;
}

/**
 * Commit accepted chunk occurrences to the check's evidence. Returns
 * the number committed; throws `RuntimeError('BACKPRESSURE')` when a
 * declared bound is exceeded — the caller terminalizes the check as
 * `resource_limit` and keeps everything committed so far (I17).
 */
export function commitChunk(
  record: CheckRecord,
  occurrences: readonly Occurrence[],
  bounds: {
    maxOccurrencesPerCheck: number;
    maxOccurrencesPerRun: number;
    maxRawTextBytes: number;
    runProduced: number;
  },
): number {
  requireRuntime(record.phase === 'running', 'STATE', 'check not running');
  const textEncoder = new TextEncoder();
  let bytes = 0;
  for (const occurrence of occurrences) {
    bytes += textEncoder.encode(occurrence.raw_text).length;
  }
  requireRuntime(
    record.produced + occurrences.length <= bounds.maxOccurrencesPerCheck,
    'BACKPRESSURE',
    `check ${record.plan.id} exceeds the per-check occurrence cap`,
  );
  requireRuntime(
    bounds.runProduced + occurrences.length <= bounds.maxOccurrencesPerRun,
    'BACKPRESSURE',
    'run exceeds the total occurrence cap',
  );
  requireRuntime(
    record.rawTextBytes + bytes <= bounds.maxRawTextBytes,
    'BACKPRESSURE',
    `check ${record.plan.id} exceeds the raw-text byte cap`,
  );
  for (const occurrence of occurrences) {
    record.retainedIds.push(occurrence.id);
    record.produced += 1;
  }
  record.rawTextBytes += bytes;
  return occurrences.length;
}

/**
 * Terminal run status from the check ledger. Requires every check to be
 * terminal first — the coordinator terminalizes leftovers on the way out
 * so the ledger always settles (I05).
 */
export function computeRunStatus(
  records: ReadonlyMap<string, CheckRecord>,
  cancelRequested: boolean,
): TerminalRunStatus {
  if (cancelRequested) return 'cancelled';
  const results = [...records.values()].map((r) => r.result);
  requireRuntime(
    results.every((r) => r !== null),
    'STATE',
    'run status computed before every check reached terminal',
  );
  const completed = results.filter((r) => r!.status === 'completed').length;
  if (completed === results.length) return 'complete';
  const failedOrTimeout = results.some(
    (r) => r!.status === 'failed' || r!.status === 'timeout',
  );
  if (completed === 0 && failedOrTimeout) return 'failed';
  return 'partial';
}

/** Schema CheckResult list in plan order, for the eventual report. */
export function checkResults(
  records: ReadonlyMap<string, CheckRecord>,
): CheckResult[] {
  return [...records.values()].map((r) => {
    requireRuntime(
      r.result !== null,
      'STATE',
      `check ${r.plan.id} has no terminal result`,
    );
    return { ...r.result, retained_occurrence_ids: [...r.result.retained_occurrence_ids] };
  });
}
