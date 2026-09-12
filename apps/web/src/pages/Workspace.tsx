import React, { useState } from "react";
import { ViewerStage } from "../features/viewer/ViewerStage";
import type { ViewerDoc } from "../features/viewer/types";
import styles from "./Workspace.module.css";

export interface WorkspaceProps {
  onNavigateHome: () => void;
  initialWithExample?: boolean;
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

export const Workspace: React.FC<WorkspaceProps> = ({
  onNavigateHome,
  initialWithExample = true,
}) => {
  const [doc, setDoc] = useState<ViewerDoc | null>(initialWithExample ? EXAMPLE_DOC : null);

  return (
    <div className={styles.workspace}>
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
          <span className={styles.documentTitle}>{doc ? "Invoice-Example.pdf" : "Workspace"}</span>
          <span className={styles.documentMeta}>
            {doc
              ? `${doc.pages.length} pages · ${doc.findings.length} findings`
              : "No document loaded"}
          </span>
        </div>

        <div>
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
              onClick={() => setDoc(null)}
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
              onClick={() => setDoc(EXAMPLE_DOC)}
            >
              Load Example
            </button>
          )}
        </div>
      </header>

      <main className={styles.workspaceMain}>
        {doc ? (
          <ViewerStage doc={doc} />
        ) : (
          <div className={styles.emptyWorkspace}>
            <h2 className={styles.emptyTitle}>Open a PDF to Inspect</h2>
            <p className={styles.emptyText}>
              Drop a PDF file here or load the prepared example to compare multiple independent
              reader extractions.
            </p>
            <button
              id="btn-empty-load-example"
              type="button"
              style={{
                minHeight: "var(--control-min-height)",
                padding: "0 var(--space-5)",
                backgroundColor: "var(--color-ink)",
                color: "var(--color-paper-pure)",
                border: "1px solid var(--color-ink)",
                borderRadius: "var(--radius-control)",
                fontSize: "var(--text-body)",
                fontWeight: 500,
                cursor: "pointer",
              }}
              onClick={() => setDoc(EXAMPLE_DOC)}
            >
              Try the example
            </button>
          </div>
        )}
      </main>
    </div>
  );
};

export default Workspace;
