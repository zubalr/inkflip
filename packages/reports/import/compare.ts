/**
 * Comparison readiness for two explicitly, locally selected reports.
 *
 * The comparison contract requires both source reports supplied locally
 * — an id, a URL, or a remote pointer is never sufficient input. Both
 * reports pass the same import gate before this check runs; this module
 * only decides whether the two validated reports may be compared at
 * all:
 *
 * - `same_report` — identical `report_id`; there is nothing to diff.
 * - `incomparable` — different `document.sha256`: different bytes are
 *   not the same file, so no same-document comparison mode applies.
 * - `ready` — two distinct reports bound to the same document bytes.
 *
 * Actual diff production belongs to the comparison engine; this gate
 * exists so the flow never fabricates a comparison from names alone.
 */
import type { Report } from "../../contracts/src/index.ts";

export type ComparisonReadiness =
  | { readonly status: "ready"; readonly documentSha256: string }
  | { readonly status: "same_report" }
  | { readonly status: "incomparable"; readonly reason: string };

export function prepareComparison(left: Report, right: Report): ComparisonReadiness {
  if (left.report_id === right.report_id) {
    return { status: "same_report" };
  }
  if (left.document.sha256 !== right.document.sha256) {
    return {
      status: "incomparable",
      reason:
        "The selected reports record different source bytes — different bytes are not the same document.",
    };
  }
  return { status: "ready", documentSha256: left.document.sha256 };
}
