import React, { useEffect, useRef } from "react";
import type { Page, Occurrence, Finding } from "../../../../../packages/contracts/src/index.ts";
import type { PageRasterView, RotationDegree, ViewerPaintStatus } from "./types";
import { isOrderOnlyFinding } from "../findings/alignment/classify.ts";
import { canonicalToDisplay, displaySize } from "../selection/region.ts";
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
  /** Real rendered page pixels in display space, when a source exists. */
  raster?: PageRasterView | null;
  rasterStatus?: ViewerPaintStatus;
  rasterNote?: string | null;
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
  raster = null,
  rasterStatus = "unavailable",
  rasterNote = null,
}) => {
  const [w, h] = page.canonical_size_pt;
  const s = zoom / 100;

  // Intrinsic page rotation is already baked into the rendered raster:
  // geometry is canonical (unrotated), pixels are display-space. The
  // paper box is therefore display-sized, then viewer rotation swaps it.
  const [dispW, dispH] = displaySize({ widthPt: w, heightPt: h, rotation: page.rotation });
  const isRotatedQuarter = rotation === 90 || rotation === 270;
  const displayWidth = (isRotatedQuarter ? dispH : dispW) * s;
  const displayHeight = (isRotatedQuarter ? dispW : dispH) * s;

  const mapPoint = (cx: number, cy: number): [number, number] => {
    const [dx, dy] = canonicalToDisplay(cx, cy, {
      widthPt: w,
      heightPt: h,
      rotation: page.rotation,
    });
    let rx = dx;
    let ry = dy;
    switch (rotation) {
      case 0:
        rx = dx;
        ry = dy;
        break;
      case 90:
        rx = dispH - dy;
        ry = dx;
        break;
      case 180:
        rx = dispW - dx;
        ry = dispH - dy;
        break;
      case 270:
        rx = dy;
        ry = dispW - dx;
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
  // A page-level finding can still name occurrences carrying estimated
  // polygons — those draw highlight boxes, so claiming "no coordinates
  // exist" would overclaim. Distinguish the two honest states.
  const namedHavePolygons = namedOccs.some((o) => o.geometry.polygon !== null);
  const isPageLevelOnly =
    (selectedFinding &&
      (namedOccs.length > 0
        ? namedOccs.every((o) => o.geometry.polygon === null)
        : selectedFinding.alignment === "page_level")) ||
    (selectedOcc &&
      (selectedOcc.geometry.precision === "page_only" ||
        selectedOcc.geometry.precision === "unknown" ||
        selectedOcc.geometry.polygon === null));
  const pageLevelNotice = isPageLevelOnly
    ? "none"
    : selectedFinding && selectedFinding.alignment === "page_level" && namedHavePolygons
      ? "estimated"
      : null;

  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Paint the real rendered page. The raster is display-space pixels;
  // viewer rotation is applied as a draw transform. Device pixel ratio
  // sizes the backing store so text stays sharp on Retina screens.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !renderCanvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(1, Math.round(displayWidth * dpr));
    canvas.height = Math.max(1, Math.round(displayHeight * dpr));
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!raster || raster.imageData.length === 0) return;

    const src = document.createElement("canvas");
    src.width = raster.widthPx;
    src.height = raster.heightPx;
    const srcCtx = src.getContext("2d");
    if (!srcCtx) return;
    srcCtx.putImageData(
      new ImageData(new Uint8ClampedArray(raster.imageData), raster.widthPx, raster.heightPx),
      0,
      0,
    );

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const bw = displayWidth;
    const bh = displayHeight;
    // Image is display-space (dispW×dispH scaled); rotate it into the
    // viewer box (displayWidth×displayHeight) for quarter turns.
    switch (rotation) {
      case 90:
        ctx.translate(bw, 0);
        ctx.rotate(Math.PI / 2);
        ctx.drawImage(src, 0, 0, bh, bw);
        break;
      case 180:
        ctx.translate(bw, bh);
        ctx.rotate(Math.PI);
        ctx.drawImage(src, 0, 0, bw, bh);
        break;
      case 270:
        ctx.translate(0, bh);
        ctx.rotate(-Math.PI / 2);
        ctx.drawImage(src, 0, 0, bh, bw);
        break;
      default:
        ctx.drawImage(src, 0, 0, bw, bh);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }, [raster, displayWidth, displayHeight, rotation, renderCanvas]);

  const showCanvas = renderCanvas && raster !== null;
  const effectiveStatus: ViewerPaintStatus = raster !== null ? "ready" : rasterStatus;
  const showState = renderCanvas && !showCanvas;

  return (
    <div className={styles.wrapper}>
      {pageLevelNotice !== null && (
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
            {pageLevelNotice === "estimated"
              ? `This reading or observation applies to Page ${page.index + 1} as a whole. Highlighted positions are estimated placements, not localized evidence.`
              : `This reading or observation applies to Page ${page.index + 1} as a whole. No localized bounding coordinates exist for this reader.`}
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
        {showCanvas && (
          <canvas
            ref={canvasRef}
            id={`page-canvas-${page.index}`}
            className={styles.canvas}
            role="img"
            aria-label={`Rendered visual page ${page.index + 1}`}
          />
        )}

        {showState && (
          <div
            id={`page-state-${page.index}`}
            className={styles.pageState}
            role={effectiveStatus === "error" ? "alert" : undefined}
          >
            <span className={styles.pageStateTitle}>
              {effectiveStatus === "loading"
                ? "Rendering page…"
                : effectiveStatus === "error"
                  ? "The page image could not be rendered"
                  : "No original PDF to render"}
            </span>
            {effectiveStatus !== "loading" && (
              <p className={styles.pageStateNote}>
                {effectiveStatus === "error"
                  ? (rasterNote ?? "Rendering failed for this page.")
                  : "This report has no verified source PDF attached, so there is no page image to paint. Recorded positions still appear as highlights; attach the original PDF to see it."}
              </p>
            )}
          </div>
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
                (selectedFinding.alignment === "ambiguous" || isOrderOnlyFinding(selectedFinding));
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
