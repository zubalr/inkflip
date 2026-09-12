import React, { useCallback, useRef, useState } from "react";
import Button from "../../components/Controls/Button";
import styles from "./FileDrop.module.css";
import { OPEN_COPY } from "./copy";
import type { FileCandidate } from "./types";

export type OpenPhase = "idle" | "validating" | "metadata";

export interface FileDropProps {
  /** Current controller phase — the input is inert while a file is in flight. */
  readonly phase: OpenPhase;
  /** Called with the offered candidate (a File satisfies FileCandidate). */
  readonly onFile: (candidate: FileCandidate) => void;
  /** True when a document is already open (compact re-open affordance). */
  readonly hasDocument?: boolean;
}

/**
 * Local-only file intake: click-to-choose plus drag-and-drop. The privacy
 * statement sits inside the control so it is read before the file, per
 * Journey B. One file at a time — a second offer replaces, never mixes.
 */
export function FileDrop({ phase, onFile, hasDocument = false }: FileDropProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const busy = phase !== "idle";

  const offer = useCallback(
    (file: File | null | undefined) => {
      if (file) onFile(file);
    },
    [onFile],
  );

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setDragging(false);
      if (busy) return;
      offer(event.dataTransfer?.files?.[0]);
    },
    [busy, offer],
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    setDragging(true);
  }, []);

  const onDragLeave = useCallback((event: React.DragEvent) => {
    if (event.currentTarget === event.target) setDragging(false);
  }, []);

  return (
    <section
      className={`${styles.drop} ${dragging ? styles.dragging : ""} ${busy ? styles.busy : ""}`}
      aria-label={OPEN_COPY.drop}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      data-testid="file-drop"
    >
      <p className={styles.invite}>{OPEN_COPY.drop}</p>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className={styles.input}
        aria-label={OPEN_COPY.drop}
        disabled={busy}
        data-testid="file-input"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          // Reset so choosing the same file twice still fires change.
          event.currentTarget.value = "";
          offer(file);
        }}
      />
      <Button
        variant="primary"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        disabledReason={
          busy
            ? phase === "validating"
              ? OPEN_COPY.validation
              : OPEN_COPY.metadata
            : undefined
        }
      >
        {hasDocument ? "Choose a different file" : "Choose a PDF"}
      </Button>
      <p className={styles.privacy}>{OPEN_COPY.private}</p>
      {busy && (
        <p className={styles.phase} role="status" data-testid="open-phase">
          {phase === "validating" ? OPEN_COPY.validation : OPEN_COPY.metadata}
        </p>
      )}
    </section>
  );
}

export default FileDrop;
