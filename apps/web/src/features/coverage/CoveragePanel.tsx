import React from "react";
import type { Plan, CheckResult, Page } from "../../../../../packages/contracts/src/index.ts";
import { explainCoverage } from "../../../../../packages/explanations/src/index.ts";
import styles from "./CoveragePanel.module.css";

export interface CoveragePanelProps {
  plan: Plan;
  checks: CheckResult[];
  pages: Page[];
  ocrRun?: boolean;
  hasInvisibleTextScan?: boolean;
  findingsCount?: number;
}

export const CoveragePanel: React.FC<CoveragePanelProps> = ({
  plan,
  checks,
  pages,
  ocrRun = true,
  hasInvisibleTextScan = false,
  findingsCount = 0,
}) => {
  const coverage = explainCoverage(plan, checks, pages, {
    ocrRun,
    hasInvisibleTextScan,
    findingsCount,
  });

  const { breakdown } = coverage.stats;

  return (
    <section className={styles.panel} aria-labelledby="coverage-heading">
      <header className={styles.header}>
        <div>
          <h2 id="coverage-heading" className={styles.title}>
            {coverage.title}
          </h2>
          <p className={styles.pagesText}>{coverage.pagesSummary}</p>
        </div>
        <p className={styles.summaryText}>{coverage.summary}</p>
      </header>

      {/* Numerical Stats Breakdown */}
      <div className={styles.statsGrid} role="group" aria-label="Check statistics">
        <div className={`${styles.statCard} ${styles.statCompleted}`}>
          <span className={styles.statValue}>{breakdown.completed}</span>
          <span className={styles.statLabel}>Completed</span>
        </div>

        {breakdown.timeout > 0 && (
          <div className={`${styles.statCard} ${styles.statTimeout}`} id="stat-timeout">
            <span className={styles.statValue}>{breakdown.timeout}</span>
            <span className={styles.statLabel}>Timed Out</span>
          </div>
        )}

        {breakdown.model_missing > 0 && (
          <div className={`${styles.statCard} ${styles.statModelMissing}`} id="stat-model-missing">
            <span className={styles.statValue}>{breakdown.model_missing}</span>
            <span className={styles.statLabel}>Model Missing</span>
          </div>
        )}

        {breakdown.unsupported > 0 && (
          <div className={`${styles.statCard} ${styles.statUnsupported}`} id="stat-unsupported">
            <span className={styles.statValue}>{breakdown.unsupported}</span>
            <span className={styles.statLabel}>Unsupported</span>
          </div>
        )}
      </div>

      {/* Normal Invisible Scan Notice (I11: informative, never a warning solely for invisibility) */}
      {coverage.normalScanNotice && (
        <div
          id="coverage-normal-scan-notice"
          className={styles.scanNotice}
          role="note"
          aria-label="Searchable scan property"
        >
          {coverage.normalScanNotice}
        </div>
      )}

      {/* Agreement & Zero-difference notice */}
      {coverage.agreementMessage && (
        <div className={styles.agreementNotice} role="region" aria-label="Checked region agreement">
          <p className={styles.agreementTitle}>{coverage.agreementMessage}</p>
          <p className={styles.agreementDisclaimer}>{coverage.noAlertDisclaimer}</p>
        </div>
      )}

      {/* Incomplete / Distinct status breakdown list */}
      {coverage.statusDetails.some((d) => d.isIncomplete) && (
        <div className={styles.statusList} role="list" aria-label="Incomplete checks detail">
          {coverage.statusDetails
            .filter((d) => d.isIncomplete)
            .map((detail, idx) => (
              <div
                key={idx}
                className={styles.statusRow}
                role="listitem"
                id={`check-status-${detail.category}-${idx}`}
              >
                <span>{detail.description}</span>
                <span
                  className={`${styles.statusBadge} ${
                    detail.category === "timeout"
                      ? styles.badgeTimeout
                      : detail.category === "model_missing"
                      ? styles.badgeModelMissing
                      : styles.badgeUnsupported
                  }`}
                >
                  {detail.label}
                </span>
              </div>
            ))}
        </div>
      )}
    </section>
  );
};

export default CoveragePanel;
