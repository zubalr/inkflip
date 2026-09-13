/**
 * Acceptance-rule evaluation for stored runs (T34).
 *
 * Scopes rules by document, page, reader, region and capability. Geometry
 * rules apply only to comparable precision. Check-plan coverage uses terminal
 * check status, not occurrence counts. Unruled differences stay informational.
 */
import type {
  AcceptanceRules,
  ComparisonStatus,
  EvaluationOutcome,
  OccurrenceChange,
  Rule,
} from "./types.ts";

export const EXIT_OK = 0;
export const EXIT_INVALID_ARGS = 2;
export const EXIT_REGRESSION = 5;
export const EXIT_INCOMPARABLE = 6;

function applies(rule: Rule, report: any): boolean {
  return report?.document?.sha256 === rule.document_sha256;
}

function scopedOccurrences(rule: Rule, report: any): any[] {
  let occs = (report?.occurrences || []).filter((o: any) => o.page_index === rule.page_index);
  if (rule.reader_id) occs = occs.filter((o: any) => o.reader_id === rule.reader_id);
  if (rule.region_id) {
    const planIds = new Set(
      (report?.plan?.checks || [])
        .filter((c: any) => c.region_id === rule.region_id)
        .map((c: any) => c.id),
    );
    const retained = new Set<string>();
    for (const check of report?.checks || []) {
      if (planIds.has(check.id)) {
        for (const id of check.retained_occurrence_ids || []) retained.add(id);
      }
    }
    occs = occs.filter((o: any) => retained.has(o.id));
  }
  return occs;
}

function scopedChecks(rule: Rule, report: any): any[] {
  const plans = new Map<string, any>((report?.plan?.checks || []).map((p: any) => [p.id, p]));
  return (report?.checks || []).filter((check: any) => {
    const plan = plans.get(check.id) || {};
    if (plan.page_index !== rule.page_index) return false;
    if (rule.reader_id && !(plan.reader_ids || []).includes(rule.reader_id)) return false;
    if (rule.capability && plan.capability !== rule.capability) return false;
    if (rule.region_id && plan.region_id !== rule.region_id) return false;
    return true;
  });
}

function change(rule: Rule, kind: OccurrenceChange["kind"], status: ComparisonStatus, explanation: string, right: any[], left: any[] = []): OccurrenceChange {
  return {
    id: `chg_${rule.id}`.slice(0, 96),
    kind,
    page_index: rule.page_index,
    left_occurrence_ids: left.map((o) => o.id).slice(0, 32),
    right_occurrence_ids: right.map((o) => o.id).slice(0, 32),
    status,
    rule_id: rule.id,
    explanation,
  };
}

