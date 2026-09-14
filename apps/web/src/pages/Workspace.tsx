import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ViewerStage } from "../features/viewer/ViewerStage";
import type { ViewerDoc } from "../features/viewer/types";
import type { Annotation } from "../../../../packages/contracts/src/index.ts";
import { FileDrop } from "../features/open/FileDrop";
import { OpenWorkspace } from "../features/open/OpenWorkspace";
import { resolveProfile } from "../features/open";
import { InspectionSession } from "../features/inspect/session";
import {
  DEFAULT_PUBLIC_EXAMPLE_ID,
  exampleAssetUrl,
  isLocalExampleUrl,
} from "../features/gallery/loader";
import { EXAMPLE_DOC } from "./exampleDoc.fixture";
import { ReplaceConfirmDialog } from "../components/Dialogs/ReplaceConfirmDialog";
import { CoveragePanel } from "../features/coverage/CoveragePanel";
import { ExportPanel } from "../features/export/ExportPanel";
import styles from "./Workspace.module.css";

export interface WorkspaceProps {
  onNavigateHome: () => void;
  onNavigateHelp?: () => void;
  onLoadPublicExample?: () => void;
  initialDoc?: ViewerDoc | null;
  /** Public-example card id (T21): its captured report is fetched and run
   *  through the real import gate, never mounted directly. */
  initialExampleId?: string | null;
  /** Test-hooks-only: mount the synthetic viewer fixture. */
  loadSyntheticFixture?: boolean;
  /** Home/hash intent: open the matching local file picker once. */
  initialOpen?: "pdf" | "report" | null;
  /** Called after the intent's picker was raised so the same intent can fire again. */
  onOpenIntentHandled?: () => void;
  /** File chosen on Home in the same click (Safari user-activation). */
  incomingFile?: File | null;
  /** Called after the incoming file has been offered to the session. */
  onIncomingFileHandled?: () => void;
}

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback: (error: Error) => React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

class ViewerErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override render() {
    if (this.state.error) {
      return this.props.fallback(this.state.error);
    }
    return this.props.children;
  }
}

const RUN_STATUS_COPY: Record<string, string> = {
  running: "Running checks…",
  preparing_assets: "Preparing the OCR model…",
};

function sessionOccupied(session: InspectionSession): boolean {
  const snap = session.getState();
  return snap.report !== null || snap.doc !== null;
}

