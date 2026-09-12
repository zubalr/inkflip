import React, { useMemo, useState } from "react";
import Button from "../../components/Controls/Button";
import Notice from "../../components/Controls/Notice";
import styles from "./PagePicker.module.css";
import { SELECTION_COPY, fill } from "../open/copy";
import type { PageSelection } from "./pages";

/** Page rows rendered per window — the picker never mounts all 1,000. */
const WINDOW_SIZE = 48;

export interface PagePickerProps {
  readonly selection: PageSelection;
  /** Called after any mutation so the parent re-renders. */
  readonly onChange: () => void;
}

/**
 * Explicit page picker. The summary always states the true selected/total
 * counts; a refused selection surfaces the profile cap in a visible notice
 * instead of silently trimming ("no silent exclusion", Journey B). Long
 * documents page through a bounded window — every page remains reachable
 * and individually toggleable.
 */
export function PagePicker({ selection, onChange }: PagePickerProps) {
  const [windowStart, setWindowStart] = useState(0);
  const [jump, setJump] = useState("");
  const summary = selection.summary();
  const maxStart = Math.max(0, summary.total - WINDOW_SIZE);
  const start = Math.min(windowStart, maxStart);
  const end = Math.min(start + WINDOW_SIZE, summary.total);
  const pages = useMemo(() => {
    const out: number[] = [];
    for (let i = start; i < end; i++) out.push(i);
    return out;
  }, [start, end]);

  const showLimitNotice = summary.limitHit || summary.truncated;

  return (
    <section className={styles.picker} aria-label={SELECTION_COPY.title}>
      <div className={styles.headerRow}>
        <h2 className={styles.title}>{SELECTION_COPY.title}</h2>
        <p className={styles.summary} data-testid="pages-summary">
          {fill(SELECTION_COPY.summary, {
            selected: String(summary.selected),
            total: String(summary.total),
          })}
        </p>
      </div>

      {showLimitNotice && (
        <Notice type="warning" title={fill(SELECTION_COPY.nativeLimit, {
          limit: String(summary.limit),
        })} id="pages-limit-notice" />
      )}

      <div className={styles.actions}>
        <Button
          variant="secondary"
          size="small"
          onClick={() => {
            selection.selectAll();
            onChange();
          }}
          data-testid="select-all"
        >
          {summary.total > summary.limit
            ? `Select first ${summary.limit}`
            : "Select all pages"}
        </Button>
        <Button
          variant="ghost"
          size="small"
          onClick={() => {
            selection.clear();
            onChange();
          }}
          data-testid="clear-pages"
        >
          Clear pages
        </Button>
      </div>

      {summary.total > WINDOW_SIZE && (
        <div className={styles.windowNav}>
          <Button
            variant="secondary"
            size="small"
            disabled={start <= 0}
            onClick={() => setWindowStart(Math.max(0, start - WINDOW_SIZE))}
          >
            ← Earlier pages
          </Button>
          <span className={styles.windowLabel} data-testid="pages-window">
            Pages {start + 1}–{end} of {summary.total}
          </span>
          <Button
            variant="secondary"
            size="small"
            disabled={end >= summary.total}
            onClick={() => setWindowStart(Math.min(maxStart, start + WINDOW_SIZE))}
          >
            Later pages →
          </Button>
          <label className={styles.jumpLabel}>
            Go to page
            <input
              className={styles.jumpInput}
              type="number"
              min={1}
              max={summary.total}
              value={jump}
              onChange={(event) => setJump(event.currentTarget.value)}
              onKeyDown={(event) => {
                if (event.key !== "Enter") return;
                const n = Number.parseInt(jump, 10);
                if (Number.isInteger(n) && n >= 1 && n <= summary.total) {
                  // Bring the requested page to the top of the window.
                  setWindowStart(Math.min(n - 1, maxStart));
                }
              }}
              data-testid="page-jump"
            />
          </label>
        </div>
      )}

      <ul className={styles.pageList} data-testid="page-list">
        {pages.map((index) => {
          const selected = selection.has(index);
          return (
            <li key={index}>
              <button
                type="button"
                className={`${styles.pageToggle} ${selected ? styles.selected : ""}`}
                aria-pressed={selected}
                data-testid={`page-toggle-${index + 1}`}
                onClick={() => {
                  selection.toggle(index);
                  onChange();
                }}
              >
                <span className={styles.pageNumber}>{index + 1}</span>
                <span className={styles.pageState}>
                  {selected ? "selected" : "not checked"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default PagePicker;
