import React, { useEffect, useRef, useState } from "react";
import styles from "./Home.module.css";
import { ExamplesGallery } from "../features/gallery/ExamplesGallery";
import { exampleDisplayCopy } from "../features/gallery/displayCopy";
import { loadHomeSample, type HomeSample } from "./homeExample";

export interface HomeProps {
  onNavigateWorkspace: (withExample?: boolean, open?: "pdf" | "report") => void;
  onOpenExample?: (exampleId: string) => void;
  onNavigateHelp?: () => void;
  /** Offer a local PDF or saved report from a Home click (Safari gesture). */
  onOfferLocalFile?: (file: File) => void;
}

function takeChosenFile(
  event: React.ChangeEvent<HTMLInputElement>,
  offer?: (file: File) => void,
): void {
  const file = event.currentTarget.files?.[0];
  event.currentTarget.value = "";
  if (file && offer) offer(file);
}

const InspectionPreview: React.FC<{
  sample: HomeSample | null;
  loading: boolean;
}> = ({ sample, loading }) => {
  const visual = sample?.visualAmount ?? "";
  const extracted = sample?.extractedAmount ?? "";
  const finding = sample?.findingTitle ?? "Selected difference";
  // Pair the readings by real evidence kind — the same pairing the
  // compare table shows inside the workspace.
  const textReader = sample?.readers.find((r) => r.method === "native_text") ?? null;
  const ocrReader = sample?.readers.find((r) => r.method === "ocr") ?? null;
  const textReaderLabel = textReader ? `${textReader.name} ${textReader.version}`.trim() : "PDF.js";
  const ocrReaderLabel = ocrReader ? `${ocrReader.name} ${ocrReader.version}`.trim() : "OCR";

  return (
    <div
      className={styles.inspectStage}
      data-testid="home-inspect-stage"
      aria-busy={loading}
    >
      <div className={styles.inspectPage} aria-label="Page preview">
        <p className={styles.inspectPageLabel}>On the page</p>
        <p className={styles.inspectPageBody}>
          Invoice total{" "}
          {loading ? (
            <span className={styles.inspectMarkMuted}>…</span>
          ) : visual ? (
            <mark className={styles.inspectMark}>{visual}</mark>
          ) : (
            <span className={styles.inspectMarkMuted}>amount</span>
          )}
        </p>
        <p className={styles.inspectPageHint}>
          The highlight marks where the finding's evidence sits on the real page.
        </p>
      </div>
      <div className={styles.inspectPanel}>
        <article className={styles.inspectFinding}>
          <h3 className={styles.inspectFindingTitle}>{loading ? "Loading sample…" : finding}</h3>
          <table className={styles.inspectPairTable}>
            <thead>
              <tr>
                <th scope="col">
                  <span className={styles.inspectPairTitle}>PDF text</span>
                  <span className={styles.inspectPairReader}>{textReaderLabel}</span>
                </th>
                <th scope="col">
                  <span className={styles.inspectPairTitle}>Text read from image</span>
                  <span className={styles.inspectPairReader}>{ocrReaderLabel}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{loading ? "…" : extracted || "unavailable"}</td>
                <td>{loading ? "…" : visual || "unavailable"}</td>
              </tr>
            </tbody>
          </table>
          <p className={styles.inspectPairStatus}>
            <span className={styles.inspectPairBadge}>Different text</span>
          </p>
          <p className={styles.inspectPairHint}>Show on page · Details</p>
        </article>
        <p className={styles.inspectSaveHint}>
          Neither reader is treated as the truth — you inspect what each returned.
        </p>
      </div>
    </div>
  );
};

