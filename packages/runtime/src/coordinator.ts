/**
 * Run lifecycle coordinator (T11).
 *
 * One explicit state machine owns the file/run lifecycle of one browser
 * workspace document (RUNTIME_LIFECYCLE.md):
 *
 * ```text
 * idle -> validating_file -> loading_metadata -> selecting
 * selecting -> preparing_assets -> running
 * selecting -> running                     (assets already available)
 * running -> complete | partial | failed | cancelled
 * terminal -> selecting                    (new explicit run on same file)
 * any -> clearing -> idle | validating_file (clear / replacement)
 * ```
 *
 * The coordinator is the authority, not the transport: it validates and
 * admits worker messages, keeps per-check terminal bookkeeping, bounds
 * acknowledged chunks, decides retries, and emits intents
 * (dispatch/terminate/message) that the embedder's host executes. It
 * never spawns workers, fetches, or touches the DOM itself.
 *
 * Invariants carried here:
 * - I05 every planned check reaches a terminal result; failure never
 *   becomes agreement.
 * - I07 events from an old generation/document/run/job cannot change
 *   current state — the registry is generation-first and the snapshot
 *   is built only from admitted bookkeeping.
 * - I17 a failure ends its own check; successfully completed
 *   independent results are never cleared by it.
 */
import {
  digest,
  type CheckPlan,
  type Document,
  type Occurrence,
  type Reader,
  type WorkerMessage,
} from '../../contracts/src/index.ts';
import {
  MessageAuthority,
  type AdmitCode,
  type Admission,
} from './authority.ts';
import { DEFAULT_CHUNK_LIMITS, TransferLedger } from './backpressure.ts';
import {
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
  type CheckRecord,
  type DependencyMap,
} from './checks.ts';
import { CleanupRegistry, type CleanupFailure, type TeardownFn } from './cleanup.ts';
import { RuntimeError, requireRuntime } from './errors.ts';
import {
  REASON,
  RUNTIME_LIMITS,
  retryKind,
  type FileState,
  type RuntimeLimits,
  type TerminalCheckStatus,
  type TerminalRunStatus,
} from './limits.ts';
import { MessageFactory, parseInbound } from './messages.ts';
import {
  NOTICE_KEYS,
  type CheckView,
  type NoticeKey,
  type SessionView,
} from './view.ts';

/** Legal transitions of the lifecycle state machine. */
export const TRANSITIONS: Readonly<Record<FileState, readonly FileState[]>> = {
  idle: ['validating_file', 'clearing'],
  validating_file: ['loading_metadata', 'clearing'],
  loading_metadata: ['selecting', 'clearing'],
  selecting: ['preparing_assets', 'running', 'clearing'],
  preparing_assets: ['running', 'clearing'],
  running: ['complete', 'partial', 'failed', 'cancelled', 'clearing'],
  complete: ['selecting', 'clearing'],
  partial: ['selecting', 'clearing'],
  failed: ['selecting', 'clearing'],
  cancelled: ['selecting', 'clearing'],
  clearing: ['idle', 'validating_file'],
};

/** Coordinator→host intents: the host executes them, nothing else does. */
export type CoordinatorIntent =
  | { readonly type: 'ack'; readonly jobId: string; readonly checkId: string; readonly message: WorkerMessage }
  | { readonly type: 'dispatch'; readonly jobId: string; readonly checkId: string; readonly capability: string }
  | { readonly type: 'terminate'; readonly jobId: string; readonly checkId: string | null }
  | { readonly type: 'message'; readonly jobId: string; readonly message: WorkerMessage };

export interface StartRunOptions {
  /** 64-hex run identity; see {@link deriveRunKey}. */
  readonly runKey: string;
  /** The immutable intended checks (schema CheckPlan). */
  readonly checks: readonly CheckPlan[];
  /** selected_pages total at run start — frozen for display honesty. */
  readonly selectedPagesTotal: number;
  /** check_id -> prerequisite check_ids; defaults to deriveDependencies. */
  readonly dependencies?: DependencyMap;
  /** Run wall-clock budget (plan.budget.timeout_ms). */
  readonly budgetMs?: number;
  /** True when OCR/model assets must be prepared first. */
  readonly needsAssets?: boolean;
}

