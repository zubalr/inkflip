import React, { useState } from "react";
import styles from "./Home.module.css";

export interface HomeProps {
  onNavigateWorkspace: (withExample?: boolean) => void;
}

export const Home: React.FC<HomeProps> = ({ onNavigateWorkspace }) => {
  const [exampleMode, setExampleMode] = useState<"page" | "reading">("page");

  return (
    <div className={styles.page}>
      {/* 64px Header */}
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
            <button
              type="button"
              className={styles.navLink}
              onClick={() => onNavigateWorkspace(true)}
            >
              Try Example
            </button>
            <a href="#how-it-works" className={styles.navLink}>
              How it works
            </a>
            <a href="#limits" className={styles.navLink}>
              Limits
            </a>
            <button
              type="button"
              className={styles.btnSecondary}
              style={{ minHeight: "36px", padding: "0 16px" }}
              onClick={() => onNavigateWorkspace(false)}
            >
              Open Workspace
            </button>
          </nav>
        </div>
      </header>

      {/* Main Landing Content */}
      <main className={styles.main}>
        {/* Editorial 2-Column Hero */}
        <section className={styles.heroGrid} aria-labelledby="hero-headline">
          {/* Left Column (Editorial) */}
          <div className={styles.heroLeft}>
            <span className={styles.eyebrow}>One document. More than one reading.</span>
            <h1 id="hero-headline" className={styles.headline}>
              Your PDF can look right and <em>read wrong</em>.
            </h1>
            <p className={styles.lede}>
              Compare the visible page with named text extractions and OCR. Pinpoint differences,
              inspect coordinate sources, and keep portable evidence on your device.
            </p>

            <div className={styles.actionRow}>
              <button
                id="btn-try-example"
                type="button"
                className={styles.btnPrimary}
                onClick={() => onNavigateWorkspace(true)}
              >
                Try the example
              </button>
              <button
                id="btn-open-locally"
                type="button"
                className={styles.btnSecondary}
                onClick={() => onNavigateWorkspace(false)}
              >
                Open locally
              </button>
            </div>
          </div>

          {/* Right Column (Above-the-fold prepared example stage) */}
          <div className={styles.heroRight}>
            <div className={styles.exampleCard} aria-label="Prepared example demonstration">
              <div className={styles.exampleHeader}>
                <span className={styles.exampleBadge}>PREPARED DEMO</span>
                <div role="tablist" aria-label="Example view mode">
                  <button
                    type="button"
                    role="tab"
                    id="hero-tab-page"
                    aria-selected={exampleMode === "page"}
                    className={styles.navLink}
                    style={{
                      fontWeight: exampleMode === "page" ? 700 : 400,
                      marginRight: "8px",
                    }}
                    onClick={() => setExampleMode("page")}
                  >
                    Page
                  </button>
                  <button
                    type="button"
                    role="tab"
                    id="hero-tab-reading"
                    aria-selected={exampleMode === "reading"}
                    className={styles.navLink}
                    style={{ fontWeight: exampleMode === "reading" ? 700 : 400 }}
                    onClick={() => setExampleMode("reading")}
                  >
                    Reading
                  </button>
                </div>
              </div>

              <div
                className={styles.exampleCrop}
                role="region"
                aria-label="Demonstrated reading difference"
              >
                <div className={styles.exampleAmount}>
                  {exampleMode === "page" ? "$100.00" : "$1,000.00"}
                </div>
                <div className={styles.exampleDiffInfo}>
                  {exampleMode === "page"
                    ? "Rendered visual pixel crop reads: $100.00"
                    : "Native reader stream extracted: $1,000.00"}
                </div>
              </div>

              <div style={{ fontSize: "var(--text-caption)", color: "var(--color-muted)" }}>
                <strong>Finding:</strong> This amount reads differently between rendered appearance
                and underlying content stream.
              </div>
            </div>
          </div>
        </section>

        {/* How It Works Section */}
        <section id="how-it-works" style={{ marginBottom: "var(--space-8)" }}>
          <h2 className={styles.sectionHeading}>How Inkflip Works</h2>
          <div className={styles.featureGrid}>
            <article className={styles.featureCard}>
              <h3 className={styles.featureTitle}>1. Extract Multiple Readings</h3>
              <p className={styles.featureText}>
                Run parallel independent PDF reader implementations (PDF.js, PDFium, OCR) directly
                in your browser with isolated sandboxing.
              </p>
            </article>

            <article className={styles.featureCard}>
              <h3 className={styles.featureTitle}>2. Align &amp; Compare Geometry</h3>
              <p className={styles.featureText}>
                Map character positions and bounding boxes to canonical page points. Detect material
                token differences without probabilistic guessing.
              </p>
            </article>

            <article className={styles.featureCard}>
              <h3 className={styles.featureTitle}>3. Preserve Evidence Locally</h3>
              <p className={styles.featureText}>
                Export self-contained, replayable HTML and JSON evidence reports. No files or
                document data ever leave your machine.
              </p>
            </article>
          </div>
        </section>

        {/* Limitations & Invariants Section */}
        <section id="limits">
          <h2 className={styles.sectionHeading}>Explicit Limits &amp; Boundaries</h2>
          <div className={styles.featureCard}>
            <p className={styles.featureText}>
              Inkflip highlights localized differences between reader implementations. A difference
              does not establish which reading is correct, and the absence of differences does not
              constitute a document correctness or safety certification (Invariant I06).
            </p>
          </div>
        </section>
      </main>
    </div>
  );
};

export default Home;
