import React, { useState, useId } from "react";
import styles from "./Disclosure.module.css";

export interface DisclosureProps {
  title: React.ReactNode;
  children: React.ReactNode;
  defaultExpanded?: boolean;
  expanded?: boolean;
  onToggle?: (expanded: boolean) => void;
  className?: string;
  id?: string;
}

export function Disclosure({
  title,
  children,
  defaultExpanded = false,
  expanded: controlledExpanded,
  onToggle,
  className,
  id: explicitId,
}: DisclosureProps) {
  const generatedId = useId();
  const baseId = explicitId || generatedId;
  const panelId = `${baseId}-panel`;

  const [internalExpanded, setInternalExpanded] = useState<boolean>(defaultExpanded);
  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;

  const handleClick = () => {
    const next = !isExpanded;
    if (controlledExpanded === undefined) {
      setInternalExpanded(next);
    }
    onToggle?.(next);
  };

  return (
    <div className={`${styles.container} ${className || ""}`}>
      <button
        type="button"
        id={`${baseId}-trigger`}
        aria-expanded={isExpanded}
        aria-controls={isExpanded ? panelId : undefined}
        className={styles.trigger}
        onClick={handleClick}
      >
        <span>{title}</span>
        <span aria-hidden="true" className={styles.chevron}>
          ▼
        </span>
      </button>
      {isExpanded && (
        <div id={panelId} className={styles.panel}>
          {children}
        </div>
      )}
    </div>
  );
}

export default Disclosure;
