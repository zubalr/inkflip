/**
 * ExamplesGallery — the six public example cards (T21).
 *
 * Renders the generated `/examples/index.json` card list and a per-card
 * detail view backed by the real captured manifests. Everyday titles and
 * one-line descriptions are a presentation overlay; sealed reports and
 * generated manifests are not rewritten here.
 *
 * "Open report" routes into the workspace's real import gate — the
 * captured report is validated like any user-supplied file before it
 * mounts, so the gallery never bypasses the same checks a user gets.
 */
import React, { useEffect, useState } from "react";
import styles from "./ExamplesGallery.module.css";
import { exampleDisplayCopy } from "./displayCopy";
import { loadExampleIndex, loadExampleManifest } from "./loader";
import type { ExampleCard, ExampleIndex, ExampleManifest } from "./types";

export interface ExamplesGalleryProps {
  /** Called with the card id when the user opens a captured report. */
  readonly onOpenExample: (exampleId: string) => void;
}

function shortSha(sha: string): string {
  return sha.slice(0, 12);
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  return `${(n / 1024).toFixed(1)} KiB`;
}

function CardDetail({
  card,
  manifest,
  onOpen,
  onClose,
}: {
  card: ExampleCard;
  manifest: ExampleManifest | null;
  onOpen: () => void;
  onClose: () => void;
}) {
  const display = exampleDisplayCopy(card.example_id, card.card_title, card.mechanism);
  return (
    <div className={styles.detail} data-testid={`example-detail-${card.example_id}`}>
      <div className={styles.detailHeader}>
        <div>
          <h3 className={styles.detailCardTitle}>{display.title}</h3>
          <p className={styles.detailLead}>{display.description}</p>
        </div>
        <button type="button" className={styles.close} onClick={onClose}>
          Close
        </button>
      </div>

      {manifest === null ? (
        <p className={styles.sub}>Loading manifest…</p>
      ) : (
        <details className={styles.techDetails} data-testid="example-tech-details">
          <summary>Fixture, readers, and files</summary>
          <p className={styles.sub}>
            {card.fixture_id} · {card.family}
          </p>
          <div className={styles.mechanismSection} data-testid="card-mechanism-section">
            <p className={styles.mechanismText}>{card.mechanism}</p>
            {card.example_id === "duplicates" && (
              <p className={styles.evidenceNote} data-testid="duplicates-evidence-note">
                Four distinct &ldquo;$100&rdquo; occurrences appear at separate page coordinates
                (occurrences #0, #2, #3, and #5). In Reading mode or the accessible text layer, each
                occurrence is individually addressable and selectable by occurrence ordinal.
              </p>
            )}
          </div>
          {card.timing_ms != null && (
            <p className={styles.sha}>Recorded run: {card.timing_ms} ms</p>
          )}
          <div className={styles.detailGrid}>
            <section aria-label="Source files">
              <h4>Source files</h4>
              <ul className={styles.fileList}>
                {Object.entries(manifest.files).map(([key, f]) => (
                  <li key={key}>
                    <span>
                      <a href={f.download_url} download={f.filename}>
                        {f.filename}
                      </a>{" "}
                      ({f.role})
                    </span>
                    <span className={styles.sha}>
                      {shortSha(f.sha256)} · {formatBytes(f.byte_length)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
            <section aria-label="Readers executed">
              <h4>Readers executed</h4>
              <ul className={styles.readerList}>
                {Object.values(manifest.readers).map((r) => (
                  <li key={r.id ?? r.name}>
                    {r.name} {r.version} ({r.method})
                  </li>
                ))}
              </ul>
              <h4 className={styles.findingsHeading}>Findings</h4>
              <ul className={styles.findingList}>
                {manifest.findings.map((f) => (
                  <li key={f.id}>
                    {f.title} <span className={styles.sha}>({f.category})</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
          <p className={styles.rights}>{manifest.rights}</p>
        </details>
      )}

      <div className={styles.openActions}>
        <button type="button" className={styles.openBtn} onClick={onOpen}>
          Inspect this example
        </button>
      </div>
    </div>
  );
}

export const ExamplesGallery: React.FC<ExamplesGalleryProps> = ({ onOpenExample }) => {
  const [index, setIndex] = useState<ExampleIndex | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [manifest, setManifest] = useState<ExampleManifest | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadExampleIndex()
      .then((ix) => {
        if (!cancelled) setIndex(ix);
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : String(exc));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (openId === null || index === null) {
      setManifest(null);
      return;
    }
    const card = index.cards.find((c) => c.example_id === openId);
    if (!card) return;
    let cancelled = false;
    loadExampleManifest(card)
      .then((m) => {
        if (!cancelled) setManifest(m);
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : String(exc));
      });
    return () => {
      cancelled = true;
    };
  }, [openId, index]);

  const openCard = index?.cards.find((c) => c.example_id === openId) ?? null;

  return (
    <section className={styles.section} aria-labelledby="examples-heading" data-testid="examples-gallery">
      <header className={styles.headingGroup}>
        <h2 id="examples-heading" className={styles.heading}>
          Try an example
        </h2>
        <p className={styles.lede}>Open a sample PDF and inspect its results.</p>
      </header>
      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {openCard !== null && (
        <CardDetail
          card={openCard}
          manifest={manifest}
          onOpen={() => onOpenExample(openCard.example_id)}
          onClose={() => setOpenId(null)}
        />
      )}

      <div className={styles.grid}>
        {(index?.cards ?? []).map((card) => {
          const display = exampleDisplayCopy(card.example_id, card.card_title, card.mechanism);
          const open = openId === card.example_id;
          return (
            <div key={card.example_id} className={styles.cardWrap}>
              <button
                type="button"
                className={styles.card}
                data-testid={`example-card-${card.example_id}`}
                aria-expanded={open}
                aria-label={`${display.title} — details`}
                onClick={() => setOpenId(open ? null : card.example_id)}
              >
                <h3 className={styles.cardTitle}>{display.title}</h3>
                <p className={styles.mechanism}>{display.description}</p>
                <span className={styles.cardMeta}>
                  <span>
                    {card.finding_count} finding{card.finding_count === 1 ? "" : "s"}
                  </span>
                  <span className={styles.cardDetailsHint}>{open ? "Hide details" : "Details"}</span>
                </span>
              </button>
              <button
                type="button"
                className={styles.inspectBtn}
                data-testid={`open-example-${card.example_id}`}
                onClick={() => onOpenExample(card.example_id)}
              >
                Inspect example
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default ExamplesGallery;
