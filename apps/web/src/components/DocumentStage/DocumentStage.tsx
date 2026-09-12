import React, { useState, useRef, useCallback } from "react";
import styles from "./DocumentStage.module.css";

export type StageMode = "page" | "reading" | "compare";
export type StageStatus = "normal" | "loading" | "failed" | "empty";

export interface OccurrenceItem {
  id: string;
  reader: string;
  text: string;
  page: number;
  occurrenceIndex: number;
  totalOccurrences: number;
}

export interface DocumentStageProps {
  initialMode?: StageMode;
  status?: StageStatus;
  errorMessage?: string;
  pageNumber?: number;
  totalPages?: number;
  imageSrc?: string;
  imageAlt?: string;
  rawReadingText?: string;
  readerName?: string;
  findingTitle?: string;
  findingSubtitle?: string;
  detailNativeReading?: string;
  detailOcrReading?: string;
  coverageText?: string;
  occurrences?: OccurrenceItem[];
  onOccurrenceSelect?: (occurrence: OccurrenceItem) => void;
  onModeChange?: (mode: StageMode) => void;
}

const DEFAULT_OCCURRENCES: OccurrenceItem[] = [
  {
    id: "occ-1",
    reader: "PDFium 149.0.7825.0",
    text: "$1,000",
    page: 1,
    occurrenceIndex: 1,
    totalOccurrences: 1,
  },
  {
    id: "occ-2",
    reader: "Tesseract 5.5.0 (OCR)",
    text: "$100",
    page: 1,
    occurrenceIndex: 1,
    totalOccurrences: 1,
  },
];

