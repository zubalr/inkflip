/**
 * Canonical user-facing strings for the open feature.
 *
 * Source of truth: this file. `planning/product/copy.json` is the frozen
 * historical mirror of the first release's copy — the planning package is no
 * longer edited, so the implemented strings here are authoritative and the
 * JSON stands as the record of the earlier wording.
 */

export const OPEN_COPY = {
  /** input.drop — the drop-zone invitation. */
  drop: "Drop one PDF here, or choose a file",
  /** input.private — privacy statement shown before reading. */
  private: "Your file is processed in this browser. It is not uploaded.",
  /** input.validation — progress while sniffing the candidate. */
  validation: "Checking the PDF…",
  /** input.metadata — progress while the reader loads page metadata. */
  metadata: "Opening the PDF…",
  /** input.notpdf — wrong declared type and/or missing %PDF- header. */
  notPdf:
    "This file could not be opened as a PDF. Choose a PDF you are permitted to inspect.",
  /** input.toobig — {limit} is replaced with the human limit label. */
  tooBig:
    "This file exceeds the {limit} local browser limit. Choose a smaller file or use the local CLI.",
  /** input.encrypted — password-protected input is unsupported. */
  encrypted:
    "Encrypted PDFs are not supported in this release. Open an unencrypted copy you are permitted to inspect.",
  /** input.malformed — the reader could not open the file. */
  malformed:
    "The reader could not open this PDF. No check was completed.",
  /** pages.toomany — document exceeds the supported page count. */
  tooManyPages:
    "This PDF exceeds the supported page count. No pages were silently skipped.",
  /** input.replace.* — replacement confirmation (also T07 dialog copy). */
  replaceTitle: "Open a different PDF?",
  replaceBody:
    "This clears the current file and its unsaved report from the workspace. Save the report first to keep it.",
  replaceConfirm: "Clear and open file",
  replaceCancel: "Keep this file",
  /** clear.action / clear.done — workspace clearing labels. */
  clearAction: "Clear this file",
} as const;

export const SELECTION_COPY = {
  /** pages.title */
  title: "Choose what to check",
  /** pages.summary — {selected}/{total} interpolation. */
  summary: "{selected} of {total} pages selected",
  /** pages.native.limit — shown whenever the run cap bites. */
  nativeLimit:
    "Check up to {limit} pages in this run. Other pages remain not checked.",
  /** pages.start */
  start: "Check selected pages",
  /** pages.region / hint / expanded */
  region: "Select a region",
  regionHint:
    "Drag a region on the page, or enter its boundaries with the keyboard.",
  regionExpanded:
    "OCR includes the outlined padding around this region.",
} as const;

/**
 * Plain-language labels for the open workspace's own groups. These are not
 * part of the frozen planning mirror — they name the visible regions of the
 * intake/selection screen (file summary, optional tuning, planned checks).
 */
export const WORKSPACE_COPY = {
  /** Small label above the loaded file's name. */
  fileLabel: "Loaded PDF",
  /** Optional tuning disclosure (preview page + region editor). */
  tuning: "Preview and region (optional)",
  tuningHint: "Only needed when you want to check one area of a page.",
  /** The raw planned-check list inside the plan section. */
  planDetails: "Show technical check list",
  /** Plain-language OCR line above the consent control. */
  ocrPlain:
    "OCR reads the text inside the page image — useful for scans where no text can be selected.",
} as const;

export const LIMITS_COPY = {
  /** limits.title — the run-limits disclosure heading. */
  title: "Run limits on this device",
  /** limits.mode — {mode} is the profile label. */
  mode: "Device mode: {mode}",
  /** limits.entries — one line per enforced bound. */
  file: "File size up to {limit}",
  pages: "Documents up to {limit} pages",
  native: "Native text checks on up to {limit} pages per run",
  ocr: "OCR on up to {limit} pages per run",
  raster: "Renders capped at {limit} pixels",
  /** ocrConsent.* — mobile OCR is heavy; it runs only on explicit consent. */
  ocrConsentLabel: "Allow OCR checks on this device",
  ocrConsentHint:
    "OCR loads a multi-megabyte model and uses significant CPU. Without consent the run still checks native text and rendering on the selected pages.",
  /** preview.ondemand — low-memory mode renders the preview only on request. */
  renderPreview: "Render preview",
} as const;

/** `{name}` interpolation matching copy.json templates. */
export function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key) ? values[key]! : match,
  );
}

/** Human-readable byte limit for messages (e.g. "20 MiB"). */
export function byteLimitLabel(bytes: number): string {
  if (bytes % (1024 * 1024) === 0) return `${bytes / (1024 * 1024)} MiB`;
  if (bytes % 1024 === 0) return `${bytes / 1024} KiB`;
  return `${bytes} bytes`;
}