export interface CoordinatorOptions {
  readonly limits?: Partial<RuntimeLimits>;
  /** Injectable clock (default performance.now, browser-safe). */
  readonly now?: () => number;
  /** Injectable timer arming for watchdog deadlines. */
  readonly schedule?: (fn: () => void, ms: number) => unknown;
  readonly unschedule?: (handle: unknown) => void;
}

export interface CancelReceipt {
  /** ms from request to the UI-visible cancelled state. */
  readonly uiMs: number;
  /** ms for the bounded teardown after the UI update. */
  readonly teardownMs: number;
  readonly totalMs: number;
  /** Generation after invalidation — late events are unreachable. */
  readonly generation: number;
  readonly cleanupFailures: readonly CleanupFailure[];
}

interface JobBinding {
  readonly jobId: string;
  readonly checkId: string;
}

interface RunContext {
  runKey: string;
  startedAt: number;
  deadlineAt: number | null;
  cancelRequested: boolean;
  status: TerminalRunStatus | null;
  checks: Map<string, CheckRecord>;
  deps: DependencyMap;
  jobs: Map<string, JobBinding>;
  /** Per-job coordinator->worker message factories (seq stays monotonic). */
  outbound: Map<string, MessageFactory>;
  occurrences: Map<string, Occurrence>;
  runProduced: number;
  jobCounter: number;
  selectedPagesTotal: number;
  outbox: CoordinatorIntent[];
  cleanup: CleanupRegistry;
  transfers: TransferLedger;
}

const defaultNow = (): number =>
  typeof performance !== 'undefined' ? performance.now() : Date.now();

/** Contract-identical run identity: digest({document_sha256, readers, plan}). */
export function deriveRunKey(
  documentSha256: string,
  readers: readonly Reader[],
  plan: unknown,
): string {
  return digest({ document_sha256: documentSha256, readers, plan });
}

export class RunCoordinator {
  private readonly limits: RuntimeLimits;
  private readonly now: () => number;
  private readonly schedule: ((fn: () => void, ms: number) => unknown) | null;
  private readonly unschedule: ((handle: unknown) => void) | null;

  private state: FileState = 'idle';
  private generation = 0;
  private revision = 0;
  private document: Pick<Document, 'sha256' | 'page_count'> | null = null;
  private run: RunContext | null = null;
  private readonly authority = new MessageAuthority();
  private readonly fileCleanup = new CleanupRegistry();
  /** Intents still deliverable after their run context is gone. */
  private pendingIntents: CoordinatorIntent[] = [];
  private readonly listeners = new Set<() => void>();
  private readonly stats = {
    admitted: 0,
    rejected: new Map<AdmitCode, number>(),
  };

  constructor(options: CoordinatorOptions = {}) {
    this.limits = { ...RUNTIME_LIMITS, ...options.limits };
    this.now = options.now ?? defaultNow;
    this.schedule = options.schedule ?? defaultSchedule;
    this.unschedule = options.unschedule ?? defaultUnschedule;
  }

