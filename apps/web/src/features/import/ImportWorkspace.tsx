/**
 * ImportWorkspace (T22) — the strict local report reopen view.
 *
 * Renders ONLY controller-validated state. Every report-controlled
 * string lands in a text node (React escapes it) — `<bdi>` additionally
 * isolates direction — and images come only from the gate's sanitized
 * PNG re-encode as a `data:` URL. No `innerHTML`, no autolinking, no
 * report-driven URLs, paths, commands, or executable names.
 *
 * Layout: report intake (real file input, local-only copy) → failure
 * notice → report panel (identity, scope/omissions, coverage, readers,
 * source/replay state, findings, annotations, crops, limitations) →
 * compare panel (two explicit local report selections + verdict).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import Button from "../../components/Controls/Button";
import Notice from "../../components/Controls/Notice";
import ModalDialog from "../../components/Dialogs/ModalDialog";
import { COMPARE_COPY, IMPORT_COPY, fill } from "./copy";
import type { ImportController, CompareState } from "./controller";
import type {
  ImportFailureLike,
  ImportHost,
  ReplayViewLike,
  ReportCandidate,
  ReportViewLike,
} from "./types";
import styles from "./ImportWorkspace.module.css";

export interface ImportWorkspaceProps {
  readonly controller: ImportController;
  /** Host with subscription — satisfied by RunCoordinator. */
  readonly host: ImportHost & {
    subscribe(listener: () => void): () => void;
    snapshot(): { fileState: string; generation: number };
  };
}

interface OpenedState {
  readonly view: ReportViewLike;
  readonly replay: ReplayViewLike;
}

function failureMessage(failure: ImportFailureLike): string {
  if (failure.kind === "unsupported_version" && failure.version !== null) {
    return fill(IMPORT_COPY.version, { version: failure.version });
  }
  return IMPORT_COPY.invalid;
}

/** Hidden real file input + button — same-file reselection supported. */
function FilePick({
  testId,
  accept,
  label,
  onFile,
  disabled = false,
}: {
  readonly testId: string;
  readonly accept: string;
  readonly label: string;
  readonly onFile: (file: File) => void;
  readonly disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <span className={styles.pick}>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className={styles.hiddenInput}
        aria-label={label}
        disabled={disabled}
        data-testid={testId}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          // Reset so choosing the same file twice still fires change.
          event.currentTarget.value = "";
          if (file) onFile(file);
        }}
      />
      <Button variant="secondary" onClick={() => inputRef.current?.click()} disabled={disabled}>
        {label}
      </Button>
    </span>
  );
}

