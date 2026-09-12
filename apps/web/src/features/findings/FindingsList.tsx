import React from "react";
import type { Finding, Occurrence, Reader } from "../../../../../packages/contracts/src/index.ts";
import { groupFindings, COPY } from "../../../../../packages/explanations/src/index.ts";
import FindingCard from "./FindingCard";
import styles from "./FindingsList.module.css";

export interface FindingsListProps {
  findings: Finding[];
  occurrences: Occurrence[];
  readers: Reader[];
  selectedFindingId?: string | null;
  onSelectFinding?: (finding: Finding) => void;
  onKeepEvidence?: (finding: Finding) => void;
}

export const FindingsList: React.FC<FindingsListProps> = ({
  findings,
  occurrences,
  readers,
  selectedFindingId,
  onSelectFinding,
  onKeepEvidence,
}) => {
  if (findings.length === 0) {
    return (
      <div
        id="findings-noalert"
        className={styles.emptyNotice}
        role="region"
        aria-label="Findings comparison status"
      >
        <h3 className={styles.emptyTitle}>Comparison Results</h3>
        <p className={styles.emptyDisclaimer}>{COPY["coverage.noalert"]}</p>
      </div>
    );
  }

  const grouped = groupFindings(findings);

  return (
    <section id="findings-list" className={styles.container} aria-labelledby="findings-heading">
      <div className={styles.listHeader}>
        <h2 id="findings-heading" className={styles.headerTitle}>
          Document Differences & Readings
        </h2>
        <span className={styles.countBadge} aria-live="polite">
          {findings.length} {findings.length === 1 ? "finding" : "findings"}
        </span>
      </div>

      {Array.from(grouped.entries()).map(([groupKey, group]) => (
        <div
          key={groupKey}
          className={styles.group}
          role="group"
          aria-labelledby={`group-title-${groupKey}`}
        >
          <div id={`group-title-${groupKey}`} className={styles.groupHeader}>
            Page {group.pageIndex + 1}
            {group.regionId ? ` · Region ${group.regionId}` : " · Page scope"}
          </div>

          {group.items.map((finding) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              occurrences={occurrences}
              readers={readers}
              isSelected={finding.id === selectedFindingId}
              onSelectFinding={onSelectFinding}
              onKeepEvidence={onKeepEvidence}
            />
          ))}
        </div>
      ))}
    </section>
  );
};

export default FindingsList;
