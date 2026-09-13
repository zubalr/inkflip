/**
 * Offline lifecycle controller (T25) — the page side of
 * `apps/web/public/sw.js`.
 *
 * Product contract this module implements:
 *
 * - **Explicit prepare only.** `prepareOfflineAssets()` is the
 *   prepare-offline action: it builds the versioned allowlist manifest
 *   (`./manifest.ts`), registers `/sw.js` when needed and asks the worker
 *   to fetch + hash-verify + store every entry under a manifest-bound
 *   cache generation. Nothing is cached by installing the worker, by
 *   loading a page, or as a side effect of opening a document — and the
 *   worker never caches at serve time.
 * - **Documents and reports are never persisted.** No document byte,
 *   crop, report, filename or hash is ever sent to the worker or placed
 *   in any storage by this module; the worker's allowlist makes such
 *   writes impossible through it. (Invariant I08 / PRIVACY_AND_NETWORK_
 *   TESTS "Default data lifetime".)
 * - **Reset ≠ remove.** Document Clear/close (the inspection session's
 *   generation-first reset: terminates reader workers, revokes owned
 *   object URLs, drops document state) does NOT touch offline assets —
 *   static model/app caching may survive Clear. `removeOfflineAssets()`
 *   is the separate explicit action that deletes every cache the worker
 *   owns. The OCR model's IndexedDB warm-start slot is a third store,
 *   removed only by the reader's own "Remove downloaded OCR data"
 *   (`TesseractOcrReader.removeModelData()`).
 * - **Explicit, honest failure.** A partially prepared browser is never
 *   reported ready: prepare is atomic per generation and integrity
 *   failures surface as `ok:false` with the failed paths.
 * - **No forensic promise.** `OFFLINE_LIMITATIONS` is the wording the
 *   product may surface: removal deletes the named caches but cannot
 *   forensically erase browser process memory, HTTP cache, OS swap,
 *   downloaded files or download history.
 *
 * Registration is gated: production builds register through
 * `registerServiceWorker()`/`prepareOfflineAssets()`; development builds
 * must pass `allowDev` so `vite dev` sessions and unprepared test runs
 * are never surprised by a controlling worker.
 */
import { buildOfflineManifest, OFFLINE_MANIFEST_SCHEMA } from "./manifest";
import type { OfflineManifest, OfflineManifestEntry } from "./manifest";

export {
  buildOfflineManifest,
  OFFLINE_MANIFEST_SCHEMA,
  type OfflineManifest,
  type OfflineManifestEntry,
};

/** Same-origin path of the service worker module. */
export const SW_URL = "/sw.js";
/**
 * Every cache name this lifecycle owns — the index plus generation
 * caches (`inkflip-offline-gen-*`). Matching is by prefix so removal can
 * sweep even generations written by older releases.
 */
export const OFFLINE_CACHE_PREFIX = "inkflip-offline-";

/** Product copy the UI may surface for these actions. */
export const OFFLINE_COPY = {
  prepareAction: "Prepare for offline use",
  prepareSummary:
    "Downloads and integrity-checks this release's app, reader and model files so inspection keeps working without a network.",
  removeAction: "Remove offline assets",
  removeSummary:
    "Deletes the prepared offline copies of app, reader and model files. " +
    "This is separate from closing a document and from removing downloaded OCR data.",
  resetVsRemove:
    "Closing a document clears the document, its readings and its workers; " +
    "prepared offline assets stay available. Removing offline assets deletes " +
    "the cached app/reader/model copies; any open document is unaffected.",
} as const;

/** Honest limitations attached to every remove/status result. */
export const OFFLINE_LIMITATIONS: readonly string[] = [
  "Removal deletes the app's own caches only. Browser process memory, the " +
    "browser HTTP cache, OS swap, downloaded files and download history " +
    "cannot be forensically erased by the app.",
  "Offline readiness covers only the exact allowlisted paths prepared for " +
    "this release; anything else still needs the network.",
];

export type OfflineReadiness =
  | "unsupported"
  | "unregistered"
  | "not_prepared"
  | "ready"
  | "degraded";

export interface OfflineStatus {
  readonly readiness: OfflineReadiness;
  /** Manifest-bound generation id when one is active. */
  readonly generation: string | null;
  /** Entries the active generation actually holds. */
  readonly entries: number;
  /** Manifest paths missing from the active generation (degraded). */
  readonly missing: readonly string[];
  /** Whether this page's fetches pass through the worker. */
  readonly controlled: boolean;
  readonly limitations: readonly string[];
}

export interface RegisterResult {
  readonly registered: boolean;
  /** Machine-readable reason when not registered. */
  readonly reason: "unsupported" | "dev-build" | "register-failed" | "activated" | null;
  readonly detail: string | null;
}

export interface PrepareResult {
  readonly ok: boolean;
  readonly generation: string | null;
  readonly stored: number;
  readonly bytes: number;
  readonly failed: readonly { path: string; error: string }[];
  /** The page is controlled by the worker (required for offline use). */
  readonly controlled: boolean;
  readonly error: string | null;
}

