/**
 * Occurrence candidate navigation (T20).
 *
 * Every occurrence a finding names stays individually addressable by id —
 * identical strings at distinct positions are never collapsed and never
 * resolved by text matching. Keyboard selection (Enter/Space) moves the
 * highlight *and* returns focus to the originating finding card; pointer
 * selection stays inside the card without re-triggering finding
 * selection. Escape returns focus without changing the selection.
 */
import React, { useCallback } from "react";
import type {
  Finding,
  Occurrence,
  Reader,
} from "../../../../../../packages/contracts/src/index.ts";
import { classifyFinding, type CandidateReading } from "../../findings/alignment/classify.ts";
import styles from "./OccurrenceCandidates.module.css";

export interface OccurrenceCandidatesProps {
  readonly finding: Finding;
  readonly occurrences: readonly Occurrence[];
  readonly readers: readonly Reader[];
  readonly selectedOccurrenceId: string | null;
  readonly onSelectOccurrence: (occ: Occurrence) => void;
  /**
   * Element id focus returns to after keyboard selection/Escape —
   * the originating finding card (`finding-item-{id}`).
   */
  readonly returnFocusId: string;
}

function positionLabel(occ: Occurrence): string {
  const poly = occ.geometry.polygon;
  if (poly === null || poly.length === 0) return "page-level";
  const xs = poly.map((p) => p[0]);
  const ys = poly.map((p) => p[1]);
  const left = Math.round(Math.min(...xs));
  const top = Math.round(Math.min(...ys));
  return `x≈${left}pt y≈${top}pt`;
}

export const OccurrenceCandidates: React.FC<OccurrenceCandidatesProps> = ({
  finding,
  occurrences,
  readers,
  selectedOccurrenceId,
  onSelectOccurrence,
  returnFocusId,
}) => {
  const semantics = classifyFinding(finding, occurrences, readers);

  const returnFocus = useCallback(() => {
    document.getElementById(returnFocusId)?.focus();
  }, [returnFocusId]);

  const onCandidateKeyDown = useCallback(
    (event: React.KeyboardEvent, candidate: CandidateReading) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        // The candidate lives inside the finding card, which has its own
        // Enter/Space handler — stop the key from re-selecting the
        // finding and wiping the occurrence selection.
        event.stopPropagation();
        onSelectOccurrence(candidate.occurrence);
        returnFocus();
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        returnFocus();
      } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const items = Array.from(
          (event.currentTarget as HTMLElement)
            .closest("[data-testid=occ-candidates]")
            ?.querySelectorAll<HTMLElement>("[data-candidate-id]") ?? [],
        );
        const idx = items.indexOf(event.currentTarget as HTMLElement);
        const next =
          event.key === "ArrowDown"
            ? items[Math.min(idx + 1, items.length - 1)]
            : items[Math.max(idx - 1, 0)];
        next?.focus();
      }
    },
    [onSelectOccurrence, returnFocus],
  );

  if (semantics.candidates.length === 0 && semantics.unresolvedIds.length === 0) {
    return null;
  }

  return (
    <div className={styles.candidates} data-testid="occ-candidates">
      <h4 className={styles.heading}>
        {semantics.candidates.length === 1
          ? "1 named reading"
          : `${semantics.candidates.length} named readings`}
      </h4>
      <ul className={styles.list} role="list">
        {semantics.candidates.map((candidate) => {
          const occ = candidate.occurrence;
          const isSelected = occ.id === selectedOccurrenceId;
          return (
            <li key={occ.id} className={styles.item}>
              <button
                type="button"
                className={`${styles.candidate} ${isSelected ? styles.candidateSelected : ""}`}
                data-testid={`occ-candidate-${occ.id}`}
                data-candidate-id={occ.id}
                aria-pressed={isSelected}
                onClick={(e) => {
                  // The candidate lives inside the finding card, whose own
                  // click handler would re-run finding selection and wipe the
                  // chosen occurrence — keep the pick local.
                  e.stopPropagation();
                  onSelectOccurrence(occ);
                }}
                onKeyDown={(e) => onCandidateKeyDown(e, candidate)}
              >
                <span className={styles.candidateText}>{occ.raw_text}</span>
                <span className={styles.candidateMeta}>
                  {candidate.readerName} · occurrence #{occ.ordinal} · {positionLabel(occ)}
                  {occ.geometry.precision !== "exact" ? ` · ${occ.geometry.precision}` : ""}
                </span>
                {candidate.identicalSiblings > 0 && (
                  <span className={styles.identicalTag} data-testid={`occ-identical-${occ.id}`}>
                    identical text, {candidate.identicalRank} of {candidate.identicalSiblings + 1}{" "}
                    at distinct positions
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      {semantics.unresolvedIds.length > 0 && (
        <p className={styles.unresolved} data-testid="occ-unresolved">
          {semantics.unresolvedIds.length} named occurrence(s) are not in this report's occurrence
          set and cannot be shown.
        </p>
      )}
    </div>
  );
};

export default OccurrenceCandidates;
