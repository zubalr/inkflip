import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import type {
  Finding,
  Occurrence,
  Reader,
  Plan,
  CheckResult,
  Page,
} from "../../../../../packages/contracts/src/index.ts";
import { FindingsList } from "./FindingsList";
import type { Annotation } from "./FindingCard";
import { CoveragePanel } from "../coverage/CoveragePanel";

const mockReaders: Reader[] = [
  {
    id: "reader-pdfium",
    name: "PDFium",
    version: "149.0.7825.0",
    build: "pdfium-wasm-v1",
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
    capabilities: [
      { name: "native_text", support: "supported", limits: [] },
      { name: "alignment", support: "supported", limits: [] },
    ],
    model_hashes: [],
    limitations: [],
  },
  {
    id: "reader-pypdf",
    name: "pypdf",
    version: "6.18.0",
    build: "pypdf-core",
    adapter_version: "1.0.0",
    method: "native_text",
    environment: "native",
    settings: {
      normalization: "scalar-whitespace-v1",
      language: null,
      psm: null,
      render_reader_id: null,
      raster_dpi: null,
      annotation_mode: "none",
    },
    capabilities: [
      { name: "native_text", support: "supported", limits: [] },
      { name: "alignment", support: "supported", limits: [] },
    ],
    model_hashes: [],
    limitations: [],
  },
  {
    id: "reader-tesseract",
    name: "Tesseract OCR",
    version: "5.3.3",
    build: "tesseract-wasm",
    adapter_version: "1.0.0",
    method: "ocr",
    environment: "browser",
    settings: {
      normalization: "scalar-whitespace-v1",
      language: "eng",
      psm: 6,
      render_reader_id: "reader-pdfium",
      raster_dpi: 150,
      annotation_mode: "none",
    },
    capabilities: [{ name: "ocr", support: "supported", limits: [] }],
    model_hashes: ["sha256:eng.traineddata.v1"],
    limitations: [],
  },
];

const mockOccurrences: Occurrence[] = [
  {
    id: "occ-1",
    reader_id: "reader-pdfium",
    page_index: 0,
    ordinal: 1,
    raw_text: "$1,000.00",
    normalized_text: "$1,000.00",
    normalization_map: [
      { raw_start: 0, raw_end: 9, normalized_start: 0, normalized_end: 9, operation: "identity" },
    ],
    geometry: {
      precision: "exact",
      space: "canonical_page",
      polygon: [
        [100, 200],
        [180, 200],
        [180, 220],
        [100, 220],
      ],
      transform_ids: [],
      basis: "pdfium_extract_text_box",
    },
    engine_score: null,
    source_asset_id: null,
    raw_source_locator: "p0:ch0-8",
    limitations: [],
  },
  {
    id: "occ-2",
    reader_id: "reader-pypdf",
    page_index: 0,
    ordinal: 1,
    raw_text: "$10,000.00",
    normalized_text: "$10,000.00",
    normalization_map: [
      { raw_start: 0, raw_end: 10, normalized_start: 0, normalized_end: 10, operation: "identity" },
    ],
    geometry: {
      precision: "exact",
      space: "canonical_page",
      polygon: [
        [100, 200],
        [185, 200],
        [185, 220],
        [100, 220],
      ],
      transform_ids: [],
      basis: "pypdf_extract_text_box",
    },
    engine_score: null,
    source_asset_id: null,
    raw_source_locator: "p0:block0",
    limitations: [],
  },
  {
    id: "occ-3",
    reader_id: "reader-pdfium",
    page_index: 0,
    ordinal: 2,
    raw_text: "Invoice Terms",
    normalized_text: "Invoice Terms",
    normalization_map: [
      { raw_start: 0, raw_end: 13, normalized_start: 0, normalized_end: 13, operation: "identity" },
    ],
    geometry: {
      precision: "exact",
      space: "canonical_page",
      polygon: [
        [100, 250],
        [200, 250],
        [200, 270],
        [100, 270],
      ],
      transform_ids: [],
      basis: "pdfium_extract_text_box",
    },
    engine_score: null,
    source_asset_id: null,
    raw_source_locator: "p0:ch10-22",
    limitations: [],
  },
  {
    id: "occ-4",
    reader_id: "reader-pypdf",
    page_index: 0,
    ordinal: 2,
    raw_text: "Invoice Term",
    normalized_text: "Invoice Term",
    normalization_map: [
      { raw_start: 0, raw_end: 12, normalized_start: 0, normalized_end: 12, operation: "identity" },
    ],
    geometry: {
      precision: "exact",
      space: "canonical_page",
      polygon: [
        [100, 250],
        [195, 250],
        [195, 270],
        [100, 270],
      ],
      transform_ids: [],
      basis: "pypdf_extract_text_box",
    },
    engine_score: null,
    source_asset_id: null,
    raw_source_locator: "p0:block1",
    limitations: [],
  },
];

