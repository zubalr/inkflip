/**
 * OCR model preparation and verified-cache plumbing (T10).
 *
 * RUNTIME_LIFECYCLE.md asset states — `not_prepared`, `downloading`,
 * `verifying`, `ready_memory`, `ready_cached`, `failed_integrity`,
 * `unavailable_offline` — are distinct and reported, never collapsed:
 * a missing/corrupt model is not an unreadable page.
 *
 * Byte provenance is explicit. The adapter itself downloads the pinned
 * same-origin traineddata URL, verifies the manifest SHA-256, and only
 * then (optionally) commits the bytes to an adapter-owned
 * warm-start cache — "verify before committing a model to cache". The
 * cache slot is the same idb-keyval store (`keyval-store`/`keyval`)
 * tesseract.js conventions use, keyed `${cachePath}/${lang}.traineddata`,
 * but the engine never reads it: workers are created with
 * `cacheMethod:'none'` and a `{code, data}` language payload carrying
 * the verified bytes themselves (see engine.ts `createEngineWorker`).
 * An unavailable or failing IndexedDB therefore degrades to honest
 * memory-only preparation — never a model failure.
 *
 * Preparation owns its asynchronous side effects: a caller-supplied
 * `AbortSignal` (the operation's terminal signal) plus a manager
 * `epoch` bumped by `remove()` are checked after every internal await
 * and before every state/memory/cache mutation, so a superseded or
 * removed preparation can neither publish states nor recreate a
 * deleted cache entry. A cancellation is never reclassified as an
 * offline/cache warning.
 *
 * A mismatched cache entry is deleted and reported, then replaced by a
 * fresh download (RUNTIME_LIFECYCLE: "A mismatched cache entry is
 * deleted and reported; retry requires a fresh download").
 */
import { sha256 } from '../../contracts/src/index.ts';
import { OcrError, OCR_REASON } from './errors.ts';
import type { OcrReason } from './errors.ts';

/** RUNTIME_LIFECYCLE.md "Asset and cache states" labels. */
export const MODEL_STATES = [
  'not_prepared',
  'downloading',
  'verifying',
  'ready_memory',
  'ready_cached',
  'failed_integrity',
  'unavailable_offline',
] as const;
export type ModelState = (typeof MODEL_STATES)[number];

/** Where the verified model bytes came from for this initialization. */
export type ModelProvenance = 'memory' | 'cache' | 'network' | null;

/** Pinned model identity from `config/resolved-assets.json`. */
export interface ModelIdentity {
  /** Manifest asset id, e.g. `tessdata-fast-eng`. */
  readonly id: string;
  /** Manifest version string (upstream commit for tessdata). */
  readonly version: string;
  /** Manifest SHA-256 of the exact bytes served at `sourcePath`. */
  readonly sha256: string;
  /** Manifest byte length — a cheap pre-hash sanity check. */
  readonly byteLength: number;
  /** Same-origin URL path of the staged file (e.g. `/models/.../eng.traineddata`). */
  readonly sourcePath: string;
  /** BCP-47-ish engine language tag (the worker `langs` value), e.g. `eng`. */
  readonly lang: string;
  /** SPDX license id recorded by the manifest. */
  readonly license: string;
  /**
   * tesseract.js `cachePath` option prefix for the worker-readable
   * cache key (`${cachePath}/${lang}.traineddata`).
   */
  readonly cachePath: string;
}

/** Result of one `prepare()` call. */
export interface ModelPreparation {
  readonly state: ModelState;
  /** Byte source actually used: memory / cache / network. */
  readonly provenance: ModelProvenance;
  /** The verified SHA-256 (lowercase hex) of the model in use. */
  readonly sha256: string;
  /** Non-fatal observations, e.g. an unavailable cache store. */
  readonly limitations: string[];
}

export interface PreparedModel {
  readonly preparation: ModelPreparation;
  /** The verified traineddata bytes (kept in memory for reuse). */
  readonly bytes: Uint8Array;
}

export interface ModelManagerHooks {
  /** State transitions for progress reporting (bounded stage codes). */
  readonly onState?: (state: ModelState) => void;
  /** Environment seams kept injectable for tests and non-IDB contexts. */
  readonly fetchImpl?: typeof fetch;
  readonly idbFactory?: IDBFactory | null;
  readonly online?: () => boolean;
}

function toHex(data: Uint8Array): string {
  let s = '';
  for (const b of data) s += b.toString(16).padStart(2, '0');
  return s;
}

