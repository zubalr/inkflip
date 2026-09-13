/**
 * T25 preview mount — exercises the REAL offline lifecycle against the
 * REAL composed inspection session. Same harness role as the feature
 * mounts (T08 open, T22 import) and the T15 privacy harness: the only
 * test-owned code is the wiring; nothing at the contract surface is
 * stubbed.
 *
 * Bound collaborators, all production code paths:
 * - `InspectionSession` (src/features/inspect/session.ts): the composed
 *   open → selection → run → report session, driven through the real
 *   `OpenWorkspace` UI (file input, document panel, clear, run).
 * - `src/offline/` (this directory, the T25 module): register / prepare /
 *   status / remove against `public/sw.js` — only ever by explicit user
 *   action (the buttons below or `__t25.*` calls); nothing registers or
 *   caches on load.
 * - `TesseractOcrReader` model probe: a direct `prepareModel()` so the
 *   spec can observe the typed `unavailable_offline`/`missing_model`
 *   asset states without driving a whole run.
 *
 * `window.__t25` exposes JSON-safe surfaces the Playwright suite drives:
 * the offline lifecycle functions, the coordinator snapshot, the real
 * controller event stream (teardown evidence), a document object-URL
 * registered through the coordinator's own file-scoped CleanupRegistry
 * (the production revocation mechanism), CacheStorage inspection and a
 * corruption helper for the serve-time wrong-hash leg.
 */
import React from "react";
import { createRoot } from "react-dom/client";
import * as tesseract from "tesseract.js";

import {
  OFFLINE_CACHE_PREFIX,
  OFFLINE_COPY,
  OFFLINE_LIMITATIONS,
  buildOfflineManifest,
  isControlled,
  offlineStatus,
  prepareOfflineAssets,
  registerServiceWorker,
  removeOfflineAssets,
  subscribeOfflineEvents,
  type OfflineManifest,
  type OfflineStatus,
  type PrepareResult,
  type RemoveResult,
} from "./index";
import { InspectionSession } from "../features/inspect/session";
import {
  OCR_ASSET_HASHES,
  OCR_CORE_BUILD,
  OCR_ENGINE_VERSION,
  OCR_MODEL,
  OCR_PATHS,
} from "../features/inspect/assets";
import { resolveProfile } from "../features/open/limits";
import { OpenWorkspace } from "../features/open/OpenWorkspace";
import { displaySize } from "../features/selection/region";
import type { RegionRaster } from "../features/selection/RegionEditor";
import { TesseractOcrReader } from "../../../../packages/readers-tesseract/src/index";
import type {
  PageRaster,
  TesseractEngineModule,
} from "../../../../packages/readers-tesseract/src/index";

import "../styles/tokens.css";
import "../styles/global.css";
import styles from "../styles/App.module.css";

const profile = resolveProfile();
const session = new InspectionSession(profile);

/** Bounded preview edge for the region editor (CSS px == raster px). */
const PREVIEW_EDGE_PX = 720;

/**
 * The real adapter render path for the workspace preview raster —
 * identical wiring to the T08 open mount, bound to the session's own
 * adapter/controller.
 */
async function renderPageRaster(handle: unknown, pageIndex: number): Promise<RegionRaster> {
  const doc = session.openController.currentDocument;
  const page = doc?.pages[pageIndex];
  if (!page) throw new Error(`page ${pageIndex + 1} has no metadata`);
  const [dispW, dispH] = displaySize(page);
  const requested = PREVIEW_EDGE_PX / Math.max(dispW, dispH);
  const checks = session.adapter.plan(handle as never, {
    pages: [pageIndex],
    capabilities: ["render"],
  });
  const check = checks[0];
  if (!check) throw new Error("render check was not planned");
  const outcome = await session.adapter.extract(
    handle as never,
    check,
    () => undefined,
    {},
    { renderScalePxPerPt: requested },
  );
  const raster = outcome.raster;
  if (!raster) throw new Error(outcome.result.reason ?? "render failed");
  return {
    widthPx: raster.widthPx,
    heightPx: raster.heightPx,
    scalePxPerPt: raster.scalePxPerPt,
    imageData: raster.imageData,
    limitations: raster.limitations,
  };
}

// ---------------------------------------------------------------------------
// Test surface: real controller event stream + the handle last opened.
// ---------------------------------------------------------------------------
const controllerEvents: { type: string; label?: string; generation?: number }[] = [];
let lastHandle: unknown = null;
session.openController.subscribe((event) => {
  controllerEvents.push({
    type: event.type,
    ...("label" in event ? { label: String(event.label) } : {}),
    ...("generation" in event ? { generation: event.generation } : {}),
  });
  if (event.type === "metadata") {
    lastHandle = session.openController.currentHandle;
  }
});

