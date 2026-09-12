import React, { useRef, useEffect } from "react";
import type {
  Page,
  Occurrence,
  Reader,
  Finding,
} from "../../../../../packages/contracts/src/index.ts";
import type { RotationDegree } from "./types";
import { CanvasOverlay } from "./CanvasOverlay";
import styles from "./ComparePanes.module.css";

export interface ComparePanesProps {
  page: Page;
  leftReader: Reader;
  rightReader: Reader;
  leftOccurrences: Occurrence[];
  rightOccurrences: Occurrence[];
  selectedOccurrenceId?: string | null;
  selectedFinding?: Finding | null;
  zoom?: number;
  rotation?: RotationDegree;
  onSelectOccurrence?: (occ: Occurrence) => void;
}

export const ComparePanes: React.FC<ComparePanesProps> = ({
  page,
  leftReader,
  rightReader,
  leftOccurrences,
  rightOccurrences,
  selectedOccurrenceId,
  selectedFinding,
  zoom = 100,
  rotation = 0,
  onSelectOccurrence,
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
          <span>Reader A (Primary)</span>
          <span className={styles.paneReaderName}>
            {leftReader.name} {leftReader.version ? `v${leftReader.version}` : ""}
          </span>
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
          />
        </div>
      </section>

      {/* Right Pane */}
      <section id="compare-pane-right" className={styles.pane} aria-labelledby="right-pane-header">
        <header id="right-pane-header" className={styles.paneHeader}>
          <span>Reader B (Comparative)</span>
          <span className={styles.paneReaderName}>
            {rightReader.name} {rightReader.version ? `v${rightReader.version}` : ""}
          </span>
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
            renderCanvas={false}
          />
        </div>
      </section>
    </div>
  );
};

export default ComparePanes;
