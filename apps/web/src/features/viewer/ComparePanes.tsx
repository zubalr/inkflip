import React, { useRef, useEffect } from "react";
import type {
  Page,
  Occurrence,
  Reader,
  Finding,
} from "../../../../../packages/contracts/src/index.ts";
import type {
  PageRasterView,
  RotationDegree,
  ViewerPaintStatus,
} from "./types";
import { CanvasOverlay } from "./CanvasOverlay";
import styles from "./ComparePanes.module.css";

export interface ComparePanesProps {
  page: Page;
  leftReader: Reader;
  rightReader: Reader;
  leftOccurrences: Occurrence[];
  rightOccurrences: Occurrence[];
  /** Occurrences the selected finding names — shown verbatim per pane so
   *  the comparison is about the recorded readings, not silhouettes. */
  namedOccurrences?: Occurrence[];
  readerOptions?: Reader[];
  onChangeLeftReader?: (readerId: string) => void;
  onChangeRightReader?: (readerId: string) => void;
  selectedOccurrenceId?: string | null;
  selectedFinding?: Finding | null;
  zoom?: number;
  rotation?: RotationDegree;
  onSelectOccurrence?: (occ: Occurrence) => void;
  raster?: PageRasterView | null;
  rasterStatus?: ViewerPaintStatus;
  rasterNote?: string | null;
}

function isRenderOnly(reader: Reader): boolean {
  return reader.method === "render";
}

const PaneReadings: React.FC<{ reader: Reader; occurrences: Occurrence[] }> = ({
  reader,
  occurrences,
}) => {
  if (isRenderOnly(reader)) {
    return (
      <p className={styles.readingsEmpty}>
        {reader.name} produces the page image itself — it has no text records.
      </p>
    );
  }
  if (occurrences.length === 0) {
    return (
      <p className={styles.readingsEmpty}>
        No readings from {reader.name} are named by this finding.
      </p>
    );
  }
  return (
    <ul className={styles.readingsList}>
      {occurrences.map((occ) => (
        <li key={occ.id} id={`compare-reading-${occ.id}`}>
          <span className={styles.readingOrdinal}>occurrence #{occ.ordinal}</span>{" "}
          <q className={styles.readingText}>{occ.raw_text}</q>
          {occ.geometry.polygon === null && (
            <span className={styles.readingScope}> page-level</span>
          )}
        </li>
      ))}
    </ul>
  );
};

