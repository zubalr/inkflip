import React, { useEffect, useRef, useId, useCallback } from "react";
import styles from "./ModalDialog.module.css";

export interface ModalDialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  triggerRef?: React.RefObject<HTMLElement | null>;
  closeOnBackdropClick?: boolean;
  className?: string;
}

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function ModalDialog({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  triggerRef,
  closeOnBackdropClick = true,
  className,
}: ModalDialogProps) {
  const titleId = useId();
  const descId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  // Store trigger element when opening, restore on close
  useEffect(() => {
    if (isOpen) {
      previousActiveElement.current =
        (triggerRef && triggerRef.current) || (document.activeElement as HTMLElement | null);

      // Shift focus into dialog after paint
      const timer = setTimeout(() => {
        if (!dialogRef.current) return;
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
        if (focusable.length > 0) {
          // Focus first interactive element (or close button)
          focusable[0].focus();
        } else {
          dialogRef.current.focus();
        }
      }, 20);

      return () => clearTimeout(timer);
    } else {
      // Focus restoration
      if (previousActiveElement.current && typeof previousActiveElement.current.focus === "function") {
        previousActiveElement.current.focus();
      }
    }
  }, [isOpen, triggerRef]);

  // Trap focus & Escape handling
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
        return;
      }

      if (e.key === "Tab") {
        if (!dialogRef.current) return;
        const focusable = Array.from(
          dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
        );
        if (focusable.length === 0) {
          e.preventDefault();
          return;
        }

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first || !dialogRef.current.contains(document.activeElement)) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last || !dialogRef.current.contains(document.activeElement)) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    },
    [onClose]
  );

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (closeOnBackdropClick && e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className={styles.backdrop}
      onClick={handleBackdropClick}
      data-testid="modal-backdrop"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={`${styles.dialog} ${className || ""}`}
        onKeyDown={handleKeyDown}
      >
        <div className={styles.header}>
          <h2 id={titleId} className={styles.title}>
            {title}
          </h2>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close dialog"
          >
            ✕
          </button>
        </div>

        <div className={styles.body}>
          {description && (
            <p id={descId} className={styles.descriptionText}>
              {description}
            </p>
          )}
          {children}
        </div>

        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>
  );
}

export default ModalDialog;
