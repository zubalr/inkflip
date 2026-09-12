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
 * then commits the bytes to the worker-readable cache — "verify before
 * committing a model to cache". The cache slot is the same
 * idb-keyval store (`keyval-store`/`keyval`) that the pinned
 * tesseract.js@7.0.0 worker reads with `cacheMethod:'readOnly'`, keyed
 * `${cachePath}/${lang}.traineddata`; that way the engine consumes the
 * exact verified bytes instead of refetching.
 *
 * The slot is the ONLY model channel the engine may use. The reader
 * calls `prepareForEngine()` immediately before each worker creation:
 * it requires the slot to exist and re-verifies its contents. The
 * worker is launched with a v7 `Lang` object payload — the pinned
 * worker script has no fetch branch for object languages — so a cache
 * miss fails initialization honestly rather than downloading
 * unverified bytes. If IndexedDB is unavailable or the verified
 * payload cannot be committed/read back, `prepareForEngine` throws:
 * the engine receives the exact verified bytes or the run fails.
 *
 * A mismatched cache entry is deleted and reported, then replaced by a
 * fresh download (RUNTIME_LIFECYCLE: "A mismatched cache entry is
 * deleted and reported; retry requires a fresh download").
 */
import { sha256 } from '../../contracts/src/index.ts';
import { OcrError, OCR_REASON, requireOcr } from './errors.ts';
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
   */
  async prepare(): Promise<PreparedModel> {
    if (this.verifiedBytes !== null) {
      this.setState('ready_memory');
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

    // 1) Probe the worker-readable cache; a hit still must verify.
    if (this.store !== null) {
      try {
        const cached = await this.store.get(this.cacheKey);
        if (cached instanceof Uint8Array && cached.length > 0) {
          if (this.verify(cached)) {
            this.verifiedBytes = cached;
            this.setState('ready_cached');
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
          this.limitations.push(
            'cache_integrity: deleted mismatched cached model entry',
          );
        }
      } catch (error) {
        this.limitations.push(
          `model_cache_unavailable: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }

    // 2) Cold path: download the pinned same-origin bytes ourselves.
    this.setState('downloading');
    const fetchImpl = this.hooks.fetchImpl ?? fetch;
    let response: Response;
    try {
      response = await fetchImpl(this.model.sourcePath, {
        cache: 'no-store',
        credentials: 'same-origin',
      });
    } catch (error) {
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
    if (!response.ok) {
      this.setState('not_prepared');
      throw new OcrError(
        OCR_REASON.MISSING_MODEL,
        `model unavailable at ${this.model.sourcePath} (HTTP ${response.status})`,
      );
    }

    this.setState('verifying');
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (!this.verify(bytes)) {
      this.setState('failed_integrity');
      throw new OcrError(
        OCR_REASON.MODEL_INTEGRITY,
        `downloaded model failed sha256 verification (${this.model.id})`,
      );
    }

    // 3) Commit verified bytes to the worker-readable cache.
    if (this.store !== null) {
      try {
        await this.store.set(this.cacheKey, bytes);
      } catch (error) {
        this.limitations.push(
          `model_cache_unavailable: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }
    this.verifiedBytes = bytes;
    this.setState('ready_memory');
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
   * Engine-boundary gate: guarantee that the worker-readable cache
   * slot holds the exact verified payload before a worker is created.
   *
   * Why this exists: the pinned worker consumes
   * `${cachePath}/${lang}.traineddata` from idb-keyval — and nothing
   * else (the `Lang` object payload it is launched with has no fetch
   * branch, and `cacheMethod:'readOnly'` never writes). So if this
   * slot cannot be committed and read back verified, there is no
   * honest way to feed the engine the verified model — the caller
   * gets a typed `missing_model`/`model_integrity` failure instead of
   * a silent second download or stale bytes.
   */
  async prepareForEngine(): Promise<PreparedModel> {
    const prepared = await this.prepare();
    requireOcr(
      this.store !== null,
      OCR_REASON.MISSING_MODEL,
      'cannot deliver verified model bytes to the engine: the ' +
        'worker-readable model cache (IndexedDB keyval-store) is ' +
        'unavailable',
    );
    const store = this.store;
    // Commit a snapshot copy so later mutation of the in-memory bytes
    // cannot alter what the worker reads.
    try {
      await store.set(this.cacheKey, prepared.bytes.slice());
    } catch (error) {
      throw new OcrError(
        OCR_REASON.MISSING_MODEL,
        'cannot deliver verified model bytes to the engine: ' +
          'worker-readable cache write failed: ' +
          `${error instanceof Error ? error.message : String(error)}`,
      );
    }
    let check: unknown;
    try {
      check = await store.get(this.cacheKey);
    } catch (error) {
      throw new OcrError(
        OCR_REASON.MISSING_MODEL,
        'cannot deliver verified model bytes to the engine: ' +
          'worker-readable cache read-back failed: ' +
          `${error instanceof Error ? error.message : String(error)}`,
      );
    }
    requireOcr(
      check instanceof Uint8Array && this.verify(check),
      OCR_REASON.MODEL_INTEGRITY,
      'worker-readable model cache slot failed verification after ' +
        'commit — refusing to let the engine consume unverified bytes',
    );
    return prepared;
  }

  /**
   * The "Remove downloaded OCR data" action: drops the persisted
   * cache entry and in-memory copy. Static model caching may survive
   * Clear — deletion is explicit only.
   */
  async remove(): Promise<void> {
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
