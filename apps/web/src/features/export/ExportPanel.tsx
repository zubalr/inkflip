/**
 * ExportPanel — pre-export preview and download surface (T16).
 *
 * Mirrors the Journey D flow: an inclusion allowlist (original PDF,
 * filename, notes, page renders default off), a preview measured on the
 * final projected object, then explicit JSON/HTML downloads. There is no
 * share link or upload path. Copy strings are the `export.*` keys from
 * planning/product/copy.json kept verbatim.
 *
 * The panel talks only to {@link ExportEngine} — the structural port in
 * `types.ts` — so wiring to `@inkflip/reports/export` happens at app
 * composition, not inside this component.
 */
import React, { useEffect, useId, useMemo, useState } from "react";
import Button from "../../components/Controls/Button";
import Notice from "../../components/Controls/Notice";
import styles from "./ExportPanel.module.css";
import type { ExportAvailability, ExportEngine, ExportRequestLike } from "./types";
import { ExportController } from "./controller";

/** Copy keys from planning/product/copy.json (verbatim strings). */
const COPY = {
  title: "Preview what you will export",
  selected: "Selected evidence",
  full: "Full run evidence",
  source: "Include the original PDF",
  sourceWarning:
    "This includes every page and any hidden content in the original file. A crop is not a safe redaction.",
  filename: "Include original filename",
  notes: "Include my notes",
  pageRenders: "Full-page images included",
  pageRendersWarning:
    "These images show complete pages, not only the selected crop. Review them before sharing.",
  cropWarning:
    "Review the actual crop for nearby private information. Cropping is not a redaction guarantee.",
  html: "Download readable HTML",
  json: "Download portable JSON",
  replayAbsent:
    "Original PDF not included. This report can be inspected, but replay requires the matching original.",
  replayPresent: "Original PDF included. Replay also requires the recorded reader environment.",
  noAssets: "Screenshot-only diagnostic · not replayable",
  success: "Report downloaded. Downloads are managed by your browser.",
} as const;

export interface ExportPanelProps {
  /** The export engine port — bound to @inkflip/reports/export. */
  readonly engine: ExportEngine;
  /** The recorded run report to export from. */
  readonly source: unknown;
  /** Original bytes provider for the explicit source opt-in. */
  readonly sourcePdfBytes?: () => Uint8Array | null;
  /** Download sink; defaults to a Blob + anchor download. */
  readonly onDownload?: (name: string, text: string) => void;
}

function defaultDownload(name: string, text: string): void {
  const blob = new Blob([text], {
    type: name.endsWith(".json") ? "application/json" : "text/html",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.rel = "noopener";
  a.click();
  URL.revokeObjectURL(url);
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
}

function Option({
  id,
  label,
  checked,
  disabled,
  hint,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  disabled?: string | null;
  hint?: string;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className={styles.option}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled != null}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(e: { target: { checked: boolean } }) => onChange(e.target.checked)}
      />
      <label htmlFor={id}>{label}</label>
      {(hint || disabled) && (
        <p id={`${id}-hint`} className={styles.optionHint}>
          {disabled ?? hint}
        </p>
      )}
    </div>
  );
}