export function DocumentStage({
  initialMode = "page",
  status = "normal",
  errorMessage,
  pageNumber = 1,
  totalPages = 1,
  imageSrc,
  imageAlt = "Visibly rendered $100 amount",
  rawReadingText = "$1,000",
  readerName = "PDFium 149.0.7825.0",
  findingTitle = "This amount reads differently",
  findingSubtitle = "Inspect the readings and their limits",
  detailNativeReading = "$1,000 (PDFium text extraction)",
  detailOcrReading = "$100 (Tesseract crop OCR)",
  coverageText = "2 checks completed · automatic alignment not checked",
  occurrences = DEFAULT_OCCURRENCES,
  onOccurrenceSelect,
  onModeChange,
}: DocumentStageProps) {
  const [mode, setMode] = useState<StageMode>(initialMode);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [rotation, setRotation] = useState<number>(0);
  const [zoom, setZoom] = useState<number>(100);
  const [activeTabIdx, setActiveTabIdx] = useState<number>(
    initialMode === "page" ? 0 : initialMode === "reading" ? 1 : 2
  );

  const stageRef = useRef<HTMLDivElement>(null);
  const tabsRef = useRef<(HTMLButtonElement | null)[]>([]);

  const modes: StageMode[] = ["page", "reading", "compare"];

  const handleModeSelect = useCallback(
    (newMode: StageMode, newIdx: number) => {
      setMode(newMode);
      setActiveTabIdx(newIdx);
      onModeChange?.(newMode);
    },
    [onModeChange]
  );

  // Keyboard navigation for tabs (roving tabindex)
  const handleTabKeyDown = (e: React.KeyboardEvent, index: number) => {
    let nextIdx = index;
    if (e.key === "ArrowRight") {
      nextIdx = (index + 1) % modes.length;
    } else if (e.key === "ArrowLeft") {
      nextIdx = (index - 1 + modes.length) % modes.length;
    } else if (e.key === "Home") {
      nextIdx = 0;
    } else if (e.key === "End") {
      nextIdx = modes.length - 1;
    } else {
      return;
    }

    e.preventDefault();
    handleModeSelect(modes[nextIdx], nextIdx);
    tabsRef.current[nextIdx]?.focus();
  };

  // Stage-focused keyboard shortcuts (F, R, +, -)
  const handleStageKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Do not intercept if focus is inside an input, textarea, or button
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }

      if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        const nextIdx = (activeTabIdx + 1) % modes.length;
        handleModeSelect(modes[nextIdx], nextIdx);
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        setRotation((prev) => (prev + 90) % 360);
      } else if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        setZoom((prev) => Math.min(prev + 25, 400));
      } else if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        setZoom((prev) => Math.max(prev - 25, 25));
      }
    },
    [activeTabIdx, handleModeSelect, modes]
  );

  const toggleFindingDetail = () => {
    setIsDetailOpen((prev) => !prev);
  };

  return (
    <div
      ref={stageRef}
      id="stage"
      className={styles.stage}
      onKeyDown={handleStageKeyDown}
      tabIndex={0}
      role="region"
      aria-label="Document examination stage"
    >
      {/* Stage Header */}
      <div className={styles.stageHeading}>
        <div className={styles.stageHeadingTitle}>
          <span className={styles.dot} aria-hidden="true" />
          <span>The amount that reads differently</span>
        </div>
        <span className={styles.badge}>SYNTHETIC</span>
      </div>

      {/* Mode bar / Toolbar */}
      <div className={styles.modebar}>
        <div
          className={styles.tabs}
          role="tablist"
          aria-label="Compare document representations"
        >
          {modes.map((m, idx) => {
            const isSelected = mode === m;
            const label =
              m === "page" ? "Page" : m === "reading" ? "Reading" : "Compare";
            return (
              <button
                key={m}
                ref={(el) => {
                  tabsRef.current[idx] = el;
                }}
                role="tab"
                id={`tab-${m}`}
                aria-selected={isSelected}
                aria-controls={status === "normal" ? "evidence-panel" : undefined}
                tabIndex={isSelected ? 0 : -1}
                className={`${styles.tab} ${isSelected ? styles.tabSelected : ""}`}
                onClick={() => handleModeSelect(m, idx)}
                onKeyDown={(e) => handleTabKeyDown(e, idx)}
                data-mode={m}
              >
                {label}
              </button>
            );
          })}
        </div>
        <span id="page-label" className={styles.pageLabel} aria-label={`Page ${pageNumber} of ${totalPages}`}>
          Page {pageNumber} / {totalPages}
          {rotation > 0 ? ` · ${rotation}°` : ""}
          {zoom !== 100 ? ` · ${zoom}%` : ""}
        </span>
      </div>

      {/* Status handling: loading, failed, empty */}
      {status === "loading" && (
        <div className={styles.stateBox} role="status" aria-live="polite">
          <span className={styles.dot} aria-hidden="true" />
          <p className={styles.stateText}>Loading document representation…</p>
        </div>
      )}

      {status === "failed" && (
        <div className={styles.stateBox} role="alert">
          <p className={`${styles.stateText} ${styles.stateErrorText}`}>
            {errorMessage || "Document stage render failed."}
          </p>
          <p className={styles.viewCaption}>
            A failed render preserves inspectable reading and status information.
          </p>
        </div>
      )}

      {status === "empty" && (
        <div className={styles.stateBox}>
          <p className={styles.stateText}>No document opened.</p>
          <p className={styles.viewCaption}>Open a local PDF to inspect its readings.</p>
        </div>
      )}

      {/* Main Evidence Panel */}
      {status === "normal" && (
        <div
          id="evidence-panel"
          className={`${styles.evidencePanel} ${mode === "compare" ? styles.compare : ""}`}
          role="tabpanel"
          aria-labelledby={`tab-${mode}`}
          tabIndex={0}
        >
          {/* Paper View (Rendered raster / crop) */}
          {(mode === "page" || mode === "compare") && (
            <div className={styles.paper} id="paper-view">
              <p className={styles.paperKicker}>SYNTHETIC EXAMPLE</p>
              <p className={styles.paperSub}>No real transaction. Reader behavior only.</p>
              <div
                className={styles.amountCrop}
                id="amount-crop"
                style={{
                  transform: `rotate(${rotation}deg) scale(${zoom / 100})`,
                  transformOrigin: "center center",
                }}
              >
                {imageSrc ? (
                  <img
                    src={imageSrc}
                    alt={imageAlt}
                    className={styles.amountImage}
                    width="240"
                    height="70"
                  />
                ) : (
                  <svg
                    width="240"
                    height="70"
                    viewBox="0 0 240 70"
                    className={styles.amountImage}
                    aria-label={imageAlt}
                    role="img"
                  >
                    <rect width="240" height="70" fill="var(--color-paper-pure, #ffffff)" />
                    <text
                      x="50%"
                      y="60%"
                      dominantBaseline="middle"
                      textAnchor="middle"
                      fontFamily="Georgia, serif"
                      fontSize="44"
                      fill="var(--color-ink, #172A2F)"
                    >
                      $100
                    </text>
                  </svg>
                )}
                <span className={`${styles.corner} ${styles.cornerA}`} aria-hidden="true" />
                <span className={`${styles.corner} ${styles.cornerB}`} aria-hidden="true" />
                <span className={`${styles.corner} ${styles.cornerC}`} aria-hidden="true" />
                <span className={`${styles.corner} ${styles.cornerD}`} aria-hidden="true" />
              </div>
              <p className={styles.paperFoot}>The picture is not the text layer.</p>
              <p className={styles.viewCaption}>Actual crop · PDFium 149.0.7825.0 render</p>
            </div>
          )}

          {/* Reading View (Extracted text) */}
          {(mode === "reading" || mode === "compare") && (
            <div className={styles.readingPaper} id="reading-view">
              <p className={styles.paperKicker}>EXTRACTED READING</p>
              <p className={styles.paperSub}>
                Reader: <bdi>{readerName}</bdi>
              </p>
              <pre className={styles.amount}>
                <bdi>{rawReadingText}</bdi>
              </pre>
              <p className={styles.readingFoot}>
                A named reader’s output. Not a verdict about the amount.
              </p>
              <p className={styles.viewCaption}>Raw output from the same PDF bytes</p>
            </div>
          )}
        </div>
      )}

      {/* Finding Banner */}
      <button
        type="button"
        id="finding-btn"
        className={styles.finding}
        onClick={toggleFindingDetail}
        aria-expanded={isDetailOpen}
        aria-controls="finding-detail"
      >
        <span className={styles.findingSymbol} aria-hidden="true">
          ≠
        </span>
        <span className={styles.findingContent}>
          <strong className={styles.findingTitle}>{findingTitle}</strong>
          <small className={styles.findingSubtitle}>{findingSubtitle}</small>
        </span>
        <span id="finding-chevron" className={styles.findingChevron} aria-hidden="true">
          {isDetailOpen ? "▲" : "▼"}
        </span>
      </button>

      {/* Finding Detail Accordion */}
      {isDetailOpen && (
        <div id="finding-detail" className={styles.detail}>
          <h2 className={styles.detailHeading}>The same glyph maps to different text.</h2>
          <p className={styles.detailDescription}>
            The example’s Unicode mapping turns the displayed “1” into the extracted
            sequence “1,0”. The unchanged rendered crop and clean twin make the difference
            inspectable.
          </p>
          <dl className={styles.detailList}>
            <div className={styles.detailRow}>
              <dt className={styles.detailLabel}>Native reading</dt>
              <dd className={styles.detailValue}>
                <bdi>{detailNativeReading}</bdi>
              </dd>
            </div>
            <div className={styles.detailRow}>
              <dt className={styles.detailLabel}>Rendered-crop OCR</dt>
              <dd className={styles.detailValue}>
                <bdi>{detailOcrReading}</bdi>
              </dd>
            </div>
            <div className={styles.detailRow}>
              <dt className={styles.detailLabel}>Alignment</dt>
              <dd className={styles.detailValue}>
                Selected crop; not an automatic browser alignment result
              </dd>
            </div>
          </dl>
          <p className={styles.limit}>
            Two readings disagree. This does not establish which is right, document safety or fraud.
          </p>
        </div>
      )}

      {/* Accessible Reading-List Sibling (usable without visual canvas) */}
      <section className={styles.readingListSection} aria-label="Available occurrences and readings">
        <h3 className={styles.readingListHeader}>Occurrences list</h3>
        <ol className={styles.readingList}>
          {occurrences.map((occ) => (
            <li key={occ.id} className={styles.readingItem}>
              <span>
                <strong>
                  <bdi>{occ.text}</bdi>
                </strong>{" "}
                (<bdi>{occ.reader}</bdi>, page {occ.page})
              </span>
              <button
                type="button"
                className={styles.occurrenceBtn}
                onClick={() => onOccurrenceSelect?.(occ)}
                aria-label={`Select occurrence ${occ.occurrenceIndex} of ${occ.totalOccurrences}: ${occ.text}`}
              >
                Occurrence {occ.occurrenceIndex} of {occ.totalOccurrences}
              </button>
            </li>
          ))}
        </ol>
      </section>

      {/* Coverage Status Footer */}
      <div className={styles.coverage}>
        <span className={styles.coverageIcon} aria-hidden="true">
          ◐
        </span>
        <span className={styles.coverageText}>{coverageText}</span>
        <button
          type="button"
          id="coverage-btn"
          className={styles.coverageButton}
          onClick={() => setIsDetailOpen((prev: boolean) => !prev)}
        >
          {isDetailOpen ? "Hide details" : "Details"}
        </button>
      </div>
    </div>
  );
}

export default DocumentStage;
