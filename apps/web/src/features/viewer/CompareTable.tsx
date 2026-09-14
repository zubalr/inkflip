/**
 * CompareTable — the paired-reading comparison surface.
 *
 * Replaces the duplicated side-by-side page panes: one semantic table where
 * each finding is a row group whose two cells hold the readings the finding
 * actually names, per selected reader. Corresponding readings stay aligned
 * because they share a row; nothing is zipped or paired by text.
 *
 * - Cells are filled from `finding.occurrence_ids` resolved by id, so
 *   ambiguous, duplicate, one-to-many and unmatched evidence stays intact.
 * - Reader selects only choose which reader each column reads from; they
 *   never create or remove findings.
 * - "Show on page" opens one shared page preview row (rendered by the
 *   parent); "Details" opens the finding's semantic detail row.
 * - At narrow widths each finding stacks its two readings — reader A label
 *   and value, reader B label and value, then status and actions.
 */
import React from "react";
import type {
  Finding,
  Occurrence,
  Reader,
} from "../../../../../packages/contracts/src/index.ts";
import {
  classifyFinding,
  isOrderOnlyFinding,
  type CandidateReading,
} from "../findings/alignment/classify.ts";
import styles from "./CompareTable.module.css";

export interface CompareTableProps {
  readonly findings: readonly Finding[];
  readonly occurrences: readonly Occurrence[];
  readonly readers: readonly Reader[];
  readonly leftReader: Reader;
  readonly rightReader: Reader;
  readonly readerOptions: readonly Reader[];
  readonly onChangeLeftReader?: (readerId: string) => void;
  readonly onChangeRightReader?: (readerId: string) => void;
  readonly selectedFindingId: string | null;
  readonly selectedOccurrenceId: string | null;
  /** The finding whose shared page preview is open, if any. */
  readonly previewFindingId: string | null;
  /** Findings whose technical detail row is open. */
  readonly detailFindingIds: ReadonlySet<string>;
  /** Toggle the shared preview for a finding (selects it and navigates). */
  readonly onShowOnPage: (finding: Finding) => void;
  readonly onToggleDetails: (finding: Finding) => void;
  /** Select an occurrence and reveal it on the shared preview. */
  readonly onLocateOccurrence: (finding: Finding, occ: Occurrence) => void;
  /** Parent-owned panels — they need the stage's paint/zoom/finding state. */
  readonly renderPreview: (finding: Finding) => React.ReactNode;
  readonly renderDetails: (finding: Finding) => React.ReactNode;
  /** Previous/next finding navigation rendered above the table. */
  readonly findingNav?: React.ReactNode;
}

/** Plain-language column label for a reader's output kind. */
export function readingColumnLabel(reader: Reader): string {
  switch (reader.method) {
    case "native_text":
      return "PDF text";
    case "ocr":
      return "Text read from image";
    case "render":
      return "Page image";
    case "structure":
      return "Document structure";
    default:
      return reader.name;
  }
}

function readerVersion(reader: Reader): string {
  return reader.version ? `${reader.name} ${reader.version}` : reader.name;
}

const BADGE_CLASS: Record<string, string | undefined> = {
  difference: styles.badgeDifference,
  order_only: styles.badgeOrder,
  ambiguous: styles.badgeAmbiguous,
  unmatched: styles.badgeUnmatched,
  page_level: styles.badgePageLevel,
  incomplete: styles.badgeIncomplete,
  one_sided: styles.badgeOneSided,
};

