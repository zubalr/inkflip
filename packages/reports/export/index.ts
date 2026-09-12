/**
 * @inkflip/reports — export surface (T16).
 *
 * Portable evidence export: inclusion-allowlist selection projection
 * (`projectReport`), deterministic canonical `.inkflip.json` serialization
 * (`serializeReportJson`), script-free `.html` rendering
 * (`renderReportHtml`) and the pre-export preview computed from the final
 * projected object (`buildExportPreview`).
 *
 * Pipeline: project → preview → serialize/render. The preview measures the
 * projected report itself, so what the user approves is what the decoded
 * file contains. Source PDF bytes, the original filename, notes and
 * full-page renders are opt-in only; every HTML byte passes the T24
 * script-free guard before it leaves the module.
 *
 * ```sh
 * node --test tests/reports/export.test.mjs
 * ```
 */
export { projectReport } from "./selection.ts";
export type {
  AssetSelection,
  ExportRequest,
  FindingSelection,
  OccurrenceSelection,
  ProjectionNotices,
  ProjectionResult,
} from "./selection.ts";
export { encodeBase64, exportFileName, reportJsonBytes, serializeReportJson } from "./serialize.ts";
export { EXPORT_CSS, exportCsp, renderReportHtml } from "./html.ts";
export { buildExportPreview } from "./preview.ts";
export type { ExportPreview, PreviewAsset, PreviewBytes, PreviewCounts } from "./preview.ts";
