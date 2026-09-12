/**
 * T08 preview mount — wires the open/selection features to the REAL
 * collaborators: the pinned pdf.js 6.3.289 legacy pair (installed by T02,
 * same-origin worker via `?url`), the T09 reader adapter and the T11
 * RunCoordinator. Nothing is stubbed: validation, metadata, page bounds,
 * generation-first replacement and the check plan are the production path.
 *
 * `?profile=mobile` pins the mobile safety profile (10 MiB / 5 pages /
 * 2 Mpx) so the limits are exercised deterministically.
 *
 * `window.__t08` exposes the coordinator, controller, adapter, profile and
 * the controller event log for the browser suite — same harness pattern as
 * tests/readers/pdfjs.spec.ts (`__t09`).
 */
import React from "react";
import { createRoot } from "react-dom/client";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.mjs?url";
import {
  MessageFactory,
  RunCoordinator,
  deriveRunKey,
} from "../../../../../packages/runtime/src/index";
import { createPdfJsReader } from "../../../../../packages/readers-pdfjs/src/index";
import type { PdfJsApi } from "../../../../../packages/readers-pdfjs/src/types.ts";
import { MOBILE_PROFILE, resolveProfile } from "./limits";
import { OpenController } from "./controller";
import { OpenWorkspace, type PlanOutcome } from "./OpenWorkspace";
import { displaySize } from "../selection/region";
import type { ContractRegion } from "../selection/region";
import type { RegionRaster } from "../selection/RegionEditor";
import "../../styles/tokens.css";
import "../../styles/global.css";
import styles from "../../styles/App.module.css";

const params = new URLSearchParams(window.location.search);
const profile =
  params.get("profile") === "mobile" ? MOBILE_PROFILE : resolveProfile();

const adapter = createPdfJsReader({
  // The injected module is the pinned 6.3.289 legacy build; the adapter
  // only touches the minimal PdfJsApi surface below.
  pdfjs: pdfjs as unknown as PdfJsApi,
  workerSrc: workerUrl,
  cMapUrl: "/assets/pdfjs/6.3.289/cmaps/",
  standardFontDataUrl: "/assets/pdfjs/6.3.289/standard_fonts/",
  wasmUrl: "/assets/pdfjs/6.3.289/wasm/",
  iccUrl: "/assets/pdfjs/6.3.289/iccs/",
  limits: { maxRasterPixels: profile.maxRasterPixels },
});

const coordinator = new RunCoordinator();
const events: unknown[] = [];
const controller = new OpenController({
  host: coordinator,
  adapter,
  profile,
  onEvent: (event) => {
    events.push(event);
  },
});

/** Fit the raster to a bounded preview edge (CSS px == raster px). */
const PREVIEW_EDGE_PX = 720;

async function renderPageRaster(
  handle: unknown,
  pageIndex: number,
): Promise<RegionRaster> {
  const doc = controller.currentDocument;
  const page = doc?.pages[pageIndex];
  if (!page) throw new Error(`page ${pageIndex + 1} has no metadata`);
  const [dispW, dispH] = displaySize(page);
  const requested = PREVIEW_EDGE_PX / Math.max(dispW, dispH);
  const checks = adapter.plan(handle as never, {
    pages: [pageIndex],
    capabilities: ["render"],
  });
  const check = checks[0];
  if (!check) throw new Error("render check was not planned");
  const outcome = await adapter.extract(
    handle as never,
    check,
    () => undefined,
    {},
    { renderScalePxPerPt: requested },
  );
  const raster = outcome.raster;
  if (!raster) {
    throw new Error(outcome.result.reason ?? "render failed");
  }
  return {
    widthPx: raster.widthPx,
    heightPx: raster.heightPx,
    scalePxPerPt: raster.scalePxPerPt,
    imageData: raster.imageData,
    limitations: raster.limitations,
  };
}

let lastStartRunRegions: ReadonlyMap<number, ContractRegion> | null = null;

function startRun(
  handle: unknown,
  pages: readonly number[],
  regions: ReadonlyMap<number, ContractRegion>,
): PlanOutcome {
  lastStartRunRegions = regions;
  const doc = controller.currentDocument;
  if (!doc) throw new Error("no document");
  const regionBindings: Record<string, string> = {};
  for (const [pageIndex, region] of regions) {
    regionBindings[`ocr:p${pageIndex}`] = region.id;
  }
  const baseChecks = adapter.plan(handle as never, {
    pages: [...pages],
    capabilities: ["native_text", "render"],
  });
  // Enforce maxOcrPagesPerRun (audit §2):
  // Prioritize pages with explicit user-defined regions, then remaining selected pages up to cap.
  const regionPages = pages.filter((p) => regions.has(p));
  const nonRegionPages = pages.filter((p) => !regions.has(p));
  const ocrPages = [...regionPages, ...nonRegionPages].slice(
    0,
    profile.maxOcrPagesPerRun,
  );
  const ocrChecks =
    ocrPages.length > 0
      ? adapter.plan(handle as never, {
          pages: ocrPages,
          capabilities: ["ocr"],
          regions: regionBindings,
        })
      : [];
  const checks = [...baseChecks, ...ocrChecks];
  const runKey = deriveRunKey(
    doc.sha256,
    [adapter.readers.text, adapter.readers.render],
    checks,
  );
  coordinator.startRun({
    runKey,
    checks,
    selectedPagesTotal: pages.length,
    budgetMs: 120_000,
  });
  const intents = coordinator.drainOutbox();
  const dispatched = intents
    .filter((intent) => intent.type === "dispatch")
    .map((intent) => ({
      jobId: intent.jobId,
      checkId: intent.checkId ?? "",
      capability: intent.capability ?? "",
    }));
  const snapshot = coordinator.snapshot();
  return {
    checks: checks.map((c) => ({
      id: c.id,
      page_index: c.page_index,
      capability: c.capability,
      region_id: c.region_id,
    })),
    dispatched,
    selectedPagesTotal: snapshot.run?.selectedPagesTotal ?? pages.length,
  };
}

(globalThis as { __t08?: unknown }).__t08 = {
  coordinator,
  controller,
  adapter,
  profile,
  events,
  MessageFactory,
  getLastStartRunRegions: () => lastStartRunRegions,
};

const rootElement = document.getElementById("root");
if (rootElement) {
  createRoot(rootElement).render(
    <React.StrictMode>
      <main className={styles.main}>
        <p className={styles.eyebrow}>T08 preview — local open and selection</p>
        <h1 className={styles.headline} style={{ fontSize: "42px" }}>
          Open a PDF on this device
        </h1>
        <OpenWorkspace
          controller={controller}
          host={coordinator}
          profile={profile}
          renderPageRaster={renderPageRaster}
          startRun={startRun}
        />
      </main>
    </React.StrictMode>,
  );
}
