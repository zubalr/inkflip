/*
 * Inkflip offline service worker (T25) — explicit, manifest-bound static
 * asset lifecycle.
 *
 * Contract (planning/security/PRIVACY_AND_NETWORK_TESTS.md +
 * deployment/STATIC_DEPLOYMENT.md + architecture/RUNTIME_LIFECYCLE.md):
 *
 * - NOTHING is precached at install/activate. Caching happens only on the
 *   explicit `inkflip:prepare` message carrying a manifest built by
 *   apps/web/src/offline (versioned same-origin allowlist: application
 *   shell, staged reader runtimes, the pinned OCR model, curated example
 *   assets). No landing-view background download exists.
 * - The fetch handler only ever *serves* exact paths named by the active
 *   manifest generation. Every other request — cross-origin, non-GET,
 *   blob:/data:, imported reports, document payloads, or simply unlisted
 *   same-origin paths — is left to the platform untouched. This worker
 *   never calls cache.put outside prepare: there is no runtime or
 *   opportunistic caching, so document bytes, report JSON, crops and
 *   filenames can never enter a cache through it.
 * - Cache generations are manifest-bound: the generation id is a digest
 *   of the normalized manifest itself, so a release that changes any
 *   declared path/digest produces a different cache — a model update can
 *   never silently reuse bytes stored for a different identity.
 * - Entries whose manifest row declares a sha256 are verified at store
 *   time AND again at serve time; a mismatching cache entry is deleted,
 *   reported to clients, and the request falls back to the network (which
 *   simply fails when offline — an honest miss, never wrong bytes).
 * - `inkflip:remove` deletes every cache this worker owns. Removal of
 *   downloaded OCR model data (the reader's IndexedDB slot) is a
 *   separate product action; document Clear is a different action again
 *   and does not touch these caches. No removal claims forensic erasure:
 *   browser process memory, HTTP cache, OS swap and download history are
 *   outside what a service worker can wipe.
 *
 * State survives worker restarts through CacheStorage itself: the index
 * cache holds the active generation pointer, and each generation cache
 * stores its own normalized manifest record under a private pseudo-URL
 * that is never a manifest path, so it is never served to a page.
 */
"use strict";

const SW_PROTOCOL_VERSION = 1;
/** Cache holding exactly one entry: the active-generation pointer. */
const INDEX_CACHE = "inkflip-offline-index";
const INDEX_KEY = "/__inkflip_sw__/index.json";
/** Generation caches: `${GEN_PREFIX}${generation}`. */
const GEN_PREFIX = "inkflip-offline-gen-";
/** Pseudo-URL inside each generation cache holding its manifest record. */
const MANIFEST_KEY = "/__inkflip_sw__/manifest.json";
/** Response header recording the sha256 of the body stored at prepare. */
const DIGEST_HEADER = "x-inkflip-sha256";
const DIGEST_HEADER_LC = DIGEST_HEADER.toLowerCase();

/**
 * Warm copy of the active generation, loaded during `activate` so the
 * fetch handler can decide synchronously whether a path is served.
 * `entries` maps pathname -> { sha256: string|null }.
 */
let active = null;