export const Home: React.FC<HomeProps> = ({
  onNavigateWorkspace,
  onOpenExample,
  onNavigateHelp,
  onOfferLocalFile,
}) => {
  const [sample, setSample] = useState<HomeSample | null>(null);
  const [sampleFailed, setSampleFailed] = useState(false);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const reportInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    loadHomeSample()
      .then((s) => {
        if (!cancelled) setSample(s);
      })
      .catch(() => {
        if (!cancelled) setSampleFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const openPdfPicker = () => {
    if (onOfferLocalFile) {
      pdfInputRef.current?.click();
      return;
    }
    onNavigateWorkspace(false, "pdf");
  };

  const openReportPicker = () => {
    if (onOfferLocalFile) {
      reportInputRef.current?.click();
      return;
    }
    onNavigateWorkspace(false, "report");
  };

  const goHelp = (e?: React.MouseEvent) => {
    if (onNavigateHelp) {
      e?.preventDefault();
      onNavigateHelp();
    }
  };

  const sampleDisplay = exampleDisplayCopy(
    "amount",
    sample?.title ?? "Example",
    sample?.mechanism ?? "",
  );

  return (
    <div className={styles.page}>
      <input
        ref={pdfInputRef}
        id="home-input-open-pdf"
        type="file"
        accept="application/pdf,.pdf"
        className={styles.visuallyHidden}
        aria-hidden="true"
        tabIndex={-1}
        onChange={(event) => takeChosenFile(event, onOfferLocalFile)}
      />
      <input
        ref={reportInputRef}
        id="home-input-open-report"
        type="file"
        accept="application/json,.json,.inkflip.json"
        className={styles.visuallyHidden}
        aria-hidden="true"
        tabIndex={-1}
        onChange={(event) => takeChosenFile(event, onOfferLocalFile)}
      />

      <header className={styles.header}>
        <div className={styles.headerInner}>
          <a href="#/" className={styles.brand} aria-label="Inkflip home">
            <span className={styles.mark} aria-hidden="true">
              if
            </span>
            <span>inkflip</span>
            <span className={styles.descriptor}>PDF reading inspector</span>
          </a>

          <nav className={styles.navLinks} aria-label="Main navigation">
            <a
              href="#/help"
              className={styles.navLink}
              onClick={(e) => goHelp(e)}
            >
              Help
            </a>
          </nav>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.hero} aria-labelledby="hero-headline">
          <div className={styles.heroLead}>
            <h1 id="hero-headline" className={styles.headline}>
              Check the text behind your PDF.
            </h1>
            <p className={styles.lede}>
              Compare the text you see with the text software reads. Choose a PDF
              to inspect the differences.
            </p>
            <p className={styles.privacyNote}>Your files stay in your browser.</p>

            <div className={styles.actionRow}>
              <button
                id="btn-open-locally"
                type="button"
                className={styles.btnPrimary}
                onClick={openPdfPicker}
              >
                Check a PDF
              </button>
              <button
                id="btn-try-example"
                type="button"
                className={styles.btnSecondary}
                onClick={() => onNavigateWorkspace(true)}
              >
                Try an example
              </button>
              <button
                id="btn-open-report"
                type="button"
                className={styles.btnQuiet}
                onClick={openReportPicker}
              >
                Open a saved report
              </button>
            </div>
          </div>

          <aside className={styles.heroSample} aria-label="Example">
            {sample === null ? (
              sampleFailed ? (
                <p className={styles.sampleFallback}>
                  The sample panel is unavailable. Every example is still in the
                  gallery below.
                </p>
              ) : (
                <p className={styles.sampleFallback} aria-live="polite">
                  Loading example…
                </p>
              )
            ) : (
              <>
                <p className={styles.sampleLabel}>Example</p>
                <p className={styles.sampleTitle}>{sampleDisplay.title}</p>
                {sample.visualAmount !== null && sample.extractedAmount !== null && (
                  <div className={styles.sampleReadings} role="group" aria-label="The two readings">
                    <div className={styles.sampleReading}>
                      <span className={styles.sampleReadingLabel}>
                        PDF text · {sample.readers.find((r) => r.method === "native_text")?.name ?? "PDF.js"}
                      </span>
                      <span className={styles.sampleReadingValue}>{sample.extractedAmount}</span>
                    </div>
                    <div className={`${styles.sampleReading} ${styles.sampleReadingAlt}`}>
                      <span className={styles.sampleReadingLabel}>
                        Text read from image · {sample.readers.find((r) => r.method === "ocr")?.name ?? "OCR"}
                      </span>
                      <span className={styles.sampleReadingValue}>{sample.visualAmount}</span>
                    </div>
                  </div>
                )}
                {onOpenExample !== undefined && (
                  <button
                    type="button"
                    className={styles.btnPrimary}
                    onClick={() => onOpenExample("amount")}
                  >
                    Inspect this example
                  </button>
                )}
                <details className={styles.sampleDetails}>
                  <summary className={styles.detailsSummary}>Example files and readers</summary>
                  <p className={styles.sampleMechanism}>{sample.mechanism}</p>
                  <p className={styles.sampleReaders}>
                    Read by{" "}
                    {sample.readers.map((r) => `${r.name} ${r.version}`.trim()).join(" · ")}
                  </p>
                  <p className={styles.sampleActions}>
                    <a className={styles.sampleLink} href={sample.sampleUrl} target="_blank" rel="noopener">
                      Open the full sample
                    </a>
                    <a className={styles.sampleLink} href={sample.reportUrl} download>
                      Captured report (JSON)
                    </a>
                  </p>
                  <p className={styles.sampleNote}>This is a sample, not a file you uploaded.</p>
                </details>
              </>
            )}
          </aside>
        </section>

        <section
          id="inspection"
          className={styles.sectionWide}
          aria-labelledby="inspection-heading"
        >
          <h2 id="inspection-heading" className={styles.sectionHeading}>
            Inspection workflow
          </h2>
          <p className={styles.sectionText}>
            Inkflip renders the page, reads the PDF text layer, and reads the
            page image with OCR (optical character recognition: reading letters
            from pixels). Then it shows those readings together so you can see
            where they differ.
          </p>
          {sampleFailed ? (
            <p className={styles.sectionText}>
              The recorded sample could not be loaded. The gallery below still
              opens each example in the inspector.
            </p>
          ) : (
            <InspectionPreview sample={sample} loading={sample === null} />
          )}
        </section>

        <section
          id="capabilities"
          className={styles.sectionWide}
          aria-labelledby="capabilities-heading"
        >
          <h2 id="capabilities-heading" className={styles.sectionHeading}>
            What you can inspect
          </h2>
          <dl className={styles.capabilityList}>
            <div>
              <dt>Pages and regions</dt>
              <dd>Choose which pages to check, or outline one region on a page.</dd>
            </div>
            <div>
              <dt>Repeated text</dt>
              <dd>
                Identical strings at different positions stay separate, so a
                repeated amount is not collapsed into one hit.
              </dd>
            </div>
            <div>
              <dt>Notes</dt>
              <dd>
                Add your own notes on a finding. Notes are not reader output and
                do not change the evidence.
              </dd>
            </div>
            <div>
              <dt>Source PDF in JSON</dt>
              <dd>
                A JSON report can include the original PDF, or omit it. HTML
                reports do not embed the file.
              </dd>
            </div>
          </dl>
        </section>

        {onOpenExample !== undefined && (
          <section id="examples" className={styles.sectionWide} aria-label="Examples">
            <ExamplesGallery onOpenExample={onOpenExample} />
          </section>
        )}

        <section id="reports" className={styles.sectionWide} aria-labelledby="reports-heading">
          <h2 id="reports-heading" className={styles.sectionHeading}>
            Reports you can save
          </h2>
          <div className={styles.reportGrid}>
            <article className={styles.reportCard}>
              <h3 className={styles.reportTitle}>HTML, for reading</h3>
              <p className={styles.sectionText}>
                A script-free page you can open without Inkflip. It lists the
                findings and readings. It does not embed the original PDF.
              </p>
              <div className={styles.htmlPreview} aria-label="HTML report excerpt">
                <p className={styles.htmlPreviewTitle}>
                  {sample?.findingTitle ?? "This amount reads differently"}
                </p>
                <p className={styles.htmlPreviewBody}>
                  Named readings from each reader, the page they came from, and
                  how they were checked — readable without this app.
                </p>
              </div>
            </article>
            <article className={styles.reportCard}>
              <h3 className={styles.reportTitle}>JSON, for reopening</h3>
              <p className={styles.sectionText}>
                A file you can open again in Inkflip through the same validation
                as any other saved report. Include the original PDF only when
                you choose to.
              </p>
              <ul className={styles.reportFacts}>
                <li>Reopens in this browser app.</li>
                <li>Original PDF is opt-in, not default.</li>
                <li>Notes export only when you include them.</li>
              </ul>
            </article>
          </div>
        </section>

        <section id="local" className={styles.sectionNarrow} aria-labelledby="local-heading">
          <h2 id="local-heading" className={styles.sectionHeading}>
            Browser-local operation
          </h2>
          <p className={styles.sectionText}>
            Files stay in this tab. There is no account and no upload. Closing
            the tab discards the session unless you saved a report. OCR uses a
            model loaded from this app; it still runs locally after that.
          </p>
        </section>
      </main>

      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <button type="button" className={styles.btnPrimary} onClick={openPdfPicker}>
            Check a PDF
          </button>
          <nav className={styles.footerNav} aria-label="Footer">
            <a href="https://github.com/zubalr/inkflip">GitHub</a>
            <a href="#/help" onClick={(e) => goHelp(e)}>
              Help
            </a>
          </nav>
          <details className={styles.footerDetails}>
            <summary className={styles.detailsSummary}>macOS and Docker companion</summary>
            <p className={styles.sectionText}>
              The same inspection also exists as a native PDFium reader through
              the macOS and Docker companion, used to compare independent reader
              implementations. See Help for CLI commands.
            </p>
          </details>
        </div>
      </footer>
    </div>
  );
};

export default Home;
