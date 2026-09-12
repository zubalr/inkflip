import React from "react";
import { createRoot } from "react-dom/client";
import DocumentStage from "./DocumentStage";
import type { StageMode, StageStatus } from "./DocumentStage";

const params = new URLSearchParams(window.location.search);
const mode = (params.get("mode") as StageMode) || "page";
const status = (params.get("status") as StageStatus) || "normal";
const initialDetailOpen = params.get("detail") === "true";
const errorMessage = params.get("error") || undefined;

const rootElement = document.getElementById("root");
if (rootElement) {
  const root = createRoot(rootElement);
  root.render(
    <DocumentStage
      initialMode={mode}
      status={status}
      initialDetailOpen={initialDetailOpen}
      errorMessage={errorMessage}
    />
  );

  const focusTarget = params.get("focus");
  if (focusTarget) {
    const focusElement = () => {
      const el =
        focusTarget === "tab" || focusTarget === "tab-page"
          ? document.getElementById("tab-page")
          : focusTarget === "stage"
          ? document.getElementById("stage")
          : document.getElementById(focusTarget);
      el?.focus();
    };
    requestAnimationFrame(() => {
      setTimeout(focusElement, 20);
    });
  }
}