export const Workspace: React.FC<WorkspaceProps> = ({
  onNavigateHome,
  onNavigateHelp,
  onLoadPublicExample,
  initialDoc,
  initialExampleId = null,
  loadSyntheticFixture = false,
  initialOpen = null,
  onOpenIntentHandled,
  incomingFile = null,
  onIncomingFileHandled,
}) => {
  const profile = useMemo(() => resolveProfile(), []);
  const session = useMemo(() => new InspectionSession(profile), [profile]);
  const [snap, setSnap] = useState(() => session.getState());
  const [exampleDoc, setExampleDoc] = useState<ViewerDoc | null>(() => {
    if (initialDoc) return initialDoc;
    if (__INKFLIP_TEST_HOOKS__ && loadSyntheticFixture) return EXAMPLE_DOC;
    return null;
  });
  const [localExampleId, setLocalExampleId] = useState<string | null>(null);
  const exampleIdToLoad = initialExampleId ?? localExampleId;
  // Set once the gallery example's report actually passed the import gate
  // — the workspace then labels the result as a prepared example rather
  // than a fresh inspection of the user's own file.
  const [loadedExampleId, setLoadedExampleId] = useState<string | null>(null);

  // Human notes (T23) live outside the sealed report — they are added to a
  // projection at export time only, never mutate machine evidence. Notes
  // reset when the open document/report identity changes.
  const [userNotes, setUserNotes] = useState<Annotation[]>([]);

  useEffect(() => session.subscribe(() => setSnap(session.getState())), [session]);
  // Unmounting the workspace releases the session's pdf.js handle,
  // OCR worker and retained bytes.
  useEffect(() => () => session.close(), [session]);
  // Read-only test handle — present only in dev/test-hook builds
  // (vite `__INKFLIP_TEST_HOOKS__` define; shipped builds omit it).
  useEffect(() => {
    if (!__INKFLIP_TEST_HOOKS__) return;
    (globalThis as { __inspect?: InspectionSession }).__inspect = session;
    return () => {
      delete (globalThis as { __inspect?: InspectionSession }).__inspect;
    };
  }, [session]);

  const exampleIntentRef = useRef(0);
  const bumpExampleIntent = useCallback(() => {
    exampleIntentRef.current += 1;
  }, []);

  const loadPublicExample = useCallback(() => {
    bumpExampleIntent();
    if (onLoadPublicExample) {
      onLoadPublicExample();
      return;
    }
    setLocalExampleId(DEFAULT_PUBLIC_EXAMPLE_ID);
  }, [bumpExampleIntent, onLoadPublicExample]);

  // T21 gallery handoff: fetch the card's committed captured report and run
  // it through the real import gate — validation, replay-readiness and the
  // evidence UI are identical to a user-supplied file. Unmount cancellation
  // is not enough: a newer local file in the same mounted workspace must
  // also own the session.
  const [exampleError, setExampleError] = useState<string | null>(null);
  useEffect(() => {
    if (exampleIdToLoad === null) return;
    const reportUrl = exampleAssetUrl(exampleIdToLoad, "report.json");
    const manifestUrl = exampleAssetUrl(exampleIdToLoad, "manifest.json");
    if (!reportUrl || !manifestUrl) return;
    const intent = ++exampleIntentRef.current;
    const startedGeneration = session.getState().generation;
    const startedOccupied = sessionOccupied(session);
    let cancelled = false;
    const stillOurs = (): boolean =>
      !cancelled && exampleIntentRef.current === intent;
    const mayOffer = (): boolean => {
      if (!stillOurs()) return false;
      const snap = session.getState();
      if (snap.generation !== startedGeneration) return false;
      if (!startedOccupied && sessionOccupied(session)) return false;
      return true;
    };
    setExampleError(null);
    void (async () => {
      try {
        const reportRes = await fetch(reportUrl, {
          credentials: "same-origin",
        });
        if (!reportRes.ok) throw new Error(`example report unavailable (${reportRes.status})`);
        const text = await reportRes.text();
        if (!mayOffer()) return;
        const file = new File([text], `${exampleIdToLoad}.inkflip.json`, {
          type: "application/json",
        });
        await session.offerFile(file);
        if (!stillOurs()) return;
        setLoadedExampleId(exampleIdToLoad);
        const generation = session.getState().generation;
        const manifestRes = await fetch(manifestUrl, {
          credentials: "same-origin",
        });
        if (!manifestRes.ok || !stillOurs()) return;
        const manifest = (await manifestRes.json()) as {
          files?: { source?: { download_url?: string; sha256?: string } };
        };
        const downloadUrl = manifest.files?.source?.download_url;
        const expectedSha = manifest.files?.source?.sha256;
        if (!downloadUrl || !expectedSha || !isLocalExampleUrl(downloadUrl)) return;
        const sourceRes = await fetch(downloadUrl, { credentials: "same-origin" });
        if (!sourceRes.ok || !stillOurs()) return;
        const bytes = new Uint8Array(await sourceRes.arrayBuffer());
        if (!stillOurs()) return;
        await session.retainVerifiedSourceBytes(bytes, expectedSha, generation);
      } catch (exc) {
        if (stillOurs()) {
          setExampleError(
            `Could not load the prepared example: ${exc instanceof Error ? exc.message : String(exc)}`,
          );
        }
      }
    })();
    return () => {
      cancelled = true;
      if (exampleIntentRef.current === intent) {
        exampleIntentRef.current += 1;
      }
    };
  }, [session, exampleIdToLoad]);

  const reportInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const sourceInputRef = useRef<HTMLInputElement>(null);
  const openedIntentRef = useRef<"pdf" | "report" | null>(null);

  useEffect(() => {
    if (incomingFile) {
      openedIntentRef.current = null;
      return;
    }
    if (initialOpen === null) {
      openedIntentRef.current = null;
      return;
    }
    if (openedIntentRef.current === initialOpen) return;
    openedIntentRef.current = initialOpen;
    const node = initialOpen === "report" ? reportInputRef.current : pdfInputRef.current;
    node?.click();
    onOpenIntentHandled?.();
  }, [incomingFile, initialOpen, onOpenIntentHandled]);

  // Defer the offer to a microtask so React Strict Mode's setup/cleanup/setup
  // cycle does not start two overlapping opens (idle -> loading_metadata).
  const incomingOfferGen = useRef(0);
  useEffect(() => {
    if (!incomingFile) return;
    let cancelled = false;
    const gen = ++incomingOfferGen.current;
    const file = incomingFile;
    queueMicrotask(() => {
      if (cancelled || incomingOfferGen.current !== gen) return;
      bumpExampleIntent();
      setLoadedExampleId(null);
      void session.offerFile(file).finally(() => {
        if (!cancelled && incomingOfferGen.current === gen) {
          onIncomingFileHandled?.();
        }
      });
    });
    return () => {
      cancelled = true;
    };
  }, [incomingFile, session, bumpExampleIntent, onIncomingFileHandled]);

  const [pendingFile, setPendingFile] = useState<File | null>(null);

  // Header-level offers while a document or report is open replace it —
  // the same confirmed-replacement contract the open workspace enforces.
  const onFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      bumpExampleIntent();
      setLoadedExampleId(null);
      const occupied = session.getState().doc !== null || session.getState().report !== null;
      if (occupied) {
        setPendingFile(file);
        return;
      }
      void session.offerFile(file);
    },
    [bumpExampleIntent, session],
  );

  const onSourceChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      await session.attachSource(file);
    },
    [session],
  );

  const report = snap.report;
  // A real document or report always takes precedence over the example.
  // Memoized: the viewer keys position/selection reset on this identity,
  // so a fresh object every render would trap it on page 1.
  const viewerDoc: ViewerDoc | null = useMemo(
    () =>
      report
        ? {
            pages: report.pages,
            readers: report.readers,
            occurrences: report.occurrences,
            findings: report.findings,
          }
        : snap.doc === null
          ? exampleDoc
          : null,
    [report, snap.doc, exampleDoc],
  );

  const fileState = snap.fileState;
  const busy =
    fileState === "validating_file" || fileState === "loading_metadata";
  const running = fileState === "running" || fileState === "preparing_assets";
  const settled =
    fileState === "complete" || fileState === "partial" || fileState === "failed";
  const showViewer = viewerDoc !== null && (settled || snap.reportSource === "import" || exampleDoc !== null);
  const docTitle = report
    ? ((report.document as { filename?: string | null; display_name?: string | null })
        .filename ??
        (report.document as { display_name?: string | null }).display_name ??
        snap.doc?.label ??
        "Inspection report")
    : snap.doc !== null
      ? (snap.doc.label ?? "PDF Document")
      : exampleDoc !== null
        ? "Invoice-Example.pdf"
        : "Workspace";

  const addNote = useCallback(
    (annotation: Annotation) => setUserNotes((prev) => [...prev, annotation]),
    [],
  );
  const removeNote = useCallback(
    (id: string) => setUserNotes((prev) => prev.filter((n) => n.id !== id)),
    [],
  );

  // Notes belong to the open document/report — a new run, import or close
  // discards them rather than leaking them onto unrelated findings.
  useEffect(() => {
    setUserNotes([]);
  }, [report, snap.doc, exampleDoc]);

  const closeAll = useCallback(() => {
    bumpExampleIntent();
    session.close();
    setExampleDoc(null);
    setLocalExampleId(null);
    setLoadedExampleId(null);
    setUserNotes([]);
  }, [bumpExampleIntent, session]);

  return (
    <div className={styles.workspace}>
      <input
        ref={reportInputRef}
        id="input-import-report"
        type="file"
        accept="application/json,.json,.inkflip.json"
        style={{ display: "none" }}
        onChange={onFileChange}
      />
      <input
        ref={pdfInputRef}
        id="input-open-pdf"
        type="file"
        accept="application/pdf,.pdf"
        style={{ display: "none" }}
        onChange={onFileChange}
      />
      <input
        ref={sourceInputRef}
        id="input-attach-source"
        type="file"
        accept="application/pdf,.pdf"
        style={{ display: "none" }}
        onChange={onSourceChange}
      />

      <header className={styles.documentBar}>
        <div className={styles.documentHeaderLeft}>
          <button
            id="btn-back-home"
            type="button"
            className={styles.backButton}
            onClick={onNavigateHome}
          >
            ← Home
          </button>
          <span id="workspace-doc-title" className={styles.documentTitle}>
            {viewerDoc || snap.doc ? docTitle : "Workspace"}
          </span>
          <span className={styles.documentMeta} data-testid="doc-stats">
            {viewerDoc
              ? `${viewerDoc.pages.length} ${viewerDoc.pages.length === 1 ? "page" : "pages"} · ${viewerDoc.findings.length} ${viewerDoc.findings.length === 1 ? "finding" : "findings"}`
              : snap.doc
                ? `${snap.doc.pageCount} ${snap.doc.pageCount === 1 ? "page" : "pages"} · not yet inspected`
                : "No document loaded"}
          </span>
          {report !== null && (
            <span
              data-testid="result-provenance"
              className={styles.provenanceBadge}
              title={
                loadedExampleId !== null
                  ? "Captured once with this example's recorded settings — a fresh inspection of the same file can legitimately produce different findings."
                  : snap.reportSource === "run"
                    ? "Produced by inspecting the open file just now."
                    : "A report saved earlier and opened for review."
              }
            >
              {loadedExampleId !== null
                ? "Prepared example"
                : snap.reportSource === "run"
                  ? "Fresh inspection"
                  : "Saved report"}
            </span>
          )}
        </div>

        <div className={styles.documentHeaderRight}>
          <button
            id="btn-header-import-report"
            type="button"
            className={styles.headerButton}
            onClick={() => reportInputRef.current?.click()}
          >
            Open saved report
          </button>
          <button
            id="btn-header-open-pdf"
            type="button"
            className={styles.headerButton}
            onClick={() => pdfInputRef.current?.click()}
          >
            Open PDF
          </button>
          {viewerDoc || snap.doc ? (
            <button
              id="btn-close-doc"
              type="button"
              className={styles.headerButton}
              onClick={closeAll}
            >
              Close Document
            </button>
          ) : (
            <button
              id="btn-load-demo"
              type="button"
              className={styles.headerButton}
              onClick={loadPublicExample}
            >
              Load Example
            </button>
          )}
          {onNavigateHelp && (
            <button
              id="btn-header-help"
              type="button"
              className={styles.headerButton}
              onClick={onNavigateHelp}
            >
              Help
            </button>
          )}
        </div>
      </header>

      <main className={styles.workspaceMain}>
        {exampleError !== null && (
          <div
            role="alert"
            data-testid="example-error"
            style={{
              marginBottom: "var(--space-3)",
              padding: "var(--space-2) var(--space-4)",
              backgroundColor: "var(--color-surface-muted)",
              border: "1px solid var(--color-line)",
              borderRadius: "var(--radius-control)",
              color: "var(--color-ink)",
              fontSize: "var(--text-caption)",
            }}
          >
            {exampleError}
          </div>
        )}
        {snap.error && (
          <div
            id="import-error"
            role="alert"
            style={{
              marginBottom: "var(--space-3)",
              padding: "var(--space-2) var(--space-4)",
              backgroundColor: "var(--color-surface-muted)",
              border: "1px solid var(--color-line)",
              borderRadius: "var(--radius-control)",
              color: "var(--color-ink)",
              fontSize: "var(--text-caption)",
            }}
          >
            {snap.error.message}
            {snap.error.detail ? ` (${snap.error.detail})` : ""}
          </div>
        )}
        {snap.notice && (
          <div
            id="pdf-received-notice"
            role="status"
            style={{
              marginBottom: "var(--space-3)",
              padding: "var(--space-2) var(--space-4)",
              backgroundColor: "var(--color-surface-subtle)",
              border: "1px solid var(--color-line)",
              borderRadius: "var(--radius-control)",
              color: "var(--color-ink)",
              fontSize: "var(--text-caption)",
            }}
          >
            {snap.notice}
          </div>
        )}

        {running && (
          <section
            aria-label="Inspection progress"
            data-testid="run-progress"
            style={{
              padding: "var(--space-4)",
              border: "1px solid var(--color-line)",
              borderRadius: "var(--radius-control)",
            }}
          >
            <h2 style={{ marginTop: 0 }}>{RUN_STATUS_COPY[fileState]}</h2>
            <ul data-testid="run-checks" style={{ listStyle: "none", padding: 0 }}>
              {(snap.run?.checks ?? []).map((check) => (
                <li
                  key={check.id}
                  data-check-id={check.id}
                  data-status={check.status ?? check.phase}
                >
                  <code>{check.id}</code> — {check.capability} on page{" "}
                  {check.pageIndex + 1}: {check.status ?? check.phase}
                </li>
              ))}
            </ul>
            <button
              id="btn-cancel-run"
              type="button"
              style={{
                padding: "4px 12px",
                borderRadius: "var(--radius-control)",
                border: "1px solid var(--color-line)",
                background: "var(--color-paper-pure)",
                cursor: "pointer",
              }}
              onClick={() => session.cancelRun()}
            >
              Cancel run
            </button>
          </section>
        )}

        {fileState === "cancelled" && (
          <section aria-label="Run cancelled" data-testid="run-cancelled">
            <p>The inspection run was cancelled.</p>
            <button
              id="btn-back-to-selection"
              type="button"
              onClick={() => session.newRun()}
              style={{
                padding: "4px 12px",
                borderRadius: "var(--radius-control)",
                border: "1px solid var(--color-line)",
                background: "var(--color-paper-pure)",
                cursor: "pointer",
              }}
            >
              Back to selection
            </button>
          </section>
        )}

        {fileState === "selecting" && snap.doc !== null && snap.reportSource !== "import" && (
          <OpenWorkspace
            controller={session.openController}
            host={session.coordinator}
            profile={profile}
            renderPageRaster={session.renderPageRaster}
            startRun={session.startRun}
          />
        )}

        {showViewer && viewerDoc && (
          <ViewerErrorBoundary
            key={docTitle}
            fallback={(error) => (
              <div
                id="import-error"
                role="alert"
                style={{
                  padding: "var(--space-4)",
                  backgroundColor: "var(--color-surface-muted)",
                  border: "1px solid var(--color-line)",
                  borderRadius: "var(--radius-control)",
                  color: "var(--color-ink)",
                  fontSize: "var(--text-caption)",
                }}
              >
                Failed to display document: {error.message}
              </div>
            )}
          >
            <ViewerStage
              doc={viewerDoc}
              renderPage={session.renderViewerPage}
              pageSourceAvailable={snap.doc !== null || snap.hasSourceBytes}
              annotations={userNotes}
              onAddAnnotation={addNote}
              onRemoveAnnotation={removeNote}
            />
          </ViewerErrorBoundary>
        )}

        {report && (
          <>
            {settled && snap.doc !== null && (
              <button
                id="btn-rerun"
                type="button"
                style={{
                  marginBottom: "var(--space-3)",
                  padding: "4px 12px",
                  borderRadius: "var(--radius-control)",
                  border: "1px solid var(--color-line)",
                  background: "var(--color-paper-pure)",
                  cursor: "pointer",
                }}
                onClick={() => session.newRun()}
              >
                Re-inspect this document
              </button>
            )}
            <CoveragePanel
              plan={report.plan}
              checks={report.checks}
              pages={report.pages}
              ocrRun={report.plan.checks.some((c) => c.capability === "ocr")}
              findingsCount={report.findings.length}
            />
            {snap.reportSource === "import" && snap.importedReplay !== null && (
              <section
                aria-label="Original PDF"
                data-testid="replay-status"
                style={{
                  marginTop: "var(--space-3)",
                  padding: "var(--space-2) var(--space-4)",
                  border: "1px solid var(--color-line)",
                  borderRadius: "var(--radius-control)",
                  fontSize: "var(--text-caption)",
                }}
              >
                {session.sourcePdfBytes() !== null ||
                snap.importedReplay.source === "embedded" ||
                snap.importedReplay.source === "attached" ? (
                  <p>
                    {snap.importedReplay.readersMissing.length > 0
                      ? `The original PDF is available. Replay still needs: ${snap.importedReplay.readersMissing.join(", ")}.`
                      : "The original PDF is available with this report. Export can include it if you choose."}
                  </p>
                ) : snap.importedReplay.source === "missing" ? (
                  <>
                    <p>
                      This saved report did not include the original PDF. Attach the
                      matching file to compare against the page.
                    </p>
                    <button
                      id="btn-attach-source"
                      type="button"
                      className={styles.headerButton}
                      onClick={() => sourceInputRef.current?.click()}
                    >
                      Attach original PDF
                    </button>
                  </>
                ) : (
                  <p>This report does not require the original PDF for replay.</p>
                )}
                {loadedExampleId !== null && (
                  <p data-testid="prepared-example-note">
                    This is a saved example captured with the settings recorded in
                    its manifest. Re-checking the same PDF fresh — a different
                    page scope or OCR region — can legitimately report different
                    findings.
                  </p>
                )}
              </section>
            )}
            <ExportPanel
              engine={session.exportEngine}
              source={
                userNotes.length === 0
                  ? report
                  : {
                      ...report,
                      annotations: [...(report.annotations ?? []), ...userNotes],
                    }
              }
              sourcePdfBytes={session.sourcePdfBytes}
            />
          </>
        )}

        {!busy && !running && fileState === "idle" && viewerDoc === null && (
          <div className={styles.emptyWorkspace}>
            <FileDrop
              phase="idle"
              onFile={(file) => {
                bumpExampleIntent();
                setLoadedExampleId(null);
                void session.offerFile(file);
              }}
              hasDocument={false}
            />
          </div>
        )}
      </main>

      <ReplaceConfirmDialog
        isOpen={pendingFile !== null}
        onCancel={() => setPendingFile(null)}
        onConfirm={() => {
          const file = pendingFile;
          setPendingFile(null);
          if (file) {
            bumpExampleIntent();
            setLoadedExampleId(null);
            void session.offerFile(file);
          }
        }}
      />
    </div>
  );
};

export default Workspace;
