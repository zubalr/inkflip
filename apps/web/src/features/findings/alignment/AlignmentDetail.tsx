/**
 * Alignment detail for a selected finding (T20).
 *
 * States the finding's alignment semantics explicitly — difference,
 * order-only, ambiguous, unmatched, page-level, incomplete or one-sided —
 * and keeps every named occurrence navigable. Ambiguous findings show all
 * candidates with no pre-picked answer; unmatched findings never claim
 * missing text; incomplete coverage is labeled partial, not clean.
 *
 * The default view is deliberately short: the status badge, one plain
 * sentence and the named readings. Reader versions, adapter identity,
 * occurrence ordinals, coordinates, precision, basis, limitations and
 * unresolved references live in the Technical details disclosure — the
 * evidence is retained, not removed.
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

function methodLabel(reader: Reader): string {
  switch (reader.method) {
    case "native_text":
      return "PDF text";
    case "ocr":
      return "text read from image";
    case "render":
      return "page image";
    case "structure":
      return "document structure";
    default:
      return reader.method;
  }
}

function geometryLabel(occ: Occurrence): string {
  const poly = occ.geometry.polygon;
  if (poly === null || poly.length === 0) return "page-level (no polygon)";
  const xs = poly.map((p) => p[0]);
  const ys = poly.map((p) => p[1]);
  return `${poly.length}-point polygon, bounds x≈${Math.round(Math.min(...xs))}–${Math.round(
    Math.max(...xs),
  )}pt y≈${Math.round(Math.min(...ys))}–${Math.round(Math.max(...ys))}pt`;
}

export const AlignmentDetail: React.FC<AlignmentDetailProps> = ({
  finding,
  occurrences,
  readers,
  selectedOccurrenceId,
  onSelectOccurrence,
  returnFocusId,
}) => {
  const semantics = classifyFinding(finding, occurrences, readers);
  // Readers this finding's evidence names — shown in emitted order.
  const namedReaderIds = new Set(semantics.candidates.map((c) => c.occurrence.reader_id));
  const namedReaders = readers.filter((r) => namedReaderIds.has(r.id));

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
        {finding.page_index !== undefined && (
          <span className={styles.scope}>Page {finding.page_index + 1}</span>
        )}
      </div>
      <p className={styles.body} data-testid="alignment-body">
        {semantics.body}
      </p>
      <OccurrenceCandidates
        finding={finding}
        occurrences={occurrences}
        readers={readers}
        selectedOccurrenceId={selectedOccurrenceId}
        onSelectOccurrence={onSelectOccurrence}
        returnFocusId={returnFocusId}
      />
      <details className={styles.tech}>
        <summary className={styles.techSummary}>Technical details</summary>
        <div className={styles.techBody}>
          {namedReaders.length > 0 && (
            <div className={styles.techGroup}>
              <h5 className={styles.techHeading}>Readers</h5>
              <ul className={styles.techList}>
                {namedReaders.map((r) => (
                  <li key={r.id}>
                    {r.name}
                    {r.version ? ` ${r.version}` : ""} — {methodLabel(r)} · adapter{" "}
                    {r.adapter_version} · {r.environment}
                    {r.limitations.length > 0 ? ` · limits: ${r.limitations.join("; ")}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {semantics.candidates.length > 0 && (
            <div className={styles.techGroup}>
              <h5 className={styles.techHeading}>Occurrence references</h5>
              <ul className={styles.techList}>
                {semantics.candidates.map((c) => (
                  <li key={c.occurrence.id}>
                    <code>{c.occurrence.id}</code> — occurrence #{c.occurrence.ordinal} on page{" "}
                    {c.occurrence.page_index + 1}, {c.occurrence.geometry.precision} precision,{" "}
                    {geometryLabel(c.occurrence)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {semantics.unresolvedIds.length > 0 && (
            <div className={styles.techGroup}>
              <h5 className={styles.techHeading}>Unresolved references</h5>
              <ul className={styles.techList}>
                {semantics.unresolvedIds.map((id) => (
                  <li key={id}>
                    <code>{id}</code> — named by this finding but absent from the occurrence set
                  </li>
                ))}
              </ul>
            </div>
          )}
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
        </div>
      </details>
    </div>
  );
};

export default AlignmentDetail;
