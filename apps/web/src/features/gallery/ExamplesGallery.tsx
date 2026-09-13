/**
 * ExamplesGallery — the six public example cards (T21).
 *
 * Renders the generated `/examples/index.json` card list and a per-card
 * detail view backed by the real captured manifests. Every card is backed
 * by an actual sealed run of the inspection pipeline (report.json) and
 * real staged source bytes — no prepared-looking placeholder is shown.
 *
 * "Open report" routes into the workspace's real import gate — the
 * captured report is validated like any user-supplied file before it
 * mounts, so the gallery never bypasses the same checks a user gets.
 */
import React, { useEffect, useState } from "react";
import styles from "./ExamplesGallery.module.css";
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
  return (
    <div className={styles.detail} data-testid={`example-detail-${card.example_id}`}>
      <div className={styles.detailHeader}>
        <div>
          <h3 className={styles.detailTitle}>{card.card_title}</h3>
          <p className={styles.sub}>
            {card.fixture_id} · {card.family} · prepared from a real captured run
          </p>
        </div>
        <button type="button" className={styles.close} onClick={onClose}>
          Close
        </button>
      </div>

      {manifest === null ? (
        <p className={styles.sub}>Loading manifest…</p>
      ) : (
        <>
          <div className={styles.mechanismSection} data-testid="card-mechanism-section">
            <h4>Verification Mechanism</h4>
            <p className={styles.mechanismText}>{card.mechanism}</p>
            {card.example_id === "duplicates" && (
              <p className={styles.evidenceNote} data-testid="duplicates-evidence-note">
                Four distinct &ldquo;$100&rdquo; occurrences appear at separate page coordinates (occurrences #0, #2, #3, and #5). In Reading mode or the accessible text layer, each occurrence is individually addressable and selectable by occurrence ordinal, demonstrating that identical text strings are never collapsed by string matching.
              </p>
            )}
          </div>

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
                      — {f.role}
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
                    {r.name} {r.version} — {r.method}
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
        </>
      )}

      <div className={styles.openActions}>
        <button
          type="button"
          className={styles.openBtn}
          data-testid={`open-example-${card.example_id}`}
          onClick={onOpen}
        >
          Open this report in the workspace
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
      <h2 id="examples-heading" className={styles.detailTitle}>
        Prepared examples
      </h2>
      <p className={styles.sub}>
        Six real captured runs — every card's bytes, readers and findings are recorded
        outputs of the same pipeline you can run locally.
      </p>
      {error !== null && <p className={styles.error} role="alert">{error}</p>}

      {openCard !== null && (
        <CardDetail
          card={openCard}
          manifest={manifest}
          onOpen={() => onOpenExample(openCard.example_id)}
          onClose={() => setOpenId(null)}
        />
      )}

      <div className={styles.grid}>
        {(index?.cards ?? []).map((card) => (
          <button
            key={card.example_id}
            type="button"
            className={styles.card}
            data-testid={`example-card-${card.example_id}`}
            aria-expanded={openId === card.example_id}
            onClick={() => setOpenId(openId === card.example_id ? null : card.example_id)}
          >
            <h3 className={styles.cardTitle}>{card.card_title}</h3>
            <span className={styles.fixture}>{card.fixture_id}</span>
            <p className={styles.mechanism}>{card.mechanism}</p>
            <span className={styles.cardMeta}>
              <span>{card.finding_count} finding{card.finding_count === 1 ? "" : "s"}</span>
              <span>
                {card.readers.length} readers · {card.timing_ms} ms
              </span>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
};

export default ExamplesGallery;
