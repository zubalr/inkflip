import React from "react";
import type { Page, Occurrence, Finding } from "../../../../../packages/contracts/src/index.ts";
import type { RotationDegree } from "./types";
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
  const isPageLevelOnly =
    (selectedFinding &&
      (selectedFinding.alignment === "page_level" ||
        selectedFinding.alignment === "not_applicable")) ||
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
              const isSelected =
                occ.id === selectedOccurrenceId ||
                (selectedFinding ? selectedFinding.occurrence_ids.includes(occ.id) : false);

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
                  } ${isSelected ? styles.highlightSelected : ""}`}
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