function hex(buffer) {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function sha256hex(data) {
  return hex(await crypto.subtle.digest("SHA-256", data));
}

function jsonResponse(value) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

/** Canonical manifest serialization — the generation id's only input. */
function normalizeManifest(manifest) {
  const entries = [...(manifest.entries ?? [])]
    .map((e) => ({
      path: String(e.path),
      sha256: typeof e.sha256 === "string" && /^[0-9a-f]{64}$/.test(e.sha256) ? e.sha256 : null,
      kind: typeof e.kind === "string" ? e.kind : "asset",
    }))
    .sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  const seen = new Set();
  const unique = [];
  for (const e of entries) {
    if (seen.has(e.path)) continue;
    seen.add(e.path);
    unique.push(e);
  }
  return {
    schema: "inkflip-offline-manifest/1",
    release: String(manifest.release ?? ""),
    entries: unique,
  };
}

function generationCacheName(generation) {
  return `${GEN_PREFIX}${generation}`;
}

function isOwnedCacheName(name) {
  return name === INDEX_CACHE || name.startsWith(GEN_PREFIX);
}

async function readIndex() {
  try {
    const cache = await caches.open(INDEX_CACHE);
    const res = await cache.match(INDEX_KEY);
    if (!res) return null;
    const body = await res.json();
    if (typeof body?.generation !== "string") return null;
    return body;
  } catch {
    return null;
  }
}

async function readManifestRecord(cacheName) {
  try {
    const cache = await caches.open(cacheName);
    const res = await cache.match(MANIFEST_KEY);
    if (!res) return null;
    const body = await res.json();
    if (!Array.isArray(body?.entries)) return null;
    return body;
  } catch {
    return null;
  }
}

/** Repopulate the warm `active` view from persisted state. */
async function loadActive() {
  const index = await readIndex();
  if (index === null) {
    active = null;
    return;
  }
  const record = await readManifestRecord(generationCacheName(index.generation));
  if (record === null || record.generation !== index.generation) {
    // Index points at a missing/incomplete generation — never pretend
    // readiness; leave no pointer at a half-written cache.
    active = null;
    return;
  }
  active = {
    generation: index.generation,
    entries: new Map(record.entries.map((e) => [e.path, e])),
  };
}

/** Report a cache integrity event to every controlled page. */
async function reportToClients(payload) {
  try {
    const list = await clients.matchAll({ type: "window" });
    for (const client of list) client.postMessage(payload);
  } catch {
    /* reporting is best-effort; the delete already happened */
  }
}

/**
 * Serve `request` from the active generation. Only ever called for exact
 * manifest paths. Stored bodies are re-verified against the declared (or
 * prepare-recorded) digest before they are handed out: a wrong-hash entry
 * is deleted and reported, never served.
 */
async function serveFromActive(request) {
  const url = new URL(request.url);
  const entry = active.entries.get(url.pathname);
  const cache = await caches.open(generationCacheName(active.generation));
  const cached = await cache.match(request, { ignoreVary: true });
  if (!cached) {
    // Declared by the manifest but absent from the cache — a partial or
    // evicted entry degrades to the plain network result (which fails
    // honestly when offline) rather than a fabricated response.
    return fetch(request);
  }
  const expected = entry?.sha256 ?? cached.headers.get(DIGEST_HEADER_LC);
  if (!expected) {
    // A manifest-path response with no digest record — neither a
    // declared sha256 nor the prepare-recorded header — was not written
    // by a verified prepare and is never served. Delete it and fall back
    // to the honest network result rather than handing out unverified
    // bytes.
    await cache.delete(request);
    await reportToClients({
      type: "inkflip:cache-evicted",
      generation: active.generation,
      path: url.pathname,
      reason: "missing_digest_record",
    });
    return fetch(request);
  }
  const body = await cached.clone().arrayBuffer();
  const digest = await sha256hex(body);
  if (digest !== expected) {
    await cache.delete(request);
    const problem = entry?.sha256 ? "declared_digest_mismatch" : "stored_digest_mismatch";
    await reportToClients({
      type: "inkflip:cache-evicted",
      generation: active.generation,
      path: url.pathname,
      reason: problem,
    });
    return fetch(request);
  }
  const headers = new Headers(cached.headers);
  headers.delete(DIGEST_HEADER_LC);
  return new Response(body, {
    status: cached.status,
    statusText: cached.statusText,
    headers,
  });
}

/**
 * Explicit prepare: fetch every manifest entry from the network, verify
 * declared digests, store under the manifest-bound generation, and only
 * then atomically repoint the index and drop superseded generations. Any
 * failure deletes the partial generation and reports — a partially
 * prepared browser is never labelled offline-ready.
 */
async function prepare(manifest) {
  const normalized = normalizeManifest(manifest);
  if (normalized.entries.length === 0) {
    return { ok: false, error: "empty_manifest" };
  }
  const generation = (
    await sha256hex(new TextEncoder().encode(JSON.stringify(normalized)))
  ).slice(0, 16);
  const cacheName = generationCacheName(generation);
  const cache = await caches.open(cacheName);
  const stored = [];
  const failed = [];
  let bytes = 0;
  try {
    for (const entry of normalized.entries) {
      if (entry.path.startsWith("/__inkflip_sw__/")) {
        failed.push({ path: entry.path, error: "reserved_path" });
        continue;
      }
      const url = new URL(entry.path, self.location.origin).href;
      let response;
      try {
        response = await fetch(url, {
          cache: "no-store",
          credentials: "same-origin",
          // A hung socket must not stall the whole prepare pass — fail
          // closed as fetch_failed instead.
          signal: AbortSignal.timeout(30_000),
        });
      } catch (error) {
        failed.push({
          path: entry.path,
          error: `fetch_failed: ${error?.message ?? error}`,
        });
        continue;
      }
      if (!response.ok) {
        failed.push({ path: entry.path, error: `http_${response.status}` });
        continue;
      }
      const body = await response.arrayBuffer();
      const digest = await sha256hex(body);
      if (entry.sha256 !== null && digest !== entry.sha256) {
        failed.push({
          path: entry.path,
          error: "integrity_mismatch",
          expected: entry.sha256,
          actual: digest,
        });
        continue;
      }
      const headers = new Headers(response.headers);
      headers.set(DIGEST_HEADER, digest);
      await cache.put(url, new Response(body, { status: 200, headers }));
      stored.push(entry.path);
      bytes += body.byteLength;
    }
    if (failed.length > 0) {
      await caches.delete(cacheName);
      return { ok: false, generation, error: "incomplete", failed, stored };
    }
    // The manifest record makes the generation self-describing; it is the
    // last entry written before the index flips, so an interrupted prepare
    // can never produce an active-but-incomplete generation.
    await cache.put(
      MANIFEST_KEY,
      jsonResponse({ ...normalized, generation, storedAt: new Date().toISOString() }),
    );
    const index = await caches.open(INDEX_CACHE);
    await index.put(
      INDEX_KEY,
      jsonResponse({
        generation,
        entries: normalized.entries.length,
        bytes,
        activatedAt: new Date().toISOString(),
      }),
    );
    active = {
      generation,
      entries: new Map(normalized.entries.map((e) => [e.path, e])),
    };
    // Superseded generations and interrupted-prepare leftovers go away now.
    const names = await caches.keys();
    for (const name of names) {
      if (name.startsWith(GEN_PREFIX) && name !== cacheName) {
        await caches.delete(name);
      }
    }
    return {
      ok: true,
      generation,
      stored: stored.length,
      bytes,
      entries: stored,
    };
  } catch (error) {
    await caches.delete(cacheName).catch(() => false);
    return {
      ok: false,
      generation,
      error: `prepare_failed: ${error?.message ?? error}`,
      failed,
      stored,
    };
  }
}

/** Delete every cache this worker owns (explicit remove-offline-assets). */
async function removeAll() {
  const names = await caches.keys();
  const removed = [];
  for (const name of names) {
    if (isOwnedCacheName(name)) {
      if (await caches.delete(name)) removed.push(name);
    }
  }
  active = null;
  return { ok: true, removed };
}

async function status() {
  if (active === null) await loadActive();
  if (active === null) return { ok: true, ready: false };
  const cache = await caches.open(generationCacheName(active.generation));
  const keys = await cache.keys();
  const paths = keys
    .map((r) => new URL(r.url).pathname)
    .filter((p) => !p.startsWith("/__inkflip_sw__/"));
  return {
    ok: true,
    ready: true,
    generation: active.generation,
    entries: paths.length,
    missing: [...active.entries.keys()].filter((p) => !paths.includes(p)),
  };
}

self.addEventListener("install", (event) => {
  // No precache here by design — installation is not preparation.
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      await loadActive();
      // Drop half-written generations left by an interrupted prepare:
      // they are not the active one and can never be activated now.
      const names = await caches.keys();
      for (const name of names) {
        if (
          name.startsWith(GEN_PREFIX) &&
          (active === null || name !== generationCacheName(active.generation))
        ) {
          await caches.delete(name);
        }
      }
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  let url;
  try {
    url = new URL(request.url);
  } catch {
    return;
  }
  // Only same-origin exact manifest paths are ever served by this worker.
  // blob:/data:/cross-origin/unlisted paths return here untouched — no
  // respondWith, no cache lookup, no storage of any kind.
  if (url.origin !== self.location.origin) return;
  const pathname = url.pathname;
  // Fast path: a loaded manifest that does not name this path means the
  // request never touches this worker at all.
  if (active !== null && !active.entries.has(pathname)) return;
  event.respondWith(
    (async () => {
      // The warm `active` view is empty after a worker restart — reload
      // the persisted generation record so a prepared browser keeps
      // working offline instead of silently passing through to a dead
      // network. With no persisted generation this still resolves to a
      // plain fetch: the honest result (offline → fails).
      if (active === null) await loadActive();
      if (active === null || !active.entries.has(pathname)) {
        return fetch(request);
      }
      return serveFromActive(request);
    })().catch(() => fetch(request)),
  );
});

self.addEventListener("message", (event) => {
  const data = event.data;
  if (typeof data !== "object" || data === null) return;
  const port = event.ports && event.ports[0];
  const reply = (value) => {
    if (port) port.postMessage(value);
  };
  const run = (promise) =>
    event.waitUntil(
      promise.then(reply, (error) => reply({ ok: false, error: String(error?.message ?? error) })),
    );
  switch (data.type) {
    case "inkflip:ping":
      reply({ ok: true, protocol: SW_PROTOCOL_VERSION });
      return;
    case "inkflip:prepare":
      run(prepare(data.manifest ?? {}));
      return;
    case "inkflip:remove":
      run(removeAll());
      return;
    case "inkflip:status":
      run(status());
      return;
    default:
      reply({ ok: false, error: "unknown_message" });
  }
});
