/**
 * Acknowledged-chunk backpressure (T11).
 *
 * The bounded result stream from `planning/config/settings.json` and
 * RUNTIME_LIFECYCLE.md: at most 256 occurrences per message and at most
 * two unacknowledged chunks per check. Acknowledgment is a capacity
 * signal only — it never marks a check successful.
 *
 * Two enforcement points keep the bound honest in both directions:
 *
 * - `ChunkSender` (producer side) refuses to emit a third chunk while
 *   two remain unacknowledged, and never emits more than 256 occurrences
 *   in one message.
 * - `InboundWindow` (receiver side) counts chunks accepted minus acks
 *   delivered per check; a chunk arriving while the sender provably had
 *   two unacknowledged is a protocol violation.
 */
import type { Occurrence } from '../../contracts/src/index.ts';
import { requireRuntime } from './errors.ts';
import { RUNTIME_LIMITS } from './limits.ts';

export interface ChunkLimits {
  readonly maxChunkOccurrences: number;
  readonly maxUnacked: number;
}

export const DEFAULT_CHUNK_LIMITS: ChunkLimits = {
  maxChunkOccurrences: RUNTIME_LIMITS.maxResultChunkOccurrences,
  maxUnacked: RUNTIME_LIMITS.maxUnackedChunks,
};

/**
 * Producer-side acknowledged window for one check's result stream.
 * Occurrences are queued, packed into <= maxChunkOccurrences messages
 * and released only while fewer than `maxUnacked` chunks await an ack.
 */
export class ChunkSender {
  readonly checkId: string;
  readonly limits: ChunkLimits;
  private pending: Occurrence[] = [];
  /** seq values of emitted chunks still waiting for their ack. */
  private readonly inFlight: number[] = [];
  private closed = false;

  constructor(checkId: string, limits: ChunkLimits = DEFAULT_CHUNK_LIMITS) {
    this.checkId = checkId;
    this.limits = limits;
  }

  enqueue(occurrences: readonly Occurrence[]): void {
    requireRuntime(!this.closed, 'STATE', 'sender closed');
    this.pending.push(...occurrences);
  }

  /** Occurrences still queued behind the window. */
  get pendingCount(): number {
    return this.pending.length;
  }

  /** Emitted chunks not yet acknowledged. */
  get unacked(): number {
    return this.inFlight.length;
  }

  /**
   * Emit the next chunk allowed by the window, stamped with the seq of
   * the message that will carry it: null while `maxUnacked` chunks are
   * unacknowledged or the queue is empty. Never returns more than
   * `maxChunkOccurrences` occurrences.
   */
  sendNext(seq: number): Occurrence[] | null {
    if (this.closed) return null;
    if (this.inFlight.length >= this.limits.maxUnacked) return null;
    if (this.pending.length === 0) return null;
    requireRuntime(
      Number.isInteger(seq) && seq >= 0,
      'SEQUENCE',
      'seq must be a nonnegative integer',
    );
    const chunk = this.pending.slice(0, this.limits.maxChunkOccurrences);
    this.pending = this.pending.slice(chunk.length);
    this.inFlight.push(seq);
    return chunk;
  }

  /**
   * Free the window for the acked chunk seq (the coordinator's ack
   * carries it in payload.completed_units). Unknown seqs are a protocol
   * violation by the coordinator side and are rejected.
   */
  acknowledge(ackedSeq: number): void {
    const at = this.inFlight.indexOf(ackedSeq);
    requireRuntime(
      at !== -1,
      'BACKPRESSURE',
      `ack for unknown chunk seq ${ackedSeq}`,
    );
    this.inFlight.splice(at, 1);
  }

  /** No more occurrences will be enqueued. */
  close(): void {
    this.closed = true;
  }
}

/**
 * Receiver-side accounting for one check: how many accepted chunks the
 * sender could not yet have seen acknowledged. An ack counts only once
 * it is actually delivered to the sender (drained out of the
 * coordinator's outbox), which is what makes a flood detectable.
 */
export class InboundWindow {
  readonly limits: ChunkLimits;
  private accepted = 0;
  private deliveredAcks = 0;

  constructor(limits: ChunkLimits = DEFAULT_CHUNK_LIMITS) {
    this.limits = limits;
  }

  /** Chunks accepted from the sender so far. */
  get acceptedCount(): number {
    return this.accepted;
  }

  /** Chunks the sender provably still holds unacknowledged. */
  get unackedInbound(): number {
    return this.accepted - this.deliveredAcks;
  }

  /**
   * True when accepting another chunk would exceed the bound — the
   * sender emitted while provably holding `maxUnacked` unacknowledged
   * chunks. The receiver treats that as a protocol violation.
   */
  wouldOverflow(): boolean {
    return this.unackedInbound >= this.limits.maxUnacked;
  }

  /** Record one accepted chunk. Call only after `wouldOverflow()` passes. */
  recordAccepted(): void {
    this.accepted += 1;
  }

  /** Record one ack actually delivered to the sender for this check. */
  recordAckDelivered(): void {
    requireRuntime(
      this.deliveredAcks < this.accepted,
      'BACKPRESSURE',
      'ack delivered with nothing in flight',
    );
    this.deliveredAcks += 1;
  }
}

/**
 * Transferred-slot ledger (`pdf_bytes` | `raster_rgba`).
 *
 * "The receiving worker must prove document and raster identity before
 * using a transferred slot." The document half of that proof is the
 * message authority (document_sha256 must match the active registry —
 * enforced before a message is ever applied); the raster half is this
 * ledger: a `raster_rgba` slot is bound to exactly the check that owns
 * the buffer, and at most `maxLiveRasters` checks may hold one at once.
 * A claim beyond the cap means the sender exceeded the bounded resource
 * and its check ends as `resource_limit`. `pdf_bytes` is the shared
 * immutable source and is not exclusive. Claims are released when the
 * check reaches terminal state.
 */
export class TransferLedger {
  private readonly maxLiveRasters: number;
  private readonly claims = new Map<string, 'pdf_bytes' | 'raster_rgba'>();
  private readonly rasterHolders = new Set<string>();

  constructor(maxLiveRasters: number = RUNTIME_LIMITS.maxLiveRasters) {
    this.maxLiveRasters = maxLiveRasters;
  }

  get liveRasters(): number {
    return this.rasterHolders.size;
  }

  claim(
    slot: 'pdf_bytes' | 'raster_rgba',
    holderCheckId: string,
  ): 'ok' | 'raster_cap' | 'foreign' {
    if (slot === 'pdf_bytes') {
      // Downgrading from a raster claim frees the raster hold — the
      // check no longer uses the buffer, so it must not count against
      // the live-raster bound.
      this.claims.set(holderCheckId, slot);
      this.rasterHolders.delete(holderCheckId);
      return 'ok';
    }
    const prior = this.claims.get(holderCheckId);
    if (prior !== undefined && prior !== slot) return 'foreign';
    if (
      !this.rasterHolders.has(holderCheckId) &&
      this.rasterHolders.size >= this.maxLiveRasters
    ) {
      return 'raster_cap';
    }
    this.claims.set(holderCheckId, slot);
    this.rasterHolders.add(holderCheckId);
    return 'ok';
  }

  /** Free every slot held by a check that reached terminal state. */
  release(holderCheckId: string): void {
    this.claims.delete(holderCheckId);
    this.rasterHolders.delete(holderCheckId);
  }
}
