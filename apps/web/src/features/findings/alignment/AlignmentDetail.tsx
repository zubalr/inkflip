/**
 * Alignment detail for a selected finding (T20).
 *
 * States the finding's alignment semantics explicitly — difference,
 * order-only, ambiguous, unmatched, page-level, incomplete or one-sided —
 * and keeps every named occurrence navigable. Ambiguous findings show all
 * candidates with no pre-picked answer; unmatched findings never claim
 * missing text; incomplete coverage is labeled partial, not clean.
 */
import React from "react";
import type {
  Finding,
  Occurrence,
  Reader,
} from "../../../../../../packages/contracts/src/index.ts";
import { classifyFinding } from "./classify.ts";
import { OccurrenceCandidates } from "../../viewer/occurrences/OccurrenceCandidates.tsx";
import styles from "./AlignmentDetail.module.css";

export interface AlignmentDetailProps {
  readonly finding: Finding;
  readonly occurrences: readonly Occurrence[];
  readonly readers: readonly Reader[];
  readonly selectedOccurrenceId: string | null;
  readonly onSelectOccurrence: (occ: Occurrence) => void;
  /** Element id keyboard focus returns to (the finding card). */
  readonly returnFocusId: string;
}

const BADGE_CLASS: Record<string, string> = {
  difference: styles.badge_difference,
  order_only: styles.badge_order_only,
  ambiguous: styles.badge_ambiguous,
  unmatched: styles.badge_unmatched,
  page_level: styles.badge_page_level,
  incomplete: styles.badge_incomplete,
  one_sided: styles.badge_one_sided,
};

export const AlignmentDetail: React.FC<AlignmentDetailProps> = ({
  finding,
  occurrences,
  readers,
  selectedOccurrenceId,
  onSelectOccurrence,
  returnFocusId,
}) => {
  const semantics = classifyFinding(finding, occurrences, readers);

  return (
    <div
      className={styles.detail}
      data-testid="alignment-detail"
      data-alignment-class={semantics.classification}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        // Only the card's activation keys need shielding — let global
        // viewer shortcuts (n/p/f/r/+/-) keep working inside the detail.
        if (e.key === "Enter" || e.key === " ") e.stopPropagation();
      }}
    >
      <div className={styles.badgeRow}>
        <span
          className={`${styles.badge} ${BADGE_CLASS[semantics.classification] ?? ""}`}
          data-testid="alignment-class-badge"
        >
          {semantics.badge}
        </span>
      </div>
      <p className={styles.body} data-testid="alignment-body">
        {semantics.body}
      </p>
      {finding.basis ? (
        <p className={styles.basis} data-testid="alignment-basis">
          How this was checked: {finding.basis}
        </p>
      ) : null}
      {finding.limitations.length > 0 ? (
        <ul className={styles.limits} data-testid="alignment-limitations">
          {finding.limitations.map((lim, i) => (
            <li key={i}>{lim}</li>
          ))}
        </ul>
      ) : null}
      <OccurrenceCandidates
        finding={finding}
        occurrences={occurrences}
        readers={readers}
        selectedOccurrenceId={selectedOccurrenceId}
        onSelectOccurrence={onSelectOccurrence}
        returnFocusId={returnFocusId}
      />
    </div>
  );
};

export default AlignmentDetail;