/** Worker→page notifications (inkflip:cache-evicted, …). */
const swEvents: { type: string; generation?: string; path?: string; reason?: string }[] = [];
subscribeOfflineEvents((event) => {
  swEvents.push({ ...event });
});

/**
 * A direct TesseractOcrReader.prepareModel() probe — isolates the asset
 * state machine (not_prepared → downloading → verifying → ready_* /
 * unavailable_offline / missing_model) from the run machinery so the
 * spec can assert the exact typed outcome on a cold offline profile.
 */
async function ocrPrepareProbe(): Promise<
  | { ok: true; preparation: unknown; modelState: string }
  | {
      ok: false;
      error: { name: string; reason: string | null; message: string };
      modelState: string;
    }
> {
  const reader = new TesseractOcrReader({
    engine: tesseract as unknown as TesseractEngineModule,
    engineVersion: OCR_ENGINE_VERSION,
    coreBuild: OCR_CORE_BUILD,
    model: OCR_MODEL,
    paths: OCR_PATHS,
    assetHashes: OCR_ASSET_HASHES,
    profile: session.profile.id,
    runKey: "t25-offline-probe",
    renderReaderId: session.adapter.readers.render.id,
    rasterSource: async (): Promise<PageRaster> => {
      throw new Error("probe reader has no rasters");
    },
  });
  try {
    const preparation = await reader.prepareModel();
    return { ok: true, preparation, modelState: reader.modelState };
  } catch (error) {
    return {
      ok: false,
      error: {
        name: (error as { name?: string })?.name ?? "Error",
        reason: (error as { reason?: string })?.reason ?? null,
        message: String((error as { message?: string })?.message ?? error),
      },
      modelState: reader.modelState,
    };
  }
}

/**
 * Register a real object URL through the coordinator's file-scoped
 * CleanupRegistry — the same ownership channel OpenController uses for
 * the pdf.js handle — so the spec can observe its revocation on the real
 * clear path (no test-private teardown).
 */
function makeDocumentUrl(bytes: number[]): { url: string } {
  const url = URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type: "application/pdf" }));
  session.coordinator.own(url, "document-object-url", () => {
    controllerEvents.push({ type: "teardown", label: "document-object-url" });
    URL.revokeObjectURL(url);
  });
  return { url };
}

/**
 * A real `Worker` owned by the coordinator's file-scoped registry — the
 * same channel that owns the pdf.js document handle — so the spec can
 * observe `worker.terminate()` actually running at clear (the teardown
 * event is pushed from inside the teardown callback itself).
 */
function makeProbeWorker(): { url: string } {
  const blobUrl = URL.createObjectURL(
    new Blob(["self.onmessage = () => self.postMessage('alive');"], {
      type: "text/javascript",
    }),
  );
  const worker = new Worker(blobUrl);
  session.coordinator.own(worker, "probe-worker", () => {
    controllerEvents.push({ type: "teardown", label: "probe-worker" });
    worker.terminate();
    URL.revokeObjectURL(blobUrl);
  });
  return { url: blobUrl };
}

/** Prove the last document handle is destroyed after clear. */
async function probeLastHandle(): Promise<{ ok: true } | { ok: false; message: string }> {
  if (lastHandle === null) return { ok: false, message: "no handle was ever opened" };
  try {
    await session.adapter.pages(lastHandle as never);
    return { ok: true };
  } catch (error) {
    return { ok: false, message: String((error as { message?: string })?.message ?? error) };
  }
}

/** CacheStorage census — every cache name and every stored request URL. */
async function cacheDump(): Promise<{ names: string[]; entries: Record<string, string[]> }> {
  const names = await caches.keys();
  const entries: Record<string, string[]> = {};
  for (const name of names) {
    const store = await caches.open(name);
    entries[name] = (await store.keys()).map((request) => request.url);
  }
  return { names, entries };
}

/**
 * Serve-time wrong-hash probe: overwrite a manifest-path entry in a
 * generation cache with different bytes while KEEPING the recorded
 * digest header — exactly what a stale/wrong-body cache entry looks
 * like. Returns the cache that held the entry, else null.
 */
async function corruptCachedEntry(path: string): Promise<{ cache: string; path: string } | null> {
  const url = new URL(path, window.location.origin).href;
  for (const name of await caches.keys()) {
    if (!name.startsWith(OFFLINE_CACHE_PREFIX) || name === "inkflip-offline-index") {
      continue;
    }
    const store = await caches.open(name);
    const stored = await store.match(url);
    if (!stored) continue;
    const headers = new Headers(stored.headers);
    const bad = new TextEncoder().encode(`inkflip-t25-corruption-probe ${path} ${Date.now()}`);
    await store.put(url, new Response(bad, { status: 200, headers }));
    return { cache: name, path };
  }
  return null;
}

