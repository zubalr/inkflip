import React, { useState } from "react";
import type { Occurrence, Reader } from "../../../../../packages/contracts/src/index.ts";
import styles from "./AccessibleTextLayer.module.css";

export interface AccessibleTextLayerProps {
  pageIndex: number;
  occurrences: Occurrence[];
  readers: Reader[];
  selectedOccurrenceId?: string | null;
  onSelectOccurrence?: (occ: Occurrence) => void;
  limitations?: string[];
  /** Reading view mounts the layer as the main content — open by default.
   *  Below the page it collapses on narrow viewports so the findings
   *  panel is not pushed thousands of pixels down. `true` forces open,
   *  `false` forces closed (compare mode keeps raw readings available
   *  without overwhelming the table), `undefined` follows viewport. */
  defaultDetailsOpen?: boolean;
}

export const AccessibleTextLayer: React.FC<AccessibleTextLayerProps> = ({
  pageIndex,
  occurrences,
  readers,
  selectedOccurrenceId,
  onSelectOccurrence,
  limitations = [],
  defaultDetailsOpen,
}) => {
  // Resolved once at mount: the `open` attribute is initial markup; React
  // does not rewrite it on later renders, so user toggling persists.
  // `true`/`false` pin the state; `undefined` follows the viewport.
  const [autoOpen] = useState<boolean>(() =>
    typeof window === "undefined"
      ? true
      : window.matchMedia("(min-width: 1100px)").matches,
  );
  const detailsOpen = defaultDetailsOpen ?? autoOpen;
  const readerMap = new Map<string, Reader>();
  for (const r of readers) {
    readerMap.set(r.id, r);
  }

  // Group occurrences by reader
  const byReader = new Map<string, Occurrence[]>();
  for (const occ of occurrences) {
    const list = byReader.get(occ.reader_id) || [];
    list.push(occ);
    byReader.set(occ.reader_id, list);
  }

  return (
    <section
      id="accessible-text-equivalent"
      className={styles.container}
      role="region"
      aria-label="Document text equivalent and limits"
    >
      <h3 className={styles.heading}>Accessible Text Equivalent &amp; Limits</h3>
      <p className={styles.intro}>
        Page {pageIndex + 1} named text extractions, verbatim occurrence ordinals, and reader
        limits.
      </p>

      {Array.from(byReader.entries()).map(([readerId, occs]) => {
        const reader = readerMap.get(readerId);
        const readerLabel = reader
          ? `${reader.name} ${reader.version ? `v${reader.version}` : ""}`
          : readerId;

        return (
          <div key={readerId} className={styles.readerGroup}>
            <details className={styles.readerDetails} open={detailsOpen}>
              <summary className={styles.readerSummary}>
                <h4 className={styles.readerHeader}>
                  {readerLabel} · {occs.length} {occs.length === 1 ? "reading" : "readings"}
                </h4>
              </summary>
              <ul className={styles.occurrenceList} role="list">
                {occs.map((occ) => {
                  const isSelected = occ.id === selectedOccurrenceId;
                  return (
                    <li
                      key={occ.id}
                      id={`text-occ-${occ.id}`}
                      className={`${styles.occurrenceItem} ${
                        isSelected ? styles.occurrenceSelected : ""
                      }`}
                    >
                      <span className={styles.occurrenceText}>
                        {occ.raw_text === "" ? "(no text captured)" : occ.raw_text}
                      </span>
                      <span className={styles.occurrenceMeta}>
                        occurrence #{occ.ordinal}
                        {occ.geometry.precision === "page_only" ||
                        occ.geometry.precision === "unknown"
                          ? " (page-level only)"
                          : ` (${occ.geometry.precision})`}
                      </span>
                      <button
                        type="button"
                        className={styles.selectBtn}
                        onClick={() => onSelectOccurrence?.(occ)}
                        aria-pressed={isSelected}
                      >
                        {isSelected ? "Selected" : "Select"}
                      </button>
                    </li>
                  );
                })}
              </ul>

              {reader && reader.limitations.length > 0 && (
                <ul className={styles.limitsList} aria-label={`${readerLabel} limitations`}>
                  {reader.limitations.map((lim, i) => (
                    <li key={i}>{lim}</li>
                  ))}
                </ul>
              )}
            </details>
          </div>
        );
      })}

      {limitations.length > 0 && (
        <div className={styles.readerGroup}>
          <h4 className={styles.readerHeader}>Page Limitations</h4>
          <ul className={styles.limitsList}>
            {limitations.map((lim, i) => (
              <li key={i}>{lim}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
};

export default AccessibleTextLayer;
