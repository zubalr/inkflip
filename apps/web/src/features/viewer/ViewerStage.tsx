import React, { useState, useRef, useCallback, useEffect } from "react";
import type {
  Page,
  Occurrence,
  Reader,
  Finding,
  Annotation,
} from "../../../../../packages/contracts/src/index.ts";
import type { ViewerMode, RotationDegree, ViewerDoc } from "./types";
import { CanvasOverlay } from "./CanvasOverlay";
import { ComparePanes } from "./ComparePanes";
import { AccessibleTextLayer } from "./AccessibleTextLayer";
import { AlignmentDetail } from "../findings/alignment/AlignmentDetail";
import { isOrderOnlyFinding } from "../findings/alignment/classify.ts";
import { FindingNotes } from "../annotations/FindingNotes.tsx";
import styles from "./ViewerStage.module.css";

export interface ViewerStageProps {
  doc: ViewerDoc;
  initialFindingId?: string | null;
  initialMode?: ViewerMode;
  initialZoom?: number;
  initialRotation?: RotationDegree;
  onKeepEvidence?: (finding: Finding) => void;
  /** User-authored notes on the open report (T23); rendered per finding. */
  annotations?: readonly Annotation[];
  onAddAnnotation?: (annotation: Annotation) => void;
  onRemoveAnnotation?: (annotationId: string) => void;
}