function idbRequest<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('IndexedDB request failed'));
  });
}

/**
 * Minimal idb-keyval@6-compatible reader/writer: database
 * `keyval-store`, object store `keyval`, `put(value, key)` — the exact
 * schema the staged tesseract.js@7.0.0 worker uses for its
 * traineddata cache (src/worker-script/browser/cache.js).
 */
export class KeyvalStore {
  private dbPromise: Promise<IDBDatabase> | null = null;

  constructor(private readonly idb: IDBFactory) {}

  private db(): Promise<IDBDatabase> {
    if (this.dbPromise === null) {
      this.dbPromise = new Promise((resolve, reject) => {
        const req = this.idb.open('keyval-store');
        req.onupgradeneeded = () => {
          if (!req.result.objectStoreNames.contains('keyval')) {
            req.result.createObjectStore('keyval');
          }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed'));
        req.onblocked = () => reject(new Error('IndexedDB open blocked'));
      });
    }
    return this.dbPromise;
  }

  async get(key: string): Promise<unknown> {
    const db = await this.db();
    return idbRequest(
      db.transaction('keyval', 'readonly').objectStore('keyval').get(key),
    );
  }

  async set(key: string, value: Uint8Array): Promise<void> {
    const db = await this.db();
    await idbRequest(
      db.transaction('keyval', 'readwrite').objectStore('keyval').put(value, key),
    );
  }

  async del(key: string): Promise<void> {
    const db = await this.db();
    await idbRequest(
      db.transaction('keyval', 'readwrite').objectStore('keyval').delete(key),
    );
  }
}

/**
 * Owns model bytes for one profile: downloads, verifies, caches and
 * hands out the exact verified payload the OCR worker will read.
 */
export class ModelAssetManager {
  private verifiedBytes: Uint8Array | null = null;
  private state: ModelState = 'not_prepared';
  private readonly store: KeyvalStore | null;
  private readonly limitations: string[] = [];
  /**
   * Manager epoch — bumped by `remove()`. A preparation snapshots it
   * at entry; any later drift means this preparation's results must
   * never publish or persist.
   */
  private epoch = 0;

  constructor(
    private readonly model: ModelIdentity,
    private readonly hooks: ModelManagerHooks = {},
  ) {
    const idb = hooks.idbFactory === undefined
      ? (typeof indexedDB === 'undefined' ? null : indexedDB)
      : hooks.idbFactory;
    this.store = idb === null ? null : new KeyvalStore(idb);
    if (this.store === null) {
      this.limitations.push('model_cache_unavailable: IndexedDB not present');
    }
  }

  /** `${cachePath}/${lang}.traineddata` — the worker's cache key. */
  get cacheKey(): string {
    return `${this.model.cachePath}/${this.model.lang}.traineddata`;
  }

  get currentState(): ModelState {
    return this.state;
  }

  /** sha256 of `bytes` matches the pinned manifest digest. */
  private verify(bytes: Uint8Array): boolean {
    if (bytes.length !== this.model.byteLength) return false;
    return toHex(sha256(bytes)) === this.model.sha256;
  }

  private setState(state: ModelState): void {
    this.state = state;
    this.hooks.onState?.(state);
  }

