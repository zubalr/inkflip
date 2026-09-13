/**
 * Acceptance rules and regression evaluator (T34).
 *
 * Implements:
 * - Changed no-rule is informational (status: "changed", exit 0)
 * - Rule regression exits 5 (status: "regressed")
 * - Lost coverage cannot count as improvement (triggers regression under policy)
 * - Incompatible files / reader config marked (status: "incomparable")
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

export function evaluateReportPair(
  leftReport: any,
  rightReport: any,
  acceptanceRules: AcceptanceRules | null = null,
): EvaluationOutcome {
  const limitations: string[] = [];
  const violations: string[] = [];
  const changes: OccurrenceChange[] = [];

  // Check document identity compatibility
  const leftDocSha = leftReport?.document?.sha256;
  const rightDocSha = rightReport?.document?.sha256;

  if (!leftDocSha || !rightDocSha) {
    return {
      status: "incomparable",
      exitCode: EXIT_INVALID_ARGS,
      changes: [],
      violations: ["Missing document sha256 in report"],
      limitations: ["Incomplete report data"],
      coverageLost: false,
    };
  }

  if (leftDocSha !== rightDocSha) {
    return {
      status: "incomparable",
      exitCode: EXIT_INVALID_ARGS,
      changes: [],
      violations: [`Document hash mismatch: ${leftDocSha} vs ${rightDocSha}`],
      limitations: ["Cannot compare reports across different documents"],
      coverageLost: false,
    };
  }

  const leftOccs = leftReport?.occurrences || [];
  const rightOccs = rightReport?.occurrences || [];

  // Group occurrences by page index
  const leftByPage = new Map<number, any[]>();
  for (const occ of leftOccs) {
    const p = occ.page_index ?? 0;
    if (!leftByPage.has(p)) leftByPage.set(p, []);
    leftByPage.get(p)!.push(occ);
  }

  const rightByPage = new Map<number, any[]>();
  for (const occ of rightOccs) {
    const p = occ.page_index ?? 0;
    if (!rightByPage.has(p)) rightByPage.set(p, []);
    rightByPage.get(p)!.push(occ);
  }

  let coverageLost = false;

  // Detect coverage loss: left occurrences dropped or missing on right
  if (rightOccs.length < leftOccs.length) {
    coverageLost = true;
    violations.push(
      `Coverage loss: occurrence count decreased from ${leftOccs.length} to ${rightOccs.length}`,
    );
  }

  // Check text content changes per page
  const allPages = new Set([...leftByPage.keys(), ...rightByPage.keys()]);
  let hasAnyChange = false;

  for (const p of Array.from(allPages).sort((a, b) => a - b)) {
    const lPageOccs = leftByPage.get(p) || [];
    const rPageOccs = rightByPage.get(p) || [];

    const lText = lPageOccs.map((o: any) => o.raw_text || "").join("\n");
    const rText = rPageOccs.map((o: any) => o.raw_text || "").join("\n");

    if (lText !== rText || lPageOccs.length !== rPageOccs.length) {
      hasAnyChange = true;
      changes.push({
        id: `chg_p${p}`,
        kind: lPageOccs.length === 0 ? "added" : rPageOccs.length === 0 ? "deleted" : "modified",
        page_index: p,
        left_occurrence_ids: lPageOccs.map((o: any) => o.id),
        right_occurrence_ids: rPageOccs.map((o: any) => o.id),
        status: "changed",
        rule_id: null,
        explanation: `Text differences observed on page ${p}`,
      });
    }
  }

  // Evaluate explicit rules if provided
  if (acceptanceRules && Array.isArray(acceptanceRules.rules)) {
    for (const rule of acceptanceRules.rules) {
      const pageOccs = rightByPage.get(rule.page_index) || [];
      const pageText = pageOccs.map((o: any) => o.raw_text || "").join("\n");

      if (rule.type === "expected_text" && rule.expected_text !== null) {
        if (!pageText.includes(rule.expected_text)) {
          violations.push(
            `Rule '${rule.id}' [expected_text] failed on page ${rule.page_index}: expected '${rule.expected_text}'`,
          );
        }
      } else if (rule.type === "stable_reading") {
        // Stable reading: candidate reading must not diverge from baseline reading
        const baseOccs = leftByPage.get(rule.page_index) || [];
        const baseText = baseOccs.map((o: any) => o.raw_text || "").join("\n");
        if (pageText !== baseText) {
          violations.push(
            `Rule '${rule.id}' [stable_reading] violated on page ${rule.page_index}: reading changed from approved baseline`,
          );
        }
      } else if (rule.type === "required_coverage") {
        if (pageOccs.length === 0) {
          violations.push(
            `Rule '${rule.id}' [required_coverage] failed on page ${rule.page_index}: page has zero extracted occurrences`,
          );
        }
      } else if (rule.type === "expected_occurrence_count" && rule.expected_count !== null) {
        if (pageOccs.length !== rule.expected_count) {
          violations.push(
            `Rule '${rule.id}' [expected_occurrence_count] failed: expected ${rule.expected_count}, got ${pageOccs.length}`,
          );
        }
      }
    }
  }

  // Determine overall status
  let status: ComparisonStatus = "unchanged";
  let exitCode = EXIT_OK;

  if (violations.length > 0) {
    status = "regressed";
    exitCode = EXIT_REGRESSION;
  } else if (coverageLost && acceptanceRules?.policy?.fail_on_coverage_loss) {
    status = "regressed";
    exitCode = EXIT_REGRESSION;
  } else if (hasAnyChange) {
    // In the absence of rule violations, changes are informational
    status = acceptanceRules?.policy?.unruled_change ?? "changed";
    exitCode = EXIT_OK;
  }

  limitations.push("Comparison limited to extracted text occurrences and bounds");

  return {
    status,
    exitCode,
    changes,
    violations,
    limitations,
    coverageLost,
  };
}