const ReaderColumn: React.FC<{
  finding: Finding;
  reader: Reader;
  candidates: readonly CandidateReading[];
  selectedOccurrenceId: string | null;
  orderOnly: boolean;
  onLocateOccurrence: (finding: Finding, occ: Occurrence) => void;
}> = ({ finding, reader, candidates, selectedOccurrenceId, orderOnly, onLocateOccurrence }) => {
  if (reader.method === "render") {
    return (
      <p className={styles.cellEmpty}>
        {reader.name} produces the page image itself — it has no text records.
      </p>
    );
  }
  if (candidates.length === 0) {
    return (
      <p className={styles.cellEmpty}>No reading named from {reader.name}.</p>
    );
  }
  return (
    <ul className={styles.cellList}>
      {candidates.map((candidate, emittedIndex) => {
        const occ = candidate.occurrence;
        const isSelected = occ.id === selectedOccurrenceId;
        return (
          <li key={occ.id} className={styles.cellItem}>
            <button
              type="button"
              id={`compare-reading-${finding.id}-${occ.id}`}
              data-testid={`compare-reading-${finding.id}-${occ.id}`}
              className={`${styles.reading} ${isSelected ? styles.readingSelected : ""}`}
              aria-pressed={isSelected}
              onClick={() => onLocateOccurrence(finding, occ)}
            >
              <q className={styles.readingText}>
                {occ.raw_text === "" ? "(no text captured)" : occ.raw_text}
              </q>
              <span className={styles.readingMeta}>
                {orderOnly
                  ? `emitted position ${emittedIndex + 1} · occurrence #${occ.ordinal}`
                  : `occurrence #${occ.ordinal}`}
                {occ.geometry.polygon === null
                  ? " · page-level"
                  : occ.geometry.precision !== "exact"
                    ? ` · ${occ.geometry.precision}`
                    : ""}
                {candidate.identicalSiblings > 0
                  ? ` · identical text ${candidate.identicalRank} of ${candidate.identicalSiblings + 1}`
                  : ""}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
};

export const CompareTable: React.FC<CompareTableProps> = ({
  findings,
  occurrences,
  readers,
  leftReader,
  rightReader,
  readerOptions,
  onChangeLeftReader,
  onChangeRightReader,
  selectedFindingId,
  selectedOccurrenceId,
  previewFindingId,
  detailFindingIds,
  onShowOnPage,
  onToggleDetails,
  onLocateOccurrence,
  renderPreview,
  renderDetails,
  findingNav,
}) => {
  const columnSelect = (
    side: "left" | "right",
    reader: Reader,
    onChange: ((id: string) => void) | undefined,
    otherReaderId: string,
  ) => {
    if (!onChange) {
      return <span className={styles.colReaderName}>{readerVersion(reader)}</span>;
    }
    // A column reading from the other column's reader would mirror, not
    // compare — keep each side's options to the other readers.
    const options = readerOptions.filter((r) => r.id !== otherReaderId || r.id === reader.id);
    return (
      <select
        id={`compare-reader-${side}`}
        className={styles.readerSelect}
        aria-label={`${side === "left" ? "First" : "Second"} column reader`}
        value={reader.id}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((r) => (
          <option key={r.id} value={r.id}>
            {readerVersion(r)}
          </option>
        ))}
        {!options.some((r) => r.id === reader.id) && (
          <option value={reader.id}>{readerVersion(reader)}</option>
        )}
      </select>
    );
  };

  return (
    <div className={styles.compare} data-testid="compare-table">
      {findingNav}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <colgroup>
            <col className={styles.col} />
            <col className={styles.col} />
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className={styles.colHead}>
                <span className={styles.colTitle}>{readingColumnLabel(leftReader)}</span>
                <span className={styles.colReader}>
                  {columnSelect("left", leftReader, onChangeLeftReader, rightReader.id)}
                </span>
              </th>
              <th scope="col" className={styles.colHead}>
                <span className={styles.colTitle}>{readingColumnLabel(rightReader)}</span>
                <span className={styles.colReader}>
                  {columnSelect("right", rightReader, onChangeRightReader, leftReader.id)}
                </span>
              </th>
            </tr>
          </thead>
          {findings.map((finding, index) => {
            const semantics = classifyFinding(finding, occurrences, readers);
            const orderOnly = isOrderOnlyFinding(finding);
            const leftCandidates = semantics.candidates.filter(
              (c) => c.occurrence.reader_id === leftReader.id,
            );
            const rightCandidates = semantics.candidates.filter(
              (c) => c.occurrence.reader_id === rightReader.id,
            );
            const isSelected = finding.id === selectedFindingId;
            const previewOpen = finding.id === previewFindingId;
            const detailOpen = detailFindingIds.has(finding.id);
            return (
              <tbody
                key={finding.id}
                className={`${styles.findingGroup} ${isSelected ? styles.findingGroupSelected : ""}`}
                data-finding-id={finding.id}
              >
                <tr className={styles.findingMetaRow}>
                  <td colSpan={2} className={styles.findingMetaCell}>
                    <span className={styles.findingRef}>Finding {index + 1}</span>
                    <span className={styles.findingName}>{finding.title}</span>
                    <span className={styles.findingPage}>
                      Page {finding.page_index + 1}
                    </span>
                  </td>
                </tr>
                <tr className={styles.valuesRow}>
                  <td className={styles.valueCell} data-reader-side="left">
                    <span className={styles.cellLabel}>
                      {readingColumnLabel(leftReader)} — {readerVersion(leftReader)}
                    </span>
                    <ReaderColumn
                      finding={finding}
                      reader={leftReader}
                      candidates={leftCandidates}
                      selectedOccurrenceId={selectedOccurrenceId}
                      orderOnly={orderOnly}
                      onLocateOccurrence={onLocateOccurrence}
                    />
                  </td>
                  <td className={styles.valueCell} data-reader-side="right">
                    <span className={styles.cellLabel}>
                      {readingColumnLabel(rightReader)} — {readerVersion(rightReader)}
                    </span>
                    <ReaderColumn
                      finding={finding}
                      reader={rightReader}
                      candidates={rightCandidates}
                      selectedOccurrenceId={selectedOccurrenceId}
                      orderOnly={orderOnly}
                      onLocateOccurrence={onLocateOccurrence}
                    />
                  </td>
                </tr>
                <tr className={styles.statusRow}>
                  <td colSpan={2} className={styles.statusCell}>
                    <div className={styles.statusLine}>
                      <span
                        className={`${styles.badge} ${BADGE_CLASS[semantics.classification] ?? ""}`}
                        data-testid={`compare-status-${finding.id}`}
                        data-alignment-class={semantics.classification}
                      >
                        {semantics.badge}
                      </span>
                    </div>
                    <div className={styles.actionLine}>
                      <button
                        type="button"
                        id={`compare-show-${finding.id}`}
                        className={styles.rowAction}
                        aria-expanded={previewOpen}
                        aria-controls={`compare-preview-${finding.id}`}
                        onClick={() => onShowOnPage(finding)}
                      >
                        {previewOpen ? "Hide page" : "Show on page"}
                      </button>
                      <span className={styles.actionSep} aria-hidden="true">
                        ·
                      </span>
                      <button
                        type="button"
                        id={`compare-details-${finding.id}`}
                        className={styles.rowAction}
                        aria-expanded={detailOpen}
                        aria-controls={`compare-detail-${finding.id}`}
                        onClick={() => onToggleDetails(finding)}
                      >
                        Details
                      </button>
                    </div>
                  </td>
                </tr>
                {previewOpen && (
                  <tr className={styles.panelRow}>
                    <td colSpan={2} className={styles.panelCell}>
                      {renderPreview(finding)}
                    </td>
                  </tr>
                )}
                {detailOpen && (
                  <tr className={styles.panelRow}>
                    <td colSpan={2} className={styles.panelCell}>
                      {renderDetails(finding)}
                    </td>
                  </tr>
                )}
              </tbody>
            );
          })}
        </table>
      </div>
    </div>
  );
};

export default CompareTable;