const mockPages: Page[] = [
  {
    index: 0,
    media_box: [0, 0, 612, 792],
    crop_box: [0, 0, 612, 792],
    effective_view_box: [0, 0, 612, 792],
    box_source: "media_box",
    user_unit: 1.0,
    rotation: 0,
    canonical_size_pt: [612, 792],
    raw_to_canonical_transform_id: "tx-p0",
    limitations: [],
  },
];

const mockPlan: Plan = {
  version: "1.0.0",
  selected_pages: [0],
  regions: [],
  checks: [
    {
      id: "chk-p0-native",
      page_index: 0,
      reader_ids: ["reader-pdfium", "reader-pypdf"],
      capability: "native_text",
      region_id: null,
    },
    {
      id: "chk-p0-ocr",
      page_index: 0,
      reader_ids: ["reader-tesseract"],
      capability: "ocr",
      region_id: null,
    },
  ],
  normalization_version: "scalar-whitespace-v1",
  alignment_version: "region-match-v1",
  profile: "desktop",
  budget: {
    max_raster_pixels: 4000000,
    max_run_ocr_pixels: 4000000,
    timeout_ms: 10000,
    max_retries: 2,
  },
};

const mockFindings: Finding[] = [
  {
    id: "f-amount-1",
    kind: "reading_difference",
    title: "This amount reads differently",
    explanation: "PDFium returned “$1,000.00”. pypdf returned “$10,000.00”.",
    page_index: 0,
    occurrence_ids: ["occ-1", "occ-2"],
    check_ids: ["chk-p0-native"],
    alignment: "unique",
    region_id: "region-total",
    priority: "material_token",
    basis: "Exact coordinate alignment over overlapping tokens.",
    limitations: [
      "A difference does not establish which reading is correct.",
      "OCR verification was not run on this page.",
    ],
  },
  {
    id: "f-text-2",
    kind: "reading_difference",
    title: "These readings differ here",
    explanation: "PDFium returned “Invoice Terms”. pypdf returned “Invoice Term”.",
    page_index: 0,
    occurrence_ids: ["occ-3", "occ-4"],
    check_ids: ["chk-p0-native"],
    alignment: "unique",
    region_id: "region-header",
    priority: "ordinary",
    basis: "Exact coordinate alignment over overlapping tokens.",
    limitations: ["A difference does not establish which reading is correct."],
  },
];