export interface RemoveResult {
  readonly ok: boolean;
  /** Cache names actually deleted. */
  readonly removed: readonly string[];
  readonly limitations: readonly string[];
}

/** Worker→page notification (integrity evictions). */
export interface OfflineEvent {
  readonly type: string;
  readonly generation?: string;
  readonly path?: string;
  readonly reason?: string;
}

const REQUEST_TIMEOUT_MS = 240_000;

/** Capabilities the lifecycle needs; absence is `unsupported`. */
export function offlineSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    "serviceWorker" in navigator &&
    typeof caches !== "undefined" &&
    typeof MessageChannel !== "undefined" &&
    typeof crypto !== "undefined" &&
    typeof crypto.subtle !== "undefined"
  );
}

/** True in Vite development-mode bundles (the `dev` server path). */
function isDevBuild(): boolean {
  try {
    return (import.meta as { env?: { DEV?: boolean } }).env?.DEV === true;
  } catch {
    return false;
  }
}

/**
 * Register `/sw.js`. Explicit opt-in only — dev builds must pass
 * `allowDev` so the worker never surprises `vite dev` sessions or test
 * contexts that did not ask for offline behavior. Production builds
 * register normally; failure is reported, never thrown away silently.
 */
export async function registerServiceWorker(options: {
  readonly allowDev?: boolean;
  readonly swUrl?: string;
}): Promise<RegisterResult> {
  if (!offlineSupported()) {
    return {
      registered: false,
      reason: "unsupported",
      detail: "service worker or cache API unavailable",
    };
  }
  if (isDevBuild() && options.allowDev !== true) {
    return {
      registered: false,
      reason: "dev-build",
      detail: "service worker registration is disabled in dev builds (pass allowDev to override)",
    };
  }
  try {
    const registration = await navigator.serviceWorker.register(options.swUrl ?? SW_URL, {
      scope: "/",
    });
    // Wait for activation so prepare/status have a live worker.
    const worker =
      registration.active ??
      (await new Promise<ServiceWorker | null>((resolve) => {
        const candidate = registration.installing ?? registration.waiting;
        if (candidate === null) {
          resolve(null);
          return;
        }
        const onChange = () => {
          if (candidate.state === "activated") {
            candidate.removeEventListener("statechange", onChange);
            resolve(candidate);
          }
        };
        candidate.addEventListener("statechange", onChange);
        onChange();
        setTimeout(() => resolve(candidate), 15_000);
      }));
    if (worker === null) {
      return {
        registered: false,
        reason: "register-failed",
        detail: "worker did not reach activated state",
      };
    }
    return {
      registered: true,
      reason: "activated",
      detail: null,
    };
  } catch (error) {
    return {
      registered: false,
      reason: "register-failed",
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

/** A registered, activated worker ready for messages, else null. */
async function readyWorker(timeoutMs = 15_000): Promise<ServiceWorker | null> {
  if (!offlineSupported()) return null;
  try {
    const registration = await Promise.race([
      navigator.serviceWorker.ready,
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("sw ready timeout")), timeoutMs),
      ),
    ]);
    return registration.active;
  } catch {
    return null;
  }
}

/** Whether this page's fetches currently pass through the worker. */
export function isControlled(): boolean {
  return (
    typeof navigator !== "undefined" &&
    "serviceWorker" in navigator &&
    navigator.serviceWorker.controller !== null
  );
}

/** Wait until `clients.claim()` has made this page controlled. */
export async function waitForControl(timeoutMs = 5_000): Promise<boolean> {
  if (isControlled()) return true;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 50));
    if (isControlled()) return true;
  }
  return isControlled();
}

interface SwReply {
  ok?: boolean;
  error?: string;
  generation?: string;
  stored?: number;
  bytes?: number;
  ready?: boolean;
  entries?: number;
  missing?: string[];
  failed?: { path: string; error: string }[];
  removed?: string[];
  protocol?: number;
}

/** One request→reply exchange with the active worker. */
function swRequest(
  worker: ServiceWorker,
  message: Record<string, unknown>,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<SwReply> {
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    const timer = setTimeout(() => {
      channel.port1.close();
      reject(new Error("service worker reply timeout"));
    }, timeoutMs);
    channel.port1.onmessage = (event: MessageEvent) => {
      clearTimeout(timer);
      channel.port1.close();
      resolve((event.data ?? {}) as SwReply);
    };
    worker.postMessage(message, [channel.port2]);
  });
}

/**
 * The explicit prepare-offline action. Registers the worker when needed
 * (same `allowDev` gate as `registerServiceWorker`), builds the versioned
 * manifest, and waits for the worker's verified-store result. An
 * incomplete or integrity-failed outcome is returned as `ok:false` — the
 * caller must not present the browser as offline-ready.
 */