  // -----------------------------------------------------------------
  // subscriptions / observation
  // -----------------------------------------------------------------

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    this.revision += 1;
    for (const listener of [...this.listeners]) listener();
  }

  get fileState(): FileState {
    return this.state;
  }

  get currentGeneration(): number {
    return this.generation;
  }

  get rejectionStats(): ReadonlyMap<AdmitCode, number> {
    return this.stats.rejected;
  }

  private rejected(code: AdmitCode): Admission {
    this.stats.rejected.set(code, (this.stats.rejected.get(code) ?? 0) + 1);
    return { ok: false, code };
  }

  // -----------------------------------------------------------------
  // state machine
  // -----------------------------------------------------------------

  private transition(to: FileState): void {
    const legal = TRANSITIONS[this.state];
    requireRuntime(
      legal.includes(to),
      'TRANSITION',
      `illegal transition ${this.state} -> ${to}`,
    );
    this.state = to;
    this.notify();
  }

  /**
   * Legality pre-check for entry points that mutate before they
   * transition — a rejected call must leave zero side effects.
   */
  private assertTransition(to: FileState): void {
    requireRuntime(
      TRANSITIONS[this.state].includes(to),
      'TRANSITION',
      `illegal transition ${this.state} -> ${to}`,
    );
  }

  /** idle -> validating_file: a file was offered. */
  openFile(): void {
    this.transition('validating_file');
  }

  /** validating_file -> loading_metadata: the file passed sniff checks. */
  fileValidated(): void {
    this.transition('loading_metadata');
  }

  /** loading_metadata -> selecting: page metadata is available. */
  metadataLoaded(
    document: Pick<Document, 'sha256' | 'page_count'>,
  ): void {
    requireRuntime(
      /^[a-f0-9]{64}$/.test(document.sha256),
      'IDENTITY',
      'document sha256 must be 64 lowercase hex',
    );
    this.assertTransition('selecting');
    this.document = { ...document };
    this.transition('selecting');
  }

  /**
   * selecting -> preparing_assets | running. The plan is frozen now; the
   * selected-page total is pinned and can never silently grow during the
   * run. A new run epoch bumps the generation and installs a fresh
   * message registry, so nothing from a previous run can be admitted.
   */
  startRun(options: StartRunOptions): void {
    requireRuntime(
      this.state === 'selecting',
      'TRANSITION',
      `startRun requires selecting, not ${this.state}`,
    );
    requireRuntime(
      this.document !== null,
      'STATE',
      'run requires a loaded document',
    );
    const runKey = options.runKey;
    const checks = freezePlan(options.checks);
    const deps = options.dependencies ?? deriveDependencies(checks);
    validateDependencies(deps, new Set(checks.map((c) => c.id)));
    this.generation += 1;
    this.authority.beginRun({
      generation: this.generation,
      documentSha256: this.document.sha256,
      runKey,
    });
    const startedAt = this.now();
    const budgetMs = options.budgetMs ?? null;
    const run: RunContext = {
      runKey,
      startedAt,
      deadlineAt: budgetMs === null ? null : startedAt + budgetMs,
      cancelRequested: false,
      status: null,
      checks: buildRecords(checks, {
        maxChunkOccurrences: this.limits.maxResultChunkOccurrences,
        maxUnacked: this.limits.maxUnackedChunks,
      }),
      deps,
      jobs: new Map(),
      outbound: new Map(),
      occurrences: new Map(),
      runProduced: 0,
      jobCounter: 0,
      selectedPagesTotal: options.selectedPagesTotal,
      outbox: [],
      cleanup: new CleanupRegistry(),
      transfers: new TransferLedger(this.limits.maxLiveRasters),
    };
    this.run = run;
    if (budgetMs !== null && this.schedule !== null) {
      const handle = this.schedule(() => this.onRunDeadline(), budgetMs);
      run.cleanup.own(handle, 'run-deadline', () => this.unschedule?.(handle));
    }
    if (options.needsAssets) {
      this.transition('preparing_assets');
    } else {
      this.enterRunning();
    }
  }

  /** preparing_assets -> running once model/assets are verified ready. */
  assetsReady(): void {
    this.enterRunning();
  }

  private enterRunning(): void {
    requireRuntime(this.run !== null, 'STATE', 'no run to enter');
    this.transition('running');
    this.dispatchRunnable();
  }

  // -----------------------------------------------------------------
  // dispatch / watchdogs
  // -----------------------------------------------------------------

  private activeByCapability(capability: string): number {
    let n = 0;
    for (const record of this.run?.checks.values() ?? []) {
      if (record.phase === 'running' && record.plan.capability === capability) {
        n += 1;
      }
    }
    return n;
  }

  /** Concurrency admission: one active render, one OCR worker. */
  private capabilityRoom(record: CheckRecord): boolean {
    if (record.plan.capability === 'render') {
      return this.activeByCapability('render') < this.limits.maxActiveRenders;
    }
    if (record.plan.capability === 'ocr') {
      return this.activeByCapability('ocr') < this.limits.maxOcrWorkers;
    }
    return true;
  }

  private dispatchRunnable(): void {
    const run = this.run;
    if (run === null || this.state !== 'running') return;
    for (const record of runnableChecks(run.checks, run.deps)) {
      if (!this.capabilityRoom(record)) continue;
      const jobId = `j_${++run.jobCounter}`;
      this.authority.registerJob(jobId);
      record.phase = 'running';
      record.jobId = jobId;
      run.jobs.set(jobId, { jobId, checkId: record.plan.id });
      run.outbox.push({
        type: 'dispatch',
        jobId,
        checkId: record.plan.id,
        capability: record.plan.capability,
      });
      if (this.schedule !== null) {
        const handle = this.schedule(
          () => this.onCheckDeadline(record.plan.id, jobId),
          this.limits.checkTimeoutMs,
        );
        run.cleanup.own(handle, `check-deadline:${jobId}`, () =>
          this.unschedule?.(handle),
        );
      }
    }
    this.notify();
  }

  private onRunDeadline(): void {
    const run = this.run;
    if (run === null || this.state !== 'running') return;
    for (const record of run.checks.values()) {
      if (record.phase !== 'terminal') {
        this.terminateJob(record, REASON.TIMEOUT);
        terminalize(record, 'timeout', REASON.TIMEOUT);
      }
    }
    this.afterTerminalSettled();
  }

  private onCheckDeadline(checkId: string, jobId: string): void {
    const run = this.run;
    if (run === null || this.state !== 'running') return;
    const record = run.checks.get(checkId);
    if (record === undefined || record.phase !== 'running') return;
    if (record.jobId !== jobId) return; // a retry replaced this job
    this.terminateJob(record, REASON.TIMEOUT);
    terminalize(record, 'timeout', REASON.TIMEOUT);
    this.afterTerminalSettled();
  }

  private terminateJob(record: CheckRecord, _reason: string): void {
    const run = this.run;
    if (run === null || record.jobId === null) return;
    run.outbox.push({
      type: 'terminate',
      jobId: record.jobId,
      checkId: record.plan.id,
    });
    this.authority.closeJob(record.jobId);
    run.jobs.delete(record.jobId);
  }

  // -----------------------------------------------------------------
  // message admission and application
  // -----------------------------------------------------------------

  /**
   * Validate, admit and apply one inbound message. Structurally invalid
   * input and stale/replayed messages are rejected without touching any
   * state (I07) — the return value says exactly why.
   */
  receive(raw: unknown): Admission {
    let msg: WorkerMessage;
    try {
      msg = parseInbound(raw);
    } catch {
      return this.rejected('malformed');
    }
    const admission = this.authority.admit(msg);
    if (!admission.ok) return this.rejected(admission.code);
    this.stats.admitted += 1;
    this.apply(msg);
    return admission;
  }

  get admittedCount(): number {
    return this.stats.admitted;
  }

  private apply(msg: WorkerMessage): void {
    const run = this.run;
    if (run === null) return;
    const binding = run.jobs.get(msg.job_id);
    const check = binding === undefined ? undefined : run.checks.get(binding.checkId);
    // A message naming a different check than its job serves is a
    // protocol violation by the sender.
    if (
      msg.payload.check_id !== null &&
      check !== undefined &&
      msg.payload.check_id !== check.plan.id
    ) {
      this.protocolViolation(check, msg.job_id);
      return;
    }
    // A transferred slot is usable only under proven document (already
    // admitted) and raster identity: the bound check claims it here.
    if (msg.payload.transfer_slot !== null && check !== undefined) {
      const verdict = run.transfers.claim(
        msg.payload.transfer_slot,
        check.plan.id,
      );
      if (verdict !== 'ok') {
        this.terminateJob(check, REASON.RESOURCE_LIMIT);
        terminalize(check, 'failed', REASON.RESOURCE_LIMIT);
        this.afterTerminalSettled();
        return;
      }
    }
    switch (msg.event) {
      case 'start':
      case 'ready':
      case 'ack':
      case 'cancel':
      case 'clear':
        // Valid but inert inbound: ack/cancel/clear travel
        // coordinator->worker; start/ready carry no payload.
        return;
      case 'progress': {
        if (check === undefined || check.phase !== 'running') return;
        check.progress = {
          completed: msg.payload.completed_units ?? 0,
          total: msg.payload.total_units,
        };
        this.notify();
        return;
      }
      case 'chunk': {
        if (check === undefined || check.phase !== 'running') return;
        this.applyChunk(check, msg);
        return;
      }
      case 'check_terminal': {
        if (check === undefined || check.phase !== 'running') return;
        this.applyCheckTerminal(check, msg);
        return;
      }
      case 'error': {
        if (check === undefined || check.phase !== 'running') return;
        this.applyFailure(check, msg.job_id, msg.payload.reason ?? 'error');
        return;
      }
    }
  }

  private applyChunk(check: CheckRecord, msg: WorkerMessage): void {
    const run = this.run!;
    if (check.inbound.wouldOverflow()) {
      this.protocolViolation(check, msg.job_id);
      return;
    }
    check.inbound.recordAccepted();
    try {
      const committed = commitChunk(check, msg.payload.occurrences, {
        maxOccurrencesPerCheck: this.limits.maxOccurrencesPerPage,
        maxOccurrencesPerRun: this.limits.maxOccurrencesPerRun,
        maxRawTextBytes: this.limits.maxRawTextBytesPerRun,
        runProduced: run.runProduced,
      });
      for (const occurrence of msg.payload.occurrences) {
        if (!run.occurrences.has(occurrence.id)) {
          run.occurrences.set(occurrence.id, occurrence);
        }
      }
      run.runProduced += committed;
    } catch (error) {
      if (error instanceof RuntimeError && error.code === 'BACKPRESSURE') {
        // Oversized output ends this check as resource_limit; every
        // previously committed result — this check's and other checks'
        // — is retained (I17).
        this.terminateJob(check, REASON.RESOURCE_LIMIT);
        terminalize(check, 'failed', REASON.RESOURCE_LIMIT);
        this.afterTerminalSettled();
        return;
      }
      throw error;
    }
    // Capacity grant: the ack frees one sender slot once delivered.
    const factory = this.outboundFactory(msg.job_id);
    run.outbox.push({
      type: 'ack',
      jobId: msg.job_id,
      checkId: check.plan.id,
      message: factory.ack(check.plan.id, msg.seq),
    });
    this.notify();
  }

  private applyCheckTerminal(check: CheckRecord, msg: WorkerMessage): void {
    const status = msg.payload.status;
    requireRuntime(status !== null, 'PLAN', 'terminal event without status');
    if (status === 'failed') {
      this.applyFailure(check, msg.job_id, msg.payload.reason ?? 'error');
      return;
    }
    const run = this.run!;
    this.authority.closeJob(msg.job_id);
    run.jobs.delete(msg.job_id);
    run.outbox.push({
      type: 'terminate',
      jobId: msg.job_id,
      checkId: check.plan.id,
    });
    terminalize(check, status as TerminalCheckStatus, msg.payload.reason);
    this.afterTerminalSettled();
  }

  /**
   * A failed report either schedules the single transient retry — a
   * fresh worker identity within remaining run budget — or settles the
   * check terminally. Completed results elsewhere are untouched.
   */
  private applyFailure(
    check: CheckRecord,
    jobId: string,
    reason: string,
  ): void {
    const run = this.run!;
    const budgetRemains =
      run.deadlineAt === null || this.now() < run.deadlineAt;
    // attempts.length counts retries already granted: one transient
    // retry maximum, on a fresh job, inside the remaining run budget.
    if (
      retryKind(reason) === 'transient' &&
      check.attempts.length < this.limits.maxTransientRetries &&
      budgetRemains &&
      !run.cancelRequested
    ) {
      check.attempts.push({ jobId, status: 'failed', reason });
      this.authority.closeJob(jobId);
      run.jobs.delete(jobId);
      run.outbox.push({ type: 'terminate', jobId, checkId: check.plan.id });
      const freshJobId = `j_${++run.jobCounter}`;
      this.authority.registerJob(freshJobId);
      check.jobId = freshJobId;
      run.jobs.set(freshJobId, { jobId: freshJobId, checkId: check.plan.id });
      run.outbox.push({
        type: 'dispatch',
        jobId: freshJobId,
        checkId: check.plan.id,
        capability: check.plan.capability,
      });
      this.notify();
      return;
    }
    this.authority.closeJob(jobId);
    run.jobs.delete(jobId);
    run.outbox.push({ type: 'terminate', jobId, checkId: check.plan.id });
    terminalize(check, 'failed', reason);
    this.afterTerminalSettled();
  }

  private protocolViolation(check: CheckRecord, jobId: string): void {
    const run = this.run;
    if (run === null) return;
    this.authority.closeJob(jobId);
    run.jobs.delete(jobId);
    run.outbox.push({ type: 'terminate', jobId, checkId: check.plan.id });
    if (check.phase !== 'terminal') {
      terminalize(check, 'failed', REASON.PROTOCOL);
    }
    this.afterTerminalSettled();
  }

  /** Terminal bookkeeping cascade: skip dependents, dispatch newly freed
   * runnable checks, and settle the run when every check is terminal. */
  private afterTerminalSettled(): void {
    const run = this.run;
    if (run === null) return;
    propagateSkips(run.checks, run.deps);
    // Terminal checks release their transferred-slot claims (raster
    // buffers freed); idempotent for checks already released.
    for (const record of run.checks.values()) {
      if (record.phase === 'terminal') {
        run.transfers.release(record.plan.id);
      }
    }
    this.dispatchRunnable();
    const allTerminal = [...run.checks.values()].every(
      (record) => record.phase === 'terminal',
    );
    if (allTerminal && this.state === 'running') {
      this.finishRun(computeRunStatus(run.checks, run.cancelRequested));
    }
    this.notify();
  }

  private finishRun(status: TerminalRunStatus): void {
    const run = this.run;
    if (run === null) return;
    run.status = status;
    run.cleanup.teardownAll();
    this.authority.invalidate();
    this.transition(status);
  }

  // -----------------------------------------------------------------
  // cancellation and clearing
  // -----------------------------------------------------------------

  /**
   * running -> cancelled. Order is the contract: the visible state moves
   * FIRST, then pending work is marked cancelled, jobs are terminated,
   * owned resources torn down, and finally the message registry is
   * invalidated — so by the measured deadline the old generation is
   * unreachable from presentation even if browser cleanup lags.
   */
  requestCancel(): CancelReceipt {
    requireRuntime(
      this.state === 'running',
      'TRANSITION',
      `cancel requires running, not ${this.state}`,
    );
    const run = this.run!;
    const t0 = this.now();
    run.cancelRequested = true;
    // 1. visible UI update first
    this.transition('cancelled');
    const uiVisibleAt = this.now();
    // 2. pending work cancelled (queued and running alike)
    for (const record of run.checks.values()) {
      if (record.phase !== 'terminal') {
        if (record.jobId !== null) {
          const factory = this.outboundFactory(record.jobId);
          run.outbox.push({
            type: 'message',
            jobId: record.jobId,
            message: factory.cancel(record.plan.id),
          });
          this.terminateJob(record, REASON.USER_CANCEL);
        }
        terminalize(record, 'cancelled', REASON.USER_CANCEL);
      }
    }
    // 3. bounded teardown of every run-scoped owned resource
    const cleanupFailures = run.cleanup.teardownAll();
    // 4. invalidate message listeners: new generation + closed registry
    this.generation += 1;
    this.authority.invalidate();
    const terminatedAt = this.now();
    run.status = 'cancelled';
    this.notify();
    return {
      uiMs: uiVisibleAt - t0,
      teardownMs: terminatedAt - uiVisibleAt,
      totalMs: terminatedAt - t0,
      generation: this.generation,
      cleanupFailures,
    };
  }

  /**
   * any -> clearing -> idle | validating_file. The generation increments
   * BEFORE handles close, workers terminate or replacement begins —
   * then every owned resource (run- and file-scoped) is released and
   * state is nulled. Static model caches may outlive this; document
   * bytes, crops, findings and filenames may not.
   */
  requestClear(next: 'idle' | 'replace' = 'idle'): CleanupFailure[] {
    // Reentrant calls (a subscriber firing mid-teardown) are rejected
    // before anything else can be mutated.
    requireRuntime(
      this.state !== 'clearing',
      'TRANSITION',
      'already clearing',
    );
    // Generation increments BEFORE handles close, workers terminate or
    // replacement begins — everything emitted afterward is stale.
    this.generation += 1;
    this.authority.invalidate();
    this.transition('clearing');
    const run = this.run;
    if (run !== null) {
      for (const binding of run.jobs.values()) {
        this.pendingIntents.push({
          type: 'terminate',
          jobId: binding.jobId,
          checkId: binding.checkId,
        });
      }
      run.jobs.clear();
    }
    const failures = [
      ...(run?.cleanup.teardownAll() ?? []),
      ...this.fileCleanup.teardownAll(),
    ];
    this.run = null;
    this.document = null;
    this.transition(next === 'replace' ? 'validating_file' : 'idle');
    this.notify();
    return failures;
  }

  /** terminal -> selecting: a new explicit run/retry on the same file. */
  prepareNewRun(): void {
    this.assertTransition('selecting');
    this.run = null;
    this.transition('selecting');
  }

  // -----------------------------------------------------------------
  // owned resources / outbox / snapshot
  // -----------------------------------------------------------------

  /** Register a file-scoped owned resource (handle, URL, observer...). */
  own(resource: unknown, label?: string, teardown?: TeardownFn): void {
    this.fileCleanup.own(resource, label ?? 'resource', teardown);
  }

  /** Register a run-scoped owned resource (worker, raster, timer...). */
  ownRunResource(resource: unknown, label?: string, teardown?: TeardownFn): void {
    requireRuntime(this.run !== null, 'STATE', 'no active run');
    this.run.cleanup.own(resource, label ?? 'resource', teardown);
  }

  /**
   * Hand queued intents to the host in order. Acknowledgements count as
   * delivered exactly here — never at send — which is what makes the
   * unacknowledged-window bound enforceable on the receive side.
   */
  drainOutbox(): CoordinatorIntent[] {
    const run = this.run;
    const out = run === null ? [] : run.outbox;
    if (run !== null) run.outbox = [];
    for (const intent of out) {
      if (intent.type === 'ack') {
        run?.checks.get(intent.checkId)?.inbound.recordAckDelivered();
      }
    }
    return [...out, ...this.pendingIntents.splice(0)];
  }

  private outboundFactory(jobId: string): MessageFactory {
    const run = this.run!;
    let factory = run.outbound.get(jobId);
    if (factory === undefined) {
      factory = new MessageFactory({
        generation: this.generation,
        documentSha256: this.document!.sha256,
        runKey: run.runKey,
        jobId,
      });
      run.outbound.set(jobId, factory);
    }
    return factory;
  }

  /** Immutable presentation view: only admitted bookkeeping, ever. */
  snapshot(): SessionView {
    const run = this.run;
    return deepFreeze({
      fileState: this.state,
      generation: this.generation,
      documentSha256: this.document?.sha256 ?? null,
      run:
        run === null
          ? null
          : {
              runKey: run.runKey,
              status: run.status,
              cancelRequested: run.cancelRequested,
              startedAt: run.startedAt,
              deadlineAt: run.deadlineAt,
              selectedPagesTotal: run.selectedPagesTotal,
              checks: [...run.checks.values()].map(
                (record): CheckView => ({
                  id: record.plan.id,
                  capability: record.plan.capability,
                  pageIndex: record.plan.page_index,
                  phase: record.phase,
                  status: record.result?.status ?? null,
                  reason: record.result?.reason ?? null,
                  producedOccurrences: record.produced,
                  retainedOccurrenceIds: [...record.retainedIds],
                  attempts: record.attempts.length,
                  progress:
                    record.progress === null ? null : { ...record.progress },
                }),
              ),
            },
      occurrences: run === null ? [] : [...run.occurrences.values()],
      notice: this.notice(),
      revision: this.revision,
    });
  }

  private notice(): NoticeKey | null {
    const run = this.run;
    if (run === null || this.state === 'running') return null;
    if (run.status === 'cancelled') return NOTICE_KEYS.cancelled;
    const checks = [...run.checks.values()];
    if (checks.some((c) => c.result?.reason === REASON.RESOURCE_LIMIT)) {
      return NOTICE_KEYS.resource;
    }
    if (checks.some((c) => c.result?.status === 'timeout')) {
      return NOTICE_KEYS.timeout;
    }
    if (run.status === 'partial') return NOTICE_KEYS.partial;
    if (run.status === 'failed') return NOTICE_KEYS.failed;
    if (run.status === 'complete') return NOTICE_KEYS.complete;
    return null;
  }

  /** Terminal CheckResults in plan order (report-ready once settled). */
  settledCheckResults(): ReturnType<typeof checkResults> {
    requireRuntime(this.run !== null, 'STATE', 'no run');
    return checkResults(this.run.checks);
  }
}

/** Recursive freeze so a snapshot can never be mutated after the fact. */
function deepFreeze<T>(value: T): T {
  if (typeof value === 'object' && value !== null) {
    for (const key of Object.keys(value)) {
      deepFreeze((value as Record<string, unknown>)[key]);
    }
    Object.freeze(value);
  }
  return value;
}

function defaultSchedule(fn: () => void, ms: number): unknown {
  if (typeof setTimeout === 'undefined') return null;
  return setTimeout(fn, ms);
}

function defaultUnschedule(handle: unknown): void {
  if (typeof clearTimeout !== 'undefined' && handle !== null) {
    clearTimeout(handle as Parameters<typeof clearTimeout>[0]);
  }
}

export type { DependencyMap };
export { DEFAULT_CHUNK_LIMITS };
