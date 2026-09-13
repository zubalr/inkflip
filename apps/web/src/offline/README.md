# `src/offline/` — explicit offline asset lifecycle (T25)

The page-side controller for `apps/web/public/sw.js`. Together they
implement the contract in `planning/security/PRIVACY_AND_NETWORK_TESTS.md`
("Asset request policy") and `planning/deployment/STATIC_DEPLOYMENT.md`
("Assets, caches and provider limits"):

- **Explicit action, never opportunistic.** Nothing is cached by
  installing the service worker, by page load, or by opening a document.
  Only `prepareOfflineAssets()` triggers a fetch+verify+store pass over
  the versioned allowlist.
- **Manifest-bound generations.** The manifest (`./manifest.ts`) names
  exact same-origin paths: the frozen `config/resolved-assets.json`
  reader/model tree (declared sha256 per file), the curated
  `/examples/amount/` mount, and the running app shell (`/`,
  `/index.html`, built script/style chunks, the emitted `pdf.worker`
  bundle). The generation id is a digest of the normalized manifest — a
  release that changes a path or digest produces a different cache, so a
  model update can never reuse a wrong-hash entry.
- **Verified at store and at serve.** The worker checks declared sha256
  when storing and re-checks on every serve; a mismatching entry is
  deleted, reported to pages (`inkflip:cache-evicted`), and the request
  falls back to the network — offline that is an honest failure, never
  wrong bytes.
- **Documents/reports are never persisted.** The worker's fetch handler
  only ever serves exact manifest paths; it performs no `cache.put`
  outside prepare and never touches `blob:`, `data:`, cross-origin or
  non-GET requests. No document byte, crop, report or filename can enter
  a cache through this module.
- **Three distinct removals.** Document Clear/close (session-owned:
  terminates reader workers, revokes owned object URLs, drops document
  state) leaves offline assets intact. `removeOfflineAssets()` deletes
  every `inkflip-offline-*` cache. The OCR model's IndexedDB warm-start
  slot is removed only by the reader's own "Remove downloaded OCR data"
  action (`TesseractOcrReader.removeModelData()`).
- **Honest failure.** Prepare is atomic per generation: any failed or
  integrity-mismatched entry discards the whole new generation and
  returns `ok:false`; a partially prepared browser is never reported
  ready. `offlineStatus()` reports `unsupported` / `unregistered` /
  `not_prepared` / `ready` / `degraded` from real persisted state.
- **No forensic promise.** `OFFLINE_LIMITATIONS` (returned with status
  and removal results, surfaced as `OFFLINE_COPY`) states that browser
  process memory, HTTP cache, OS swap, downloaded files and download
  history cannot be forensically erased.

## API

```ts
import {
  buildOfflineManifest,
  isControlled,
  offlineStatus,
  offlineSupported,
  prepareOfflineAssets,
  registerServiceWorker,
  removeOfflineAssets,
  subscribeOfflineEvents,
  waitForControl,
  OFFLINE_COPY,
  OFFLINE_LIMITATIONS,
} from "./offline"; // apps/web/src/offline/index.ts

// Registration is gated out of dev builds; pass { allowDev: true } to
// override (tests do).
await registerServiceWorker({});

const result = await prepareOfflineAssets({
  release: "web-static", // label carried into the generation record
});
// result.ok === true only when every allowlisted byte was fetched,
// hash-verified and stored; result.controlled confirms this page's
// fetches now pass through the worker.

const status = await offlineStatus();
await removeOfflineAssets();
```

## Composition note

The application shell does **not** import this module yet — wiring the
"Prepare for offline use" control into the page belongs to the UI owner
scope. The app is fully functional without the worker; the worker script
ships inert in `public/` until a page registers it. Tests exercise the
real lifecycle against the production build (see
`tests/privacy/cache.spec.ts`).

## Acceptance

```sh
bun run test:privacy -- tests/privacy/cache.spec.ts
```
