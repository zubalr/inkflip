import React from "react";
import type { Finding, Occurrence, Reader } from "../../../../../packages/contracts/src/index.ts";
import { explainFinding } from "../../../../../packages/explanations/src/index.ts";
import { Disclosure } from "../../components/Controls/Disclosure";
import { Button } from "../../components/Controls/Button";
import styles from "./FindingCard.module.css";

export interface FindingCardProps {
  finding: Finding;
  occurrences: Occurrence[];
  readers: Reader[];
  onKeepEvidence?: (finding: Finding) => void;
  onSelectFinding?: (finding: Finding) => void;
  isSelected?: boolean;
}

export const FindingCard: React.FC<FindingCardProps> = ({
  finding,
  occurrences,
  readers,
  onKeepEvidence,
  onSelectFinding,
  isSelected = false,
}) => {
  const explanation = explainFinding(finding, occurrences, readers);

  return (
    <article
      id={`finding-${finding.id}`}
      className={`${styles.card} ${isSelected ? styles.cardSelected : ""}`}
      aria-labelledby={`finding-title-${finding.id}`}
      onClick={() => onSelectFinding?.(finding)}
    >
      <header className={styles.header}>
        <div className={styles.titleArea}>
          <h3 id={`finding-title-${finding.id}`} className={styles.title}>
            {explanation.title}
          </h3>
          <div className={styles.metaRow}>
            <span>Page {finding.page_index + 1}</span>
            <span className={styles.badge}>{explanation.alignmentLabel}</span>
            {explanation.isMaterialToken && (
              <span className={`${styles.badge} ${styles.badgeMaterial}`}>Material difference</span>
            )}
            {finding.alignment === "ambiguous" && (
              <span className={`${styles.badge} ${styles.badgeAmbiguous}`}>Ambiguous</span>
            )}
          </div>
        </div>
      </header>

      <p className={styles.explanation}>{explanation.explanation}</p>

      {explanation.readings.length > 0 && (
        <div className={styles.readingsGrid} role="group" aria-label="Comparative readings">
          {explanation.readings.map((item, idx) => (
            <div key={`${item.readerId}-${item.occurrenceId}-${idx}`} className={styles.readingBox}>
              <span className={styles.readerLabel}>
                {item.readerName} {item.readerVersion ? `v${item.readerVersion}` : ""}
                {item.ordinal !== undefined ? ` (occurrence #${item.ordinal})` : ""}
              </span>
              <div
                className={`${styles.readingValue} ${idx > 0 ? styles.readingAlt : ""}`}
                dir="auto"
              >
                <bdi>{item.readingText}</bdi>
              </div>
            </div>
          ))}
        </div>
      )}

      <p className={styles.disclaimer}>{explanation.disclaimer}</p>

      <Disclosure id={`disclosure-${finding.id}`} title="How this was checked">
        <div className={styles.detailsContent}>
          {explanation.basis && (
            <div>
              <strong>Basis:</strong> {explanation.basis}
            </div>
          )}
          {finding.check_ids.length > 0 && (
            <div>
              <strong>Checks:</strong> {finding.check_ids.join(", ")}
            </div>
          )}
          {explanation.limitations.length > 0 && (
            <div>
              <strong>Limitations:</strong>
              <ul className={styles.limitationsList}>
                {explanation.limitations.map((lim, i) => (
                  <li key={i}>{lim}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Disclosure>

      {onKeepEvidence && (
        <div className={styles.actions}>
          <Button
            variant="ghost"
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              onKeepEvidence(finding);
            }}
          >
            Keep this evidence
          </Button>
        </div>
      )}
    </article>
  );
};

export default FindingCard;