  /**
   * Ensure verified model bytes are available. Idempotent: already
   * verified in-memory bytes are reused without a network or cache
   * round-trip (`ready_memory` / provenance `memory`).
   *
   * `signal` is the calling operation's terminal signal: together with
   * the manager `epoch` (bumped by `remove()`) it is checked after
   * EVERY internal await and before every state/memory/cache mutation,
   * so a dead preparation can neither publish states nor recreate a
   * deleted cache slot — and cancellation is never reclassified as an
   * offline/cache warning.
   */
  async prepare(signal?: AbortSignal): Promise<PreparedModel> {
    const epoch = this.epoch;
    const alive = (): void => {
      if (this.epoch !== epoch) {
        throw new OcrError(
          OCR_REASON.USER_CANCEL,
          'model preparation invalidated by removeModelData',
        );
      }
      if (signal?.aborted) {
        throw new OcrError(
          OCR_REASON.USER_CANCEL,
          'model preparation cancelled',
        );
      }
    };
    const publish = (state: ModelState): void => {
      alive();
      this.setState(state);
    };

    if (this.verifiedBytes !== null) {
      publish('ready_memory');
      return {
        preparation: {
          state: 'ready_memory',
          provenance: 'memory',
          sha256: this.model.sha256,
          limitations: [...this.limitations],
        },
        bytes: this.verifiedBytes,
      };
    }

    // 1) Probe the warm-start cache; a hit still must verify.
    if (this.store !== null) {
      try {
        const cached = await this.store.get(this.cacheKey);
        alive();
        if (cached instanceof Uint8Array && cached.length > 0) {
          if (this.verify(cached)) {
            this.verifiedBytes = cached;
            publish('ready_cached');
            return {
              preparation: {
                state: 'ready_cached',
                provenance: 'cache',
                sha256: this.model.sha256,
                limitations: [...this.limitations],
              },
              bytes: cached,
            };
          }
          // Mismatched cache entry: delete and report; a fresh
          // download below is the only permitted recovery.
          await this.store.del(this.cacheKey);
          alive();
          this.limitations.push(
            'cache_integrity: deleted mismatched cached model entry',
          );
        }
      } catch (error) {
        if (error instanceof OcrError) throw error;
        alive();
        this.limitations.push(
          `model_cache_unavailable: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }

    // 2) Cold path: download the pinned same-origin bytes ourselves.
    publish('downloading');
    const fetchImpl = this.hooks.fetchImpl ?? fetch;
    let response: Response;
    try {
      response = await fetchImpl(this.model.sourcePath, {
        cache: 'no-store',
        credentials: 'same-origin',
        ...(signal !== undefined ? { signal } : {}),
      });
    } catch (error) {
      // Cancellation/invalidation is never reclassified as offline.
      alive();
      const online = this.hooks.online
        ? this.hooks.online()
        : (typeof navigator === 'undefined' ? true : navigator.onLine !== false);
      const reason: OcrReason = online
        ? OCR_REASON.MISSING_MODEL
        : OCR_REASON.UNAVAILABLE_OFFLINE;
      this.setState(online ? 'not_prepared' : 'unavailable_offline');
      throw new OcrError(
        reason,
        `model fetch failed for ${this.model.sourcePath}: ` +
          `${error instanceof Error ? error.message : String(error)}`,
      );
    }
    alive();
    if (!response.ok) {
      this.setState('not_prepared');
      throw new OcrError(
        OCR_REASON.MISSING_MODEL,
        `model unavailable at ${this.model.sourcePath} (HTTP ${response.status})`,
      );
    }

    publish('verifying');
    const bytes = new Uint8Array(await response.arrayBuffer());
    alive();
    if (!this.verify(bytes)) {
      this.setState('failed_integrity');
      throw new OcrError(
        OCR_REASON.MODEL_INTEGRITY,
        `downloaded model failed sha256 verification (${this.model.id})`,
      );
    }

    // 3) Commit verified bytes to the optional warm-start cache. The
    //    engine never reads this slot — failure degrades to memory-only.
    if (this.store !== null) {
      try {
        alive();
        await this.store.set(this.cacheKey, bytes.slice());
        if (this.epoch !== epoch || signal?.aborted) {
          // Died during the write — remove the resurrected slot so a
          // completed remove() is not silently undone.
          try {
            await this.store.del(this.cacheKey);
          } catch {
            // best-effort cleanup of our own write
          }
          throw new OcrError(
            OCR_REASON.USER_CANCEL,
            'model preparation invalidated during cache commit',
          );
        }
      } catch (error) {
        if (error instanceof OcrError) throw error;
        alive();
        this.limitations.push(
          `model_cache_unavailable: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }
    alive();
    this.verifiedBytes = bytes;
    publish('ready_memory');
    return {
      preparation: {
        state: 'ready_memory',
        provenance: 'network',
        sha256: this.model.sha256,
        limitations: [...this.limitations],
      },
      bytes,
    };
  }

  /**
   * The "Remove downloaded OCR data" action: drops the persisted
   * cache entry and in-memory copy. Static model caching may survive
   * Clear — deletion is explicit only. Invalidates any in-flight
   * preparation FIRST so a stale fetch cannot recreate the slot or
   * republish states afterwards.
   */
  async remove(): Promise<void> {
    this.epoch++;
    this.verifiedBytes = null;
    if (this.store !== null) {
      try {
        await this.store.del(this.cacheKey);
      } catch (error) {
        this.limitations.push(
          `model_cache_unavailable: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }
    this.setState('not_prepared');
  }
}

/** Narrow error helper for integrity failures observed at prepare. */
export function isIntegrityFailure(error: unknown): boolean {
  return error instanceof OcrError && error.reason === OCR_REASON.MODEL_INTEGRITY;
}
