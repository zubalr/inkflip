/**
 * FindingNotes — human notes on a finding (T23).
 *
 * Notes are the user's own words. They are stored as contract
 * `human_entered` annotations and exported only on explicit opt-in —
 * they never become machine readings and never overwrite evidence.
 * Pointer and keyboard events stop at this block so they cannot leak
 * into the surrounding finding card's selection handlers.
 */
import React, { useState } from "react";
import type { Annotation, Finding } from "../../../../../packages/contracts/src/index.ts";
import { createAnnotation, notesForFinding, MAX_NOTE_CHARS } from "./store.ts";
import styles from "./FindingNotes.module.css";

export interface FindingNotesProps {
  readonly finding: Finding;
  /** All user notes on the open report; filtered internally. */
  readonly notes: readonly Annotation[];
  readonly onAdd: (annotation: Annotation) => void;
  readonly onRemove: (annotationId: string) => void;
}

export const FindingNotes: React.FC<FindingNotesProps> = ({
  finding,
  notes,
  onAdd,
  onRemove,
}) => {
  const [draft, setDraft] = useState("");
  const own = notesForFinding(notes, finding.id);

  const add = () => {
    const note = createAnnotation({
      findingId: finding.id,
      pageIndex: finding.page_index,
      text: draft,
    });
    if (note === null) return;
    onAdd(note);
    setDraft("");
  };

  return (
    <div
      className={styles.notes}
      data-testid="finding-notes"
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") e.stopPropagation();
      }}
    >
      <h4 className={styles.heading}>My notes</h4>
      <p className={styles.humanOnly}>
        Your notes stay yours. They are never reader output and never change the evidence.
      </p>
      {own.length > 0 && (
        <ul className={styles.list}>
          {own.map((note) => (
            <li key={note.id} className={styles.note} data-note-id={note.id}>
              <span className={styles.noteText}>
                {note.text}
                {note.author_label !== null && (
                  <span className={styles.noteAuthor}> · {note.author_label}</span>
                )}
              </span>
              <button
                type="button"
                className={styles.remove}
                aria-label={`Remove note ${note.id}`}
                data-testid={`note-remove-${note.id}`}
                onClick={() => onRemove(note.id)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className={styles.form}>
        <textarea
          className={styles.input}
          data-testid="note-input"
          placeholder="Add a note about this finding…"
          maxLength={MAX_NOTE_CHARS}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div className={styles.addRow}>
          <button
            type="button"
            className={styles.add}
            data-testid="note-add"
            disabled={draft.trim().length === 0}
            onClick={add}
          >
            Add note
          </button>
        </div>
      </div>
    </div>
  );
};

export default FindingNotes;
