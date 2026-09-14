import React from "react";
import styles from "./Home.module.css";
import { ExamplesGallery } from "../features/gallery/ExamplesGallery";

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
        {/* Single-column hero. */}
        <section className={styles.hero} aria-labelledby="hero-headline">
          <h1 id="hero-headline" className={styles.headline}>
            Your PDF can look right and <em>read wrong</em>.
          </h1>
          <p className={styles.lede}>
            Compare the text inside a PDF with what appears on the page.
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
        </section>

        {/* How it works: one plain paragraph naming the real reader roles. */}
        <section
          id="how-it-works"
          className={styles.section}
          aria-labelledby="how-it-works-heading"
        >
          <h2 id="how-it-works-heading" className={styles.sectionHeading}>
            How it works
          </h2>
          <p className={styles.sectionText}>
            PDF.js and Tesseract OCR run in the browser and compare the text inside a PDF with what
            appears on the page. The native PDFium reader is available through the separate
            macOS/Docker companion.
          </p>
        </section>

        {onOpenExample !== undefined && (
          <section id="examples" className={styles.section} aria-label="Prepared example demos">
            <span className={styles.eyebrow}>Prepared demo</span>
            <ExamplesGallery onOpenExample={onOpenExample} />
          </section>
        )}

        {/* Honest limits. */}
        <section id="limits" className={styles.section} aria-labelledby="limits-heading">
          <h2 id="limits-heading" className={styles.sectionHeading}>
            Limits
          </h2>
          <p className={styles.sectionText}>
            Differences need human review: a highlighted difference does not prove fraud or
            correctness, and the absence of differences is not a certification.
          </p>
        </section>
      </main>
    </div>
  );
};

export default Home;
