import React, { forwardRef } from "react";
import styles from "./Notice.module.css";
import Button from "./Button";

export type NoticeType = "error" | "warning" | "info";

export interface NoticeProps {
  id?: string;
  type?: NoticeType;
  title: string;
  children?: React.ReactNode;
  disclaimer?: string;
  retryAction?: {
    label: string;
    onRetry: () => void;
  };
  className?: string;
}

export const Notice = forwardRef<HTMLDivElement, NoticeProps>(function Notice(
  {
    id,
    type = "info",
    title,
    children,
    disclaimer,
    retryAction,
    className,
  },
  ref
) {
  const role = type === "error" ? "alert" : "status";

  return (
    <div
      ref={ref}
      id={id}
      role={role}
      tabIndex={-1}
      className={`${styles.notice} ${styles[type]} ${className || ""}`}
    >
      <div className={styles.titleRow}>
        <strong className={styles.title}>{title}</strong>
      </div>
      {children && <div className={styles.description}>{children}</div>}
      {disclaimer && <p className={styles.disclaimer}>{disclaimer}</p>}
      {retryAction && (
        <div className={styles.actions}>
          <Button variant="secondary" size="small" onClick={retryAction.onRetry}>
            {retryAction.label}
          </Button>
        </div>
      )}
    </div>
  );
});

export default Notice;
