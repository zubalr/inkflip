import React from "react";
import styles from "./HelpPage.module.css";

export interface HelpPageProps {
  readonly onNavigateHome: () => void;
  readonly onNavigateWorkspace: (loadExample?: boolean) => void;
}

export const HelpPage: React.FC<HelpPageProps> = ({
  onNavigateHome,
  onNavigateWorkspace,
}) => {
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
              onClick={() => onNavigateWorkspace(true)}
            >
              Open Workspace
            </button>
          </nav>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.hero} aria-labelledby="help-headline">
          <div className={styles.eyebrow}>Product Guide &amp; Invariants</div>
          <h1 id="help-headline" className={styles.headline}>
            Understanding Inkflip
          </h1>
          <p className={styles.lede}>
            Inkflip is an offline-capable, privacy-preserving PDF reading inspector. It exposes
            divergences between the visible page rendering and extracted text streams across
            multiple independent reader engines.
          </p>
        </section>

        <section aria-labelledby="core-concepts-heading">
          <h2 id="core-concepts-heading" className={styles.sectionHeading}>
            Core Concepts
          </h2>
          <div className={styles.grid}>
            <article className={styles.card}>
              <h3 className={styles.cardTitle}>
                Local-First Privacy
                <span className={`${styles.cardBadge} ${styles.cardBadgeHighlight}`}>
                  Zero Cloud
                </span>
              </h3>
              <p className={styles.cardText}>
                Your documents never leave your device. All rendering, text extraction, coordinate
                mapping, and alignment checks run entirely inside your browser sandbox or local
                companion runtime.
              </p>
              <ul className={styles.cardList}>
                <li>No telemetry, analytics, or third-party tracking.</li>
                <li>No remote servers or cloud storage dependencies.</li>
                <li>Sandboxed Web Workers isolate reader execution.</li>
              </ul>
            </article>

            <article className={styles.card}>
              <h3 className={styles.cardTitle}>
                Multi-Reader Comparison &amp; OCR
                <span className={styles.cardBadge}>Parallel</span>
              </h3>
              <p className={styles.cardText}>
                Different PDF readers interpret text streams, font encodings, and layout matrices in
                divergent ways. Inkflip compares readings from distinct engines side-by-side.
              </p>
              <ul className={styles.cardList}>
                <li>
                  <strong>PDF.js:</strong> Standard browser client-side content stream extraction.
                </li>
                <li>
                  <strong>PDFium / Native:</strong> High-fidelity C++ engine extractions via companion.
                </li>
                <li>
                  <strong>Tesseract OCR:</strong> Pixel-level optical character recognition from
                  rendered raster images.
                </li>
              </ul>
            </article>

            <article className={styles.card}>
              <h3 className={styles.cardTitle}>
                Geometry &amp; Selection
                <span className={styles.cardBadge}>Canonical</span>
              </h3>
              <p className={styles.cardText}>
                Every extracted token and bounding box is mapped to canonical PDF coordinate space
                points. Selecting any finding immediately highlights its geometric bounds.
              </p>
              <ul className={styles.cardList}>
                <li>Interactive highlights link directly to source occurrence lists.</li>
                <li>Accessible text layer exposes full character occurrences to screen readers.</li>
                <li>Keyboard disclosure uses standard <code>aria-current</code> semantics.</li>
              </ul>
            </article>

            <article className={styles.card}>
              <h3 className={styles.cardTitle}>
                Import &amp; Export Contracts
                <span className={styles.cardBadge}>Strict Schema</span>
              </h3>
              <p className={styles.cardText}>
                Reports are portable evidence packages. Imported reports are validated strictly
                against the central JSON Schema before any data is mounted.
              </p>
              <ul className={styles.cardList}>
                <li>Single-file HTML and standalone JSON exports.</li>
                <li>Replayable offline without external network assets.</li>
                <li>Strict import gate rejects malformed or unverified payloads.</li>
              </ul>
            </article>

            <article className={styles.card}>
              <h3 className={styles.cardTitle}>
                Offline Readiness
                <span className={styles.cardBadge}>Independent</span>
              </h3>
              <p className={styles.cardText}>
                Once loaded, Inkflip functions entirely offline. All scripts, fonts, and WebAssembly
                bundles are local assets without external CDN requirements.
              </p>
              <ul className={styles.cardList}>
                <li>Browser cache persists app assets for disconnected use.</li>
                <li>No session timeouts or remote entitlement checks.</li>
              </ul>
            </article>

            <article className={styles.card}>
              <h3 className={styles.cardTitle}>
                Coverage Measurement
                <span className={styles.cardBadge}>Audit</span>
              </h3>
              <p className={styles.cardText}>
                Inkflip reports the exact percentage of page text and geometry that each reader
                successfully covered, ensuring visibility into partial extractions.
              </p>
              <ul className={styles.cardList}>
                <li>Explicit character counts per reader and per page.</li>
                <li>Visual indication of unmapped or overlapping glyph zones.</li>
              </ul>
            </article>
          </div>
        </section>

        <section aria-labelledby="limits-heading">
          <div className={styles.noticeCard}>
            <h2 id="limits-heading" className={styles.noticeTitle}>
              Explicit Invariants &amp; Boundaries
            </h2>
            <p className={styles.noticeText}>
              <strong>Invariant I06 (Non-Certification):</strong> Inkflip surfaces localized,
              measurable differences between independent reader implementations. Identifying a
              difference does not establish which reading is correct or authoritative. The absence of
              detected differences does NOT certify that a document is authentic, safe, or free of
              hidden content.
            </p>
            <p className={`${styles.noticeText}`} style={{ marginTop: "var(--space-3)" }}>
              <strong>Invariant I11 (Explicit Omissions):</strong> When a reader fails, encounters an
              unsupported operator, or cannot parse an element, Inkflip records the event as an
              explicit omission. Silence is never substituted for missing coverage.
            </p>
          </div>
        </section>

        <section className={styles.guidesSection} aria-labelledby="guides-heading">
          <h2 id="guides-heading" className={styles.sectionHeading}>
            Available Project Guides
          </h2>
          <div className={styles.guidesGrid}>
            <article className={styles.guideCard}>
              <span className={styles.guideCode}>docs/CLI.md</span>
              <h3 className={styles.guideTitle}>Command-Line Interface</h3>
              <p className={styles.guideDesc}>
                Reference for running batch corpus comparisons and native companion inspections from
                the terminal.
              </p>
            </article>

            <article className={styles.guideCard}>
              <span className={styles.guideCode}>docs/accessibility/flows.md</span>
              <h3 className={styles.guideTitle}>Accessibility &amp; Assistive Flows</h3>
              <p className={styles.guideDesc}>
                Keyboard navigation walks, screen reader announcements, and automated axe-core
                compliance requirements.
              </p>
            </article>

            <article className={styles.guideCard}>
              <span className={styles.guideCode}>docs/CORPUS.md</span>
              <h3 className={styles.guideTitle}>Corpus &amp; Test Invariants</h3>
              <p className={styles.guideDesc}>
                Explanation of synthetic, adversarial, and real-world test fixtures used to verify
                reader divergence detection.
              </p>
            </article>

            <article className={styles.guideCard}>
              <span className={styles.guideCode}>docs/READER_UPGRADE.md</span>
              <h3 className={styles.guideTitle}>Reader Integration Guide</h3>
              <p className={styles.guideDesc}>
                Specifications for adding or upgrading independent PDF extraction engines and
                coordinate normalizers.
              </p>
            </article>

            <article className={styles.guideCard}>
              <span className={styles.guideCode}>docs/ATTRIBUTION.md</span>
              <h3 className={styles.guideTitle}>Attribution &amp; Licenses</h3>
              <p className={styles.guideDesc}>
                Credits, open-source licenses, and notices for bundled libraries including PDF.js,
                Tesseract.js, and font oracles.
              </p>
            </article>
          </div>
        </section>
      </main>
    </div>
  );
};

export default HelpPage;
