/**
 * T16 export feature preview mount.
 *
 * Wires the ExportPanel to the real export engine from packages/reports/export.
 * Exposes window.__exportHarness for browser test automation.
 */
import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  buildExportPreview,
  exportFileName,
  projectReport,
  renderReportHtml,
  serializeReportJson,
} from "../../../../../packages/reports/export/index.ts";
import sampleReport from "../../../../../planning/contracts/examples/valid/native-evidence.inkflip.json";
import { ExportPanel } from "./ExportPanel";
import type { ExportEngine } from "./types";
import "../../styles/tokens.css";
import "../../styles/global.css";
import styles from "../../styles/App.module.css";

const F01_BASE64 =
  "JVBERi0xLjcKJeLjz9MKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIg" +
  "Pj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW" +
  "50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAv" +
  "TWVkaWFCb3ggWzAgMCA1MjAgNDAwXSAvQ3JvcEJveCBbMCAwIDUyMCA0MDBdIC9Sb3RhdG" +
  "UgMCAvVXNlclVuaXQgMSAvUmVzb3VyY2VzIDw8IC9Gb250IDw8IC9GMCA0IDAgUiAvRjEg" +
  "NiAwIFIgPj4gPj4gL0NvbnRlbnRzIDUgMCBSID4+CmVuZG9iago0IDAgb2JqCjw8IC9UeX" +
  "BlIC9Gb250IC9TdWJ0eXBlIC9UeXBlMSAvQmFzZUZvbnQgL0hlbHZldGljYSAvRW5jb2Rp" +
  "bmcgL1dpbkFuc2lFbmNvZGluZyA+PgplbmRvYmoKNSAwIG9iago8PCAvTGVuZ3RoIDIzOC" +
  "A+PgpzdHJlYW0KQlQgL0YwIDE2IFRmIDQ4IDM1MiBUZCAoU1lOVEhFVElDIEVYQU1QTEUp" +
  "IFRqIEVUCkJUIC9GMCAxMiBUZiA0OCAzMjAgVGQgKE5vIHJlYWwgdHJhbnNhY3Rpb24uIF" +
  "JlYWRlciBiZWhhdmlvciBvbmx5LikgVGogRVQKQlQgL0YxIDQ4IFRmIDQ4IDIyMCBUZCAo" +
  "JDEwMCkgVGogRVQKQlQgL0YwIDEyIFRmIDQ4IDEzMCBUZCAoUmVuZGVyZWQgbWFya3MgYW" +
  "5kIGV4dHJhY3RlZCB0ZXh0IGFyZSBzZXBhcmF0ZS4pIFRqIEVUCgplbmRzdHJlYW0KZW5k" +
  "b2JqCjYgMCBvYmoKPDwgL1R5cGUgL0ZvbnQgL1N1YnR5cGUgL1R5cGUxIC9CYXNlRm9ud" +
  "CAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9Ub1VuaWNvZGUgNyAw" +
  "IFIgPj4KZW5kb2JqCjcgMCBvYmoKPDwgL0xlbmd0aCAzNjAgPj4Kc3RyZWFtCi9DSURJbm" +
  "l0IC9Qcm9jU2V0IGZpbmRyZXNvdXJjZSBiZWdpbgoxMiBkaWN0IGJlZ2luCmJlZ2luY21h" +
  "cAovQ0lEU3lzdGVtSW5mbyA8PCAvUmVnaXN0cnkgKEFkb2JlKSAvT3JkZXJpbmcgKFVDUy" +
  "kgL1N1cHBsZW1lbnQgMCA+PiBkZWYKL0NNYXBOYW1lIC9JbmtmbGlwRXhhbXBsZSBkZWYK" +
  "L0NNYXBUeXBlIDIgZGVmCjEgYmVnaW5jb2Rlc3BhY2VyYW5nZQo8MDA+IDxGRj4KZW5kY2" +
  "9kZXNwYWNlcmFuZ2UKMyBiZWdpbmJmY2hhcgo8MjQ+IDwwMDI0Pgo8MzA+IDwwMDMwPgo8" +
  "MzE+IDwwMDMxMDAyQzAwMzA+CmVuZGJmY2hhcgplbmRjbWFwCkNNYXBOYW1lIGN1cnJlbn" +
  "RkaWN0IC9DTWFwIGRlZmluZXJlc291cmNlIHBvcAplbmQKZW5kCgplbmRzdHJlYW0KZW5k" +
  "b2JqCnhyZWYKMCA4CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxNSAwMDAwMCBuIA" +
  "owMDAwMDAwMDY0IDAwMDAwIG4gCjAwMDAwMDAxMjEgMDAwMDAgbiAKMDAwMDAwMDMwMiAw" +
  "MDAwMCBuIAowMDAwMDAwMzk5IDAwMDAwIG4gCjAwMDAwMDA2ODggMDAwMDAgbiAKMDAwMD" +
  "AwMDgwMiAwMDAwMCBuIAp0cmFpbGVyCjw8IC9TaXplIDggL1Jvb3QgMSAwIFIgPj4Kc3Rh" +
  "cnR4cmVmCjEyMTMKJSVFT0YK";

