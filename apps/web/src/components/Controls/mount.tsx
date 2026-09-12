import React, { useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import Button from "./Button";
import IconButton from "./IconButton";
import Tabs from "./Tabs";
import Disclosure from "./Disclosure";
import ProgressBar from "./ProgressBar";
import Notice from "./Notice";
import ModalDialog from "../Dialogs/ModalDialog";
import ReplaceConfirmDialog from "../Dialogs/ReplaceConfirmDialog";
import AppHeader from "../AppHeader/AppHeader";

function A11yHarness() {
  const [isCustomModalOpen, setIsCustomModalOpen] = useState(false);
  const [isReplaceModalOpen, setIsReplaceModalOpen] = useState(false);
  const [stage, setStage] = useState("Rendering page 1…");
  const [progress, setProgress] = useState<number | undefined>(25);
  const [tokenMetric, setTokenMetric] = useState("1,420 characters read");

  const openCustomBtnRef = useRef<HTMLButtonElement>(null);
  const openReplaceBtnRef = useRef<HTMLButtonElement>(null);

  const tabItems = [
    {
      id: "tab-1",
      label: "Overview",
      content: <p id="panel-1-content">Document overview and verified reading representations.</p>,
    },
    {
      id: "tab-2",
      label: "Readings",
      content: <p id="panel-2-content">Named reader outputs: PDFium 149.0.7825.0 and pypdf 6.18.0.</p>,
    },
    {
      id: "tab-3",
      label: "Limits",
      content: <p id="panel-3-content">A difference does not establish document safety or fraud.</p>,
    },
  ];

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-canvas)", color: "var(--color-ink)" }}>
      <AppHeader />

      <main style={{ maxWidth: "var(--layout-max)", margin: "0 auto", padding: "var(--space-6) var(--space-4)" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: "var(--space-6)", marginBottom: "var(--space-4)" }}>
          Accessible Primitives & Controls
        </h1>

        {/* Section: Buttons */}
        <section aria-labelledby="sec-buttons" style={{ marginBottom: "var(--space-6)" }}>
          <h2 id="sec-buttons" style={{ fontSize: "var(--space-5)", marginBottom: "var(--space-3)" }}>
            Buttons & Touch Targets
          </h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)", alignItems: "center" }}>
            <Button id="btn-primary" variant="primary">
              Primary Action
            </Button>
            <Button id="btn-secondary" variant="secondary">
              Secondary Action
            </Button>
            <Button id="btn-danger" variant="danger">
              Destructive Action
            </Button>
            <Button id="btn-ghost" variant="ghost">
              Ghost Action
            </Button>
            <Button id="btn-small" variant="secondary" size="small">
              Small Button
            </Button>
            <Button
              id="btn-disabled"
              variant="secondary"
              disabled
              disabledReason="Upload a PDF file to enable this action"
            >
              Disabled Action
            </Button>
            <IconButton
              id="btn-icon"
              aria-label="Search documents"
              bordered
            >
              🔍
            </IconButton>
          </div>
        </section>

        {/* Section: Tabs */}
        <section aria-labelledby="sec-tabs" style={{ marginBottom: "var(--space-6)" }}>
          <h2 id="sec-tabs" style={{ fontSize: "var(--space-5)", marginBottom: "var(--space-3)" }}>
            Tabs (Roving TabIndex)
          </h2>
          <Tabs aria-label="Document examination views" items={tabItems} defaultSelectedId="tab-1" />
        </section>

        {/* Section: Disclosure */}
        <section aria-labelledby="sec-disclosure" style={{ marginBottom: "var(--space-6)" }}>
          <h2 id="sec-disclosure" style={{ fontSize: "var(--space-5)", marginBottom: "var(--space-3)" }}>
            Disclosures
          </h2>
          <Disclosure id="disc-1" title="How OCR reading alignment works">
            <p>Selected crops are extracted via PDFium and compared against rendered-crop OCR text.</p>
          </Disclosure>
        </section>

        {/* Section: Progress Bar */}
        <section aria-labelledby="sec-progress" style={{ marginBottom: "var(--space-6)" }}>
          <h2 id="sec-progress" style={{ fontSize: "var(--space-5)", marginBottom: "var(--space-3)" }}>
            Progress Bar (Polite Announcements Without Token Chatter)
          </h2>
          <ProgressBar
            stage={stage}
            value={progress}
            detail={tokenMetric}
            onCancel={() => setStage("Cancelled — completed results kept.")}
          />
          <div style={{ marginTop: "var(--space-3)", display: "flex", gap: "var(--space-2)" }}>
            <Button
              id="btn-update-stage"
              variant="secondary"
              size="small"
              onClick={() => {
                setStage("Reading text on page 2…");
                setProgress(50);
                setTokenMetric("2,840 characters read");
              }}
            >
              Simulate Stage Transition
            </Button>
            <Button
              id="btn-update-token"
              variant="secondary"
              size="small"
              onClick={() => {
                // Token metric changes without changing stage
                setTokenMetric("2,841 characters read");
              }}
            >
              Simulate Token Tick (Silent to SR)
            </Button>
          </div>
        </section>

        {/* Section: Notices */}
        <section aria-labelledby="sec-notices" style={{ marginBottom: "var(--space-6)" }}>
          <h2 id="sec-notices" style={{ fontSize: "var(--space-5)", marginBottom: "var(--space-3)" }}>
            Notices & Alerts
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
            <Notice
              id="notice-error"
              type="error"
              title="Render failed"
              disclaimer="A failed render preserves inspectable reading and status information."
              retryAction={{ label: "Retry render", onRetry: () => {} }}
            >
              Unable to rasterize page 1 with PDFium.
            </Notice>
            <Notice
              id="notice-warning"
              type="warning"
              title="Two readings disagree"
              disclaimer="A difference does not establish which reading is correct."
            >
              PDFium extracted “$1,000” while rendered OCR read “$100”.
            </Notice>
          </div>
        </section>

        {/* Section: Dialogs */}
        <section aria-labelledby="sec-dialogs" style={{ marginBottom: "var(--space-6)" }}>
          <h2 id="sec-dialogs" style={{ fontSize: "var(--space-5)", marginBottom: "var(--space-3)" }}>
            Modal Dialogs & Focus Management
          </h2>
          <div style={{ display: "flex", gap: "var(--space-3)" }}>
            <button
              ref={openCustomBtnRef}
              id="btn-open-custom-modal"
              type="button"
              className="button secondary medium"
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                minHeight: "44px",
                minWidth: "44px",
                padding: "10px 16px",
                borderRadius: "var(--radius-control)",
                background: "var(--color-paper)",
                color: "var(--color-ink)",
                border: "1px solid var(--color-line)",
                cursor: "pointer",
              }}
              onClick={() => setIsCustomModalOpen(true)}
            >
              Open Custom Modal
            </button>

            <button
              ref={openReplaceBtnRef}
              id="btn-open-replace-modal"
              type="button"
              className="button secondary medium"
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                minHeight: "44px",
                minWidth: "44px",
                padding: "10px 16px",
                borderRadius: "var(--radius-control)",
                background: "var(--color-paper)",
                color: "var(--color-ink)",
                border: "1px solid var(--color-line)",
                cursor: "pointer",
              }}
              onClick={() => setIsReplaceModalOpen(true)}
            >
              Open Replace Confirmation
            </button>
          </div>
        </section>
      </main>

      {/* Modal Dialogs */}
      <ModalDialog
        isOpen={isCustomModalOpen}
        onClose={() => setIsCustomModalOpen(false)}
        title="Inspection Report Details"
        description="Review findings and technical comparison parameters."
        triggerRef={openCustomBtnRef}
        footer={
          <Button id="btn-modal-close" variant="primary" onClick={() => setIsCustomModalOpen(false)}>
            Close
          </Button>
        }
      >
        <p id="modal-content-text">This dialog traps Tab navigation while open and restores focus on close.</p>
      </ModalDialog>

      <ReplaceConfirmDialog
        isOpen={isReplaceModalOpen}
        onCancel={() => setIsReplaceModalOpen(false)}
        onConfirm={() => setIsReplaceModalOpen(false)}
        triggerRef={openReplaceBtnRef}
      />
    </div>
  );
}

const rootEl = document.getElementById("root");
if (rootEl) {
  createRoot(rootEl).render(<A11yHarness />);
}