export async function prepareOfflineAssets(
  options: {
    readonly allowDev?: boolean;
    /** Manifest override — tests build fault variants through this. */
    readonly manifest?: OfflineManifest;
    readonly release?: string;
    readonly timeoutMs?: number;
  } = {},
): Promise<PrepareResult> {
  if (!offlineSupported()) {
    return {
      ok: false,
      generation: null,
      stored: 0,
      bytes: 0,
      failed: [],
      controlled: false,
      error: "unsupported",
    };
  }
  const registered = await registerServiceWorker(
    options.allowDev === undefined ? {} : { allowDev: options.allowDev },
  );
  if (!registered.registered) {
    return {
      ok: false,
      generation: null,
      stored: 0,
      bytes: 0,
      failed: [],
      controlled: isControlled(),
      error: `register:${registered.reason} ${registered.detail ?? ""}`.trim(),
    };
  }
  const worker = await readyWorker();
  if (worker === null) {
    return {
      ok: false,
      generation: null,
      stored: 0,
      bytes: 0,
      failed: [],
      controlled: isControlled(),
      error: "worker_not_active",
    };
  }
  const manifest =
    options.manifest ??
    (options.release === undefined
      ? buildOfflineManifest()
      : buildOfflineManifest({ release: options.release }));
  const reply = await swRequest(
    worker,
    { type: "inkflip:prepare", manifest },
    options.timeoutMs ?? REQUEST_TIMEOUT_MS,
  ).catch((error: unknown): SwReply => ({
    ok: false,
    error: error instanceof Error ? error.message : String(error),
  }));
  const controlled = await waitForControl();
  return {
    ok: reply.ok === true,
    generation: reply.generation ?? null,
    stored: reply.stored ?? 0,
    bytes: reply.bytes ?? 0,
    failed: reply.failed ?? [],
    controlled,
    error: reply.ok === true ? null : (reply.error ?? "prepare_failed"),
  };
}

/** Current lifecycle state, honestly reported (never guessed). */
export async function offlineStatus(): Promise<OfflineStatus> {
  const base = {
    generation: null as string | null,
    entries: 0,
    missing: [] as string[],
    controlled: isControlled(),
    limitations: OFFLINE_LIMITATIONS,
  };
  if (!offlineSupported()) {
    return { readiness: "unsupported", ...base };
  }
  const registration = await navigator.serviceWorker.getRegistration("/").catch(() => undefined);
  if (registration === undefined) {
    return { readiness: "unregistered", ...base };
  }
  const worker = registration.active ?? (await readyWorker(3_000));
  if (worker === null) {
    return { readiness: "unregistered", ...base };
  }
  const reply = await swRequest(worker, { type: "inkflip:status" }, 10_000).catch(() => null);
  if (reply === null || reply.ok !== true) {
    return { readiness: "degraded", ...base };
  }
  if (reply.ready !== true) {
    return { readiness: "not_prepared", ...base };
  }
  const missing = reply.missing ?? [];
  return {
    readiness: missing.length === 0 ? "ready" : "degraded",
    generation: reply.generation ?? null,
    entries: reply.entries ?? 0,
    missing,
    controlled: isControlled(),
    limitations: OFFLINE_LIMITATIONS,
  };
}

/**
 * The explicit remove-offline-assets action: every cache the lifecycle
 * owns is deleted, through the worker when one is present and always via
 * a direct CacheStorage sweep so removal works even with no worker.
 * Distinct from document Clear and from the reader's own OCR-data
 * removal; carries no forensic-erasure promise (OFFLINE_LIMITATIONS).
 */
export async function removeOfflineAssets(): Promise<RemoveResult> {
  const removed = new Set<string>();
  if (offlineSupported()) {
    const worker = await readyWorker(3_000);
    if (worker !== null) {
      const reply = await swRequest(worker, { type: "inkflip:remove" }, 15_000).catch(() => null);
      for (const name of reply?.removed ?? []) removed.add(name);
    }
  }
  if (typeof caches !== "undefined") {
    for (const name of await caches.keys()) {
      if (name.startsWith(OFFLINE_CACHE_PREFIX) && (await caches.delete(name))) {
        removed.add(name);
      }
    }
  }
  return {
    ok: true,
    removed: [...removed].sort(),
    limitations: OFFLINE_LIMITATIONS,
  };
}

/** Subscribe to worker→page notifications (e.g. integrity evictions). */
export function subscribeOfflineEvents(listener: (event: OfflineEvent) => void): () => void {
  if (!offlineSupported()) return () => undefined;
  const handler = (event: MessageEvent): void => {
    const data = event.data;
    if (typeof data !== "object" || data === null) return;
    if (typeof data.type !== "string") return;
    if (!data.type.startsWith("inkflip:")) return;
    listener(data as OfflineEvent);
  };
  navigator.serviceWorker.addEventListener("message", handler);
  return () => navigator.serviceWorker.removeEventListener("message", handler);
}
