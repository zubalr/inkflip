import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Button from "../../components/Controls/Button";
import styles from "./RegionEditor.module.css";
import { SELECTION_COPY } from "../open/copy";
import type { PageMeta } from "../open/types";
import {
  canonicalBoxToDisplay,
  displaySize,
  displayToCanonical,
  draggedBox,
  paddedRasterRegion,
  validateRegionBox,
  type RegionBox,
} from "./region";

/** Bounded raster the editor draws and measures against. */
export interface RegionRaster {
  readonly widthPx: number;
  readonly heightPx: number;
  /** Actual px/pt used by the render (post-clamp). */
  readonly scalePxPerPt: number;
  /** RGBA pixels — drawn to the canvas by the editor. */
  readonly imageData?: Uint8ClampedArray;
  /** Render limitations worth surfacing (e.g. downsampling). */
  readonly limitations?: readonly string[];
}

export interface RegionEditorProps {
  readonly page: PageMeta;
  readonly raster: RegionRaster | null;
  /** Currently committed box on this page (canonical pt), or null. */
  readonly box: RegionBox | null;
  readonly label: string;
  readonly onCommit: (box: RegionBox, label: string) => void;
  readonly onClear: () => void;
  readonly onLabelChange?: (label: string) => void;
}

const clamp = (v: number, lo: number, hi: number): number =>
  Math.min(hi, Math.max(lo, v));

/**
 * Region selection on a real bounded raster. Dragging produces a
 * canonical-space box (display px → display pt → canonical pt through the
 * document rotation); keyboard input goes through explicit validation —
 * out-of-bounds or degenerate values are rejected with a visible reason,
 * never clamped into place. The committed region and its OCR padding are
 * outlined separately per READER_ADAPTER_CONTRACT.
 */
