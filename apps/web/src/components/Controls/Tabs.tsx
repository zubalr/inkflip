import React, { useState, useRef, useId } from "react";
import styles from "./Tabs.module.css";

export interface TabItem {
  id: string;
  label: string;
  content: React.ReactNode;
  disabled?: boolean;
}

export interface TabsProps {
  "aria-label": string;
  items: TabItem[];
  selectedId?: string;
  defaultSelectedId?: string;
  onSelect?: (id: string) => void;
  className?: string;
}

export function Tabs({
  "aria-label": ariaLabel,
  items,
  selectedId: controlledSelectedId,
  defaultSelectedId,
  onSelect,
  className,
}: TabsProps) {
  const baseId = useId();
  const [internalSelectedId, setInternalSelectedId] = useState<string>(
    defaultSelectedId || items[0]?.id || ""
  );

  const selectedId = controlledSelectedId !== undefined ? controlledSelectedId : internalSelectedId;
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const enabledItems = items.filter((item) => !item.disabled);
  const selectedIndex = items.findIndex((item) => item.id === selectedId);

  const handleSelect = (id: string) => {
    if (controlledSelectedId === undefined) {
      setInternalSelectedId(id);
    }
    onSelect?.(id);
  };

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    if (enabledItems.length <= 1) return;

    let nextIndex = index;
    if (e.key === "ArrowRight") {
      e.preventDefault();
      do {
        nextIndex = (nextIndex + 1) % items.length;
      } while (items[nextIndex].disabled && nextIndex !== index);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      do {
        nextIndex = (nextIndex - 1 + items.length) % items.length;
      } while (items[nextIndex].disabled && nextIndex !== index);
    } else if (e.key === "Home") {
      e.preventDefault();
      nextIndex = 0;
      while (items[nextIndex].disabled && nextIndex < items.length - 1) {
        nextIndex++;
      }
    } else if (e.key === "End") {
      e.preventDefault();
      nextIndex = items.length - 1;
      while (items[nextIndex].disabled && nextIndex > 0) {
        nextIndex--;
      }
    } else {
      return;
    }

    const nextItem = items[nextIndex];
    if (nextItem && !nextItem.disabled) {
      handleSelect(nextItem.id);
      tabRefs.current[nextIndex]?.focus();
    }
  };

  const activeItem = items.find((item) => item.id === selectedId) || items[0];

  return (
    <div className={`${styles.container} ${className || ""}`}>
      <div role="tablist" aria-label={ariaLabel} className={styles.tablist}>
        {items.map((item, idx) => {
          const isSelected = item.id === selectedId;
          const tabId = `${baseId}-tab-${item.id}`;
          const panelId = `${baseId}-panel-${item.id}`;

          return (
            <button
              key={item.id}
              ref={(el) => {
                tabRefs.current[idx] = el;
              }}
              role="tab"
              id={tabId}
              aria-selected={isSelected}
              aria-controls={panelId}
              tabIndex={isSelected ? 0 : -1}
              disabled={item.disabled}
              className={styles.tab}
              onClick={() => handleSelect(item.id)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {activeItem && (
        <div
          role="tabpanel"
          id={`${baseId}-panel-${activeItem.id}`}
          aria-labelledby={`${baseId}-tab-${activeItem.id}`}
          tabIndex={0}
          className={styles.tabpanel}
        >
          {activeItem.content}
        </div>
      )}
    </div>
  );
}

export default Tabs;
