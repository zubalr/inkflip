import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ViewerStage } from "../features/viewer/ViewerStage";
import type { ViewerDoc } from "../features/viewer/types";
import { FileDrop } from "../features/open/FileDrop";
import { OpenWorkspace } from "../features/open/OpenWorkspace";
import { resolveProfile } from "../features/open";
import { InspectionSession } from "../features/inspect/session";
import { ReplaceConfirmDialog } from "../components/Dialogs/ReplaceConfirmDialog";
import { CoveragePanel } from "../features/coverage/CoveragePanel";
import { ExportPanel } from "../features/export/ExportPanel";
import styles from "./Workspace.module.css";

export interface WorkspaceProps {
  onNavigateHome: () => void;
  initialWithExample?: boolean;
  initialDoc?: ViewerDoc | null;
}

const EXAMPLE_DOC: ViewerDoc = {
  pages: [
    {
      index: 0,
      media_box: [0, 0, 612, 792],
      crop_box: [0, 0, 612, 792],
      effective_view_box: [0, 0, 612, 792],
      box_source: "media_box",
      user_unit: 1.0,
      rotation: 0,
      canonical_size_pt: [612, 792],
      raw_to_canonical_transform_id: "t_p0",
      limitations: ["OCR verification was not run on page 0."],
    },
    {
      index: 1,
      media_box: [0, 0, 612, 792],
      crop_box: [0, 0, 612, 792],
      effective_view_box: [0, 0, 612, 792],
      box_source: "media_box",
      user_unit: 1.0,
      rotation: 0,
      canonical_size_pt: [612, 792],
      raw_to_canonical_transform_id: "t_p1",
      limitations: [],
    },
  ],
  readers: [
    {
      id: "reader-pdfium",
      name: "PDFium",
      version: "149.0.7825.0",
      build: "pdfium-wasm",
      adapter_version: "1.0.0",
      method: "native_text",
      environment: "browser",
      settings: {
        normalization: "scalar-whitespace-v1",
        language: null,
        psm: null,
        render_reader_id: null,
        raster_dpi: null,
        annotation_mode: "none",
      },
      capabilities: [],
      model_hashes: [],
      limitations: [],
    },
    {
      id: "reader-pypdf",
      name: "pypdf",
      version: "6.18.0",
      build: "pypdf-wasm",
      adapter_version: "1.0.0",
      method: "native_text",
      environment: "browser",
      settings: {
        normalization: "scalar-whitespace-v1",
        language: null,
        psm: null,
        render_reader_id: null,
        raster_dpi: null,
        annotation_mode: "none",
      },
      capabilities: [],
      model_hashes: [],
      limitations: [],
    },
  ],
  occurrences: [
    {
      id: "occ-p0-dup1",
      reader_id: "reader-pdfium",
      page_index: 0,
      ordinal: 1,
      raw_text: "$1,000.00",
      normalized_text: "$1,000.00",
      normalization_map: [],
      geometry: {
        precision: "exact",
        space: "canonical_page",
        polygon: [
          [100, 150],
          [180, 150],
          [180, 170],
          [100, 170],
        ],
        transform_ids: [],
        basis: "pdfium_char_boxes",
      },
      engine_score: null,
      source_asset_id: null,
      raw_source_locator: "p0:line1",
      limitations: [],
    },
    {
      id: "occ-p0-dup2",
      reader_id: "reader-pdfium",
      page_index: 0,
      ordinal: 2,
      raw_text: "$1,000.00",
      normalized_text: "$1,000.00",
      normalization_map: [],
      geometry: {
        precision: "exact",
        space: "canonical_page",
        polygon: [
          [100, 350],
          [180, 350],
          [180, 370],
          [100, 370],
        ],
        transform_ids: [],
        basis: "pdfium_char_boxes",
      },
      engine_score: null,
      source_asset_id: null,
      raw_source_locator: "p0:line5",
      limitations: [],
    },
    {
      id: "occ-p0-pypdf1",
      reader_id: "reader-pypdf",
      page_index: 0,
      ordinal: 1,
      raw_text: "$10,000.00",
      normalized_text: "$10,000.00",
      normalization_map: [],
      geometry: {
        precision: "exact",
        space: "canonical_page",
        polygon: [
          [100, 150],
          [185, 150],
          [185, 170],
          [100, 170],
        ],
        transform_ids: [],
        basis: "pypdf_boxes",
      },
      engine_score: null,
      source_asset_id: null,
      raw_source_locator: "p0:block1",
      limitations: [],
    },
    {
      id: "occ-p1-item1",
      reader_id: "reader-pdfium",
      page_index: 1,
      ordinal: 1,
      raw_text: "Total Amount Due",
      normalized_text: "Total Amount Due",
      normalization_map: [],
      geometry: {
        precision: "exact",
        space: "canonical_page",
        polygon: [
          [120, 200],
          [240, 200],
          [240, 220],
          [120, 220],
        ],
        transform_ids: [],
        basis: "pdfium_char_boxes",
      },
      engine_score: null,
      source_asset_id: null,
      raw_source_locator: "p1:line2",
      limitations: [],
    },
    {
      id: "occ-p1-pagelevel",
      reader_id: "reader-pypdf",
      page_index: 1,
      ordinal: 2,
      raw_text: "Metadata font dictionary notice",
      normalized_text: "Metadata font dictionary notice",
      normalization_map: [],
      geometry: {
        precision: "page_only",
        space: "canonical_page",
        polygon: null,
        transform_ids: [],
        basis: "page_level_font_dict",
      },
      engine_score: null,
      source_asset_id: null,
      raw_source_locator: "p1:dict",
      limitations: ["Page-level property only; no localized bounding coordinates."],
    },
  ],
  findings: [
    {
      id: "finding-dup1",
      kind: "reading_difference",
      title: "Amount reads differently (occurrence #1)",
      explanation: "PDFium returned “$1,000.00”. pypdf returned “$10,000.00”.",
      page_index: 0,
      occurrence_ids: ["occ-p0-dup1", "occ-p0-pypdf1"],
      check_ids: ["chk-1"],
      alignment: "unique",
      region_id: "region-1",
      priority: "material_token",
      basis: "Exact coordinate alignment.",
      limitations: ["A difference does not establish which reading is correct."],
    },
    {
      id: "finding-dup2",
      kind: "reading_difference",
      title: "Amount reads differently (occurrence #2)",
      explanation: "Duplicate amount token at lower section of Page 1.",
      page_index: 0,
      occurrence_ids: ["occ-p0-dup2"],
      check_ids: ["chk-2"],
      alignment: "unique",
      region_id: "region-2",
      priority: "material_token",
      basis: "Exact coordinate alignment.",
      limitations: ["A difference does not establish which reading is correct."],
    },
    {
      id: "finding-page1-unknown",
      kind: "observed_structure",
      title: "Font metadata structure observation (Page 2)",
      explanation: "Font dictionary observation on Page 2 without localized coordinate bounding.",
      page_index: 1,
      occurrence_ids: ["occ-p1-pagelevel"],
      check_ids: ["chk-3"],
      alignment: "page_level",
      region_id: null,
      priority: "informational",
      basis: "Font dictionary parsing.",
      limitations: ["Page-level only; no localized bounding coordinates."],
    },
  ],
};

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback: (error: Error) => React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

class ViewerErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override render() {
    if (this.state.error) {
      return this.props.fallback(this.state.error);
    }
    return this.props.children;
  }
}

const RUN_STATUS_COPY: Record<string, string> = {
  running: "Running checks…",
  preparing_assets: "Preparing the OCR model…",
};

export const Workspace: React.FC<WorkspaceProps> = ({
  onNavigateHome,
  initialWithExample = true,
  initialDoc,
}) => {
  const profile = useMemo(() => resolveProfile(), []);
  const session = useMemo(() => new InspectionSession(profile), [profile]);
  const [snap, setSnap] = useState(() => session.getState());
  const [exampleDoc, setExampleDoc] = useState<ViewerDoc | null>(
    initialDoc ?? (initialWithExample ? EXAMPLE_DOC : null),
  );

  useEffect(() => session.subscribe(() => setSnap(session.getState())), [session]);
  // Unmounting the workspace releases the session's pdf.js handle,
  // OCR worker and retained bytes.
  useEffect(() => () => session.close(), [session]);
  // Read-only test handle — present only in dev/test-hook builds
  // (vite `__INKFLIP_TEST_HOOKS__` define; shipped builds omit it).
  useEffect(() => {
    if (!__INKFLIP_TEST_HOOKS__) return;
    (globalThis as { __inspect?: InspectionSession }).__inspect = session;
    return () => {
      delete (globalThis as { __inspect?: InspectionSession }).__inspect;
    };
  }, [session]);

  const reportInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const sourceInputRef = useRef<HTMLInputElement>(null);

  const [pendingFile, setPendingFile] = useState<File | null>(null);

  // Header-level offers while a document or report is open replace it —
  // the same confirmed-replacement contract the open workspace enforces.
  const onFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      const occupied = session.getState().doc !== null || session.getState().report !== null;
      if (occupied) {
        setPendingFile(file);
        return;
      }
      void session.offerFile(file);
    },
    [session],
  );

  const onSourceChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      await session.attachSource(file);
    },
    [session],
  );

  const report = snap.report;
  // A real document or report always takes precedence over the example.
  const viewerDoc: ViewerDoc | null = report
    ? {
        pages: report.pages,
        readers: report.readers,
        occurrences: report.occurrences,
        findings: report.findings,
      }
    : snap.doc === null
      ? exampleDoc
      : null;

  const fileState = snap.fileState;
  const busy =
    fileState === "validating_file" || fileState === "loading_metadata";
  const running = fileState === "running" || fileState === "preparing_assets";
  const settled =
    fileState === "complete" || fileState === "partial" || fileState === "failed";
  const showViewer = viewerDoc !== null && (settled || snap.reportSource === "import" || exampleDoc !== null);
  const docTitle = report
    ? ((report.document as { filename?: string | null; display_name?: string | null })
        .filename ??
        (report.document as { display_name?: string | null }).display_name ??
        snap.doc?.label ??
        "Inspection report")
    : exampleDoc !== null
      ? "Invoice-Example.pdf"
      : "Workspace";

  const closeAll = useCallback(() => {
    session.close();
    setExampleDoc(null);
  }, [session]);

  return (
    <div className={styles.workspace}>
      <input
        ref={reportInputRef}
        id="input-import-report"
        type="file"
        accept="application/json,.json,.inkflip.json"
        style={{ display: "none" }}
        onChange={onFileChange}
      />
      <input
        ref={pdfInputRef}
        id="input-open-pdf"
        type="file"
        accept="application/pdf,.pdf"
        style={{ display: "none" }}
        onChange={onFileChange}
      />
      <input
        ref={sourceInputRef}
        id="input-attach-source"
        type="file"
        accept="application/pdf,.pdf"
        style={{ display: "none" }}
        onChange={onSourceChange}
      />

      <header className={styles.documentBar}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <button
            id="btn-back-home"
            type="button"
            className={styles.documentMeta}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              fontWeight: 600,
            }}
            onClick={onNavigateHome}
          >
            ← Home
          </button>
          <span className={styles.documentTitle}>
            {viewerDoc || snap.doc ? docTitle : "Workspace"}
          </span>
          <span className={styles.documentMeta} data-testid="doc-stats">
            {viewerDoc
              ? `${viewerDoc.pages.length} pages · ${viewerDoc.findings.length} findings`
              : snap.doc
                ? `${snap.doc.pageCount} pages · not yet inspected`
                : "No document loaded"}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <button
            id="btn-header-import-report"
            type="button"
            style={{
              padding: "4px 12px",
              fontSize: "var(--text-caption)",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--color-line)",
              background: "var(--color-paper-pure)",
              cursor: "pointer",
            }}
            onClick={() => reportInputRef.current?.click()}
          >
            Open saved report
          </button>
          <button
            id="btn-header-open-pdf"
            type="button"
            style={{
              padding: "4px 12px",
              fontSize: "var(--text-caption)",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--color-line)",
              background: "var(--color-paper-pure)",
              cursor: "pointer",
            }}
            onClick={() => pdfInputRef.current?.click()}
          >
            Open PDF
          </button>
          {viewerDoc || snap.doc ? (
            <button
              id="btn-close-doc"
              type="button"
              style={{
                padding: "4px 12px",
                fontSize: "var(--text-caption)",
                borderRadius: "var(--radius-control)",
                border: "1px solid var(--color-line)",
                background: "var(--color-paper-pure)",
                cursor: "pointer",
              }}
              onClick={closeAll}
            >
              Close Document
            </button>
          ) : (
            <button
              id="btn-load-demo"
              type="button"
              style={{
                padding: "4px 12px",
                fontSize: "var(--text-caption)",
                borderRadius: "var(--radius-control)",
                border: "1px solid var(--color-line)",
                background: "var(--color-paper-pure)",
                cursor: "pointer",
              }}
              onClick={() => setExampleDoc(EXAMPLE_DOC)}
            >
              Load Example
            </button>
          )}
        </div>
      </header>

      <main className={styles.workspaceMain}>
        {snap.error && (
          <div
            id="import-error"
            role="alert"
            style={{
              marginBottom: "var(--space-3)",
              padding: "var(--space-2) var(--space-4)",
              backgroundColor: "var(--color-surface-muted)",
              border: "1px solid var(--color-line)",
              borderRadius: "var(--radius-control)",
              color: "var(--color-ink)",
              fontSize: "var(--text-caption)",
            }}
          >
            {snap.error.message}
            {snap.error.detail ? ` (${snap.error.detail})` : ""}
          </div>
        )}
        {snap.notice && (
          <div
            id="pdf-received-notice"
            role="status"
            style={{
              marginBottom: "var(--space-3)",
              padding: "var(--space-2) var(--space-4)",
              backgroundColor: "var(--color-surface-subtle)",
              border: "1px solid var(--color-line)",
              borderRadius: "var(--radius-control)",
              color: "var(--color-ink)",
              fontSize: "var(--text-caption)",
            }}
          >
            {snap.notice}
          </div>
        )}

        {running && (
          <section
            aria-label="Inspection progress"
            data-testid="run-progress"
            style={{
              padding: "var(--space-4)",
              border: "1px solid var(--color-line)",
              borderRadius: "var(--radius-control)",
            }}
          >
            <h2 style={{ marginTop: 0 }}>{RUN_STATUS_COPY[fileState]}</h2>
            <ul data-testid="run-checks" style={{ listStyle: "none", padding: 0 }}>
              {(snap.run?.checks ?? []).map((check) => (
                <li
                  key={check.id}
                  data-check-id={check.id}
                  data-status={check.status ?? check.phase}
                >
                  <code>{check.id}</code> — {check.capability} on page{" "}
                  {check.pageIndex + 1}: {check.status ?? check.phase}
                </li>
              ))}
            </ul>
            <button
              id="btn-cancel-run"
              type="button"
              style={{
                padding: "4px 12px",
                borderRadius: "var(--radius-control)",
                border: "1px solid var(--color-line)",
                background: "var(--color-paper-pure)",
                cursor: "pointer",
              }}
              onClick={() => session.cancelRun()}
            >
              Cancel run
            </button>
          </section>
        )}

        {fileState === "cancelled" && (
          <section aria-label="Run cancelled" data-testid="run-cancelled">
            <p>The inspection run was cancelled.</p>
            <button
              id="btn-back-to-selection"
              type="button"
              onClick={() => session.newRun()}
              style={{
                padding: "4px 12px",
                borderRadius: "var(--radius-control)",
                border: "1px solid var(--color-line)",
                background: "var(--color-paper-pure)",
                cursor: "pointer",
              }}
            >
              Back to selection
            </button>
          </section>
        )}

        {fileState === "selecting" && snap.doc !== null && snap.reportSource !== "import" && (
          <OpenWorkspace
            controller={session.openController}
            host={session.coordinator}
            profile={profile}
            renderPageRaster={session.renderPageRaster}
            startRun={session.startRun}
          />
        )}

        {showViewer && viewerDoc && (
          <ViewerErrorBoundary
            key={docTitle}
            fallback={(error) => (
              <div
                id="import-error"
                role="alert"
                style={{
                  padding: "var(--space-4)",
                  backgroundColor: "var(--color-surface-muted)",
                  border: "1px solid var(--color-line)",
                  borderRadius: "var(--radius-control)",
                  color: "var(--color-ink)",
                  fontSize: "var(--text-caption)",
                }}
              >
                Failed to display document: {error.message}
              </div>
            )}
          >
            <ViewerStage doc={viewerDoc} />
          </ViewerErrorBoundary>
        )}

        {report && (
          <>
            {settled && snap.doc !== null && (
              <button
                id="btn-rerun"
                type="button"
                style={{
                  marginBottom: "var(--space-3)",
                  padding: "4px 12px",
                  borderRadius: "var(--radius-control)",
                  border: "1px solid var(--color-line)",
                  background: "var(--color-paper-pure)",
                  cursor: "pointer",
                }}
                onClick={() => session.newRun()}
              >
                Re-inspect this document
              </button>
            )}
            <CoveragePanel
              plan={report.plan}
              checks={report.checks}
              pages={report.pages}
              ocrRun={report.plan.checks.some((c) => c.capability === "ocr")}
              findingsCount={report.findings.length}
            />
            {snap.reportSource === "import" && snap.importedReplay !== null && (
              <section
                aria-label="Replay readiness"
                data-testid="replay-status"
                style={{
                  marginTop: "var(--space-3)",
                  padding: "var(--space-2) var(--space-4)",
                  border: "1px solid var(--color-line)",
                  borderRadius: "var(--radius-control)",
                  fontSize: "var(--text-caption)",
                }}
              >
                {snap.importedReplay.source === "missing" ? (
                  <>
                    <p>
                      The original PDF was not embedded in this report. Attach the
                      matching file to enable source replay.
                    </p>
                    <button
                      id="btn-attach-source"
                      type="button"
                      onClick={() => sourceInputRef.current?.click()}
                      style={{
                        padding: "4px 12px",
                        borderRadius: "var(--radius-control)",
                        border: "1px solid var(--color-line)",
                        background: "var(--color-paper-pure)",
                        cursor: "pointer",
                      }}
                    >
                      Attach original PDF
                    </button>
                  </>
                ) : snap.importedReplay.ready ? (
                  <p>Original document {snap.importedReplay.source}; replay ready.</p>
                ) : (
                  <p>
                    Original document {snap.importedReplay.source}. Replay is not
                    ready
                    {snap.importedReplay.readersMissing.length > 0
                      ? ` — missing reader${snap.importedReplay.readersMissing.length === 1 ? "" : "s"}: ${snap.importedReplay.readersMissing.join(", ")}`
                      : ""}
                    .
                  </p>
                )}
              </section>
            )}
            <ExportPanel
              engine={session.exportEngine}
              source={report}
              sourcePdfBytes={session.sourcePdfBytes}
            />
          </>
        )}

        {!busy && !running && fileState === "idle" && viewerDoc === null && (
          <div className={styles.emptyWorkspace}>
            <FileDrop phase="idle" onFile={(file) => void session.offerFile(file)} hasDocument={false} />
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "var(--space-3)",
                marginTop: "var(--space-4)",
                justifyContent: "center",
              }}
            >
              <button
                id="btn-import-report"
                type="button"
                style={{
                  minHeight: "var(--control-min-height)",
                  padding: "0 var(--space-4)",
                  backgroundColor: "var(--color-paper-pure)",
                  color: "var(--color-ink)",
                  border: "1px solid var(--color-line)",
                  borderRadius: "var(--radius-control)",
                  fontSize: "var(--text-body)",
                  fontWeight: 500,
                  cursor: "pointer",
                }}
                onClick={() => reportInputRef.current?.click()}
              >
                Open saved report
              </button>
              <button
                id="btn-open-pdf"
                type="button"
                style={{
                  minHeight: "var(--control-min-height)",
                  padding: "0 var(--space-4)",
                  backgroundColor: "var(--color-paper-pure)",
                  color: "var(--color-ink)",
                  border: "1px solid var(--color-line)",
                  borderRadius: "var(--radius-control)",
                  fontSize: "var(--text-body)",
                  fontWeight: 500,
                  cursor: "pointer",
                }}
                onClick={() => pdfInputRef.current?.click()}
              >
                Open local PDF
              </button>
              <button
                id="btn-empty-load-example"
                type="button"
                style={{
                  minHeight: "var(--control-min-height)",
                  padding: "0 var(--space-4)",
                  backgroundColor: "var(--color-ink)",
                  color: "var(--color-paper-pure)",
                  border: "1px solid var(--color-line)",
                  borderRadius: "var(--radius-control)",
                  fontSize: "var(--text-body)",
                  fontWeight: 500,
                  cursor: "pointer",
                }}
                onClick={() => setExampleDoc(EXAMPLE_DOC)}
              >
                Try the example
              </button>
            </div>
          </div>
        )}
      </main>

      <ReplaceConfirmDialog
        isOpen={pendingFile !== null}
        onCancel={() => setPendingFile(null)}
        onConfirm={() => {
          const file = pendingFile;
          setPendingFile(null);
          if (file) void session.offerFile(file);
        }}
      />
    </div>
  );
};

export default Workspace;