export function ExportPanel({
  engine,
  source,
  sourcePdfBytes,
  onDownload = defaultDownload,
}: ExportPanelProps) {
  const baseId = useId();
  const controller = useMemo(
    () =>
      new ExportController(engine, source, {
        sourcePdfBytes: sourcePdfBytes ?? (() => null),
      }),
    [engine, source, sourcePdfBytes],
  );
  const [prevController, setPrevController] = useState(controller);
  const [state, setState] = useState(controller.state);
  const [downloaded, setDownloaded] = useState<string | null>(null);

  if (prevController !== controller) {
    setPrevController(controller);
    setState(controller.state);
    setDownloaded(null);
  }

  useEffect(() => {
    setState(controller.state);
  }, [controller]);

  const setRequest = (patch: Partial<ExportRequestLike>) => setState(controller.setOption(patch));

  const availability: ExportAvailability = state.availability;
  const preview = state.preview;
  const counts = preview?.counts;

  const download = (format: "json" | "html") => {
    const out = format === "json" ? controller.jsonOutput() : controller.htmlOutput();
    onDownload(out.name, out.text);
    setDownloaded(out.name);
  };

  return (
    <section className={styles.panel} aria-labelledby={`${baseId}-title`}>
      <h2 id={`${baseId}-title`} className={styles.title}>
        {COPY.title}
      </h2>

      <fieldset className={styles.options}>
        <legend className={styles.legend}>Inclusion</legend>
        <Option
          id={`${baseId}-source`}
          label={COPY.source}
          checked={state.request.sourcePdf !== null}
          disabled={
            !availability.hasSourcePdf && sourcePdfBytes === undefined
              ? "Original bytes are not available to this run."
              : null
          }
          hint={COPY.sourceWarning}
          onChange={(next) => setState(controller.setSourcePdfWanted(next))}
        />
        <Option
          id={`${baseId}-filename`}
          label={COPY.filename}
          checked={state.request.filename === true}
          disabled={availability.hasFilename ? null : "No filename was recorded."}
          onChange={(next) => setRequest({ filename: next })}
        />
        <Option
          id={`${baseId}-notes`}
          label={COPY.notes}
          checked={state.request.annotations === true}
          disabled={availability.hasAnnotations ? null : "No notes were recorded."}
          onChange={(next) => setRequest({ annotations: next })}
        />
        <Option
          id={`${baseId}-renders`}
          label={COPY.pageRenders}
          checked={state.request.pageRenders === "all"}
          disabled={availability.hasPageRenders ? null : "No full-page images were recorded."}
          hint={COPY.pageRendersWarning}
          onChange={(next) => setRequest({ pageRenders: next ? "all" : "none" })}
        />
      </fieldset>

      {state.error !== null && (
        <Notice type="error" title="Export failed">
          {state.error}
        </Notice>
      )}

      {preview !== null && (
        <div className={styles.preview} aria-live="polite">
          <h3 className={styles.previewTitle}>
            {state.request.scope === "run" ? COPY.full : COPY.selected}
          </h3>
          <dl className={styles.previewGrid}>
            <dt>Findings</dt>
            <dd>{counts?.findings ?? 0}</dd>
            <dt>Readings kept / produced</dt>
            <dd>
              {counts?.retainedOccurrences ?? 0} / {counts?.producedOccurrences ?? 0}
            </dd>
            <dt>Checks complete</dt>
            <dd>
              {counts?.checksCompleted ?? 0} / {counts?.checks ?? 0}
            </dd>
            <dt>Pages selected</dt>
            <dd>
              {counts?.pagesSelected ?? 0} / {counts?.pageCount ?? 0}
            </dd>
            <dt>Crops / page images</dt>
            <dd>
              {counts?.crops ?? 0} / {counts?.pageRenders ?? 0}
            </dd>
            <dt>JSON size</dt>
            <dd>{formatBytes(preview.bytes.jsonBytes)}</dd>
            <dt>Decoded assets</dt>
            <dd>{formatBytes(preview.bytes.decodedAssetBytes)}</dd>
          </dl>
          <p className={styles.manifest}>
            Included: {preview.included.join(", ")}. Excluded: {preview.omissions.join(" ")}
          </p>
          <p className={styles.replay}>
            {preview.mode === "diagnostic"
              ? COPY.noAssets
              : preview.sourcePdfIncluded
                ? COPY.replayPresent
                : COPY.replayAbsent}
          </p>
          {preview.sourcePdfIncluded && <p className={styles.warning}>{COPY.sourceWarning}</p>}
          {(counts?.crops ?? 0) > 0 && <p className={styles.warning}>{COPY.cropWarning}</p>}
          {(counts?.pageRenders ?? 0) > 0 && (
            <p className={styles.warning}>{COPY.pageRendersWarning}</p>
          )}
          {!preview.withinLimits && (
            <p className={styles.warning}>
              This export exceeds the portable bundle limits and cannot be reopened in the browser;
              reduce the selection.
            </p>
          )}
          {state.sourceUnavailable && (
            <p className={styles.warning}>
              Original bytes unavailable — this export is evidence-only.
            </p>
          )}
        </div>
      )}

      <div className={styles.actions}>
        <Button
          variant="primary"
          onClick={() => download("json")}
          disabled={preview === null || !preview.withinLimits}
          disabledReason="Projection failed or exceeds the portable limits."
        >
          {COPY.json}
        </Button>
        <Button
          variant="secondary"
          onClick={() => download("html")}
          disabled={preview === null}
          disabledReason="Projection failed."
        >
          {COPY.html}
        </Button>
      </div>
      {downloaded !== null && (
        <p className={styles.success} role="status">
          {COPY.success}
        </p>
      )}
    </section>
  );
}

export default ExportPanel;