function ReportPanel({ opened }: { readonly opened: OpenedState }) {
  const { view } = opened;
  return (
    <section className={styles.report} aria-label="Imported report" data-testid="import-report">
      <header className={styles.reportHeader}>
        <div>
          <p className={styles.reportTitle} data-testid="report-title">
            <bdi>{view.title}</bdi>
          </p>
          <p className={styles.reportMeta} data-testid="report-id">
            report <bdi>{view.reportId.slice(0, 16)}</bdi>… · document{" "}
            <bdi>{view.document.sha256.slice(-12)}</bdi> · {view.document.pageCount} page
            {view.document.pageCount === 1 ? "" : "s"} · {view.document.byteLength} bytes
          </p>
        </div>
      </header>

      <div className={styles.panel} data-testid="report-scope">
        <p className={styles.panelTitle}>
          Export scope: <bdi>{view.scope.mode}</bdi> · <bdi>{view.scope.scope}</bdi> · replay{" "}
          <bdi>{view.scope.replay}</bdi>
        </p>
        <ul className={styles.chips} data-testid="scope-included">
          {view.scope.included.map((item) => (
            <li key={item} className={styles.chip}>
              <bdi>{item}</bdi>
            </li>
          ))}
        </ul>
        {view.scope.omissions.length > 0 && (
          <ul className={styles.omissions} data-testid="scope-omissions">
            {view.scope.omissions.map((item, index) => (
              <li key={index}>
                <bdi>{item}</bdi>
              </li>
            ))}
          </ul>
        )}
      </div>

      <dl className={styles.coverage} data-testid="report-coverage">
        <div>
          <dt>checks</dt>
          <dd data-testid="coverage-checks">{view.coverage.checks}</dd>
        </div>
        <div>
          <dt>completed</dt>
          <dd data-testid="coverage-completed">{view.coverage.checksCompleted}</dd>
        </div>
        <div>
          <dt>unsupported</dt>
          <dd data-testid="coverage-unsupported">{view.coverage.checksUnsupported}</dd>
        </div>
        <div>
          <dt>produced</dt>
          <dd data-testid="coverage-produced">{view.coverage.producedOccurrences}</dd>
        </div>
        <div>
          <dt>retained</dt>
          <dd data-testid="coverage-retained">{view.coverage.retainedOccurrences}</dd>
        </div>
        <div>
          <dt>pages</dt>
          <dd data-testid="coverage-pages">
            {view.coverage.pagesSelected} of {view.coverage.pageCount}
          </dd>
        </div>
      </dl>

      <div className={styles.panel} data-testid="report-readers">
        <p className={styles.panelTitle}>Recorded readers</p>
        <ul className={styles.readerList}>
          {view.readers.map((reader) => (
            <li key={reader.id} data-testid={`reader-${reader.id}`}>
              <bdi>{reader.label}</bdi> · <bdi>{reader.method}</bdi> ·{" "}
              <bdi>{reader.environment}</bdi>{" "}
              <span
                className={reader.installed ? styles.badgeOk : styles.badgeMissing}
                data-testid={
                  reader.installed ? `reader-installed-${reader.id}` : `reader-missing-${reader.id}`
                }
              >
                {reader.installed ? "installed" : "unavailable"}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function SourcePanel({
  opened,
  sourceError,
  sourceBusy,
  onSource,
}: {
  readonly opened: OpenedState;
  readonly sourceError: string | null;
  readonly sourceBusy: boolean;
  readonly onSource: (file: File) => void;
}) {
  const { replay } = opened;
  const sourceKind = replay.source;
  return (
    <section className={styles.panel} aria-label="Original source" data-testid="source-panel">
      <p className={styles.panelTitle}>Original PDF</p>
      {sourceKind === "missing" && (
        <>
          <p data-testid="source-missing">{IMPORT_COPY.sourceMissing}</p>
          <FilePick
            testId="source-file-input"
            accept="application/pdf,.pdf"
            label={IMPORT_COPY.sourceChoose}
            onFile={onSource}
            disabled={sourceBusy}
          />
        </>
      )}
      {sourceKind === "attached" && (
        <p data-testid="source-attached">
          The matching original is attached locally. It stays on this device.
        </p>
      )}
      {sourceKind === "embedded" && (
        <p data-testid="source-embedded">Original PDF included in this report.</p>
      )}
      {sourceKind === "not_applicable" && <p data-testid="source-none">{IMPORT_COPY.noAssets}</p>}
      {sourceError !== null && (
        <Notice type="error" title={IMPORT_COPY.sourceMismatch} id="source-mismatch">
          <span className={styles.errorDetail} data-testid="source-error-detail">
            {sourceError}
          </span>
        </Notice>
      )}
      <p className={styles.hint} data-testid="source-nofetch">
        {IMPORT_COPY.nofetch}
      </p>
    </section>
  );
}

function ReplayPanel({ replay }: { readonly replay: ReplayViewLike }) {
  return (
    <section className={styles.panel} aria-label="Replay state" data-testid="replay-panel">
      <p className={styles.panelTitle}>Replay</p>
      {replay.source === "not_applicable" ? (
        <p data-testid="replay-state">{IMPORT_COPY.noAssets}</p>
      ) : replay.source === "missing" ? (
        <p data-testid="replay-state">{IMPORT_COPY.replayAbsent}</p>
      ) : (
        <p data-testid="replay-state">{IMPORT_COPY.replayPresent}</p>
      )}
      {replay.readersMissing.length > 0 && (
        <div data-testid="replay-missing">
          <p className={styles.hint}>
            Recorded readers not installed on this device — replay cannot substitute them:
          </p>
          <ul className={styles.omissions} data-testid="replay-missing-readers">
            {replay.readersMissing.map((label) => (
              <li key={label}>
                <bdi>{label}</bdi>
              </li>
            ))}
          </ul>
        </div>
      )}
      {replay.ready && (
        <p className={styles.hint} data-testid="replay-ready">
          Original bytes and every recorded reader are present locally — a replay may proceed
          against the recorded environment.
        </p>
      )}
    </section>
  );
}

function FindingsPanel({ view }: { readonly view: ReportViewLike }) {
  return (
    <section className={styles.panel} data-testid="report-findings">
      <p className={styles.panelTitle}>Findings ({view.findings.length})</p>
      {view.findings.map((finding) => (
        <article key={finding.id} className={styles.finding} data-testid={`finding-${finding.id}`}>
          <p className={styles.findingTitle}>
            <bdi>{finding.title}</bdi>
          </p>
          <p className={styles.findingMeta}>
            <bdi>{finding.kind}</bdi> · page {finding.pageIndex + 1} ·{" "}
            <bdi>{finding.alignment}</bdi> · <bdi>{finding.priority}</bdi>
          </p>
          <p className={styles.findingBody}>
            <bdi>{finding.explanation}</bdi>
          </p>
          <p className={styles.findingMeta}>
            Basis: <bdi>{finding.basis}</bdi>
          </p>
          {finding.occurrences.map((occurrence) => (
            <div
              key={occurrence.id}
              className={styles.occurrence}
              data-testid={`occurrence-${occurrence.id}`}
            >
              <p className={styles.findingMeta}>
                <bdi>{occurrence.readerLabel}</bdi> · page {occurrence.pageIndex + 1} · geometry{" "}
                <bdi>{occurrence.geometryPrecision}</bdi>
              </p>
              <p className={styles.findingBody}>
                raw “<bdi data-testid={`occurrence-raw-${occurrence.id}`}>{occurrence.rawText}</bdi>
                ”
                {occurrence.normalizedText !== occurrence.rawText && (
                  <>
                    {" "}
                    · normalized “<bdi>{occurrence.normalizedText}</bdi>”
                  </>
                )}
              </p>
            </div>
          ))}
          {finding.limitations.length > 0 && (
            <ul className={styles.omissions}>
              {finding.limitations.map((item, index) => (
                <li key={index}>
                  <bdi>{item}</bdi>
                </li>
              ))}
            </ul>
          )}
        </article>
      ))}
    </section>
  );
}

export function ImportWorkspace({ controller, host }: ImportWorkspaceProps) {
  const [view, setView] = useState(() => host.snapshot());
  const [opened, setOpened] = useState<OpenedState | null>(null);
  const [failure, setFailure] = useState<ImportFailureLike | null>(null);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [pending, setPending] = useState<ReportCandidate | null>(null);
  const [compare, setCompare] = useState<CompareState>(() => controller.compareState);

  useEffect(() => host.subscribe(() => setView(host.snapshot())), [host]);

  // The workspace renders the controller's event stream — offers made
  // through any caller surface identically (I07).
  useEffect(
    () =>
      controller.subscribe((event) => {
        if (event.type === "imported") {
          setOpened({ view: event.view, replay: event.replay });
          setFailure(null);
          setSourceError(null);
        } else if (event.type === "rejected") {
          setOpened(null);
          setFailure(event.failure);
        } else if (event.type === "clear") {
          // The old report is gone regardless of what the new offer
          // does next — never show a stale report.
          setOpened(null);
          setSourceError(null);
          setFailure(null);
        } else if (event.type === "source_attached") {
          setSourceError(null);
          setSourceBusy(false);
          setOpened((current) => (current === null ? null : { ...current, replay: event.replay }));
        } else if (event.type === "source_rejected") {
          setSourceBusy(false);
          setSourceError(event.detail);
        } else if (event.type === "compare_side" || event.type === "compare_ready") {
          setCompare(controller.compareState);
        }
      }),
    [controller],
  );

  const fileState = view.fileState;
  const busy = fileState === "validating_file" || fileState === "loading_metadata";

  const offer = useCallback(
    async (candidate: ReportCandidate) => {
      setFailure(null);
      await controller.offer(candidate);
    },
    [controller],
  );

  const onReportFile = useCallback(
    (file: File) => {
      if (opened !== null) {
        // Replacement must be confirmed: it clears the current report.
        setPending(file);
        return;
      }
      void offer(file);
    },
    [opened, offer],
  );

  const confirmReplace = useCallback(() => {
    const candidate = pending;
    setPending(null);
    if (candidate) void offer(candidate);
  }, [pending, offer]);

  const onSourceFile = useCallback(
    (file: File) => {
      setSourceError(null);
      setSourceBusy(true);
      void controller.offerSource(file).then((check) => {
        if (!check.ok) setSourceBusy(false);
      });
    },
    [controller],
  );

  const onCompareFile = useCallback(
    (side: "left" | "right", file: File) => {
      void controller.offerCompareSide(side, file);
    },
    [controller],
  );

  return (
    <div className={styles.workspace} data-testid="import-workspace">
      <section className={styles.drop} aria-label={IMPORT_COPY.title} data-testid="import-drop">
        <p className={styles.invite}>{IMPORT_COPY.title}</p>
        <FilePick
          testId="import-file-input"
          accept="application/json,.json,.inkflip.json"
          label={opened === null ? "Choose a saved report" : "Choose a different report"}
          onFile={onReportFile}
          disabled={busy}
        />
        <p className={styles.privacy}>{IMPORT_COPY.local}</p>
      </section>

      {failure !== null && (
        <Notice type="error" title={failureMessage(failure)} id={`import-error-${failure.kind}`}>
          <span className={styles.errorDetail} data-testid="import-error-detail">
            {failure.code}: {failure.detail}
          </span>
        </Notice>
      )}

      {opened !== null && (
        <>
          <ReportPanel opened={opened} />
          <SourcePanel
            opened={opened}
            sourceError={sourceError}
            sourceBusy={sourceBusy}
            onSource={onSourceFile}
          />
          <ReplayPanel replay={opened.replay} />
          <FindingsPanel view={opened.view} />
          {opened.view.annotations.length > 0 && (
            <section className={styles.panel} data-testid="report-annotations">
              <p className={styles.panelTitle}>Annotations ({opened.view.annotations.length})</p>
              <ul className={styles.omissions}>
                {opened.view.annotations.map((annotation) => (
                  <li key={annotation.id} data-testid={`annotation-${annotation.id}`}>
                    <bdi>{annotation.text}</bdi>
                    {annotation.authorLabel !== null && (
                      <>
                        {" "}
                        — <bdi>{annotation.authorLabel}</bdi>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {opened.view.assets.length > 0 && (
            <section className={styles.panel} data-testid="report-assets">
              <p className={styles.panelTitle}>Evidence images ({opened.view.assets.length})</p>
              <div className={styles.assets}>
                {opened.view.assets.map((asset) => (
                  <figure key={asset.id} className={styles.asset} data-testid={`asset-${asset.id}`}>
                    {asset.dataUrl !== null ? (
                      <img
                        src={asset.dataUrl}
                        alt={`${asset.purpose} evidence`}
                        className={styles.assetImg}
                        data-testid={`asset-img-${asset.id}`}
                      />
                    ) : (
                      <p className={styles.hint}>
                        <bdi>{asset.mediaType}</bdi> payload — not rendered
                      </p>
                    )}
                    <figcaption className={styles.findingMeta}>
                      <bdi>{asset.purpose}</bdi>
                      {asset.pageIndex !== null && <> · page {asset.pageIndex + 1}</>} ·{" "}
                      {asset.byteLength} bytes
                    </figcaption>
                  </figure>
                ))}
              </div>
            </section>
          )}
          {opened.view.limitations.length > 0 && (
            <section className={styles.panel} data-testid="report-limitations">
              <p className={styles.panelTitle}>Limitations</p>
              <ul className={styles.omissions}>
                {opened.view.limitations.map((item, index) => (
                  <li key={index}>
                    <bdi>{item}</bdi>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <section className={styles.panel} aria-label={COMPARE_COPY.title} data-testid="compare-panel">
        <p className={styles.panelTitle}>{COMPARE_COPY.title}</p>
        <p className={styles.hint}>
          Both reports must be chosen locally — a report id or link is never enough.
        </p>
        <div className={styles.compareRow}>
          <div className={styles.compareSlot} data-testid="compare-left">
            <FilePick
              testId="compare-input-left"
              accept="application/json,.json,.inkflip.json"
              label="Select left report"
              onFile={(file) => onCompareFile("left", file)}
            />
            {compare.left !== null && (
              <p className={styles.hint} data-testid="compare-left-id">
                <bdi>{compare.left.view.reportId.slice(0, 16)}</bdi>… ·{" "}
                <bdi>{compare.left.view.title}</bdi>
              </p>
            )}
            {compare.leftFailure !== null && (
              <p className={styles.compareError} data-testid="compare-left-error">
                <bdi>{failureMessage(compare.leftFailure)}</bdi>
              </p>
            )}
          </div>
          <div className={styles.compareSlot} data-testid="compare-right">
            <FilePick
              testId="compare-input-right"
              accept="application/json,.json,.inkflip.json"
              label="Select right report"
              onFile={(file) => onCompareFile("right", file)}
            />
            {compare.right !== null && (
              <p className={styles.hint} data-testid="compare-right-id">
                <bdi>{compare.right.view.reportId.slice(0, 16)}</bdi>… ·{" "}
                <bdi>{compare.right.view.title}</bdi>
              </p>
            )}
            {compare.rightFailure !== null && (
              <p className={styles.compareError} data-testid="compare-right-error">
                <bdi>{failureMessage(compare.rightFailure)}</bdi>
              </p>
            )}
          </div>
        </div>
        {compare.readiness !== null && (
          <div className={styles.verdict} data-testid="compare-verdict">
            {compare.readiness.status === "ready" && (
              <p data-testid="compare-status-ready">
                Both reports record the same document bytes (
                <bdi>{compare.readiness.documentSha256.slice(-12)}</bdi>) — they can be compared.
              </p>
            )}
            {compare.readiness.status === "same_report" && (
              <p data-testid="compare-status-same">
                Both selections are the same report — there is nothing to compare.
              </p>
            )}
            {compare.readiness.status === "incomparable" && (
              <p data-testid="compare-status-incomparable">
                {COMPARE_COPY.incomparable}. <bdi>{compare.readiness.reason}</bdi>
              </p>
            )}
          </div>
        )}
      </section>

      <ModalDialog
        isOpen={pending !== null}
        onClose={() => setPending(null)}
        title={IMPORT_COPY.replaceTitle}
        description={IMPORT_COPY.replaceBody}
        footer={
          <>
            <Button variant="secondary" onClick={() => setPending(null)}>
              {IMPORT_COPY.replaceCancel}
            </Button>
            <Button variant="danger" onClick={confirmReplace}>
              {IMPORT_COPY.replaceConfirm}
            </Button>
          </>
        }
      >
        <div />
      </ModalDialog>
    </div>
  );
}

export default ImportWorkspace;
