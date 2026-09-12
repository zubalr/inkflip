/**
 * Session state binding for the browser app (T11).
 *
 * This module is the app's single doorway into the runtime lifecycle:
 * the UI renders `SessionStore.view` and nothing else, and every inbound
 * worker message passes through `ingest`, which applies only what the
 * coordinator's authority admitted. A stale event — old generation,
 * document, run, job or sequence — is rejected before it can touch the
 * view, so stale results can never render (I07).
 *
 * The store is deliberately generic over its host and view types: the
 * concrete wiring is `new SessionStore(new RunCoordinator(...))` from
 * `packages/runtime`. Naming it structurally keeps this file free of
 * cross-package `.ts` import specifiers, which `apps/web/tsconfig.json`
 * cannot yet resolve — and keeps the state layer testable with either
 * the real coordinator or a recording double.
 */

/** Minimal view shape the store itself needs; the rest stays opaque. */
export interface SessionViewCore {
  readonly fileState: string;
  readonly generation: number;
  readonly notice: string | null;
  readonly revision: number;
}

/** Admission result shape shared with the runtime authority. */
export interface AdmissionLike {
  readonly ok: boolean;
  readonly code: string;
}

/** The lifecycle host contract — satisfied by RunCoordinator. */
export interface StoreHost<S extends SessionViewCore> {
  snapshot(): S;
  receive(message: unknown): AdmissionLike;
  requestCancel(): unknown;
  requestClear(next?: 'idle' | 'replace'): unknown;
  subscribe(listener: () => void): () => void;
}

export class SessionStore<S extends SessionViewCore, H extends StoreHost<S>> {
  private readonly host: H;
  private view: S;
  private readonly listeners = new Set<(view: S) => void>();
  private readonly detach: () => void;

  constructor(host: H) {
    this.host = host;
    this.view = host.snapshot();
    this.detach = host.subscribe(() => this.refresh());
  }

  /**
   * The current presentation snapshot. It is replaced wholesale on every
   * accepted mutation — never patched by an in-flight or rejected event.
   */
  get current(): S {
    return this.view;
  }

  get fileState(): string {
    return this.view.fileState;
  }

  get notice(): string | null {
    return this.view.notice;
  }

  get generation(): number {
    return this.view.generation;
  }

  /** Subscribe to view changes; returns an unsubscribe function. */
  subscribe(listener: (view: S) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private refresh(): void {
    this.view = this.host.snapshot();
    for (const listener of [...this.listeners]) listener(this.view);
  }

  /**
   * Offer one inbound worker message. The coordinator validates and
   * admits or rejects it; a rejection changes nothing here — the view is
   * only ever rebuilt from admitted bookkeeping.
   */
  ingest(message: unknown): AdmissionLike {
    return this.host.receive(message);
  }

  /**
   * User cancellation: the coordinator moves the visible state to
   * cancelled first, then tears down — completed results are kept
   * (notice key `progress.cancelled`).
   */
  cancel(): unknown {
    return this.host.requestCancel();
  }

  /** Clear the workspace, or clear-and-replace with the next file. */
  clear(next: 'idle' | 'replace' = 'idle'): unknown {
    return this.host.requestClear(next);
  }

  /** Detach from the host (module teardown/tests). */
  destroy(): void {
    this.detach();
    this.listeners.clear();
  }
}