function decodeBase64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

const DEFAULT_PDF_BYTES = decodeBase64ToBytes(F01_BASE64);

const defaultReport = (() => {
  const rep = structuredClone(sampleReport) as any;
  rep.document.display_name = "mapping-amount.pdf";
  if (!rep.export.included.includes("filename")) rep.export.included.push("filename");
  if (!rep.export.included.includes("annotations")) rep.export.included.push("annotations");
  rep.annotations = [
    {
      id: "a_note_1",
      finding_id: "f_amount",
      page_index: 0,
      text: "Review discrepancy in rendered glyph",
      author_label: "analyst",
      origin: "human_entered",
    },
  ];
  return rep;
})();

const defaultEngine: ExportEngine = {
  project: (source, request) => projectReport(source as never, request as never),
  preview: (report, options) => buildExportPreview(report as never, options as never),
  serializeJson: (report) => serializeReportJson(report as never),
  renderHtml: (report) => renderReportHtml(report as never),
  fileName: (report, format) => exportFileName(report as never, format),
};

interface DownloadEntry {
  readonly filename: string;
  readonly text: string;
}

export interface ExportHarnessApi {
  setSource: (newSource: unknown, bytes?: Uint8Array | null) => void;
  setEngine: (newEngine: ExportEngine) => void;
  engine: ExportEngine;
  getDownloads: () => readonly DownloadEntry[];
  clearDownloads: () => void;
  defaultReport: unknown;
  defaultPdfBytes: Uint8Array;
}

let capturedDownloads: DownloadEntry[] = [];

function ExportHarnessApp() {
  const [source, setSource] = useState<unknown>(defaultReport);
  const [rawBytes, setRawBytes] = useState<Uint8Array | null | undefined>(DEFAULT_PDF_BYTES);
  const [engine, setEngine] = useState<ExportEngine>(defaultEngine);

  const sourcePdfBytes = useMemo(() => {
    if (rawBytes === undefined) return undefined;
    return () => rawBytes;
  }, [rawBytes]);

  const onDownload = (filename: string, text: string) => {
    capturedDownloads = [...capturedDownloads, { filename, text }];
  };

  (globalThis as unknown as { __exportHarness?: ExportHarnessApi }).__exportHarness = {
    setSource: (newSource: unknown, bytes?: Uint8Array | null) => {
      setSource(newSource);
      if (bytes !== undefined) {
        setRawBytes(bytes);
      }
    },
    setEngine: (newEngine: ExportEngine) => {
      setEngine(newEngine);
    },
    engine,
    getDownloads: () => capturedDownloads,
    clearDownloads: () => {
      capturedDownloads = [];
    },
    defaultReport,
    defaultPdfBytes: DEFAULT_PDF_BYTES,
  };

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <h1 className={styles.headline}>T16 Export Preview</h1>
      </header>
      <ExportPanel
        engine={engine}
        source={source}
        sourcePdfBytes={sourcePdfBytes}
        onDownload={onDownload}
      />
    </main>
  );
}

const rootElement = document.getElementById("root");
if (rootElement) {
  createRoot(rootElement).render(
    <React.StrictMode>
      <ExportHarnessApp />
    </React.StrictMode>,
  );
}
