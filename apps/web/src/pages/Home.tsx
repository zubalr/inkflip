import React, { useEffect, useState } from "react";
import styles from "./Home.module.css";
import { ExamplesGallery } from "../features/gallery/ExamplesGallery";
import { loadHomeSample, type HomeSample } from "./homeExample";

export interface HomeProps {
  onNavigateWorkspace: (withExample?: boolean, open?: "pdf" | "report") => void;
  onOpenExample?: (exampleId: string) => void;
  onNavigateHelp?: () => void;
}

export const Home: React.FC<HomeProps> = ({
  onNavigateWorkspace,
  onOpenExample,
  onNavigateHelp,
}) => {
  // One real shipped example, loaded from its recorded manifest for the
  // hero's right side. Load/failure states keep the page honest and usable.
  const [sample, setSample] = useState<HomeSample | null>(null);
  const [sampleFailed, setSampleFailed] = useState(false);

  React.useEffect(() => {
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

  return (
    <div className={styles.page}>
      {/* Compact header: brand plus a single Help link. */}
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
              onClick={(e) => {
                if (onNavigateHelp) {
                  e.preventDefault();
                  onNavigateHelp();
                }
              }}
            >
              Help
            </a>
          </nav>
        </div>
      </header>

      <main className={styles.main}>
        {/* Hero: actions on the left, one real shipped example on the right. */}
        <section className={styles.hero} aria-labelledby="hero-headline">
          <div className={styles.heroLead}>
            <h1 id="hero-headline" className={styles.headline}>
              Your PDF can look right and <em>read wrong</em>.
            </h1>
            <p className={styles.lede}>
              Inkflip compares what a PDF shows on the page with the text its
              layers claim — so a "$100" that extracts as "$1,000" is caught
              before it reaches your data.
            </p>
            <p className={styles.privacyNote}>Your files stay in your browser.</p>

            <div className={styles.actionRow}>
              <button
                id="btn-open-locally"
                type="button"
                className={styles.btnPrimary}
                onClick={() => onNavigateWorkspace(false, "pdf")}
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
                onClick={() => onNavigateWorkspace(false, "report")}
              >
                Open a saved report
              </button>
            </div>
          </div>

          {/* Right side: the real amount example, from its recorded manifest. */}
          <aside className={styles.heroSample} aria-label="Real example from the shipped app">
            {sample === null ? (
              sampleFailed ? (
                // Failure fallback: the page stays honest and usable.
                <p className={styles.sampleFallback}>
                  The sample panel is unavailable — every example is still in
                  the gallery below.
                </p>
              ) : (
                <p className={styles.sampleFallback} aria-live="polite">
                  Loading a real sample…
                </p>
              )
            ) : (
              <>
                <p className={styles.sampleKicker}>From a real captured run</p>
                <p className={styles.sampleTitle}>{sample.title}</p>
                {sample.visualAmount !== null && sample.extractedAmount !== null && (
                  <div className={styles.sampleReadings} role="group" aria-label="The two readings">
                    <div className={styles.sampleReading}>
                      <span className={styles.sampleReadingLabel}>Shown on the page</span>
                      <span className={styles.sampleReadingValue}>{sample.visualAmount}</span>
                    </div>
                    <span className={styles.sampleVs} aria-hidden="true">
                      vs
                    </span>
                    <div className={`${styles.sampleReading} ${styles.sampleReadingAlt}`}>
                      <span className={styles.sampleReadingLabel}>Text layer says</span>
                      <span className={styles.sampleReadingValue}>{sample.extractedAmount}</span>
                    </div>
                  </div>
                )}
                <p className={styles.sampleMechanism}>{sample.mechanism}</p>
                <p className={styles.sampleReaders}>
                  Read by{" "}
                  {sample.readers.map((r) => `${r.name} ${r.version}`).join(" · ")}
                </p>
                <p className={styles.sampleActions}>
                  <a className={styles.sampleLink} href={sample.sampleUrl} target="_blank" rel="noopener">
                    Open the full sample
                  </a>
                  {onOpenExample !== undefined && (
                    <button
                      type="button"
                      className={styles.sampleLinkBtn}
                      onClick={() => onOpenExample("amount")}
                    >
                      Inspect its captured report
                    </button>
                  )}
                  <a className={styles.sampleLink} href={sample.reportUrl} download>
                    Captured report (JSON)
                  </a>
                </p>
                <p className={styles.sampleNote}>Sample document — not your file, not a verdict.</p>
              </>
            )}
          </aside>
        </section>

        {/* How it works: one plain paragraph; native companion in a disclosure. */}
        <section
          id="how-it-works"
          className={styles.sectionNarrow}
          aria-labelledby="how-it-works-heading"
        >
          <h2 id="how-it-works-heading" className={styles.sectionHeading}>
            How it works
          </h2>
          <p className={styles.sectionText}>
            Inkflip runs entirely in your browser: it renders each page, reads
            the text layer, and reads the rendered pixels with OCR — then shows
            the readings side by side.
          </p>
          <details className={styles.details}>
            <summary className={styles.detailsSummary}>About the readers and the native companion</summary>
            <p className={styles.sectionText}>
              Pages render with PDF.js 6.3.289 and OCR runs on Tesseract 7.0.0
              (English). The same inspection also exists as a native PDFium
              reader through the macOS/Docker companion, used to compare
              independent reader implementations.
            </p>
          </details>
        </section>

        {onOpenExample !== undefined && (
          <section id="examples" className={styles.sectionWide} aria-label="Real examples you can inspect">
            <ExamplesGallery onOpenExample={onOpenExample} />
          </section>
        )}

        {/* Honest limits. */}
        <section id="limits" className={styles.sectionNarrow} aria-labelledby="limits-heading">
          <h2 id="limits-heading" className={styles.sectionHeading}>
            Limits
          </h2>
          <p className={styles.sectionText}>
            A difference needs human review: Inkflip shows both readings and
            never decides which one is correct. A missing difference is not a
            certificate, and OCR quality depends on the scan.
          </p>
        </section>
      </main>
    </div>
  );
};

export default Home;