function FindingsHarness() {
  const params = new URLSearchParams(window.location.search);
  const scenario = params.get("scenario") || "default";

  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [keptFindingIds, setKeptFindingIds] = useState<string[]>([]);
  const [annotations, setAnnotations] = useState<Annotation[]>([
    {
      id: "note-1",
      finding_id: "f-amount-1",
      page_index: 0,
      text: "Verified manual ledger entry matches PDFium amount.",
      author_label: "Reviewer Audit",
      origin: "human_entered",
    },
  ]);

  const handleAddNote = (findingId: string, text: string) => {
    setAnnotations((prev) => [
      ...prev,
      {
        id: `note-${Date.now()}`,
        finding_id: findingId,
        page_index: 0,
        text,
        author_label: "Local Reviewer",
        origin: "human_entered",
      },
    ]);
  };

  let findings: Finding[] = [];
  let checks: CheckResult[] = [];
  let hasInvisibleTextScan = false;
  let ocrRun = true;

  if (scenario === "normal-scan" || scenario === "default") {
    findings = mockFindings;
    hasInvisibleTextScan = true;
    ocrRun = true;
    checks = [
      {
        id: "chk-p0-native",
        status: "completed",
        reason: null,
        produced_occurrence_count: 4,
        retained_occurrence_ids: ["occ-1", "occ-2", "occ-3", "occ-4"],
      },
      {
        id: "chk-p0-ocr",
        status: "completed",
        reason: null,
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
    ];
  } else if (scenario === "incomplete-statuses") {
    findings = mockFindings;
    checks = [
      {
        id: "chk-1",
        status: "completed",
        reason: null,
        produced_occurrence_count: 2,
        retained_occurrence_ids: ["occ-1", "occ-2"],
      },
      {
        id: "chk-2",
        status: "timeout",
        reason: "Page 0 timed out after 10000ms",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
      {
        id: "chk-3",
        status: "failed",
        reason: "Tesseract OCR could not start due to missing traineddata model",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
      {
        id: "chk-4",
        status: "unsupported",
        reason: "Reader does not support font metrics inspection",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
    ];
  } else if (scenario === "all-terminal-statuses") {
    findings = mockFindings;
    checks = [
      {
        id: "chk-completed",
        status: "completed",
        reason: null,
        produced_occurrence_count: 2,
        retained_occurrence_ids: ["occ-1", "occ-2"],
      },
      {
        id: "chk-timeout",
        status: "timeout",
        reason: "Page 0 timed out after 10000ms",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
      {
        id: "chk-model-missing",
        status: "failed",
        reason: "Tesseract OCR could not start due to missing traineddata model",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
      {
        id: "chk-unsupported",
        status: "unsupported",
        reason: "Reader does not support font metrics inspection",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
      {
        id: "chk-failed",
        status: "failed",
        reason: "Decoder crashed with syntax error",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
      {
        id: "chk-cancelled",
        status: "cancelled",
        reason: "Execution cancelled by user",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
      {
        id: "chk-skipped",
        status: "skipped",
        reason: "Feature flag disabled",
        produced_occurrence_count: 0,
        retained_occurrence_ids: [],
      },
    ];
  } else if (scenario === "zero-findings") {
    findings = [];
    checks = [
      {
        id: "chk-p0-native",
        status: "completed",
        reason: null,
        produced_occurrence_count: 4,
        retained_occurrence_ids: ["occ-1", "occ-2", "occ-3", "occ-4"],
      },
    ];
  } else if (scenario === "amount-diff") {
    findings = [
      {
        id: "f-ordinary-1",
        kind: "reading_difference",
        title: "These readings differ here",
        explanation: "PDFium returned “Invoice Terms”. pypdf returned “Invoice Term”.",
        page_index: 0,
        occurrence_ids: ["occ-3", "occ-4"],
        check_ids: ["chk-p0-native"],
        alignment: "unique",
        region_id: "region-header",
        priority: "ordinary",
        basis: "Exact coordinate alignment over overlapping tokens.",
        limitations: [],
      },
      {
        id: "f-amount-1",
        kind: "reading_difference",
        title: "This amount reads differently",
        explanation: "PDFium returned “$1,000.00”. pypdf returned “$10,000.00”.",
        page_index: 0,
        occurrence_ids: ["occ-1", "occ-2"],
        check_ids: ["chk-p0-native"],
        alignment: "unique",
        region_id: "region-total",
        priority: "material_token",
        basis: "Exact coordinate alignment over overlapping tokens.",
        limitations: [],
      },
      {
        id: "f-info-1",
        kind: "observed_structure",
        title: "A supported structural check found this property",
        explanation: "Font metadata contains non-standard identity encoding.",
        page_index: 0,
        occurrence_ids: [],
        check_ids: ["chk-p0-native"],
        alignment: "page_level",
        region_id: null,
        priority: "informational",
        basis: "Font dictionary parsing.",
        limitations: [],
      },
    ];
    checks = [
      {
        id: "chk-p0-native",
        status: "completed",
        reason: null,
        produced_occurrence_count: 4,
        retained_occurrence_ids: ["occ-1", "occ-2", "occ-3", "occ-4"],
      },
    ];
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--color-canvas)",
        color: "var(--color-ink)",
        padding: "var(--space-6)",
      }}
    >
      <main style={{ maxWidth: "var(--layout-max)", margin: "0 auto" }}>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "var(--space-6)",
            marginBottom: "var(--space-4)",
          }}
        >
          Inkflip Findings &amp; Coverage
        </h1>

        <CoveragePanel
          plan={mockPlan}
          checks={checks}
          pages={mockPages}
          ocrRun={ocrRun}
          hasInvisibleTextScan={hasInvisibleTextScan}
          findingsCount={findings.length}
        />

        <div style={{ marginTop: "var(--space-6)" }}>
          <FindingsList
            findings={findings}
            occurrences={mockOccurrences}
            readers={mockReaders}
            annotations={annotations}
            selectedFindingId={selectedFindingId}
            onSelectFinding={(f) => setSelectedFindingId(f.id)}
            onKeepEvidence={(f) => setKeptFindingIds((prev) => [...prev, f.id])}
            onAddNote={handleAddNote}
          />
        </div>

        {keptFindingIds.length > 0 && (
          <div
            id="kept-evidence-status"
            style={{ marginTop: "var(--space-4)", fontSize: "var(--font-size-sm)" }}
          >
            Kept evidence count: {keptFindingIds.length}
          </div>
        )}
      </main>
    </div>
  );
}

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(<FindingsHarness />);
}
