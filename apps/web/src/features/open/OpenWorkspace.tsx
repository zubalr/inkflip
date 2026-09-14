import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Button from "../../components/Controls/Button";
import Notice from "../../components/Controls/Notice";
import ReplaceConfirmDialog from "../../components/Dialogs/ReplaceConfirmDialog";
import styles from "./OpenWorkspace.module.css";
import { LIMITS_COPY, OPEN_COPY, SELECTION_COPY, WORKSPACE_COPY, fill } from "./copy";
import { FileDrop, type OpenPhase } from "./FileDrop";
import type { OpenController } from "./controller";
import type {
  FileCandidate,
  OpenError,
  OpenHost,
  OpenedDocumentInfo,
} from "./types";
import { PageSelection } from "../selection/pages";
import { PagePicker } from "../selection/PagePicker";
import {
  RegionEditor,
  type RegionRaster,
} from "../selection/RegionEditor";
import {
  regionToContract,
  type ContractRegion,
  type RegionBox,
} from "../selection/region";
import type { OpenProfile } from "./limits";

/** What a "Compare" action produced — the immutable plan + dispatched jobs. */
export interface PlanOutcome {
  readonly checks: readonly {
    id: string;
    page_index: number;
    capability: string;
    region_id: string | null;
  }[];
  readonly dispatched: readonly {
    jobId: string;
    checkId: string;
    capability: string;
  }[];
  /** Pinned by the coordinator at run start — can never grow silently. */
  readonly selectedPagesTotal: number;
}

export interface OpenWorkspaceProps {
  readonly controller: OpenController;
  /** Host with subscription — satisfied by RunCoordinator. */
  readonly host: OpenHost & {
    subscribe(listener: () => void): () => void;
    snapshot(): { fileState: string; generation: number };
  };
  readonly profile: OpenProfile;
  /** Render one bounded page raster through the real adapter. */
  readonly renderPageRaster?: (
    handle: unknown,
    pageIndex: number,
  ) => Promise<RegionRaster>;
  /** Start a run: build the plan through the adapter and start the host. */
  readonly startRun?: (
    handle: unknown,
    pages: readonly number[],
    regions: ReadonlyMap<number, ContractRegion>,
    options?: { readonly ocrConsent?: boolean },
  ) => PlanOutcome;
}

interface RegionEntry {
  readonly box: RegionBox;
  readonly region: ContractRegion;
  readonly label: string;
}

