/**
 * Owned-resource teardown (T11; invariant I17 bounded work).
 *
 * Clear and cancellation both end at the same place: every owned
 * resource is torn down in a bounded pass — RenderTasks cancelled,
 * fetches aborted, OCR/alignment workers terminated, PDF
 * document/worker handles destroyed, object URLs revoked, observers
 * disconnected, canvases removed, message listeners invalidated.
 *
 * The registry stores teardown callbacks plus the browser resource
 * verbs it knows how to invoke. Teardown runs in reverse registration
 * order (LIFO, dependents before their dependencies), is bounded, and
 * collects failures instead of aborting: cleanup continues and the
 * failures are returned for the record. This is deterministic local
 * release, not a forensic secure-erasure claim.
 */

/** Teardown verbs probed on owned resources, in invocation order. */
export const TEARDOWN_VERBS = [
  'cancel',
  'abort',
  'unsubscribe',
  'disconnect',
  'terminate',
  'destroy',
  'close',
  'remove',
  'revoke',
] as const;

export type TeardownVerb = (typeof TEARDOWN_VERBS)[number];

export type TeardownFn = () => void;

interface Owned {
  readonly label: string;
  readonly teardown: TeardownFn;
}

export interface CleanupFailure {
  readonly label: string;
  readonly error: unknown;
}

function probeTeardown(resource: unknown, label: string): TeardownFn {
  if (typeof resource === 'function') {
    return resource as TeardownFn;
  }
  const record = resource as Record<string, unknown>;
  const verbs = TEARDOWN_VERBS.filter(
    (verb) => typeof record?.[verb] === 'function',
  );
  return () => {
    for (const verb of verbs) {
      (record[verb] as TeardownFn).call(record);
    }
  };
}

export class CleanupRegistry {
  private readonly owned: Owned[] = [];

  /**
   * Register an owned resource. `teardown` may be an explicit callback;
   * without one the registry probes the standard verbs (cancel, abort,
   * disconnect, terminate, destroy, close, remove, unsubscribe, revoke)
   * and invokes all it finds, so a handle can give up every release it
   * offers.
   */
  own(resource: unknown, label = 'resource', teardown?: TeardownFn): void {
    this.owned.push({
      label,
      teardown: teardown ?? probeTeardown(resource, label),
    });
  }

  /** Convenience: register an owned object URL for revocation. */
  ownObjectUrl(url: string, label = `object-url:${url.slice(0, 24)}`): void {
    this.own(url, label, () => URL.revokeObjectURL(url));
  }

  get size(): number {
    return this.owned.length;
  }

  /**
   * Tear everything down in reverse registration order. Returns the
   * failures encountered; the registry is always emptied, so a second
   * call is a no-op rather than a second teardown.
   */
  teardownAll(): CleanupFailure[] {
    const failures: CleanupFailure[] = [];
    while (this.owned.length > 0) {
      const entry = this.owned.pop()!;
      try {
        entry.teardown();
      } catch (error) {
        failures.push({ label: entry.label, error });
      }
    }
    return failures;
  }
}
