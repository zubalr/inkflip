import React, { useState, useEffect, useRef } from "react";
import { ModalDialog } from "../../components/Dialogs";
import styles from "./HelpPage.module.css";

export interface HelpPageProps {
  readonly onNavigateHome: () => void;
  readonly onNavigateWorkspace: () => void;
  readonly onReturnToWorkspace?: () => void;
  readonly onOpenExample?: () => void;
  readonly hasActiveWorkspace?: boolean;
}

type GuideId = "cli" | "a11y" | "corpus" | "readers" | "attribution";

interface GuideInfo {
  readonly id: GuideId;
  readonly badge: string;
  readonly title: string;
  readonly summary: string;
  readonly modalTitle: string;
  readonly modalDescription: string;
  readonly content: React.ReactNode;
}

export const HelpPage: React.FC<HelpPageProps> = ({
  onNavigateHome,
  onNavigateWorkspace,
  onReturnToWorkspace,
  onOpenExample,
  hasActiveWorkspace = false,
}) => {
  const [activeGuide, setActiveGuide] = useState<GuideId | null>(null);
  const triggerRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  // Focus primary action on mount so keyboard focus is securely inside Help
  useEffect(() => {
    const returnBtn = document.getElementById("btn-help-back-workspace");
    if (returnBtn) {
      returnBtn.focus();
    }
  }, []);

  // Handle Escape key to return to workspace when no guide modal is open
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (activeGuide !== null) return;
      if (e.key === "Escape" && hasActiveWorkspace && onReturnToWorkspace) {
        e.preventDefault();
        onReturnToWorkspace();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeGuide, hasActiveWorkspace, onReturnToWorkspace]);

  const guides: readonly GuideInfo[] = [
    {
      id: "cli",
      badge: "Terminal Companion",
      title: "Command-Line Interface",
      summary: "Batch inspections, report replay, and hardened Docker runs from the shell.",
      modalTitle: "Command-Line Interface Guide",
      modalDescription: "Terminal workflows for batch corpus inspections across macOS native and Docker environments.",
      content: (
        <div className={styles.guideModalContent}>
          <div>
            <h4>Supported Delivery Targets</h4>
            <p>Inkflip officially targets modern desktop web browsers, the macOS native companion runtime, and a reproducible Docker CLI workflow. Separate Windows and Linux desktop applications remain deferred.</p>
          </div>
          <div>
            <h4>macOS Companion CLI</h4>
            <p>Inspect a local PDF using native engine profiles directly on macOS (requires <code>--out</code> for the output report JSON). Run it from the repository root with <code>native/.venv/bin</code> on <code>PATH</code>, as <code>docs/CLI.md</code> documents:</p>
            <pre className={styles.guideCodeBlock}><code>PYTHONPATH=native python -m inkflip.cli inspect &lt;pdf-file&gt; --out report.json</code></pre>
            <p>Optional flags: <code>--profile native-default</code>, <code>--reader pdfium</code>, <code>--pages 1</code>, <code>--embed-source</code>.</p>
          </div>
          <div>
            <h4>Report Generation (HTML Export)</h4>
            <p>Export a self-contained HTML inspection report from an existing validated report JSON:</p>
            <pre className={styles.guideCodeBlock}><code>PYTHONPATH=native python -m inkflip.cli report &lt;report.json&gt; --format html --out report.html</code></pre>
          </div>
          <div>
            <h4>Evidence Replay</h4>
            <p>Replay recorded findings from a previously generated report file. When source bytes are not embedded, provide the original source PDF:</p>
            <pre className={styles.guideCodeBlock}><code>PYTHONPATH=native python -m inkflip.cli replay &lt;report.json&gt; --source &lt;pdf-file&gt; --profile native-default --out replay.json</code></pre>
          </div>
          <div>
            <h4>Reproducible Docker CLI Workflow</h4>
            <p>Run batch inspections in a reproducible Linux container with pinned dependencies and zero network access. Requires built image <code>inkflip</code>; mount input directories read-only (<code>:ro</code>) and output directories writable (<code>:rw</code>):</p>
            <pre className={styles.guideCodeBlock}><code>docker run --rm --network none -v "$PWD/input":/data/in:ro -v "$PWD/output":/data/out:rw inkflip inspect /data/in/&lt;pdf-file&gt; --out /data/out/report.json</code></pre>
          </div>
          <div>
            <h4>Fail-Closed Security</h4>
            <p>The CLI strictly refuses remote URLs and network paths (exit code 2). All execution remains confined to local files and isolated containers.</p>
          </div>
        </div>
      ),
    },
    {
      id: "a11y",
      badge: "Assistive Flows",
      title: "Accessibility & Assistive Flows",
      summary: "Keyboard shortcuts, focus restoration, and accessible text equivalents.",
      modalTitle: "Accessibility & Assistive Flows Guide",
      modalDescription: "Standards-compliant navigation, focus restoration, and screen reader equivalents.",
      content: (
        <div className={styles.guideModalContent}>
          <div>
            <h4>Keyboard Shortcuts</h4>
            <ul>
              <li><strong>f:</strong> Cycle view modes between Page, Reading, and Compare.</li>
              <li><strong>+ / -:</strong> Zoom in and out; <strong>r:</strong> Rotate page 90 degrees.</li>
              <li><strong>n:</strong> Navigate to next finding card; <strong>Tab / Shift+Tab:</strong> Standard control traversal.</li>
            </ul>
          </div>
          <div>
            <h4>Shortcut Suppression</h4>
            <p>Typing inside user notes or form input fields automatically suppresses single-key shortcuts so typing is never interrupted.</p>
          </div>
          <div>
            <h4>Candidate Selection &amp; Focus Restoration</h4>
            <p>When multiple locations match an ambiguous finding, candidate buttons can be selected via Enter. Selecting or dismissing an occurrence returns focus to the originating finding card.</p>
          </div>
          <div>
            <h4>400% Zoom Reflow</h4>
            <p>The interface remains completely operable at 400% browser zoom reflow (320px CSS width equivalent) with zero horizontal document clipping.</p>
          </div>
        </div>
      ),
    },
    {
      id: "corpus",
      badge: "Fixture Testing",
      title: "Corpus & Test Invariants",
      summary: "Fixture families and reproducibility backing multi-reader divergence detection.",
      modalTitle: "Corpus & Test Invariants Guide",
      modalDescription: "Ground-truth evaluation fixtures verifying detection across independent engines.",
      content: (
        <div className={styles.guideModalContent}>
          <div>
            <h4>Fixture Families (F01–F21)</h4>
            <p>The evaluation corpus includes synthetic alignments, scanned raster receipts, font dictionary anomalies, and reading-order permutations.</p>
          </div>
          <div>
            <h4>Bounded Comparison</h4>
            <p>Differences are detected without assuming any single reader engine is authoritative or correct.</p>
          </div>
          <div>
            <h4>Cryptographic Reproducibility</h4>
            <p>Each fixture is pinned by cryptographic SHA-256 digests and immutable baselines to prevent test regression.</p>
          </div>
        </div>
      ),
    },
    {
      id: "readers",
      badge: "Engine Architecture",
      title: "Reader Integration Guide",
      summary: "Adapter contract, canonical coordinates, and explicit omission handling.",
      modalTitle: "Reader Integration Guide",
      modalDescription: "Standards for connecting independent extraction engines into Inkflip.",
      content: (
        <div className={styles.guideModalContent}>
          <div>
            <h4>Engine Adapter Contract</h4>
            <p>Readers implement decoupled adapter interfaces producing standardized occurrences and check records.</p>
          </div>
          <div>
            <h4>Canonical Coordinate Normalization</h4>
            <p>Token bounding boxes are transformed from engine-specific coordinates into canonical PDF page points [x0, y0, x1, y1].</p>
          </div>
          <div>
            <h4>Explicit Omission Protocol</h4>
            <p>If an engine cannot parse an operator or skips content, it must record an explicit omission rather than omitting records silently.</p>
          </div>
          <div>
            <h4>Integrated Engines</h4>
            <ul>
              <li><strong>PDF.js:</strong> Client-side JavaScript content stream extraction (in-browser and Node).</li>
              <li><strong>PDFium:</strong> High-fidelity native C++ text and geometry extraction (macOS companion &amp; Docker CLI).</li>
              <li><strong>Tesseract OCR:</strong> Optical character recognition for scanned raster pages (browser WASM &amp; native companion).</li>
            </ul>
          </div>
        </div>
      ),
    },
    {
      id: "attribution",
      badge: "Licenses & Credits",
      title: "Attribution & Licenses",
      summary: "Credits and licenses for bundled libraries, fonts, and runtimes.",
      modalTitle: "Attribution & Licenses Guide",
      modalDescription: "Open-source notices and clean-room provenance.",
      content: (
        <div className={styles.guideModalContent}>
          <div>
            <h4>Bundled Open-Source Libraries</h4>
            <ul>
              <li><strong>PDF.js:</strong> Apache License 2.0 (Mozilla Foundation).</li>
              <li><strong>Tesseract.js &amp; Tesseract.js-core:</strong> Apache License 2.0.</li>
              <li><strong>React &amp; React-DOM:</strong> MIT License (Meta Platforms, Inc.).</li>
            </ul>
          </div>
          <div>
            <h4>Typography</h4>
            <p>Inkflip ships no bundled fonts. It renders with your system's Georgia, system-ui, and ui-monospace stacks.</p>
          </div>
          <div>
            <h4>Privacy &amp; Telemetry Notice</h4>
            <p>Inkflip contains zero telemetry, analytics, remote beacons, or third-party cloud connections.</p>
          </div>
        </div>
      ),
    },
  ];

  const currentGuide = guides.find((g) => g.id === activeGuide);

  const handleCloseGuide = (id: GuideId | null) => {
    setActiveGuide(null);
    if (id) {
      setTimeout(() => {
        const btn = triggerRefs.current[id];
        if (btn) {
          btn.focus();
        }
      }, 20);
    }
  };

  return (
    <div className={styles.page} data-testid="help-page">
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <a
            href="#/"
            className={styles.brand}
            aria-label="Inkflip home"
            onClick={(e) => {
              e.preventDefault();
              onNavigateHome();
            }}
          >
            <span className={styles.mark} aria-hidden="true">
              if
            </span>
            <span>inkflip</span>
            <span className={styles.descriptor}>PDF reading inspector</span>
          </a>

          <nav className={styles.navActions} aria-label="Help navigation">
            <button
              id="btn-help-back-home"
              type="button"
              className={styles.btnSecondary}
              onClick={onNavigateHome}
            >
              Home
            </button>
            <button
              id="btn-help-back-workspace"
              type="button"
              className={styles.btnPrimary}
              onClick={() => {
                if (hasActiveWorkspace && onReturnToWorkspace) {
                  onReturnToWorkspace();
                } else {
                  onNavigateWorkspace();
                }
              }}
            >
              {hasActiveWorkspace ? "Return to Workspace" : "Open Workspace"}
            </button>
            <button
              id="btn-help-open-example"
              type="button"
              className={styles.btnSecondary}
              onClick={() => {
                if (onOpenExample) {
                  onOpenExample();
                } else {
                  onNavigateWorkspace();
                }
              }}
            >
              Try an example
            </button>
          </nav>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.hero} aria-labelledby="help-headline">
          <h1 id="help-headline" className={styles.headline}>
            How to check a PDF
          </h1>
          <p className={styles.lede}>
            Compare the text you see with the text software reads. Files stay in
            this browser.
          </p>
        </section>

        <section className={styles.section} aria-labelledby="steps-heading">
          <h2 id="steps-heading" className={styles.sectionHeading}>
            Open → Inspect → Save
          </h2>
          <ol className={styles.steps}>
            <li>
              <strong>Open</strong> a PDF — or start with an example to see the
              interface before using your own file.
            </li>
            <li>
              <strong>Inspect</strong> the findings. In Compare, each finding shows
              the paired readings side by side; <em>Show on page</em> marks the
              evidence on the real page, and <em>Details</em> lists every
              candidate reading.
            </li>
            <li>
              <strong>Interpret</strong> honestly — a difference means the readers
              disagree, not that one of them is right.
            </li>
            <li>
              <strong>Save</strong> a report: HTML to read or share, JSON to reopen
              here later.
            </li>
          </ol>
        </section>

        <section className={styles.section} aria-labelledby="faq-heading">
          <h2 id="faq-heading" className={styles.sectionHeading}>
            Common questions
          </h2>
          <dl className={styles.faq}>
            <dt>What is compared?</dt>
            <dd>
              The PDF text layer against what appears on the page, using PDF.js
              and Tesseract OCR in the browser.
            </dd>
            <dt>Where do my files go?</dt>
            <dd>They stay in this tab. Nothing is uploaded.</dd>
            <dt>How do I read a difference?</dt>
            <dd>
              A highlighted difference needs review. It does not prove fraud or
              correctness.
            </dd>
            <dt>What gets saved?</dt>
            <dd>
              An HTML report for reading, or a JSON file you can reopen here.
              The original PDF is included in JSON only when you choose that.
            </dd>
            <dt>Why can't I see the page after reopening a report?</dt>
            <dd>
              If the saved JSON did not embed the original PDF, Inkflip still
              shows every recorded reading and finding — only the painted page
              preview is unavailable. Reattach the PDF (its checksum is verified
              against the report) to restore page rendering.
            </dd>
            <dt>Do my notes persist?</dt>
            <dd>
              Notes are session-only while you work. To keep them, include them
              in a saved report — the export makes notes an explicit opt-in.
            </dd>
            <dt>A check didn't finish — is the PDF still checked?</dt>
            <dd>
              Partial results are reported, never smoothed over. The coverage
              summary lists skipped, failed, and unsupported checks, and a
              completed selection never implies the whole document is clean.
            </dd>
            <dt>Does this work in Safari?</dt>
            <dd>
              Yes. Check a PDF on Home opens the file picker from that click. If
              you cancel, you stay on Home and can choose a file again. A saved
              link to the workspace may not raise the picker; use Open PDF there.
            </dd>
          </dl>
        </section>

        <section className={styles.section} aria-labelledby="limits-heading">
          <div className={styles.noticeCard}>
            <h2 id="limits-heading" className={styles.noticeTitle}>
              Limits &amp; principles
            </h2>
            <p className={styles.noticeText}>
              <strong>Non-Certification Principle:</strong> Inkflip surfaces localized, observable
              differences between independent reader implementations. Identifying a divergence does
              not establish which reading is correct or authoritative, and the absence of detected
              differences does NOT certify that a document is authentic, safe, accessible, or free
              of hidden content.
            </p>
            <p className={styles.noticeText}>
              <strong>Explicit Omission Reporting:</strong> When a reader engine fails, encounters
              unsupported PDF operators, or skips unparseable content, Inkflip explicitly records
              the condition as an omission or incomplete check. Silence is never substituted for
              missing coverage.
            </p>
            <p className={styles.noticeText}>
              <strong>Platform Scope &amp; Availability:</strong> Official delivery targets are
              modern desktop web browsers, the macOS native companion, and the reproducible Docker
              CLI workflow. Separate Windows and Linux desktop GUI applications remain deferred;
              automated remediation or silent modifications to PDF binaries are intentionally not
              supported.
            </p>
            <p className={styles.noticeText}>
              <strong>Provenance &amp; Audit Trail:</strong> Exported inspection packages preserve
              reader engine versions, adapter builds, and timestamped run metadata so findings can
              be independently evaluated.
            </p>
            <ul className={styles.noticeList}>
              <li>
                <strong>Local-First Processing:</strong> Your documents never leave your device.
                Rendering, extraction, and comparison run in your browser or in the companion
                tools.
              </li>
              <li>
                <strong>Offline Readiness:</strong> Once the app assets and OCR language models are
                cached by your browser, inspections run without a connection.
              </li>
              <li>
                <strong>Inspection Coverage &amp; Status:</strong> Reports show completed, skipped,
                and unsupported checks; coverage reflects verification status, not a guarantee.
              </li>
            </ul>
          </div>
        </section>

        <section className={styles.guidesSection} aria-labelledby="guides-heading">
          <h2 id="guides-heading" className={styles.sectionHeading}>
            Advanced guides
          </h2>
          <p className={styles.guidesIntro}>
            Technical references for the command-line companion, reader integrations, fixture
            testing, accessibility flows, and licensing.
          </p>
          <div className={styles.guidesGrid}>
            {guides.map((guide) => (
              <article key={guide.id} className={styles.guideCard}>
                <span className={styles.guideBadge}>{guide.badge}</span>
                <h3 className={styles.guideTitle}>{guide.title}</h3>
                <p className={styles.guideDesc}>{guide.summary}</p>
                <button
                  id={`btn-guide-${guide.id}`}
                  ref={(el) => {
                    triggerRefs.current[guide.id] = el;
                  }}
                  type="button"
                  className={styles.guideButton}
                  onClick={() => setActiveGuide(guide.id)}
                >
                  Read Quick Guide
                </button>
              </article>
            ))}
          </div>
        </section>
      </main>

      {currentGuide && (
        <ModalDialog
          isOpen={true}
          onClose={() => handleCloseGuide(currentGuide.id)}
          title={currentGuide.modalTitle}
          description={currentGuide.modalDescription}
          triggerRef={{ current: triggerRefs.current[currentGuide.id] ?? null }}
          footer={
            <button
              type="button"
              className={styles.btnSecondary}
              onClick={() => handleCloseGuide(currentGuide.id)}
            >
              Close Guide
            </button>
          }
        >
          {currentGuide.content}
        </ModalDialog>
      )}
    </div>
  );
};

export default HelpPage;
