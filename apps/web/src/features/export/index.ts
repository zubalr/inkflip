/**
 * Export feature surface (T16): pre-export preview + JSON/HTML downloads.
 *
 * `ExportPanel` renders the inclusion allowlist and the preview measured
 * on the final projected object; `ExportController` drives the
 * project→preview→download flow against the injected `ExportEngine`
 * port. The engine binding to `@inkflip/reports/export` lands with app
 * composition — this directory stays free of cross-package `.ts`
 * specifiers (same pattern as `state/store.ts`).
 */
export { ExportPanel, default } from "./ExportPanel";
export type { ExportPanelProps } from "./ExportPanel";
export { ExportController, probeAvailability } from "./controller";
export type { ExportControllerOptions, ExportControllerState } from "./controller";
export type {
  ExportAvailability,
  ExportEngine,
  ExportOutput,
  ExportPreviewLike,
  ExportRequestLike,
  PreviewCountsLike,
  ProjectionLike,
  ProjectionNoticesLike,
} from "./types";
