/**
 * Message admission authority (T11; invariant I07).
 *
 * "Reject a message unless all five match the active registry and
 * sequence exceeds last accepted." The registry is generation-first:
 * when a document is cleared or replaced, or a run is cancelled, the
 * generation is bumped BEFORE handles close — so an event from an old
 * generation/document/run/job can never reach current state.
 *
 * A terminal job rejects late chunks: once a job's check has reported a
 * terminal result (or the job was closed), no further message from that
 * job is admitted.
 */
import type { WorkerMessage } from '../../contracts/src/index.ts';
import { requireRuntime } from './errors.ts';
import { JOB_ID_PATTERN, RUN_KEY_PATTERN } from './messages.ts';

export const ADMIT_CODES = [
  'accepted',
  'stale_generation',
  'stale_document',
  'stale_run',
  'unknown_job',
  'terminal_job',
  'sequence',
  'malformed',
] as const;
export type AdmitCode = (typeof ADMIT_CODES)[number];

export interface Admission {
  readonly ok: boolean;
  readonly code: AdmitCode;
}

const OK: Admission = { ok: true, code: 'accepted' };
const reject = (code: AdmitCode): Admission => ({ ok: false, code });

export interface ActiveRun {
  readonly generation: number;
  readonly documentSha256: string;
  readonly runKey: string;
}

interface JobEntry {
  lastSeq: number;
  terminal: boolean;
}

export class MessageAuthority {
  private active: ActiveRun | null = null;
  private readonly jobs = new Map<string, JobEntry>();

  /** Install a fresh registry for a new run epoch. */
  beginRun(active: ActiveRun): void {
    requireRuntime(
      Number.isInteger(active.generation) && active.generation >= 0,
      'IDENTITY',
      'generation must be a nonnegative integer',
    );
    requireRuntime(
      RUN_KEY_PATTERN.test(active.runKey),
      'IDENTITY',
      'run_key must be 64 lowercase hex',
    );
    requireRuntime(
      RUN_KEY_PATTERN.test(active.documentSha256),
      'IDENTITY',
      'document_sha256 must be 64 lowercase hex',
    );
    this.active = active;
    this.jobs.clear();
  }

  /** Drop the whole registry: every subsequent message is stale. */
  invalidate(): void {
    this.active = null;
    this.jobs.clear();
  }

  get generation(): number | null {
    return this.active?.generation ?? null;
  }

  registerJob(jobId: string): void {
    requireRuntime(this.active !== null, 'STATE', 'no active run');
    requireRuntime(
      JOB_ID_PATTERN.test(jobId),
      'IDENTITY',
      `job_id ${JSON.stringify(jobId)} fails the schema pattern`,
    );
    requireRuntime(
      !this.jobs.has(jobId),
      'IDENTITY',
      `job_id ${jobId} already registered`,
    );
    this.jobs.set(jobId, { lastSeq: -1, terminal: false });
  }

  hasJob(jobId: string): boolean {
    return this.jobs.has(jobId);
  }

  /**
   * Mark a job terminal. Late messages — including chunks and terminal
   * duplicates — are rejected with `terminal_job`.
   */
  closeJob(jobId: string): void {
    const job = this.jobs.get(jobId);
    if (job) job.terminal = true;
  }

  isTerminal(jobId: string): boolean {
    return this.jobs.get(jobId)?.terminal ?? false;
  }

  /**
   * Admit a structurally valid message. Rejection order is the registry
   * order: generation, then document, then run, then job, then sequence.
   * The message is never partially applied: callers apply admitted
   * messages only.
   */
  admit(msg: WorkerMessage): Admission {
    const active = this.active;
    if (active === null) return reject('stale_generation');
    if (msg.generation !== active.generation) {
      return reject('stale_generation');
    }
    if (msg.document_sha256 !== active.documentSha256) {
      return reject('stale_document');
    }
    if (msg.run_key !== active.runKey) return reject('stale_run');
    const job = this.jobs.get(msg.job_id);
    if (job === undefined) return reject('unknown_job');
    if (job.terminal) return reject('terminal_job');
    if (msg.seq <= job.lastSeq) return reject('sequence');
    job.lastSeq = msg.seq;
    return OK;
  }
}
