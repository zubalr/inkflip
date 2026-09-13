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
  NormalizationMapEntry,
  Occurrence,
  Page,
  Plan,
  Reader,
  Report,
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
  readonly runStatus: string;
  /** All pages' metadata (viewport + canonical transform). */
  readonly pages: readonly Page[];
  readonly maxOcrPagesPerRun: number;
  /** Why OCR coverage was narrowed for this run (profile caps), or null. */
  readonly ocrCoverageNote: string | null;
}

function buildNormalizationMap(
  occurrences: readonly Occurrence[],
): NormalizationMapEntry[] {
  const seen = new Map<string, NormalizationMapEntry>();
  for (const occ of occurrences) {
    if (!seen.has(occ.text_transform.transform_id)) {
      seen.set(occ.text_transform.transform_id, occ.text_transform);
    }
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
  const regionsById = new Map(input.regions.map((r) => [r.region_id, r]));
  const findings = deriveFindings({
    checks: input.checks,
    occurrences: input.occurrences,
    plansById,
    regionsById,
    alignments: input.alignments,
    readers: input.readers,
  });

  const report: Report = {
    schema_version: "inkflip.report@1",
    report_id: null,
    created_at: new Date().toISOString(),
    document: {
      sha256: input.document.sha256,
      byte_length: input.document.byte_length,
      page_count: input.document.page_count,
      filename: input.fileName,
      opened_at: input.openedAtIso,
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
    normalization_map: buildNormalizationMap(input.occurrences),
    pages: input.pages.map((p) => ({ ...p })),
    findings,
    annotations: [],
    assets: [],
    execution: {
      run_key: null,
      started_at: input.runStartedAtIso,
      duration_ms: Math.max(0, Math.round(input.durationMs)),
      status: input.runStatus,
      errors: input.checks
        .filter((c) => c.status === "failed" || c.status === "timeout")
        .map((c) => ({
          check_id: c.id,
          error_kind: c.status,
          error_detail: c.reason ?? c.status,
        })),
    },
    limitations: buildLimitations(input),
    export: {
      mode: "selected",
      scope: "evidence_only",
      replay: "requires_original",
      document_hash: input.document.sha256,
      settings: {
        selection: "user-selected pages and drawn regions",
        findings: "derived from retained reader evidence",
        readers: input.readers.map((r) => `${r.id}@${r.version}`),
        profile: { max_ocr_pages_per_run: input.maxOcrPagesPerRun },
      },
      coverage: {
        selected_pages: [...input.selectedPages],
        page_count: input.document.page_count,
        checks: input.checks.length,
        checks_completed: input.checks.filter((c) => c.status === "completed").length,
        checks_unsupported: input.checks.filter((c) => c.status === "unsupported").length,
        checks_failed: input.checks.filter((c) => c.status === "failed").length,
        produced_occurrences: input.checks.reduce((n, c) => n + c.produced_occurrence_count, 0),
        retained_occurrences: input.occurrences.length,
      },
      included: [
        "document identity (SHA-256)",
        "reader manifests",
        "check plan and terminal results",
        "retained occurrences with raw readings",
        "findings derived from evidence",
        "coverage and limitations",
      ],
      omissions: ["source PDF bytes (opt-in)", "unselected pages"],
    },
  };

  const sealed = seal(report);
  const verdict = validateReport(sealed);
  if (!verdict.ok) {
    const detail = verdict.issues.map((i) => `${i.code} ${i.path}`).join("; ");
    throw new Error(`Assembled report failed validation: ${detail}`);
  }
  return sealed;
}
