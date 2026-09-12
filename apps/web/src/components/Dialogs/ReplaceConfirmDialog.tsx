import React from "react";
import ModalDialog from "./ModalDialog";
import Button from "../Controls/Button";

export interface ReplaceConfirmDialogProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  triggerRef?: React.RefObject<HTMLElement | null>;
}

export function ReplaceConfirmDialog({
  isOpen,
  onConfirm,
  onCancel,
  triggerRef,
}: ReplaceConfirmDialogProps) {
  return (
    <ModalDialog
      isOpen={isOpen}
      onClose={onCancel}
      title="Open a different PDF?"
      description="This clears the current file and its unsaved report from the workspace. Download the evidence first to keep it."
      triggerRef={triggerRef}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            Keep this file
          </Button>
          <Button variant="danger" onClick={onConfirm}>
            Clear and open file
          </Button>
        </>
      }
    >
      <div />
    </ModalDialog>
  );
}

export default ReplaceConfirmDialog;
