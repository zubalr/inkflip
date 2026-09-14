import React, { useState, useRef, useCallback, useEffect, useMemo } from "react";
import type {
  Page,
  Occurrence,
  Reader,
  Finding,
  Annotation,
} from "../../../../../packages/contracts/src/index.ts";
import type {
  PageRasterView,
  RenderPageFn,
  ViewerDoc,
  ViewerMode,
  ViewerPaintStatus,
  RotationDegree,
} from "./types";
import { CanvasOverlay } from "./CanvasOverlay";
import { CompareTable } from "./CompareTable";
import { AccessibleTextLayer } from "./AccessibleTextLayer";
import { AlignmentDetail } from "../findings/alignment/AlignmentDetail";
import { isOrderOnlyFinding } from "../findings/alignment/classify.ts";
import { FindingNotes } from "../annotations/FindingNotes.tsx";
import { displaySize } from "../selection/region.ts";
import styles from "./ViewerStage.module.css";

const FALLBACK_READER: Reader = {
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

interface PaintState {
  status: ViewerPaintStatus;
  note: string | null;
  raster: PageRasterView | null;
  rasterPageIndex: number;
}

const NO_SOURCE_NOTE =
  "This report has no verified source PDF attached, so there is no page image to paint. Recorded positions still appear as highlights; attach the original PDF to see it.";
const LOADING_SOURCE_NOTE = "Loading preview…";

export interface ViewerStageProps {
  doc: ViewerDoc;
  /** Paints a report page through the session/PDF.js render boundary. */
  renderPage?: RenderPageFn;
  /** False when no verified source exists — the viewer then shows the
   *  honest source-unavailable state without attempting a render. */
  pageSourceAvailable?: boolean;
  /** True while verified source bytes are being fetched (prepared
   *  examples) — the viewer shows "Loading preview", never a flash of
   *  the absent-source state. */
  pageSourcePending?: boolean;
  /** Set when the source fetch failed — distinct from a genuinely
   *  absent source and from a render error. */
  pageSourceFailed?: string | null;
  initialFindingId?: string | null;
  initialMode?: ViewerMode;
  initialZoom?: number;
  initialRotation?: RotationDegree;
  onKeepEvidence?: (finding: Finding) => void;
  /** User-authored notes on the open report (T23); rendered per finding. */
  annotations?: readonly Annotation[];
  onAddAnnotation?: (annotation: Annotation) => void;
  onRemoveAnnotation?: (annotation: Annotation) => void;
}

export const ViewerStage: React.FC<ViewerStageProps> = ({
  doc,
  renderPage,
  pageSourceAvailable = true,
  pageSourcePending = false,
  pageSourceFailed = null,
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
  // Selection and disclosure are separate: a finding can stay selected
  // while its detail panel is collapsed, and re-activating the same card
  // toggles the panel rather than doing nothing.
  const [expandedFindingId, setExpandedFindingId] = useState<string | null>(initialFindingId);
  const [shortcutsEnabled, setShortcutsEnabled] = useState<boolean>(true);
  const [paneReaderOverride, setPaneReaderOverride] = useState<{
    left: string | null;
    right: string | null;
  }>({ left: null, right: null });
  // Compare mode: the finding whose shared page preview is open, and the
  // findings whose technical detail row is open. Both are independent of
  // selection — a row can show detail without becoming the selection.
  const [previewFindingId, setPreviewFindingId] = useState<string | null>(null);
  const [detailFindingIds, setDetailFindingIds] = useState<ReadonlySet<string>>(new Set());
  // Evidence emphasis: by default only finding-named positions draw boxes;
  // this deliberate toggle reveals every recorded position on the page.
  const [showAllPositions, setShowAllPositions] = useState<boolean>(false);

  const stageRef = useRef<HTMLDivElement>(null);
  const paperAreaRef = useRef<HTMLDivElement>(null);

  const clampedPageIndex = Math.max(0, Math.min(pageIndex, Math.max(0, doc.pages.length - 1)));
  const currentPage: Page = doc.pages[clampedPageIndex] || doc.pages[0];

  const pageOccurrences = doc.occurrences.filter(
    (o) => o.page_index === (currentPage?.index ?? clampedPageIndex),
  );
  const selectedFinding = doc.findings.find((f) => f.id === selectedFindingId) || null;

  // ------------------------------------------------------------------
  // Page raster: painted through the real render boundary, cancelled on
  // every document/page/scale change so a stale raster can never land.
  // ------------------------------------------------------------------
  const [paint, setPaint] = useState<PaintState>({
    status: "loading",
    note: null,
    raster: null,
    rasterPageIndex: -1,
  });
  const paintSeqRef = useRef(0);

  const dpr = typeof window === "undefined" ? 1 : Math.min(window.devicePixelRatio || 1, 2);
  const requestScale = (zoom / 100) * dpr;

  useEffect(() => {
    if (mode === "reading") return;
    if (pageSourcePending) {
      paintSeqRef.current += 1;
      setPaint({
        status: "loading",
        note: LOADING_SOURCE_NOTE,
        raster: null,
        rasterPageIndex: -1,
      });
      return;
    }
    if (pageSourceFailed !== null) {
      paintSeqRef.current += 1;
      setPaint({
        status: "unavailable",
        note: `The original PDF could not be loaded. ${pageSourceFailed}`,
        raster: null,
        rasterPageIndex: -1,
      });
      return;
    }
    if (renderPage === undefined || pageSourceAvailable === false) {
      paintSeqRef.current += 1;
      setPaint({ status: "unavailable", note: NO_SOURCE_NOTE, raster: null, rasterPageIndex: -1 });
      return;
    }
    const seq = ++paintSeqRef.current;
    const ac = new AbortController();
    setPaint((prev) => ({
      status: "loading",
      note: null,
      // Keep the previous raster only while re-rendering the same page
      // (e.g. a zoom change) — never flash a different page's pixels.
      raster: prev.rasterPageIndex === clampedPageIndex ? prev.raster : null,
      rasterPageIndex: prev.rasterPageIndex === clampedPageIndex ? prev.rasterPageIndex : -1,
    }));
    renderPage(clampedPageIndex, requestScale, ac.signal)
      .then((raster) => {
        if (ac.signal.aborted || seq !== paintSeqRef.current) return;
        if (raster === null) {
          setPaint({
            status: "unavailable",
            note: "The page image could not be produced for this page.",
            raster: null,
            rasterPageIndex: -1,
          });
        } else {
          setPaint({
            status: "ready",
            note: raster.limitations.length > 0 ? raster.limitations.join(" ") : null,
            raster,
            rasterPageIndex: clampedPageIndex,
          });
        }
      })
      .catch((err: unknown) => {
        if (ac.signal.aborted || seq !== paintSeqRef.current) return;
        setPaint({
          status: "error",
          note: err instanceof Error ? err.message : "Rendering failed.",
          raster: null,
          rasterPageIndex: -1,
        });
      });
    return () => {
      ac.abort();
    };
  }, [doc, clampedPageIndex, requestScale, mode, renderPage, pageSourceAvailable, pageSourcePending, pageSourceFailed]);

  const paneRaster =
    paint.rasterPageIndex === clampedPageIndex ? paint.raster : null;

  // ------------------------------------------------------------------
  // Reader derivation — Compare names the readers the selected finding
  // actually compares, not just the first two records in the report.
  // ------------------------------------------------------------------
  const readersOnPage = useMemo(() => {
    const seen = new Set(pageOccurrences.map((o) => o.reader_id));
    const withEvidence = doc.readers.filter((r) => seen.has(r.id));
    return withEvidence.length > 0 ? withEvidence : doc.readers;
  }, [doc.readers, pageOccurrences]);

  const findingReaderIds = useMemo(() => {
    if (!selectedFinding) return [] as string[];
    const named = new Set(selectedFinding.occurrence_ids);
    const ids: string[] = [];
    const seen = new Set<string>();
    for (const o of doc.occurrences) {
      if (!named.has(o.id) || seen.has(o.reader_id)) continue;
      seen.add(o.reader_id);
      ids.push(o.reader_id);
    }
    return ids;
  }, [selectedFinding, doc.occurrences]);

  // Pane overrides reset whenever the selected finding or document
  // changes — a stale pane choice must not outlive its evidence.
  useEffect(() => {
    setPaneReaderOverride({ left: null, right: null });
  }, [selectedFindingId, doc]);

  const readerById = useCallback(
    (id: string | null | undefined): Reader | undefined =>
      id === null || id === undefined
        ? undefined
        : doc.readers.find((r) => r.id === id),
    [doc.readers],
  );

  const defaultLeftId = findingReaderIds[0] ?? readersOnPage[0]?.id;
  const defaultRightId =
    findingReaderIds.find((id) => id !== defaultLeftId) ??
    readersOnPage.find((r) => r.id !== defaultLeftId)?.id ??
    defaultLeftId;
  const leftReader: Reader =
    readerById(paneReaderOverride.left) ?? readerById(defaultLeftId) ?? FALLBACK_READER;
  const rightReader: Reader =
    readerById(paneReaderOverride.right) ?? readerById(defaultRightId) ?? leftReader;

  const paneReaderOptions = useMemo(() => {
    const ids = new Set<string>([...findingReaderIds, ...readersOnPage.map((r) => r.id)]);
    const inScope = doc.readers.filter((r) => ids.has(r.id));
    return inScope.length > 0 ? inScope : doc.readers;
  }, [doc.readers, findingReaderIds, readersOnPage]);

  // ------------------------------------------------------------------
  // Evidence emphasis: every finding-named occurrence is evidence; all
  // other recorded positions stay available through the explicit
  // "show all positions" toggle rather than covering the page.
  // ------------------------------------------------------------------
  const findingNamedIds = useMemo(
    () => new Set(doc.findings.flatMap((f) => f.occurrence_ids)),
    [doc.findings],
  );

  const overlayOccurrences = useMemo(() => {
    if (showAllPositions) return pageOccurrences;
    if (selectedFinding) {
      const named = new Set(selectedFinding.occurrence_ids);
      return pageOccurrences.filter(
        (o) => named.has(o.id) || o.id === selectedOccurrenceId,
      );
    }
    const evidence = pageOccurrences.filter((o) => findingNamedIds.has(o.id));
    return evidence.length > 0 ? evidence : pageOccurrences;
  }, [pageOccurrences, selectedFinding, selectedOccurrenceId, showAllPositions, findingNamedIds]);

  // The compare preview is bound to its row's finding, which may differ
  // from the global selection.
  const previewOccurrences = useCallback(
    (finding: Finding) => {
      if (showAllPositions) return pageOccurrences;
      const named = new Set(finding.occurrence_ids);
      return pageOccurrences.filter(
        (o) => named.has(o.id) || o.id === selectedOccurrenceId,
      );
    },
    [pageOccurrences, selectedOccurrenceId, showAllPositions],
  );

  // ------------------------------------------------------------------
  // Selection / disclosure
  // ------------------------------------------------------------------
  const handleSelectFinding = useCallback(
    (finding: Finding) => {
      setSelectedFindingId(finding.id);
      // Repeated activation toggles disclosure without losing selection.
      setExpandedFindingId((prev) => (prev === finding.id ? null : finding.id));
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
      if (occ.page_index !== (currentPage?.index ?? pageIndex)) {
        setPageIndex(occ.page_index);
      }
    },
    [pageIndex, currentPage],
  );

  // Next / Previous finding selects and expands the target.
  const handleNextFinding = useCallback(() => {
    if (doc.findings.length === 0) return;
    const currentIdx = doc.findings.findIndex((f) => f.id === selectedFindingId);
    const nextIdx = (currentIdx + 1) % doc.findings.length;
    const target = doc.findings[nextIdx];
    setSelectedFindingId(target.id);
    setExpandedFindingId(target.id);
    if (target.page_index !== undefined) setPageIndex(target.page_index);
    if (mode === "compare") {
      previewFitPendingRef.current = true;
      setPreviewFindingId(target.id);
    }
    if (
      target.occurrence_ids.length > 0 &&
      target.alignment !== "ambiguous" &&
      !isOrderOnlyFinding(target)
    ) {
      setSelectedOccurrenceId(target.occurrence_ids[0]);
    } else {
      setSelectedOccurrenceId(null);
    }
  }, [doc.findings, selectedFindingId, mode]);

  const handlePrevFinding = useCallback(() => {
    if (doc.findings.length === 0) return;
    const currentIdx = doc.findings.findIndex((f) => f.id === selectedFindingId);
    const prevIdx = (currentIdx - 1 + doc.findings.length) % doc.findings.length;
    const target = doc.findings[prevIdx];
    setSelectedFindingId(target.id);
    setExpandedFindingId(target.id);
    if (target.page_index !== undefined) setPageIndex(target.page_index);
    if (mode === "compare") {
      previewFitPendingRef.current = true;
      setPreviewFindingId(target.id);
    }
    if (
      target.occurrence_ids.length > 0 &&
      target.alignment !== "ambiguous" &&
      !isOrderOnlyFinding(target)
    ) {
      setSelectedOccurrenceId(target.occurrence_ids[0]);
    } else {
      setSelectedOccurrenceId(null);
    }
  }, [doc.findings, selectedFindingId, mode]);

  // Focus hand-off on mode switch: entering compare unmounts the findings
  // aside, so a focused element disappears and focus falls to <body> —
  // outside the stage's keydown scope, which silently kills every stage
  // shortcut. When (and only when) focus was actually lost, land on the
  // stage itself; focus still on a live control (e.g. the mode tab) is
  // left alone.
  const prevModeRef = useRef(mode);
  useEffect(() => {
    const prev = prevModeRef.current;
    prevModeRef.current = mode;
    if (mode === "compare" && prev !== "compare") {
      const active = document.activeElement;
      if (!active || active === document.body || !document.contains(active)) {
        stageRef.current?.focus();
      }
    }
  }, [mode]);

  const gotoPage = useCallback(
    (idx: number) => {
      setPageIndex(Math.max(0, Math.min(idx, doc.pages.length - 1)));
    },
    [doc.pages.length],
  );

  // Compare mode: "Show on page" opens the finding's shared preview row
  // and navigates to the page its evidence is on. Activating again closes
  // it. Preview is independent of selection expansion.
  const handleShowOnPage = (finding: Finding) => {
    if (previewFindingId === finding.id) {
      setPreviewFindingId(null);
      return;
    }
    if (finding.page_index !== undefined && finding.page_index !== clampedPageIndex) {
      setPageIndex(finding.page_index);
    }
    setSelectedFindingId(finding.id);
    previewFitPendingRef.current = true;
    setPreviewFindingId(finding.id);
  };

  const handleToggleDetails = (finding: Finding) => {
    setDetailFindingIds((prev) => {
      const next = new Set(prev);
      if (next.has(finding.id)) {
        next.delete(finding.id);
      } else {
        next.add(finding.id);
      }
      return next;
    });
  };

  // Picking a reading in the table (or a polygon on the shared preview)
  // selects that occurrence and reveals the preview on its page.
  const handleLocateOccurrence = (finding: Finding, occ: Occurrence) => {
    if (occ.page_index !== (currentPage?.index ?? clampedPageIndex)) {
      setPageIndex(occ.page_index);
    }
    setSelectedFindingId(finding.id);
    setSelectedOccurrenceId(occ.id);
    if (previewFindingId !== finding.id) previewFitPendingRef.current = true;
    setPreviewFindingId(finding.id);
  };

  // Fit the rotated page box inside the visible paper area (or the shared
  // compare preview surface) instead of assuming 100%.
  const handleFit = useCallback(() => {
    const area = paperAreaRef.current;
    if (!area || !currentPage) return;
    const surface =
      (mode === "compare"
        ? area.querySelector<HTMLElement>("[data-testid='compare-preview-surface']")
        : area) ?? area;
    const slack = 64; // padding + paper margins around the page box
    const availW = Math.max(0, surface.clientWidth - slack);
    const rect = surface.getBoundingClientRect();
    const availH =
      mode === "compare"
        ? Math.max(0, surface.clientHeight - slack)
        : Math.max(0, window.innerHeight - rect.top - slack);
    const [pw, ph] = currentPage.canonical_size_pt;
    const [dw, dh] = displaySize({ widthPt: pw, heightPt: ph, rotation: currentPage.rotation });
    const quarter = rotation === 90 || rotation === 270;
    const boxW = quarter ? dh : dw;
    const boxH = quarter ? dw : dh;
    if (boxW <= 0 || boxH <= 0) return;
    let fit = availW > 0 ? availW / boxW : 1;
    if (availH > 0) fit = Math.min(fit, availH / boxH);
    const pct = Math.round(Math.max(0.25, Math.min(fit, 4)) * 100);
    setZoom(pct);
  }, [mode, currentPage, rotation]);

  // When a compare preview opens, fit the page inside it once — the flag
  // keeps later zoom/handleFit identity changes from re-fitting.
  const previewFitPendingRef = useRef(false);
  useEffect(() => {
    if (!previewFitPendingRef.current || previewFindingId === null || mode !== "compare") {
      return;
    }
    previewFitPendingRef.current = false;
    const raf = requestAnimationFrame(() => handleFit());
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewFindingId, mode, handleFit]);

  // Stage Keyboard Shortcuts
  const handleStageKeyDown = (e: React.KeyboardEvent) => {
    if (!shortcutsEnabled) return;
    const target = e.target as HTMLElement;
    if (
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.tagName === "SELECT" ||
      target.isContentEditable
    ) {
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
    } else if (e.key === "PageDown") {
      e.preventDefault();
      gotoPage(clampedPageIndex + 1);
    } else if (e.key === "PageUp") {
      e.preventDefault();
      gotoPage(clampedPageIndex - 1);
    }
  };

  // Document/report identity (and the initial-finding request) owns the
  // selection reset. One merged effect so the initial finding's page and
  // occurrence are applied exactly once per document — previously a page
  // change re-fired the initial-finding effect and snapped back.
  useEffect(() => {
    setMode(initialMode);
    setRotation(initialRotation);
    setZoom(initialZoom);
    setPageIndex(0);
    setSelectedOccurrenceId(null);
    const found = initialFindingId
      ? doc.findings.find((f) => f.id === initialFindingId)
      : undefined;
    setSelectedFindingId(found?.id ?? null);
    setExpandedFindingId(found?.id ?? null);
    setPreviewFindingId(null);
    setDetailFindingIds(new Set());
    setShowAllPositions(false);
    if (found) {
      if (found.page_index !== undefined) setPageIndex(found.page_index);
      if (
        found.occurrence_ids.length > 0 &&
        found.alignment !== "ambiguous" &&
        !isOrderOnlyFinding(found)
      ) {
        setSelectedOccurrenceId(found.occurrence_ids[0]);
      }
    }
  }, [doc, initialFindingId, initialMode, initialZoom, initialRotation]);

  const textLayer = (
    <AccessibleTextLayer
      pageIndex={clampedPageIndex}
      occurrences={pageOccurrences}
      readers={doc.readers}
      selectedOccurrenceId={selectedOccurrenceId}
      onSelectOccurrence={(occ) => {
        handleSelectOccurrence(occ);
        if (mode === "reading") setMode("page");
      }}
      limitations={currentPage?.limitations ?? []}
      defaultDetailsOpen={
        mode === "reading" ? true : mode === "compare" ? false : undefined
      }
    />
  );

  const findingNav = (
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
      <span id="findings-counter" className={styles.findingNavCounter}>
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
  );

  // Deliberate reveal of every recorded position — the default view
  // emphasises only the selected evidence.
  const positionsToggle = (
    <button
      type="button"
      id="btn-all-positions"
      className={styles.toolButton}
      aria-pressed={showAllPositions}
      onClick={() => setShowAllPositions((prev) => !prev)}
    >
      {showAllPositions ? "Show selected evidence only" : "Show all positions"}
    </button>
  );

  const renderComparePreview = (finding: Finding) => {
    const findingOnOtherPage =
      finding.page_index !== undefined && finding.page_index !== clampedPageIndex;
    return (
      <div
        id={`compare-preview-${finding.id}`}
        className={styles.previewPanel}
        data-testid={`compare-preview-${finding.id}`}
      >
        <div className={styles.previewHeader}>
          <p className={styles.previewTitle}>
            Page {clampedPageIndex + 1}
            {findingOnOtherPage ? ` — finding is on page ${finding.page_index! + 1}` : ""}
          </p>
          <div className={styles.previewHeaderActions}>
            {positionsToggle}
            <button
              type="button"
              className={styles.toolButton}
              onClick={() => setPreviewFindingId(null)}
            >
              Close preview
            </button>
          </div>
        </div>
        <div className={styles.previewSurface} data-testid="compare-preview-surface">
          <CanvasOverlay
            page={currentPage}
            occurrences={previewOccurrences(finding)}
            selectedOccurrenceId={selectedOccurrenceId}
            selectedFinding={finding}
            zoom={zoom}
            rotation={rotation}
            onSelectOccurrence={(occ) => handleLocateOccurrence(finding, occ)}
            renderCanvas={true}
            raster={paneRaster}
            rasterStatus={paint.status}
            rasterNote={paint.note}
          />
        </div>
        <p className={styles.previewHint}>
          {findingOnOtherPage
            ? "This finding's evidence is on a different page — its positions are not highlighted here."
            : "Select a reading or a highlighted position to locate it. Page, zoom, Fit and Rotate controls above apply to this preview."}
        </p>
      </div>
    );
  };

  const renderCompareDetails = (finding: Finding) => (
    <div
      id={`compare-detail-${finding.id}`}
      className={styles.detailPanel}
      data-testid={`compare-detail-${finding.id}`}
    >
      <AlignmentDetail
        finding={finding}
        occurrences={doc.occurrences}
        readers={doc.readers}
        selectedOccurrenceId={selectedOccurrenceId}
        onSelectOccurrence={(occ) => handleLocateOccurrence(finding, occ)}
        returnFocusId={`compare-details-${finding.id}`}
      />
      {onAddAnnotation && onRemoveAnnotation && (
        <FindingNotes
          finding={finding}
          notes={annotations ?? []}
          onAdd={onAddAnnotation}
          onRemove={onRemoveAnnotation}
        />
      )}
      <div className={styles.detailActions}>
        {onKeepEvidence && (
          <button
            type="button"
            className={styles.toolButton}
            onClick={() => onKeepEvidence(finding)}
          >
            Keep this evidence
          </button>
        )}
        <button
          type="button"
          className={styles.toolButton}
          onClick={() => handleToggleDetails(finding)}
        >
          Back to finding
        </button>
      </div>
    </div>
  );

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

          <div
            className={styles.pageNav}
            role="group"
            aria-label="Page navigation"
          >
            <button
              id="btn-page-prev"
              type="button"
              className={styles.toolButton}
              onClick={() => gotoPage(clampedPageIndex - 1)}
              disabled={clampedPageIndex <= 0}
              aria-label="Previous page"
            >
              ←
            </button>
            <span id="page-indicator" className={styles.pageIndicator}>
              Page {clampedPageIndex + 1} of {doc.pages.length}
            </span>
            <button
              id="btn-page-next"
              type="button"
              className={styles.toolButton}
              onClick={() => gotoPage(clampedPageIndex + 1)}
              disabled={clampedPageIndex >= doc.pages.length - 1}
              aria-label="Next page"
            >
              →
            </button>
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
              onClick={handleFit}
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

      {/* Main Workspace Layout — compare mode drops the sidebar: the
          paired-reading table is the content and its shared preview. */}
      <div
        className={`${styles.workspaceGrid} ${mode === "compare" ? styles.workspaceGridSingle : ""}`}
      >
        {/* Paper / Canvas / Compare / Reading Area */}
        <div ref={paperAreaRef} id="viewer-paper-area" className={styles.stagePaperArea}>
          {mode === "compare" ? (
            <CompareTable
              findings={doc.findings}
              occurrences={doc.occurrences}
              readers={doc.readers}
              leftReader={leftReader}
              rightReader={rightReader}
              readerOptions={paneReaderOptions}
              onChangeLeftReader={(id) =>
                setPaneReaderOverride((prev) => ({ ...prev, left: id }))
              }
              onChangeRightReader={(id) =>
                setPaneReaderOverride((prev) => ({ ...prev, right: id }))
              }
              selectedFindingId={selectedFindingId}
              selectedOccurrenceId={selectedOccurrenceId}
              previewFindingId={previewFindingId}
              detailFindingIds={detailFindingIds}
              onShowOnPage={handleShowOnPage}
              onToggleDetails={handleToggleDetails}
              onLocateOccurrence={handleLocateOccurrence}
              renderPreview={renderComparePreview}
              renderDetails={renderCompareDetails}
              findingNav={findingNav}
            />
          ) : mode === "reading" ? (
            textLayer
          ) : (
            <>
              <CanvasOverlay
                page={currentPage}
                occurrences={overlayOccurrences}
                selectedOccurrenceId={selectedOccurrenceId}
                selectedFinding={selectedFinding}
                zoom={zoom}
                rotation={rotation}
                onSelectOccurrence={handleSelectOccurrence}
                renderCanvas={true}
                raster={paneRaster}
                rasterStatus={paint.status}
                rasterNote={paint.note}
              />
              <div className={styles.pageModeActions}>{positionsToggle}</div>
            </>
          )}

          {/* Accessible Text Equivalent & Limits — in Reading mode the
              layer IS the main content, so it is not repeated below. In
              compare mode it remains as the "all recorded readings" list. */}
          {mode !== "reading" && textLayer}
        </div>

        {/* Differences — hidden in compare mode where each finding's own
            row carries status, preview and detail. */}
        {mode !== "compare" && (
          <aside
            id="evidence-slip"
            className={styles.evidenceSlip}
            aria-labelledby="evidence-slip-heading"
          >
            <h2 id="evidence-slip-heading" className={styles.evidenceHeading}>
              Differences
            </h2>
            <p className={styles.evidenceIntro}>
              Readings that do not match between the page and extracted text.
            </p>

            {findingNav}

            {/* List of findings */}
            <div id="findings-nav-list" role="list" aria-label="Discovered findings">
              {doc.findings.map((f) => {
              const isSelected = f.id === selectedFindingId;
              const isExpanded = f.id === expandedFindingId;
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
                      aria-expanded={isExpanded}
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

                  {isExpanded && (
                    <AlignmentDetail
                      finding={f}
                      occurrences={doc.occurrences}
                      readers={doc.readers}
                      selectedOccurrenceId={selectedOccurrenceId}
                      onSelectOccurrence={handleSelectOccurrence}
                      returnFocusId={`finding-item-${f.id}`}
                    />
                  )}

                  {isExpanded && onAddAnnotation && onRemoveAnnotation && (
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
        )}
      </div>
    </div>
  );
};

export default ViewerStage;