export function evaluateReportPair(
  leftReport: any,
  rightReport: any,
  acceptanceRules: AcceptanceRules | null = null,
): EvaluationOutcome {
  const limitations = [
    "Rule evaluation is scoped by document, page, reader, region and capability.",
  ];
  const violations: string[] = [];
  const changes: OccurrenceChange[] = [];

  const leftSha = leftReport?.document?.sha256;
  const rightSha = rightReport?.document?.sha256;
  if (!leftSha || !rightSha) {
    return {
      status: "incomparable",
      exitCode: EXIT_INVALID_ARGS,
      changes: [],
      violations: ["Missing document sha256 in report"],
      limitations: ["Incomplete report data"],
      coverageLost: false,
    };
  }
  if (leftSha !== rightSha) {
    return {
      status: "incomparable",
      exitCode: EXIT_INCOMPARABLE,
      changes: [],
      violations: [`Document hash mismatch: ${leftSha} vs ${rightSha}`],
      limitations: ["Cannot compare reports across different documents"],
      coverageLost: false,
    };
  }

  const leftOccs = leftReport?.occurrences || [];
  const rightOccs = rightReport?.occurrences || [];
  const coverageLost = rightOccs.length < leftOccs.length ||
    (rightReport?.checks || []).filter((c: any) => c.status === "completed").length <
      (leftReport?.checks || []).filter((c: any) => c.status === "completed").length;

  let hasAnyChange = coverageLost ||
    JSON.stringify(leftReport?.checks?.map((c: any) => [c.id, c.status])) !==
      JSON.stringify(rightReport?.checks?.map((c: any) => [c.id, c.status]));
  const leftText = leftOccs.map((o: any) => o.raw_text || "").join("\n");
  const rightText = rightOccs.map((o: any) => o.raw_text || "").join("\n");
  if (leftText !== rightText) hasAnyChange = true;

  if (acceptanceRules?.rules) {
    for (const rule of acceptanceRules.rules) {
      if (!applies(rule, rightReport)) continue;
      const pageOccs = scopedOccurrences(rule, rightReport);
      const pageText = pageOccs.map((o: any) => o.raw_text || "").join("\n");
      if (rule.type === "expected_text" && rule.expected_text != null) {
        if (!pageText.includes(rule.expected_text)) {
          violations.push(`Rule '${rule.id}' [expected_text] failed`);
          changes.push(change(rule, "text", "regressed", "expected_text missing", pageOccs));
        }
      } else if (rule.type === "stable_reading") {
        const base = scopedOccurrences(rule, leftReport);
        const baseText = base.map((o: any) => o.raw_text || "").join("\n");
        if (pageText !== baseText) {
          violations.push(`Rule '${rule.id}' [stable_reading] violated`);
          changes.push(change(rule, "text", "regressed", "stable_reading changed", pageOccs, base));
        }
      } else if (rule.type === "required_coverage") {
        const checks = scopedChecks(rule, rightReport);
        if (!checks.some((c: any) => c.status === "completed")) {
          violations.push(`Rule '${rule.id}' [required_coverage] failed`);
          changes.push(change(rule, "coverage", "regressed", "required coverage missing", pageOccs));
        }
      } else if (rule.type === "expected_occurrence_count" && rule.expected_count != null) {
        if (pageOccs.length !== rule.expected_count) {
          violations.push(`Rule '${rule.id}' [expected_occurrence_count] failed`);
          changes.push(change(rule, "coverage", "regressed", "occurrence count mismatch", pageOccs));
        }
      } else if (rule.type === "max_geometry_delta" && rule.max_delta_pt != null) {
        const base = scopedOccurrences(rule, leftReport);
        let comparable = false;
        let over = false;
        for (let i = 0; i < Math.min(base.length, pageOccs.length); i++) {
          const lg = base[i].geometry;
          const rg = pageOccs[i].geometry;
          if (!lg?.polygon || !rg?.polygon) continue;
          if (lg.precision !== "exact" && lg.precision !== "estimated") continue;
          if (rg.precision !== "exact" && rg.precision !== "estimated") continue;
          comparable = true;
          const delta = Math.max(
            ...lg.polygon.map((pt: number[], idx: number) => {
              const other = rg.polygon[idx];
              return Math.hypot(pt[0] - other[0], pt[1] - other[1]);
            }),
          );
          if (delta > rule.max_delta_pt) over = true;
        }
        if (!comparable) {
          changes.push(change(rule, "geometry", "incomparable", "geometry not comparable", pageOccs, base));
        } else if (over) {
          violations.push(`Rule '${rule.id}' [max_geometry_delta] exceeded`);
          changes.push(change(rule, "geometry", "regressed", "geometry delta exceeded", pageOccs, base));
        }
      }
    }
  }

  let status: ComparisonStatus = "unchanged";
  let exitCode = EXIT_OK;
  if (violations.length > 0) {
    status = "regressed";
    exitCode = EXIT_REGRESSION;
  } else if (coverageLost && acceptanceRules?.policy?.fail_on_coverage_loss) {
    status = "regressed";
    exitCode = EXIT_REGRESSION;
  } else if (hasAnyChange) {
    status = "changed";
    exitCode = EXIT_OK;
  }
  return { status, exitCode, changes, violations, limitations, coverageLost };
}
