/**
 * WorkerMessage construction and inbound validation (T11).
 *
 * The schema `WorkerMessage` is the ONLY wire shape between the
 * coordinator and job workers. Every message carries the five identity
 * fields — generation, document_sha256, run_key, job_id and a strictly
 * increasing per-job `seq` — so a stale or replayed event can always be
 * recognized (I07). A worker's local filename is never identity.
 *
 * `MessageFactory` allocates sequence numbers for ONE sender on ONE job;
 * each direction (worker→coordinator, coordinator→worker) owns a
 * factory, so sequences stay strictly increasing per sender.
 */
import {
  validate,
  type Occurrence,
  type WorkerMessage,
} from '../../contracts/src/index.ts';

export const RUN_KEY_PATTERN = /^[a-f0-9]{64}$/;
export const JOB_ID_PATTERN = /^[a-z][a-z0-9_-]{0,95}$/;

export type MessageEvent = WorkerMessage['event'];
export type MessagePayload = WorkerMessage['payload'];

export function emptyPayload(): MessagePayload {
  return {
    check_id: null,
    occurrences: [],
    status: null,
    reason: null,
    completed_units: null,
    total_units: null,
    transfer_slot: null,
    transfer_bytes: 0,
  };
}

export interface MessageIdentity {
  generation: number;
  documentSha256: string;
  runKey: string;
  jobId: string;
}

/**
 * Allocate strictly increasing `seq` values and stamp the identity
 * five-tuple on every emitted message.
 */
export class MessageFactory {
  readonly identity: MessageIdentity;
  private seq = 0;

  constructor(identity: MessageIdentity) {
    this.identity = identity;
  }

  /** The next sequence value this sender will use. */
  peekSeq(): number {
    return this.seq;
  }

  message(
    event: MessageEvent,
    payload: Partial<MessagePayload> = {},
  ): WorkerMessage {
    return {
      kind: 'worker_message',
      schema_version: '1.0.0',
      generation: this.identity.generation,
      run_key: this.identity.runKey,
      document_sha256: this.identity.documentSha256,
      job_id: this.identity.jobId,
      seq: this.seq++,
      event,
      payload: { ...emptyPayload(), ...payload },
    };
  }

  start(): WorkerMessage {
    return this.message('start');
  }

  ready(): WorkerMessage {
    return this.message('ready');
  }

  chunk(checkId: string, occurrences: Occurrence[]): WorkerMessage {
    return this.message('chunk', { check_id: checkId, occurrences });
  }

  /**
   * Coordinator→worker capacity grant for one accepted chunk.
   * `completed_units` carries the seq of the acknowledged chunk message;
   * `check_id` names its check. An ack frees sender window only — it is
   * never a success finding.
   */
  ack(checkId: string, ackedSeq: number): WorkerMessage {
    return this.message('ack', {
      check_id: checkId,
      completed_units: ackedSeq,
    });
  }

  progress(
    checkId: string,
    completedUnits: number,
    totalUnits: number | null = null,
  ): WorkerMessage {
    return this.message('progress', {
      check_id: checkId,
      completed_units: completedUnits,
      total_units: totalUnits,
    });
  }

  checkTerminal(
    checkId: string,
    status: NonNullable<MessagePayload['status']>,
    reason: string | null = null,
  ): WorkerMessage {
    return this.message('check_terminal', {
      check_id: checkId,
      status,
      reason,
    });
  }

  error(reason: string, checkId: string | null = null): WorkerMessage {
    return this.message('error', { reason, check_id: checkId });
  }

  cancel(checkId: string | null = null): WorkerMessage {
    return this.message('cancel', { check_id: checkId });
  }

  clear(): WorkerMessage {
    return this.message('clear');
  }
}

/**
 * Parse and contract-validate inbound wire data. Throws `ContractError`
 * on malformed input; only a fully valid `WorkerMessage` is returned, so
 * admission logic never inspects a partial message.
 */
export function parseInbound(data: unknown): WorkerMessage {
  validate(data);
  return data as WorkerMessage;
}
