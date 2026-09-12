import React, { useId } from "react";
import styles from "./ProgressBar.module.css";
import Button from "./Button";

export interface ProgressBarProps {
  /** The high-level stage being executed (e.g. "Reading text on page 1…") */
  stage: string;
  /** Percentage from 0 to 100, or undefined for indeterminate */
  value?: number;
  /** Detailed metric (e.g. "1,420 characters read") displayed visually, NOT announced to screen reader on every token */
  detail?: string;
  /** Optional cancellation handler */
  onCancel?: () => void;
  className?: string;
}

export function ProgressBar({
  stage,
  value,
  detail,
  onCancel,
  className,
}: ProgressBarProps) {
  const labelId = useId();
  const isIndeterminate = value === undefined || value === null;
  const clampedValue = !isIndeterminate ? Math.max(0, Math.min(100, Math.round(value!))) : undefined;

  return (
    <div className={`${styles.container} ${className || ""}`}>
      {/* Polite stage-based announcement region: only announces named stages, never token chatter */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className={styles.srAnnouncement}
      >
        {stage}
      </div>

      <div className={styles.header}>
        <span id={labelId} className={styles.stageLabel}>
          {stage}
        </span>
        {detail && <span className={styles.detail}>{detail}</span>}
      </div>

      <div
        role="progressbar"
        aria-labelledby={labelId}
        aria-valuenow={clampedValue}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext={!isIndeterminate ? `${clampedValue}%` : stage}
        className={styles.track}
      >
        {isIndeterminate ? (
          <div className={styles.indeterminate} />
        ) : (
          <div className={styles.fill} style={{ width: `${clampedValue}%` }} />
        )}
      </div>

      {onCancel && (
        <div className={styles.footer}>
          <Button variant="ghost" size="small" onClick={onCancel} aria-label="Cancel check">
            Cancel check
          </Button>
        </div>
      )}
    </div>
  );
}

export default ProgressBar;
