import React, { useCallback, useRef, useState } from "react";
import { ViewerStage } from "../features/viewer/ViewerStage";
import type { ViewerDoc } from "../features/viewer/types";
import { FileDrop, type OpenPhase } from "../features/open/FileDrop";
import { validateCandidate, resolveProfile } from "../features/open";
import type { FileCandidate } from "../features/open/types";
import styles from "./Workspace.module.css";

export interface WorkspaceProps {
  onNavigateHome: () => void;
  initialWithExample?: boolean;
  initialDoc?: ViewerDoc | null;
  onImportReport?: (doc: ViewerDoc) => void;
  onOpenFile?: (file: File) => void;
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
    // Duplicate occurrence 1 on page 0
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
    // Duplicate occurrence 2 on page 0 (different coordinate!)
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
    // Pypdf counterpart for occurrence 1
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
    // Page 1 occurrence
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
    // Page-level unknown geometry occurrence on page 1
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

export const Workspace: React.FC<WorkspaceProps> = ({
  onNavigateHome,
  initialWithExample = true,
  initialDoc,
  onImportReport,
  onOpenFile,
}) => {
  const [doc, setDoc] = useState<ViewerDoc | null>(
    initialDoc !== undefined ? initialDoc : initialWithExample ? EXAMPLE_DOC : null,
  );
  const [docTitle, setDocTitle] = useState<string>(
    initialDoc !== undefined
      ? "Imported Report"
      : initialWithExample
        ? "Invoice-Example.pdf"
        : "Workspace",
  );
  const [openPhase, setOpenPhase] = useState<OpenPhase>("idle");
  const [importError, setImportError] = useState<string | null>(null);
  const [pdfNotice, setPdfNotice] = useState<string | null>(null);

  const reportInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);

  const handleImportReportText = useCallback(
    (text: string, fallbackName: string) => {
      try {
        const data = JSON.parse(text);
        if (!data || typeof data !== "object") {
          setImportError("Invalid report JSON: Expected JSON object.");
          setDoc(null);
          return;
        }
        if (!Array.isArray(data.pages) || data.pages.length === 0) {
          setImportError("Invalid report JSON: report must contain at least one page.");
          setDoc(null);
          return;
        }
        if (!Array.isArray(data.findings)) {
          setImportError("Invalid report JSON: missing required findings array.");
          setDoc(null);
          return;
        }
        for (const p of data.pages) {
          if (!p || typeof p.index !== "number" || !Array.isArray(p.canonical_size_pt)) {
            setImportError("Invalid report JSON: malformed page structure in report.");
            setDoc(null);
            return;
          }
        }
        if (Array.isArray(data.occurrences)) {
          for (const occ of data.occurrences) {
            if (
              !occ ||
              typeof occ.page_index !== "number" ||
              !occ.geometry ||
              !Array.isArray(occ.geometry.polygon)
            ) {
              setImportError(
                "Invalid report JSON: occurrence missing required geometry or page_index.",
              );
              setDoc(null);
              return;
            }
          }
        }
        for (const f of data.findings) {
          if (!f || typeof f.id !== "string" || !Array.isArray(f.occurrence_ids)) {
            setImportError("Invalid report JSON: malformed finding structure in report.");
            setDoc(null);
            return;
          }
        }

        const importedDoc: ViewerDoc = {
          pages: data.pages,
          readers: Array.isArray(data.readers) ? data.readers : [],
          occurrences: Array.isArray(data.occurrences) ? data.occurrences : [],
          findings: data.findings,
        };
        setDoc(importedDoc);
        setDocTitle(data.document?.display_name || fallbackName);
        setImportError(null);
        setPdfNotice(null);
        onImportReport?.(importedDoc);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Invalid JSON";
        setImportError(`Could not parse report file: ${msg}`);
        setDoc(null);
      }
    },
    [onImportReport],
  );

