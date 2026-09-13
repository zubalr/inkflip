import React from "react";
import type { Page, Occurrence, Finding } from "../../../../../packages/contracts/src/index.ts";
import type { RotationDegree } from "./types";
import { isOrderOnlyFinding } from "../findings/alignment/classify.ts";
import styles from "./CanvasOverlay.module.css";

export interface CanvasOverlayProps {
  page: Page;
  occurrences: Occurrence[];
  selectedOccurrenceId?: string | null;
  selectedFinding?: Finding | null;
  zoom?: number;
  rotation?: RotationDegree;
  onSelectOccurrence?: (occ: Occurrence) => void;
  renderCanvas?: boolean;
}

export const CanvasOverlay: React.FC<CanvasOverlayProps> = ({
  page,
  occurrences,
  selectedOccurrenceId,
  selectedFinding,
  zoom = 100,
  rotation = 0,
  onSelectOccurrence,
  renderCanvas = true,
}) => {
  const [w, h] = page.canonical_size_pt;
  const s = zoom / 100;

  const isRotatedQuarter = rotation === 90 || rotation === 270;
  const displayWidth = (isRotatedQuarter ? h : w) * s;
  const displayHeight = (isRotatedQuarter ? w : h) * s;

  const mapPoint = (cx: number, cy: number): [number, number] => {
    let rx = cx;
    let ry = cy;
    switch (rotation) {
      case 0:
        rx = cx;
        ry = cy;
        break;
      case 90:
        rx = h - cy;
        ry = cx;
        break;
      case 180:
        rx = w - cx;
        ry = h - cy;
        break;
      case 270:
        rx = cy;
        ry = w - cx;
        break;
    }
    return [rx * s, ry * s];
  };

  const selectedOcc = occurrences.find((o) => o.id === selectedOccurrenceId);
  // The notice is only honest when the finding's evidence actually lacks
  // localized geometry — `not_applicable` alignment alone (e.g. an
  // order-only finding naming polygon'd occurrences) must not claim it.
  const namedOccs = selectedFinding
    ? occurrences.filter((o) => selectedFinding.occurrence_ids.includes(o.id))
    : [];
  const isPageLevelOnly =
    (selectedFinding &&
      (selectedFinding.alignment === "page_level" ||
        (namedOccs.length > 0 &&
          namedOccs.every((o) => o.geometry.polygon === null)))) ||
    (selectedOcc &&
      (selectedOcc.geometry.precision === "page_only" ||
        selectedOcc.geometry.precision === "unknown" ||
        selectedOcc.geometry.polygon === null));

  return (
    <div className={styles.wrapper}>
      {isPageLevelOnly && (
        <div
          id="page-level-geometry-notice"
          className={styles.pageLevelNotice}
          role="status"
          aria-live="polite"
        >
          <span className={styles.pageLevelIcon} aria-hidden="true">
            ℹ️
          </span>
          <span>
            This reading or observation applies to Page {page.index + 1} as a whole. No localized
            bounding coordinates exist for this reader.
          </span>
        </div>
      )}

      <div
        id="document-paper"
        className={styles.paperContainer}
        style={{
          width: `${displayWidth}px`,
          height: `${displayHeight}px`,
        }}
        data-page-index={page.index}
        data-rotation={rotation}
        data-zoom={zoom}
      >
        {renderCanvas && (
          <canvas
            id={`page-canvas-${page.index}`}
            className={styles.canvas}
            width={displayWidth}
            height={displayHeight}
            role="img"
            aria-label={`Rendered visual page ${page.index + 1}`}
          />
        )}

        <svg
          className={styles.svgOverlay}
          width={displayWidth}
          height={displayHeight}
          aria-hidden="true"
        >
          {occurrences
            .filter((occ) => occ.geometry.polygon !== null && occ.geometry.polygon.length >= 3)
            .map((occ) => {
              const poly = occ.geometry.polygon!;
              const mappedPoints = poly.map((pt) => mapPoint(pt[0], pt[1]));
              const pointsStr = mappedPoints.map((pt) => `${pt[0]},${pt[1]}`).join(" ");
              // The chosen occurrence is the selection. For ambiguous and
              // order-only findings the other named occurrences are
              // *candidates* — marked distinctly so a navigation pick never
              // looks like an engine selection. For settled findings all
              // named occurrences are co-equal evidence and stay selected.
              const isChosen = occ.id === selectedOccurrenceId;
              const isNamed = selectedFinding
                ? selectedFinding.occurrence_ids.includes(occ.id)
                : false;
              const isCandidateSet =
                selectedFinding !== null &&
                selectedFinding !== undefined &&
                (selectedFinding.alignment === "ambiguous" ||
                  isOrderOnlyFinding(selectedFinding));
              const isCandidate = !isChosen && isNamed && isCandidateSet;
              const isCoEvidence = !isChosen && isNamed && !isCandidateSet;

              return (
                <polygon
                  key={occ.id}
                  id={`highlight-${occ.id}`}
                  data-occurrence-id={occ.id}
                  data-ordinal={occ.ordinal}
                  points={pointsStr}
                  className={`${styles.highlightBox} ${
                    occ.geometry.precision === "exact"
                      ? styles.highlightExact
                      : styles.highlightEstimated
                  } ${isChosen || isCoEvidence ? styles.highlightSelected : ""} ${
                    isCandidate ? styles.highlightAmbiguous : ""
                  }`}
                  onClick={() => onSelectOccurrence?.(occ)}
                  aria-label={`Reading occurrence ${occ.ordinal}: ${occ.raw_text}`}
                />
              );
            })}
        </svg>
      </div>
    </div>
  );
};

export default CanvasOverlay;