export const ViewerStage: React.FC<ViewerStageProps> = ({
  doc,
  initialFindingId = null,
  initialMode = "page",
  initialZoom = 100,
  initialRotation = 0,
  onKeepEvidence,
  annotations,
  onAddAnnotation,
  onRemoveAnnotation,
}) => {
  const [mode, setMode] = useState<ViewerMode>(initialMode);
  const [pageIndex, setPageIndex] = useState<number>(0);
  const [zoom, setZoom] = useState<number>(initialZoom);
  const [rotation, setRotation] = useState<RotationDegree>(initialRotation);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(initialFindingId);
  const [selectedOccurrenceId, setSelectedOccurrenceId] = useState<string | null>(null);
  const [shortcutsEnabled, setShortcutsEnabled] = useState<boolean>(true);

  const stageRef = useRef<HTMLDivElement>(null);

  const clampedPageIndex = Math.max(0, Math.min(pageIndex, Math.max(0, doc.pages.length - 1)));
  const currentPage: Page = doc.pages[clampedPageIndex] || doc.pages[0];

  const pageOccurrences = doc.occurrences.filter((o) => o.page_index === pageIndex);
  const selectedFinding = doc.findings.find((f) => f.id === selectedFindingId) || null;

  // Reader mapping
  const leftReader: Reader = doc.readers[0] || {
    id: "reader-default",
    name: "Default Reader",
    version: "1.0.0",
    build: "v1",
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
  };

  const rightReader: Reader = doc.readers[1] || doc.readers[0] || leftReader;

  const leftOccurrences = pageOccurrences.filter((o) => o.reader_id === leftReader.id);
  const rightOccurrences = pageOccurrences.filter((o) => o.reader_id === rightReader.id);

  // Finding selection handler
  const handleSelectFinding = useCallback(
    (finding: Finding) => {
      setSelectedFindingId(finding.id);
      if (finding.page_index !== undefined && finding.page_index !== pageIndex) {
        setPageIndex(finding.page_index);
      }
      if (
        finding.occurrence_ids &&
        finding.occurrence_ids.length > 0 &&
        finding.alignment !== "ambiguous" &&
        !isOrderOnlyFinding(finding)
      ) {
        setSelectedOccurrenceId(finding.occurrence_ids[0]);
      } else {
        // Ambiguous and order-only findings keep every candidate equally
        // marked; no single occurrence is pre-picked — never
        // first-match-wins.
        setSelectedOccurrenceId(null);
      }
    },
    [pageIndex],
  );

  const handleSelectOccurrence = useCallback(
    (occ: Occurrence) => {
      setSelectedOccurrenceId(occ.id);
      if (occ.page_index !== pageIndex) {
        setPageIndex(occ.page_index);
      }
    },
    [pageIndex],
  );

  // Next / Previous finding
  const handleNextFinding = useCallback(() => {
    if (doc.findings.length === 0) return;
    const currentIdx = doc.findings.findIndex((f) => f.id === selectedFindingId);
    const nextIdx = (currentIdx + 1) % doc.findings.length;
    handleSelectFinding(doc.findings[nextIdx]);
  }, [doc.findings, selectedFindingId, handleSelectFinding]);

  const handlePrevFinding = useCallback(() => {
    if (doc.findings.length === 0) return;
    const currentIdx = doc.findings.findIndex((f) => f.id === selectedFindingId);
    const prevIdx = (currentIdx - 1 + doc.findings.length) % doc.findings.length;
    handleSelectFinding(doc.findings[prevIdx]);
  }, [doc.findings, selectedFindingId, handleSelectFinding]);

  // Stage Keyboard Shortcuts
  const handleStageKeyDown = (e: React.KeyboardEvent) => {
    if (!shortcutsEnabled) return;
    const target = e.target as HTMLElement;
    if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) {
      return;
    }

    if (e.key === "f" || e.key === "F") {
      e.preventDefault();
      setMode((prev) => (prev === "page" ? "reading" : prev === "reading" ? "compare" : "page"));
    } else if (e.key === "r" || e.key === "R") {
      e.preventDefault();
      setRotation((prev) => ((prev + 90) % 360) as RotationDegree);
    } else if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      setZoom((prev) => Math.min(prev + 25, 400));
    } else if (e.key === "-" || e.key === "_") {
      e.preventDefault();
      setZoom((prev) => Math.max(prev - 25, 25));
    } else if (e.key === "n" || e.key === "N") {
      e.preventDefault();
      handleNextFinding();
    } else if (e.key === "p" || e.key === "P") {
      e.preventDefault();
      handlePrevFinding();
    }
  };

  useEffect(() => {
    if (initialFindingId) {
      const found = doc.findings.find((f) => f.id === initialFindingId);
      if (found) {
        handleSelectFinding(found);
      }
    }
  }, [initialFindingId, doc.findings, handleSelectFinding]);

  return (
    <div
      ref={stageRef}
      id="viewer-stage"
      data-testid="viewer-stage"
      className={styles.stage}
      tabIndex={0}
      onKeyDown={handleStageKeyDown}
      role="region"
      aria-label="PDF reading inspector viewer stage"
    >
      {/* 48px Stage Toolbar */}
      <header className={styles.toolbar} role="toolbar" aria-label="Viewer controls">
        <div className={styles.toolbarGroup}>
          <div
            id="view-mode-tabs"
            className={styles.modeTabs}
            role="tablist"
            aria-label="View representation mode"
          >
            {(["page", "reading", "compare"] as const).map((m) => {
              const isSelected = mode === m;
              return (
                <button
                  key={m}
                  id={`tab-mode-${m}`}
                  role="tab"
                  aria-selected={isSelected}
                  tabIndex={isSelected ? 0 : -1}
                  className={`${styles.modeTab} ${isSelected ? styles.modeTabSelected : ""}`}
                  onClick={() => setMode(m)}
                  onKeyDown={(e) => {
                    // Roving-tabindex tabs also need arrow-key movement:
                    // without it the unselected tabs can never receive
                    // keyboard focus (automatic activation follows focus).
                    const order = ["page", "reading", "compare"] as const;
                    const idx = order.indexOf(m);
                    let next: number | null = null;
                    if (e.key === "ArrowRight") next = (idx + 1) % order.length;
                    else if (e.key === "ArrowLeft") next = (idx - 1 + order.length) % order.length;
                    else if (e.key === "Home") next = 0;
                    else if (e.key === "End") next = order.length - 1;
                    if (next === null) return;
                    e.preventDefault();
                    setMode(order[next]);
                    document.getElementById(`tab-mode-${order[next]}`)?.focus();
                  }}
                >
                  {m === "page" ? "Page" : m === "reading" ? "Reading" : "Compare"}
                </button>
              );
            })}
          </div>

          <div className={styles.toolbarGroup}>
            <button
              id="btn-zoom-out"
              type="button"
              className={styles.toolButton}
              onClick={() => setZoom((prev) => Math.max(prev - 25, 25))}
              aria-label="Zoom out"
            >
              −
            </button>
            <span id="label-zoom" className={styles.zoomLabel}>
              {zoom}%
            </span>
            <button
              id="btn-zoom-in"
              type="button"
              className={styles.toolButton}
              onClick={() => setZoom((prev) => Math.min(prev + 25, 400))}
              aria-label="Zoom in"
            >
              +
            </button>
            <button
              id="btn-zoom-fit"
              type="button"
              className={styles.toolButton}
              onClick={() => setZoom(100)}
            >
              Fit
            </button>
            <button
              id="btn-rotate"
              type="button"
              className={styles.toolButton}
              onClick={() => setRotation((prev) => ((prev + 90) % 360) as RotationDegree)}
              aria-label={`Rotate 90 degrees (currently ${rotation}°)`}
            >
              Rotate ({rotation}°)
            </button>
          </div>
        </div>

        <div className={styles.toolbarGroup}>
          <button
            id="btn-toggle-shortcuts"
            type="button"
            className={styles.toolButton}
            onClick={() => setShortcutsEnabled((prev) => !prev)}
            aria-pressed={shortcutsEnabled}
          >
            {shortcutsEnabled ? "Shortcuts: On" : "Shortcuts: Off"}
          </button>
        </div>
      </header>

      {/* Main Workspace Layout */}
      <div className={styles.workspaceGrid}>
        {/* Paper / Canvas / Compare Area */}
        <div id="viewer-paper-area" className={styles.stagePaperArea}>
          {mode === "compare" ? (
            <ComparePanes
              page={currentPage}
              leftReader={leftReader}
              rightReader={rightReader}
              leftOccurrences={leftOccurrences}
              rightOccurrences={rightOccurrences}
              selectedOccurrenceId={selectedOccurrenceId}
              selectedFinding={selectedFinding}
              zoom={zoom}
              rotation={rotation}
              onSelectOccurrence={handleSelectOccurrence}
            />
          ) : (
            <CanvasOverlay
              page={currentPage}
              occurrences={pageOccurrences}
              selectedOccurrenceId={selectedOccurrenceId}
              selectedFinding={selectedFinding}
              zoom={zoom}
              rotation={rotation}
              onSelectOccurrence={handleSelectOccurrence}
              renderCanvas={mode === "page"}
            />
          )}

          {/* Accessible Text Equivalent & Limits */}
          <AccessibleTextLayer
            pageIndex={pageIndex}
            occurrences={pageOccurrences}
            readers={doc.readers}
            selectedOccurrenceId={selectedOccurrenceId}
            onSelectOccurrence={handleSelectOccurrence}
            limitations={currentPage.limitations}
          />
        </div>

        {/* 360px Evidence Slip */}
        <aside
          id="evidence-slip"
          className={styles.evidenceSlip}
          aria-labelledby="evidence-slip-heading"
        >
          <h2 id="evidence-slip-heading" className={styles.evidenceHeading}>
            Evidence Slip
          </h2>

          <div className={styles.findingNav}>
            <button
              id="btn-prev-finding"
              type="button"
              className={styles.toolButton}
              onClick={handlePrevFinding}
              disabled={doc.findings.length <= 1}
              aria-label="Previous finding"
            >
              ← Prev
            </button>
            <span id="findings-counter" style={{ fontSize: "var(--text-caption)" }}>
              {doc.findings.length > 0
                ? selectedFindingId
                  ? `${doc.findings.findIndex((f) => f.id === selectedFindingId) + 1} of ${doc.findings.length}`
                  : `0 of ${doc.findings.length}`
                : "0 findings"}
            </span>
            <button
              id="btn-next-finding"
              type="button"
              className={styles.toolButton}
              onClick={handleNextFinding}
              disabled={doc.findings.length <= 1}
              aria-label="Next finding"
            >
              Next →
            </button>
          </div>

          {/* List of findings */}
          <div id="findings-nav-list" role="list" aria-label="Discovered findings">
            {doc.findings.map((f) => {
              const isSelected = f.id === selectedFindingId;
              return (
                <div
                  key={f.id}
                  role="listitem"
                  className={`${styles.findingCard} ${isSelected ? styles.findingCardSelected : ""}`}
                  style={{
                    marginBottom: "var(--space-3)",
                    cursor: "pointer",
                    backgroundColor: isSelected ? "var(--color-paper-pure)" : undefined,
                  }}
                  onClick={() => handleSelectFinding(f)}
                >
                  <h3 className={styles.findingTitle} style={{ marginBottom: 0 }}>
                    <button
                      type="button"
                      id={`finding-item-${f.id}`}
                      className={styles.findingToggle}
                      aria-expanded={isSelected}
                      aria-current={isSelected}
                    >
                      <span className={styles.findingToggleTitle}>{f.title}</span>
                      <span className={styles.findingMeta}>
                        <span>Page {f.page_index + 1}</span> ·{" "}
                        <span data-priority={f.priority}>
                          {f.priority === "material_token"
                            ? "Material difference"
                            : f.priority === "informational"
                              ? "Informational"
                              : "Ordinary"}
                        </span>
                        {f.alignment === "ambiguous" && <span> · Ambiguous</span>}
                        {f.alignment === "page_level" && <span> · Page-level</span>}
                      </span>
                      <span className={styles.findingExplanation}>{f.explanation}</span>
                    </button>
                  </h3>

                  {isSelected && (
                    <AlignmentDetail
                      finding={f}
                      occurrences={doc.occurrences}
                      readers={doc.readers}
                      selectedOccurrenceId={selectedOccurrenceId}
                      onSelectOccurrence={handleSelectOccurrence}
                      returnFocusId={`finding-item-${f.id}`}
                    />
                  )}

                  {isSelected && onAddAnnotation && onRemoveAnnotation && (
                    <FindingNotes
                      finding={f}
                      notes={annotations ?? []}
                      onAdd={onAddAnnotation}
                      onRemove={onRemoveAnnotation}
                    />
                  )}

                  {isSelected && onKeepEvidence && (
                    <button
                      id="btn-keep-evidence"
                      type="button"
                      className={styles.toolButton}
                      style={{ marginTop: "var(--space-2)", width: "100%" }}
                      onClick={(e) => {
                        e.stopPropagation();
                        onKeepEvidence(f);
                      }}
                    >
                      Keep this evidence
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </aside>
      </div>
    </div>
  );
};

export default ViewerStage;