function byteLabel(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${bytes} bytes`;
}

/**
 * The open+selection workspace composition: drop/replace intake on top, the
 * loaded-file summary beneath it, then what to check — the bounded page
 * picker, the OCR cap/consent decisions the run acts on, and the plan-producing
 * "Check selected pages" action. Every optional or advanced group (region and
 * preview tuning, device limits) sits below that action, so the ordinary path
 * is file → pages → check. Everything the UI shows is derived from the
 * coordinator snapshot and the controller's last outcome — no parallel state
 * can drift (I07).
 */
export function OpenWorkspace({
  controller,
  host,
  profile,
  renderPageRaster,
  startRun,
}: OpenWorkspaceProps) {
  const [view, setView] = useState(() => host.snapshot());
  // Lazy-init from the controller: this component can mount after the
  // `metadata` event already fired (the host decides when to mount it).
  const [doc, setDoc] = useState<OpenedDocumentInfo | null>(
    () => controller.currentDocument,
  );
  const [error, setError] = useState<OpenError | null>(null);
  const [pending, setPending] = useState<FileCandidate | null>(null);
  const [selectionRev, setSelectionRev] = useState(0);
  const [previewPage, setPreviewPage] = useState(0);
  const [raster, setRaster] = useState<RegionRaster | null>(null);
  const [rasterError, setRasterError] = useState<string | null>(null);
  const [regions, setRegions] = useState<ReadonlyMap<number, RegionEntry>>(
    new Map(),
  );
  const [plan, setPlan] = useState<PlanOutcome | null>(null);
  // Mobile OCR is opt-in: the model download and CPU cost are real, so the
  // low-memory profile requires an explicit consent before OCR is planned.
  const [ocrConsent, setOcrConsent] = useState(false);
  // Low-memory mode renders the preview raster only on explicit request.
  const [previewRequested, setPreviewRequested] = useState(false);
  const lowMemory = profile.id === "mobile";

  useEffect(() => host.subscribe(() => setView(host.snapshot())), [host]);

  // The workspace renders the controller's event stream — offers made
  // through any caller (the drop zone, a future host action) surface
  // identically, so the view can never drift from controller state.
  useEffect(
    () =>
      controller.subscribe((event) => {
        if (event.type === "metadata") {
          setDoc(event.document);
          setError(null);
          setPreviewPage(0);
          setRaster(null);
          setRasterError(null);
          setRegions(new Map());
          setPlan(null);
          setOcrConsent(false);
          setPreviewRequested(false);
          setSelectionRev((r) => r + 1);
        } else if (event.type === "rejected") {
          setDoc(null);
          setError(event.error);
          setPlan(null);
          setRegions(new Map());
          setRaster(null);
        } else if (event.type === "clear") {
          // The old handle is gone regardless of what the new offer
          // does next — never show a stale document.
          setDoc(null);
          setPlan(null);
          setRegions(new Map());
          setRaster(null);
        }
      }),
    [controller],
  );

  const fileState = view.fileState;
  const phase: OpenPhase =
    fileState === "validating_file"
      ? "validating"
      : fileState === "loading_metadata"
        ? "metadata"
        : "idle";

  const selection = useMemo(
    () => new PageSelection(doc?.pageCount ?? 0, profile.maxNativePagesPerRun),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rebuild only on a new document identity
    [doc?.sha256, doc?.pageCount, profile.maxNativePagesPerRun],
  );

  const offer = useCallback(
    async (candidate: FileCandidate) => {
      setError(null);
      await controller.offer(candidate);
    },
    [controller],
  );

  const onFile = useCallback(
    (candidate: FileCandidate) => {
      if (doc !== null) {
        // Replacement must be confirmed: it clears the current workspace.
        setPending(candidate);
        return;
      }
      void offer(candidate);
    },
    [doc, offer],
  );

  const confirmReplace = useCallback(() => {
    const candidate = pending;
    setPending(null);
    if (candidate) void offer(candidate);
  }, [pending, offer]);

  // Bounded preview raster for the region editor's page. In low-memory
  // mode it renders only on explicit request — the auto-preview is real
  // work a constrained device may not want.
  useEffect(() => {
    // A new page must never retain the preceding page's pixels while
    // waiting for an explicit low-memory preview request.
    setRaster(null);
    setRasterError(null);
    if (!doc || !renderPageRaster || !controller.currentHandle) return;
    if (lowMemory && !previewRequested) return;
    if (previewPage < 0 || previewPage >= doc.pageCount) return;
    let cancelled = false;
    renderPageRaster(controller.currentHandle, previewPage)
      .then((next) => {
        if (!cancelled) setRaster(next);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setRasterError(
            e instanceof Error ? e.message.slice(0, 160) : "render failed",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [doc, previewPage, controller, renderPageRaster, lowMemory, previewRequested]);

  const regionSeq = useRef(0);
  const commitRegion = useCallback(
    (pageIndex: number, box: RegionBox, label: string) => {
      const page = doc?.pages[pageIndex];
      if (!page) return;
      regionSeq.current += 1;
      const region = regionToContract(
        box,
        page,
        regionSeq.current,
        label.trim() || "Region 1",
      );
      const next = new Map(regions);
      next.set(pageIndex, { box, region, label });
      setRegions(next);
    },
    [doc, regions],
  );

  const clearRegion = useCallback(
    (pageIndex: number) => {
      const next = new Map(regions);
      next.delete(pageIndex);
      setRegions(next);
    },
    [regions],
  );

  const runStart = useCallback(() => {
    if (!startRun || !controller.currentHandle || selection.size === 0) return;
    const contractRegions = new Map<number, ContractRegion>();
    for (const [pageIndex, entry] of regions) {
      if (selection.has(pageIndex)) contractRegions.set(pageIndex, entry.region);
    }
    setPlan(
      startRun(controller.currentHandle, selection.pages(), contractRegions, {
        ocrConsent: !lowMemory || ocrConsent,
      }),
    );
  }, [startRun, controller, selection, regions, selectionRev, lowMemory, ocrConsent]);

  const selectedPages = useMemo(
    () => selection.pages(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selection, selectionRev],
  );
  const selectedRegionPages = useMemo(
    () => selectedPages.filter((p) => regions.has(p)),
    [selectedPages, regions],
  );
  const selectedNonRegionPages = useMemo(
    () => selectedPages.filter((p) => !regions.has(p)),
    [selectedPages, regions],
  );
  const plannedOcrPages = useMemo(
    () =>
      [...selectedRegionPages, ...selectedNonRegionPages].slice(
        0,
        profile.maxOcrPagesPerRun,
      ),
    [selectedRegionPages, selectedNonRegionPages, profile.maxOcrPagesPerRun],
  );
  const omittedRegionPages = useMemo(
    () => selectedRegionPages.filter((p) => !plannedOcrPages.includes(p)),
    [selectedRegionPages, plannedOcrPages],
  );

  const previewMeta = doc?.pages[previewPage] ?? null;
  const previewRegion = regions.get(previewPage) ?? null;

  return (
    <div className={styles.workspace}>
      <FileDrop phase={phase} onFile={onFile} hasDocument={doc !== null} />

      {error && (
        <Notice type="error" title={error.message} id={`open-error-${error.kind}`}>
          {error.detail && (
            <span className={styles.errorDetail} data-testid="open-error-detail">
              {error.detail}
            </span>
          )}
        </Notice>
      )}

      {doc !== null && (
        <section className={styles.document} aria-label="Open document">
          <div className={styles.summary}>
            <div className={styles.summaryText}>
              <p className={styles.summaryLabel}>{WORKSPACE_COPY.fileLabel}</p>
              <p className={styles.docLabel} data-testid="doc-label">
                {doc.label}
              </p>
              <p className={styles.docMeta} data-testid="doc-meta">
                Local file · {doc.pageCount}{" "}
                {doc.pageCount === 1 ? "page" : "pages"} ·{" "}
                {byteLabel(doc.byteLength)} · sha256 …{doc.sha256.slice(-8)}
              </p>
            </div>
            <div className={styles.docActions}>
              <Button
                variant="secondary"
                size="small"
                onClick={() => {
                  controller.clear();
                  setDoc(null);
                  setError(null);
                  setPlan(null);
                  setRegions(new Map());
                  setRaster(null);
                }}
                data-testid="clear-file"
              >
                {OPEN_COPY.clearAction}
              </Button>
            </div>
          </div>

          <PagePicker
            selection={selection}
            onChange={() => setSelectionRev((r) => r + 1)}
          />

          {/* The OCR cap and the opt-in consent are decisions the run acts
              on, not advanced tuning: they stay visible and keep their place
              ahead of the action. */}
          {omittedRegionPages.length > 0 ? (
            <Notice
              type="warning"
              title={`OCR is capped at ${profile.maxOcrPagesPerRun} pages per run`}
              id="ocr-limit-notice"
            >
              {`Explicit regions on page ${omittedRegionPages
                .map((p) => p + 1)
                .join(", ")} exceed the ${profile.maxOcrPagesPerRun}-page OCR limit. They will be checked with native text and rendering, but OCR is omitted.`}
            </Notice>
          ) : selectedPages.length > profile.maxOcrPagesPerRun ? (
            <Notice
              type="info"
              title={`OCR is capped at ${profile.maxOcrPagesPerRun} pages per run`}
              id="ocr-limit-notice"
            >
              {`OCR is capped at ${profile.maxOcrPagesPerRun} pages per run (prioritizing explicit regions). Pages ${plannedOcrPages
                .map((p) => p + 1)
                .join(", ")} will include OCR; all ${selectedPages.length} selected pages will be checked with native text and rendering.`}
            </Notice>
          ) : null}

          {lowMemory && (
            <div className={styles.ocrConsent} data-testid="ocr-consent-row">
              <p className={styles.ocrConsentPlain}>{WORKSPACE_COPY.ocrPlain}</p>
              <label className={styles.ocrConsentLabel}>
                <input
                  type="checkbox"
                  checked={ocrConsent}
                  onChange={(event) => setOcrConsent(event.currentTarget.checked)}
                  data-testid="ocr-consent"
                />
                {LIMITS_COPY.ocrConsentLabel}
              </label>
              <p className={styles.ocrConsentHint} data-testid="ocr-consent-hint">
                {LIMITS_COPY.ocrConsentHint}
              </p>
            </div>
          )}

          {/* The primary action closes the selection step: every optional or
              advanced group (region/preview tuning, device limits) sits below
              it. */}
          <div className={styles.startRow}>
            <Button
              variant="primary"
              onClick={runStart}
              disabled={selection.size === 0 || !startRun}
              disabledReason={
                selection.size === 0 ? "Select at least one page" : undefined
              }
              data-testid="start-run"
            >
              {SELECTION_COPY.start}
            </Button>
            <span className={styles.startNote}>
              {fill(SELECTION_COPY.summary, {
                selected: String(selection.size),
                total: String(doc.pageCount),
              })}
            </span>
          </div>

          {/* Optional tuning: the preview page and the region editor. Open by
              default so every control stays visible and reachable; collapsing
              it hides the pixels without unmounting the editor's state. */}
          <details className={styles.tuning} open>
            <summary className={styles.tuningSummary}>
              <span className={styles.disclosureTitle}>
                {WORKSPACE_COPY.tuning}
              </span>
              <span className={styles.disclosureHint}>
                {WORKSPACE_COPY.tuningHint}
              </span>
            </summary>
            <div className={styles.tuningBody}>
              <div className={styles.previewRow}>
                <label className={styles.previewLabel}>
                  Preview page
                  <input
                    className={styles.previewInput}
                    type="number"
                    min={1}
                    max={doc.pageCount}
                    value={previewPage + 1}
                    data-testid="preview-page"
                    onChange={(event) => {
                      const n = Number.parseInt(event.currentTarget.value, 10);
                      if (Number.isInteger(n) && n >= 1 && n <= doc.pageCount) {
                        setPreviewPage(n - 1);
                        setPreviewRequested(false);
                      }
                    }}
                  />
                </label>
                {!selection.has(previewPage) ? (
                  <span className={styles.previewNote} data-testid="preview-notselected">
                    Page {previewPage + 1} is not selected — its region will not be checked.
                  </span>
                ) : omittedRegionPages.includes(previewPage) ? (
                  <span className={styles.previewNote} data-testid="preview-ocromitted">
                    Page {previewPage + 1} region exceeds the {profile.maxOcrPagesPerRun}-page OCR cap — native text and render checks will run, but OCR is omitted.
                  </span>
                ) : null}
              </div>

              {lowMemory && !previewRequested && (
                <div className={styles.previewRequest}>
                  <Button
                    variant="secondary"
                    size="small"
                    onClick={() => setPreviewRequested(true)}
                    data-testid="render-preview"
                  >
                    {LIMITS_COPY.renderPreview}
                  </Button>
                </div>
              )}

              {rasterError && (
                <Notice type="warning" title="Preview render failed" id="raster-error">
                  {rasterError}
                </Notice>
              )}

              {previewMeta && (
                <RegionEditor
                  page={previewMeta}
                  raster={raster}
                  box={previewRegion?.box ?? null}
                  label={previewRegion?.label ?? "Region 1"}
                  onCommit={(box, label) => commitRegion(previewPage, box, label)}
                  onClear={() => clearRegion(previewPage)}
                  onLabelChange={(next) => {
                    if (!previewRegion) return;
                    const trimmed = next.trim() || "Region 1";
                    const updated = new Map(regions);
                    updated.set(previewPage, {
                      ...previewRegion,
                      label: next,
                      region: {
                        ...previewRegion.region,
                        label: trimmed.slice(0, 200),
                      },
                    });
                    setRegions(updated);
                  }}
                />
              )}
            </div>
          </details>

          {/* Reference material, not part of the ordinary path: the bounds
              this device enforces are stated once, below the action. The
              summary keeps the device mode readable while the individual
              bounds stay one disclosure away. */}
          <details
            className={styles.limits}
            data-testid="run-limits"
            data-profile={profile.id}
          >
            <summary className={styles.limitsSummary}>
              <span className={styles.disclosureTitle}>{LIMITS_COPY.title}</span>
              <span className={styles.limitsMode}>
                {fill(LIMITS_COPY.mode, {
                  mode:
                    profile.id === "mobile"
                      ? "mobile (low-memory mode)"
                      : "desktop",
                })}
              </span>
            </summary>
            <ul className={styles.limitsList}>
              <li>
                {fill(LIMITS_COPY.file, {
                  limit: byteLabel(profile.maxFileBytes),
                })}
              </li>
              <li>
                {fill(LIMITS_COPY.pages, {
                  limit: profile.maxDocumentPages.toLocaleString(),
                })}
              </li>
              <li>
                {fill(LIMITS_COPY.native, {
                  limit: String(profile.maxNativePagesPerRun),
                })}
              </li>
              <li>
                {fill(LIMITS_COPY.ocr, {
                  limit: String(profile.maxOcrPagesPerRun),
                })}
              </li>
              <li>
                {fill(LIMITS_COPY.raster, {
                  limit: profile.maxRasterPixels.toLocaleString(),
                })}
              </li>
            </ul>
          </details>

          {plan && (
            <section className={styles.plan} aria-label="Check plan" data-testid="plan">
              <h3 className={styles.planTitle}>
                Planned checks · {plan.selectedPagesTotal}{" "}
                {plan.selectedPagesTotal === 1 ? "page" : "pages"} selected
              </h3>
              {/* The heading above stays visible; the raw check ids and the
                  dispatch intents are one disclosure down, still mounted. */}
              <details className={styles.planDetails}>
                <summary className={styles.planSummary}>
                  {WORKSPACE_COPY.planDetails}
                </summary>
                <ul className={styles.planList} data-testid="plan-checks">
                  {plan.checks.map((check) => (
                    <li key={check.id} data-check-id={check.id} data-page={check.page_index} data-capability={check.capability} data-region={check.region_id ?? ""}>
                      <code>{check.id}</code> — page {check.page_index + 1},{" "}
                      {check.capability}
                      {check.region_id ? ` · region ${check.region_id}` : ""}
                    </li>
                  ))}
                </ul>
                {plan.dispatched.length > 0 && (
                  <ul className={styles.planList} data-testid="plan-dispatched">
                    {plan.dispatched.map((job) => (
                      <li key={job.jobId}>
                        dispatched {job.checkId} on {job.jobId}
                      </li>
                    ))}
                  </ul>
                )}
              </details>
            </section>
          )}
        </section>
      )}

      <ReplaceConfirmDialog
        isOpen={pending !== null}
        onCancel={() => setPending(null)}
        onConfirm={confirmReplace}
      />
    </div>
  );
}

export default OpenWorkspace;
