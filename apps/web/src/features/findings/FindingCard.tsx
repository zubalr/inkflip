import React, { useState } from "react";
import type { Finding, Occurrence, Reader } from "../../../../../packages/contracts/src/index.ts";
import { COPY, explainFinding } from "../../../../../packages/explanations/src/index.ts";
import { Disclosure } from "../../components/Controls/Disclosure";
import { Button } from "../../components/Controls/Button";
import styles from "./FindingCard.module.css";

export interface Annotation {
  id: string;
  finding_id: string | null;
  page_index: number;
  text: string;
  author_label: string | null;
  origin: "human_entered";
}

export interface FindingCardProps {
  finding: Finding;
  occurrences: Occurrence[];
  readers: Reader[];
  annotations?: Annotation[];
  onKeepEvidence?: (finding: Finding) => void;
  onSelectFinding?: (finding: Finding) => void;
  onAddNote?: (findingId: string, text: string) => void;
  isSelected?: boolean;
}

export const FindingCard: React.FC<FindingCardProps> = ({
  finding,
  occurrences,
  readers,
  annotations = [],
  onKeepEvidence,
  onSelectFinding,
  onAddNote,
  isSelected = false,
}) => {
  const [showNoteInput, setShowNoteInput] = useState(false);
  const [newNoteText, setNewNoteText] = useState("");
  const explanation = explainFinding(finding, occurrences, readers);

  const findingNotes = annotations.filter((a) => a.finding_id === finding.id);

  const handleSaveNote = () => {
    if (!newNoteText.trim()) return;
    onAddNote?.(finding.id, newNoteText.trim());
    setNewNoteText("");
    setShowNoteInput(false);
  };

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
        <details className={styles.readingsDetails}>
          <summary className={styles.readingsSummary}>
            Reader readings ({explanation.readings.length})
          </summary>
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
        </details>
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

      {findingNotes.length > 0 && (
        <div className={styles.notesSection} role="region" aria-label="Local notes">
          <span className={styles.noteLabel}>{COPY["finding.note.label"]}</span>
          {findingNotes.map((note) => (
            <div key={note.id} className={styles.noteCard} id={`note-${note.id}`}>
              <p className={styles.noteText}>{note.text}</p>
              {note.author_label && <span className={styles.noteAuthor}>{note.author_label}</span>}
            </div>
          ))}
          <p className={styles.noteDisclosure}>{COPY["finding.note.disclosure"]}</p>
        </div>
      )}

      {showNoteInput && (
        <div className={styles.noteInputArea} onClick={(e) => e.stopPropagation()}>
          <input
            id={`input-note-${finding.id}`}
            type="text"
            className={styles.noteInput}
            placeholder="Enter local note..."
            value={newNoteText}
            onChange={(e) => setNewNoteText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleSaveNote();
              }
            }}
          />
          <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
            <Button variant="ghost" size="small" onClick={() => setShowNoteInput(false)}>
              Cancel
            </Button>
            <Button variant="primary" size="small" onClick={handleSaveNote}>
              Save Note
            </Button>
          </div>
        </div>
      )}

      <div className={styles.actions}>
        {onKeepEvidence && (
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
        )}
        <button
          id={`btn-add-note-${finding.id}`}
          type="button"
          className={styles.addNoteBtn}
          onClick={(e) => {
            e.stopPropagation();
            setShowNoteInput((prev) => !prev);
          }}
        >
          {COPY["finding.note"]}
        </button>
      </div>
    </article>
  );
};

export default FindingCard;