  const handleReportFileChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      event.target.value = "";
      const text = await file.text();
      handleImportReportText(text, file.name);
    },
    [handleImportReportText],
  );

  const handlePdfCandidate = useCallback(
    async (file: FileCandidate) => {
      setOpenPhase("validating");
      try {
        const profile = resolveProfile();
        const err = await validateCandidate(file, profile);
        if (err) {
          setImportError(err.message);
          setDoc(null);
          setPdfNotice(null);
          return;
        }
        // Valid PDF: do NOT fabricate canned findings!
        setDoc(null);
        setImportError(null);
        setPdfNotice(
          `PDF received: ${file.name}. In-browser inspection pipeline is unavailable in this viewer build. Open an exported report (.inkflip.json) to inspect findings.`,
        );
        if (onOpenFile && file instanceof File) {
          onOpenFile(file);
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Validation error";
        setImportError(`Failed to validate PDF: ${msg}`);
        setDoc(null);
        setPdfNotice(null);
      } finally {
        setOpenPhase("idle");
      }
    },
    [onOpenFile],
  );

  const handlePdfFileChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      event.target.value = "";
      await handlePdfCandidate(file);
    },
    [handlePdfCandidate],
  );

  const handleFileCandidate = useCallback(
    async (candidate: FileCandidate) => {
      const isJson =
        candidate.name.endsWith(".json") ||
        candidate.name.endsWith(".inkflip.json") ||
        candidate.type === "application/json";

      if (isJson) {
        setOpenPhase("validating");
        try {
          const buf = await candidate.arrayBuffer();
          const text = new TextDecoder().decode(buf);
          handleImportReportText(text, candidate.name);
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : "Read failure";
          setImportError(`Failed to read report file: ${msg}`);
          setDoc(null);
        } finally {
          setOpenPhase("idle");
        }
        return;
      }

      // Handle PDF candidate with strict validation
      await handlePdfCandidate(candidate);
    },
    [handleImportReportText, handlePdfCandidate],
  );

  return (
    <div className={styles.workspace}>
      <input
        ref={reportInputRef}
        id="input-import-report"
        type="file"
        accept="application/json,.json,.inkflip.json"
        style={{ display: "none" }}
        onChange={handleReportFileChange}
      />
      <input
        ref={pdfInputRef}
        id="input-open-pdf"
        type="file"
        accept="application/pdf,.pdf"
        style={{ display: "none" }}
        onChange={handlePdfFileChange}
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
          <span className={styles.documentTitle}>{doc ? docTitle : "Workspace"}</span>
          <span className={styles.documentMeta}>
            {doc
              ? `${doc.pages.length} pages · ${doc.findings.length} findings`
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
          {doc ? (
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
              onClick={() => {
                setDoc(null);
                setDocTitle("Workspace");
                setImportError(null);
                setPdfNotice(null);
              }}
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
              onClick={() => {
                setDoc(EXAMPLE_DOC);
                setDocTitle("Invoice-Example.pdf");
                setImportError(null);
                setPdfNotice(null);
              }}
            >
              Load Example
            </button>
          )}
        </div>
      </header>

      <main className={styles.workspaceMain}>
        {doc ? (
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
            <ViewerStage doc={doc} />
          </ViewerErrorBoundary>
        ) : (
          <div className={styles.emptyWorkspace}>
            <FileDrop phase={openPhase} onFile={handleFileCandidate} hasDocument={false} />
            {importError && (
              <div
                id="import-error"
                role="alert"
                style={{
                  marginTop: "var(--space-3)",
                  padding: "var(--space-2) var(--space-4)",
                  backgroundColor: "var(--color-surface-muted)",
                  border: "1px solid var(--color-line)",
                  borderRadius: "var(--radius-control)",
                  color: "var(--color-ink)",
                  fontSize: "var(--text-caption)",
                }}
              >
                {importError}
              </div>
            )}
            {pdfNotice && (
              <div
                id="pdf-received-notice"
                role="status"
                style={{
                  marginTop: "var(--space-3)",
                  padding: "var(--space-2) var(--space-4)",
                  backgroundColor: "var(--color-surface-subtle)",
                  border: "1px solid var(--color-line)",
                  borderRadius: "var(--radius-control)",
                  color: "var(--color-ink)",
                  fontSize: "var(--text-caption)",
                }}
              >
                {pdfNotice}
              </div>
            )}
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
                  border: "1px solid var(--color-ink)",
                  borderRadius: "var(--radius-control)",
                  fontSize: "var(--text-body)",
                  fontWeight: 500,
                  cursor: "pointer",
                }}
                onClick={() => {
                  setDoc(EXAMPLE_DOC);
                  setDocTitle("Invoice-Example.pdf");
                  setImportError(null);
                  setPdfNotice(null);
                }}
              >
                Try the example
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default Workspace;