const api = {
  // The module under test — the real lifecycle functions, unwrapped.
  OFFLINE_CACHE_PREFIX,
  OFFLINE_COPY,
  OFFLINE_LIMITATIONS,
  modelPath: OCR_MODEL.sourcePath,
  register: () => registerServiceWorker({}),
  prepare: (options?: { manifest?: OfflineManifest }) => prepareOfflineAssets(options ?? {}),
  status: (): Promise<OfflineStatus> => offlineStatus(),
  remove: (): Promise<RemoveResult> => removeOfflineAssets(),
  isControlled,
  buildManifest: () => buildOfflineManifest(),
  // The real session/coordinator surface.
  session,
  snapshot: () => session.coordinator.snapshot(),
  events: controllerEvents,
  swEvents,
  // Probes built on real production paths (documented above).
  ocrPrepareProbe,
  makeDocumentUrl,
  makeProbeWorker,
  probeLastHandle,
  cacheDump,
  corruptCachedEntry,
};

(globalThis as { __t25?: unknown }).__t25 = api;

// ---------------------------------------------------------------------------
// Offline panel — the explicit actions, current status and the honest
// limitation copy, all driven by the real module (no store of results
// outside this panel's React state).
// ---------------------------------------------------------------------------
function OfflinePanel() {
  const [status, setStatus] = React.useState<OfflineStatus | null>(null);
  const [prepare, setPrepare] = React.useState<PrepareResult | null>(null);
  const [remove, setRemove] = React.useState<RemoveResult | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setStatus(await offlineStatus());
  }, []);

  React.useEffect(() => {
    void refresh();
    return subscribeOfflineEvents(() => void refresh());
  }, [refresh]);

  const doPrepare = React.useCallback(async () => {
    setBusy("prepare");
    try {
      const result = await prepareOfflineAssets({});
      setPrepare(result);
      await refresh();
    } finally {
      setBusy(null);
    }
  }, [refresh]);

  const doRemove = React.useCallback(async () => {
    setBusy("remove");
    try {
      const result = await removeOfflineAssets();
      setRemove(result);
      await refresh();
    } finally {
      setBusy(null);
    }
  }, [refresh]);

  return (
    <section aria-label="Offline assets" data-testid="offline-panel">
      <h2>Offline use</h2>
      <p data-testid="offline-status">
        {status === null
          ? "status: probing…"
          : `status: ${status.readiness}` +
            (status.generation ? ` · generation ${status.generation}` : "") +
            ` · entries ${status.entries}` +
            (status.missing.length > 0 ? ` · missing ${status.missing.length}` : "") +
            ` · ${status.controlled ? "controlled" : "not controlled"}`}
      </p>
      {status !== null && status.missing.length > 0 && (
        <ul data-testid="offline-missing">
          {status.missing.map((path: string) => (
            <li key={path}>{path}</li>
          ))}
        </ul>
      )}
      <div>
        <button
          type="button"
          data-testid="prepare-offline"
          disabled={busy !== null}
          onClick={() => void doPrepare()}
        >
          {OFFLINE_COPY.prepareAction}
        </button>
        <button
          type="button"
          data-testid="remove-offline"
          disabled={busy !== null}
          onClick={() => void doRemove()}
        >
          {OFFLINE_COPY.removeAction}
        </button>
      </div>
      <p data-testid="prepare-summary">{OFFLINE_COPY.prepareSummary}</p>
      {prepare !== null && (
        <p data-testid="prepare-result">
          {prepare.ok
            ? `prepared · generation ${prepare.generation} · ${prepare.stored} files · ${prepare.bytes} bytes · ${prepare.controlled ? "controlled" : "not controlled"}`
            : `prepare failed · ${prepare.error ?? "unknown"} · ${prepare.failed.length} failed`}
        </p>
      )}
      {remove !== null && (
        <p data-testid="remove-result">
          {`removed ${remove.removed.length} cache(s)` +
            (remove.removed.length > 0 ? ` · ${remove.removed.join(", ")}` : "")}
        </p>
      )}
      <ul data-testid="offline-limitations">
        {OFFLINE_LIMITATIONS.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p data-testid="offline-distinction">{OFFLINE_COPY.resetVsRemove}</p>
    </section>
  );
}

const rootElement = document.getElementById("root");
if (rootElement) {
  createRoot(rootElement).render(
    <React.StrictMode>
      <main className={styles.main}>
        <p className={styles.eyebrow}>T25 preview — offline asset lifecycle</p>
        <h1 className={styles.headline} style={{ fontSize: "42px" }}>
          Inspect a PDF without a network
        </h1>
        <OfflinePanel />
        <OpenWorkspace
          controller={session.openController}
          host={session.coordinator}
          profile={profile}
          renderPageRaster={renderPageRaster}
          startRun={session.startRun}
        />
      </main>
    </React.StrictMode>,
  );
}
