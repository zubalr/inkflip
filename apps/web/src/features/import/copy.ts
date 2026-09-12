/**
 * Canonical user-facing strings for the import feature (T22).
 *
 * Source of truth: `planning/product/copy.json`. The planning package is
 * frozen, so the strings are mirrored here verbatim — if the two ever
 * disagree, copy.json wins and this file must be corrected through the
 * contract owner, not edited ad hoc.
 */

export const IMPORT_COPY = {
  /** import.title — heading over the report drop zone. */
  title: "Open a saved report",
  /** import.local — the local-only statement, read before any file. */
  local: "Saved reports are opened locally, not uploaded.",
  /** import.invalid — every rejection class except the version one. */
  invalid: "This report is invalid or uses an unsupported format. Nothing in it was executed.",
  /** import.version — {version} is the declared schema_version. */
  version:
    "This report uses schema {version}. Open it with a compatible release or use an explicit migration.",
  /** import.source.missing — evidence export without original bytes. */
  sourceMissing: "The original PDF is not included. The saved evidence is still available.",
  /** import.source.choose — label on the explicit local PDF chooser. */
  sourceChoose: "Choose the matching original locally",
  /** import.source.mismatch — wrong bytes offered as the original. */
  sourceMismatch:
    "This file does not match the original document checksum. It was not attached to the report.",
  /** import.nofetch — shown wherever missing material could tempt a fetch. */
  nofetch: "Reports never fetch missing files or install readers automatically.",
  /** export.replay.absent — replay state for a source-less evidence report. */
  replayAbsent:
    "Original PDF not included. This report can be inspected, but replay requires the matching original.",
  /** export.replay.present — replay state with original bytes present. */
  replayPresent: "Original PDF included. Replay also requires the recorded reader environment.",
  /** export.noassets — diagnostic reports carry no replay semantics. */
  noAssets: "Screenshot-only diagnostic · not replayable",
  /** Report replacement confirmation (mirrors input.replace.*). */
  replaceTitle: "Open a different report?",
  replaceBody:
    "This clears the currently open report and any source attached to it. Download or reopen the evidence later from the saved file.",
  replaceConfirm: "Clear and open report",
  replaceCancel: "Keep this report",
} as const;

export const COMPARE_COPY = {
  /** compare.title — heading over the two-report picker. */
  title: "Compare saved runs",
  /** compare.incomparable — different documents, no same-doc mode applies. */
  incomparable: "These runs are not comparable under this mode",
} as const;

/** `{name}` interpolation matching copy.json templates. */
export function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key) ? values[key]! : match,
  );
}
