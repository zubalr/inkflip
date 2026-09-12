/**
 * T22 preview mount — wires the import feature to the REAL
 * collaborators: the T11 RunCoordinator (generation-first lifecycle),
 * the T24 import gate via `packages/reports/import`, and the T09
 * pdf.js adapter as the host-installed reader allowlist. Nothing is
 * stubbed: parsing, bounds, schema/hash/asset verification, source
 * binding and comparison readiness are the production path.
 *
 * `window.__t22` exposes the coordinator, controller, engine, adapter,
 * installed readers, the controller event log, the T16 export engine
 * (so tests can produce real selected exports in-page), the contracts
 * `seal`/`normalize` helpers (for building valid report variants) and
 * `MessageFactory` (for stale-generation proof) — same harness pattern
 * as `__t08`/`__t09`.
 */
import React from "react";
import { createRoot } from "react-dom/client";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.mjs?url";
import { MessageFactory, RunCoordinator } from "../../../../../packages/runtime/src/index";
import { createPdfJsReader } from "../../../../../packages/readers-pdfjs/src/index";
import type { PdfJsApi } from "../../../../../packages/readers-pdfjs/src/types.ts";
import { normalize, seal } from "../../../../../packages/contracts/src/index";
import type { Reader, Report } from "../../../../../packages/contracts/src/index";
import {
  IMPORT_JSON_LIMIT,
  openReport,
  prepareComparison,
  readerAvailability,
  replayView,
  reportViewModel,
  verifySourceCandidate,
} from "../../../../../packages/reports/import/index";
import type {
  ImportedReport,
  ReaderAvailability,
} from "../../../../../packages/reports/import/index";
import { projectReport, serializeReportJson } from "../../../../../packages/reports/export/index";
import { ImportController } from "./controller";
import { ImportWorkspace } from "./ImportWorkspace";
import "../../styles/tokens.css";
import "../../styles/global.css";
import styles from "../../styles/App.module.css";

const adapter = createPdfJsReader({
  // The injected module is the pinned 6.3.289 legacy build; the adapter
  // only touches the minimal PdfJsApi surface.
  pdfjs: pdfjs as unknown as PdfJsApi,
  workerSrc: workerUrl,
  cMapUrl: "/assets/pdfjs/6.3.289/cmaps/",
  standardFontDataUrl: "/assets/pdfjs/6.3.289/standard_fonts/",
  wasmUrl: "/assets/pdfjs/6.3.289/wasm/",
  iccUrl: "/assets/pdfjs/6.3.289/iccs/",
});

/** The host-installed reader allowlist — the only runnable identities. */
const installed: Reader[] = [adapter.readers.text, adapter.readers.render];

const engine = {
  maxJsonBytes: IMPORT_JSON_LIMIT,
  openReport: (data: Uint8Array) => openReport(data),
  readerAvailability: (
    report: unknown,
    list: readonly { id: string; name: string; version: string }[],
  ) => readerAvailability(report as Report, list),
  reportView: (
    imported: unknown,
    availability: { available: readonly { id: string }[]; missing: readonly { id: string }[] },
  ) => reportViewModel(imported as ImportedReport, availability as ReaderAvailability),
  replayView: (
    imported: unknown,
    availability: { available: readonly { id: string }[]; missing: readonly { id: string }[] },
    attached: boolean,
  ) => replayView(imported as ImportedReport, availability as ReaderAvailability, attached),
  verifySource: (report: unknown, bytes: Uint8Array) =>
    verifySourceCandidate(report as Report, bytes),
  prepareComparison: (left: unknown, right: unknown) =>
    prepareComparison(left as Report, right as Report),
};

const coordinator = new RunCoordinator();
const events: unknown[] = [];
const controller = new ImportController({
  host: coordinator,
  engine,
  installedReaders: () => installed,
  onEvent: (event) => {
    events.push(event);
  },
});

(globalThis as { __t22?: unknown }).__t22 = {
  coordinator,
  controller,
  engine,
  adapter,
  installed,
  events,
  MessageFactory,
  exportEngine: { projectReport, serializeReportJson },
  contracts: { seal, normalize },
};

const rootElement = document.getElementById("root");
if (rootElement) {
  createRoot(rootElement).render(
    <React.StrictMode>
      <main className={styles.main}>
        <p className={styles.eyebrow}>T22 preview — strict report import</p>
        <h1 className={styles.headline} style={{ fontSize: "42px" }}>
          Open a saved report
        </h1>
        <ImportWorkspace controller={controller} host={coordinator} />
      </main>
    </React.StrictMode>,
  );
}