export function RegionEditor({
  page,
  raster,
  box,
  label,
  onCommit,
  onClear,
  onLabelChange,
}: RegionEditorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const surfaceRef = useRef<HTMLDivElement>(null);
  const dragOrigin = useRef<readonly [number, number] | null>(null);
  const [draft, setDraft] = useState<RegionBox | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<[string, string, string, string]>([
    "",
    "",
    "",
    "",
  ]);

  const [dispW, dispH] = displaySize(page);
  const scale = raster?.scalePxPerPt ?? 1;

  // Draw the adapter raster once it arrives.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !raster?.imageData) return;
    canvas.width = raster.widthPx;
    canvas.height = raster.heightPx;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.putImageData(
      new ImageData(
        new Uint8ClampedArray(raster.imageData),
        raster.widthPx,
        raster.heightPx,
      ),
      0,
      0,
    );
  }, [raster]);

  // Keep the numeric fields in sync with the committed region.
  useEffect(() => {
    if (box) {
      setFields([
        String(box[0]),
        String(box[1]),
        String(box[2]),
        String(box[3]),
      ]);
    }
  }, [box]);

  /** CSS px on the surface -> clamped canonical pt. */
  const toCanonical = useCallback(
    (cssX: number, cssY: number): readonly [number, number] => {
      const px = clamp(cssX, 0, raster?.widthPx ?? 0);
      const py = clamp(cssY, 0, raster?.heightPx ?? 0);
      const [cx, cy] = displayToCanonical(px / scale, py / scale, page);
      return [clamp(cx, 0, page.widthPt), clamp(cy, 0, page.heightPt)];
    },
    [page, raster, scale],
  );

  const surfacePoint = useCallback(
    (event: React.PointerEvent): readonly [number, number] => {
      const rect = surfaceRef.current?.getBoundingClientRect();
      const x = event.clientX - (rect?.left ?? 0);
      const y = event.clientY - (rect?.top ?? 0);
      return [x, y];
    },
    [],
  );

  const onPointerDown = useCallback(
    (event: React.PointerEvent) => {
      if (!raster) return;
      event.preventDefault();
      surfaceRef.current?.setPointerCapture(event.pointerId);
      const [x, y] = surfacePoint(event);
      dragOrigin.current = toCanonical(x, y);
      setDraft(null);
      setError(null);
    },
    [raster, surfacePoint, toCanonical],
  );

  const onPointerMove = useCallback(
    (event: React.PointerEvent) => {
      if (dragOrigin.current === null) return;
      const [x, y] = surfacePoint(event);
      const [cx, cy] = toCanonical(x, y);
      setDraft(draggedBox(dragOrigin.current[0], dragOrigin.current[1], cx, cy));
    },
    [surfacePoint, toCanonical],
  );

  const onPointerUp = useCallback(
    (event: React.PointerEvent) => {
      if (dragOrigin.current === null) return;
      const [x, y] = surfacePoint(event);
      const [cx, cy] = toCanonical(x, y);
      const final = draggedBox(dragOrigin.current[0], dragOrigin.current[1], cx, cy);
      dragOrigin.current = null;
      setDraft(null);
      const verdict = validateRegionBox(final, page);
      if (!verdict.ok) {
        setError(verdict.reason);
        return;
      }
      onCommit(verdict.box, label);
    },
    [surfacePoint, toCanonical, page, onCommit, label],
  );

  const applyFields = useCallback(() => {
    const nums = fields.map((f) => Number.parseFloat(f)) as [
      number,
      number,
      number,
      number,
    ];
    const verdict = validateRegionBox(nums, page);
    if (!verdict.ok) {
      setError(verdict.reason);
      return;
    }
    setError(null);
    onCommit(verdict.box, label);
  }, [fields, page, onCommit, label]);

  const shown = draft ?? box;
  const displayRect = useMemo(() => {
    if (!shown) return null;
    const d = canonicalBoxToDisplay(shown, page);
    return {
      x: d[0] * scale,
      y: d[1] * scale,
      w: (d[2] - d[0]) * scale,
      h: (d[3] - d[1]) * scale,
    };
  }, [shown, page, scale]);

  const padded = useMemo(() => {
    if (!box || !raster) return null;
    const paddedPx = paddedRasterRegion(
      canonicalBoxToDisplay(box, page),
      scale,
      raster.widthPx,
      raster.heightPx,
    );
    return {
      x: paddedPx.x0,
      y: paddedPx.y0,
      w: paddedPx.x1 - paddedPx.x0,
      h: paddedPx.y1 - paddedPx.y0,
      padPx: paddedPx.padPx,
    };
  }, [box, raster, page, scale]);

  const fieldNames = ["x0", "y0", "x1", "y1"] as const;
  const fieldLabels = ["Left pt", "Top pt", "Right pt", "Bottom pt"];

  return (
    <section className={styles.editor} aria-label={SELECTION_COPY.region}>
      <h3 className={styles.title}>{SELECTION_COPY.region}</h3>
      <p className={styles.hint}>{SELECTION_COPY.regionHint}</p>

      <div className={styles.surfaceWrap}>
        <div
          ref={surfaceRef}
          className={styles.surface}
          style={{
            width: raster ? `${raster.widthPx}px` : `${dispW}px`,
            height: raster ? `${raster.heightPx}px` : `${dispH}px`,
          }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          data-testid="region-surface"
          role="img"
          aria-label={`Page ${page.index + 1} render for region selection`}
        >
          <canvas
            ref={canvasRef}
            className={styles.canvas}
            width={raster?.widthPx ?? 0}
            height={raster?.heightPx ?? 0}
            data-testid="region-canvas"
          />
          {displayRect && (
            <div
              className={styles.regionRect}
              style={{
                left: `${displayRect.x}px`,
                top: `${displayRect.y}px`,
                width: `${displayRect.w}px`,
                height: `${displayRect.h}px`,
              }}
              data-testid="region-rect"
              aria-hidden="true"
            />
          )}
          {padded && (
            <div
              className={styles.paddedRect}
              style={{
                left: `${padded.x}px`,
                top: `${padded.y}px`,
                width: `${padded.w}px`,
                height: `${padded.h}px`,
              }}
              data-testid="region-padded"
              aria-hidden="true"
            />
          )}
        </div>
      </div>

      {raster?.limitations && raster.limitations.length > 0 && (
        <p className={styles.limitation} data-testid="raster-limitation">
          {raster.limitations.join(" ")}
        </p>
      )}

      <div className={styles.fields} role="group" aria-label="Region bounds in points">
        {fieldNames.map((name, i) => (
          <label key={name} className={styles.fieldLabel}>
            {fieldLabels[i]}
            <input
              className={styles.fieldInput}
              type="number"
              step="any"
              value={fields[i]}
              data-testid={`region-${name}`}
              onChange={(event) => {
                const next = [...fields] as typeof fields;
                next[i] = event.currentTarget.value;
                setFields(next);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") applyFields();
              }}
            />
          </label>
        ))}
        <Button variant="secondary" size="small" onClick={applyFields} data-testid="region-apply">
          Set region
        </Button>
        {box && (
          <Button variant="ghost" size="small" onClick={onClear} data-testid="region-clear">
            Clear region
          </Button>
        )}
      </div>

      <label className={styles.labelField}>
        Region label
        <input
          className={styles.fieldInput}
          type="text"
          maxLength={200}
          value={label}
          data-testid="region-label"
          onChange={(event) => onLabelChange?.(event.currentTarget.value)}
        />
      </label>

      {error && (
        <p className={styles.error} role="alert" data-testid="region-error">
          {error}
        </p>
      )}
      {box && (
        <p className={styles.committed} data-testid="region-committed">
          Region on page {page.index + 1}: {box.map((v) => Math.round(v * 100) / 100).join(", ")} pt
          {padded && ` · padding ${Math.round(padded.padPx)} px`}
        </p>
      )}
      {box && <p className={styles.hint}>{SELECTION_COPY.regionExpanded}</p>}
    </section>
  );
}

export default RegionEditor;
