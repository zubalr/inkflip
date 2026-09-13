/**
 * Report assembly for the public inspection session (pdf-3g8).
 *
 * Builds a contract `Report` from a *settled* coordinator run — every
 * check result, occurrence, and finding on the record was produced by a
 * real reader or the `region-match-v1` alignment engine during the run.
 * The record is then `seal()`ed and passed through `validateReport()`
 * before the UI is ever allowed to render or export it; an assembly
 * that fails validation is surfaced as an error, never rendered
 * half-checked.
 */
import type {
  CheckPlan,
  CheckResult,
  Finding,
  Occurrence,
  Page,
  Plan,
  Reader,
  Report,
  Transform,
} from "../../../../../packages/contracts/src/index.ts";
import {
  seal,
  validateReport,
} from "../../../../../packages/contracts/src/index.ts";
import type { ContractRegion } from "../selection/region";
import { deriveFindings } from "./findings";
import type { FindingsInput } from "./findings";
import type { AlignmentResult } from "../../../../../packages/compare/alignment/index.ts";

export interface AssembleReportInput {
  readonly fileName: string | null;
  readonly openedAtIso: string;
  readonly runStartedAtIso: string;
  readonly durationMs: number;
  readonly document: {
    readonly sha256: string;
    readonly byte_length: number;
    readonly page_count: number;
  };
  readonly plan: Plan;
  readonly selectedPages: readonly number[];
  readonly regions: readonly ContractRegion[];
  readonly readers: readonly Reader[];
  readonly checks: readonly CheckResult[];
  readonly occurrences: readonly Occurrence[];
  readonly alignments: FindingsInput["alignments"];
  readonly runKey: string;
  readonly runStatus: Report["execution"]["status"];
  /** All pages' metadata (viewport + canonical transform). */
  readonly pages: readonly Page[];
  /** Page-box, raster-scale and OCR-crop transform records. */
  readonly transforms: readonly Transform[];
  /** Environment string recorded on the execution block. */
  readonly environment: string;
  readonly maxOcrPagesPerRun: number;
  /** Why OCR coverage was narrowed for this run (profile caps), or null. */
  readonly ocrCoverageNote: string | null;
}

function dedupeTransforms(
  transforms: readonly Transform[],
): Transform[] {
  const seen = new Map<string, Transform>();
  for (const t of transforms) {
    if (!seen.has(t.id)) seen.set(t.id, t);
  }
  return [...seen.values()];
}

function buildLimitations(input: AssembleReportInput): string[] {
  const lines: string[] = [];
  const byStatus = new Map<string, string[]>();
  for (const check of input.checks) {
    if (check.status === "completed") continue;
    const label = check.reason ? `${check.status}: ${check.reason}` : check.status;
    const list = byStatus.get(label) ?? [];
    list.push(check.id);
    byStatus.set(label, list);
  }
  for (const [label, ids] of byStatus) {
    lines.push(`${ids.length} check(s) ended ${label}: ${ids.join(", ")}`);
  }
  if (input.ocrCoverageNote) lines.push(input.ocrCoverageNote);
  const unseen = input.document.page_count - input.selectedPages.length;
  if (unseen > 0) {
    lines.push(
      `${unseen} of ${input.document.page_count} page(s) were not inspected in this run.`,
    );
  }
  lines.push("Findings are reader differences, not document verdicts.");
  return lines;
}

/**
 * Assemble, seal, and validate a report. Throws with the validation
 * issue list when the evidence cannot form a lawful record — the
 * caller must surface that as an assembly failure rather than render.
 */
export function assembleReport(input: AssembleReportInput): Report {
  const plansById = new Map(input.plan.checks.map((p) => [p.id, p]));
  const regionsById = new Map(input.regions.map((r) => [r.id, r]));
  const findings = deriveFindings({
    checks: input.checks,
    occurrences: input.occurrences,
    plansById,
    regionsById,
    alignments: input.alignments,
    readers: input.readers,
  });

  const report: Report = {
    kind: "report",
    schema_version: "1.0.0",
    // seal() assigns the content digest.
    report_id: "",
    document: {
      sha256: input.document.sha256,
      byte_length: input.document.byte_length,
      page_count: input.document.page_count,
      display_name: input.fileName,
      source_asset_id: null,
    },
    readers: [...input.readers],
    plan: {
      ...input.plan,
      selected_pages: [...input.selectedPages],
      regions: [...input.regions],
      checks: [...input.plan.checks],
    },
    checks: [...input.checks],
    occurrences: [...input.occurrences],
    transforms: dedupeTransforms(input.transforms),
    pages: input.pages.map((p) => ({ ...p })),
    findings,
    annotations: [],
    assets: [],
    execution: {
      execution_id: crypto.randomUUID(),
      run_key: input.runKey,
      started_at: input.runStartedAtIso,
      duration_ms: Math.max(0, Math.round(input.durationMs)),
      status: input.runStatus,
      environment: input.environment,
      result_origin: "live",
      errors: input.checks
        .filter(
          (c) =>
            c.status === "failed" ||
            c.status === "timeout" ||
            c.status === "cancelled",
        )
        .map((c) => `${c.id}: ${c.status}${c.reason ? ` — ${c.reason}` : ""}`),
    },
    limitations: buildLimitations(input),
    export: {
      mode: "evidence",
      scope: "selection",
      included: [
        "selected_text",
        "document_hash",
        "filename",
        "settings",
        "coverage",
      ],
      omissions: [
        "Original PDF excluded (explicit opt-in only).",
        "Page renders and OCR crops excluded.",
        "Annotations excluded.",
        "Pages outside the selection are not covered.",
      ],
      replay: "requires_original",
      origin_report_id: null,
    },
  };

  const sealed = seal(report);
  try {
    validateReport(sealed);
  } catch (error) {
    throw new Error(
      `Assembled report failed validation: ${error instanceof Error ? error.message : "invalid"}`,
    );
  }
  return sealed;
}