export const ComparePanes: React.FC<ComparePanesProps> = ({
  page,
  leftReader,
  rightReader,
  leftOccurrences,
  rightOccurrences,
  namedOccurrences = [],
  readerOptions,
  onChangeLeftReader,
  onChangeRightReader,
  selectedOccurrenceId,
  selectedFinding,
  zoom = 100,
  rotation = 0,
  onSelectOccurrence,
  raster = null,
  rasterStatus = "unavailable",
  rasterNote = null,
}) => {
  const leftScrollRef = useRef<HTMLDivElement>(null);
  const rightScrollRef = useRef<HTMLDivElement>(null);
  const isSyncingRef = useRef<boolean>(false);

  useEffect(() => {
    const leftEl = leftScrollRef.current;
    const rightEl = rightScrollRef.current;
    if (!leftEl || !rightEl) return;

    const syncScroll = (source: HTMLDivElement, target: HTMLDivElement) => {
      if (isSyncingRef.current) return;
      isSyncingRef.current = true;

      const maxSource = source.scrollHeight - source.clientHeight;
      const maxTarget = target.scrollHeight - target.clientHeight;

      if (maxSource > 0 && maxTarget > 0) {
        const ratio = source.scrollTop / maxSource;
        target.scrollTop = ratio * maxTarget;
      }

      const maxSourceH = source.scrollWidth - source.clientWidth;
      const maxTargetH = target.scrollWidth - target.clientWidth;
      if (maxSourceH > 0 && maxTargetH > 0) {
        const ratioH = source.scrollLeft / maxSourceH;
        target.scrollLeft = ratioH * maxTargetH;
      }

      requestAnimationFrame(() => {
        isSyncingRef.current = false;
      });
    };

    const handleLeftScroll = () => syncScroll(leftEl, rightEl);
    const handleRightScroll = () => syncScroll(rightEl, leftEl);

    leftEl.addEventListener("scroll", handleLeftScroll, { passive: true });
    rightEl.addEventListener("scroll", handleRightScroll, { passive: true });

    return () => {
      leftEl.removeEventListener("scroll", handleLeftScroll);
      rightEl.removeEventListener("scroll", handleRightScroll);
    };
  }, []);

  const leftNamed = namedOccurrences.filter((o) => o.reader_id === leftReader.id);
  const rightNamed = namedOccurrences.filter((o) => o.reader_id === rightReader.id);

  const readerSelect = (
    side: "left" | "right",
    reader: Reader,
    onChange: ((id: string) => void) | undefined,
  ) => {
    const label = `${reader.name}${reader.version ? ` v${reader.version}` : ""}`;
    if (!readerOptions || !onChange) {
      return <span className={styles.paneReaderName}>{label}</span>;
    }
    return (
      <select
        id={`compare-reader-${side}`}
        className={styles.readerSelect}
        aria-label={`${side === "left" ? "Left" : "Right"} pane reader`}
        value={reader.id}
        onChange={(e) => onChange(e.target.value)}
      >
        {readerOptions.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
            {r.version ? ` v${r.version}` : ""}
          </option>
        ))}
        {!readerOptions.some((r) => r.id === reader.id) && (
          <option value={reader.id}>{label}</option>
        )}
      </select>
    );
  };

  return (
    <div
      id="compare-panes-container"
      className={styles.container}
      role="group"
      aria-label="Synchronized comparison views"
    >
      {/* Left Pane */}
      <section id="compare-pane-left" className={styles.pane} aria-labelledby="left-pane-header">
        <header id="left-pane-header" className={styles.paneHeader}>
          <span>Reader A</span>
          {readerSelect("left", leftReader, onChangeLeftReader)}
        </header>
        <div
          ref={leftScrollRef}
          id="compare-scroll-left"
          className={styles.paneScrollArea}
          tabIndex={0}
          role="region"
          aria-label={`${leftReader.name} document representation`}
        >
          <CanvasOverlay
            page={page}
            occurrences={leftOccurrences}
            selectedOccurrenceId={selectedOccurrenceId}
            selectedFinding={selectedFinding}
            zoom={zoom}
            rotation={rotation}
            onSelectOccurrence={onSelectOccurrence}
            renderCanvas={true}
            raster={raster}
            rasterStatus={rasterStatus}
            rasterNote={rasterNote}
          />
        </div>
        <div className={styles.paneReadings} aria-label={`${leftReader.name} named readings`}>
          <PaneReadings reader={leftReader} occurrences={leftNamed} />
        </div>
      </section>

      {/* Right Pane */}
      <section id="compare-pane-right" className={styles.pane} aria-labelledby="right-pane-header">
        <header id="right-pane-header" className={styles.paneHeader}>
          <span>Reader B</span>
          {readerSelect("right", rightReader, onChangeRightReader)}
        </header>
        <div
          ref={rightScrollRef}
          id="compare-scroll-right"
          className={styles.paneScrollArea}
          tabIndex={0}
          role="region"
          aria-label={`${rightReader.name} document representation`}
        >
          <CanvasOverlay
            page={page}
            occurrences={rightOccurrences}
            selectedOccurrenceId={selectedOccurrenceId}
            selectedFinding={selectedFinding}
            zoom={zoom}
            rotation={rotation}
            onSelectOccurrence={onSelectOccurrence}
            renderCanvas={true}
            raster={raster}
            rasterStatus={rasterStatus}
            rasterNote={rasterNote}
          />
        </div>
        <div className={styles.paneReadings} aria-label={`${rightReader.name} named readings`}>
          <PaneReadings reader={rightReader} occurrences={rightNamed} />
        </div>
      </section>
    </div>
  );
};

export default ComparePanes;
