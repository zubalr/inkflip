/**
 * Findings derivation for the public inspection session (pdf-3g8).
 *
 * Turns *settled* run evidence into contract `Finding` records. Every
 * finding cites real occurrences produced by real reader checks —
 * nothing is fabricated from invisibility alone and a finding never
 * claims more alignment certainty than the `region-match-v1` engine
 * returned (I04/I06/I11):
 *
 * - completed alignment → `alignPage` output drives the kinds:
 *   differing unique matches become `reading_difference` records,
 *   unresolved units become `ambiguous`, bounded-work abstentions and
 *   one-sided readings stay visibly incomplete/one-sided.
 * - any non-completed check → an `incomplete_check` finding naming its
 *   terminal status (timeout/model-missing/cancelled/skipped stay
 *   distinct in `reason`).
 * - when comparison could not run but exactly one side produced a
 *   reading, the reading is still reported one-sided — never upgraded
 *   to a two-reader `reading_difference` (contract requires two actual
 *   reader identities).
 */
import type {
  CheckPlan,
  CheckResult,
  Finding,
  Occurrence,
  Reader,
} from "../../../../../packages/contracts/src/index.ts";
import { digest } from "../../../../../packages/contracts/src/index.ts";
import type { AlignmentResult } from "../../../../../packages/compare/alignment/index.ts";
import { isMaterialTokenDifference } from "../../../../../packages/explanations/src/index.ts";
import type { ContractRegion } from "../selection/region";

const DIFFERENCE_DISCLAIMER =
  "A difference does not establish which reading is correct.";
const ALIGNMENT_BASIS =
  "region-match-v1 bounded matching over retained reader occurrences";

export interface FindingsInput {
  /** Terminal results in plan order (`settledCheckResults`). */
  readonly checks: readonly CheckResult[];
  /** Retained run occurrences (coordinator snapshot). */
  readonly occurrences: readonly Occurrence[];
  /** plan.checks by id (capability/region lookup). */
  readonly plansById: ReadonlyMap<string, CheckPlan>;
  /** Contract regions by id (polygon lookup for `unique` claims). */
  readonly regionsById: ReadonlyMap<string, ContractRegion>;
  /** Alignment results keyed by the alignment check id that produced them. */
  readonly alignments: ReadonlyMap<string, AlignmentResult>;
  /** Reader records for names used in stored explanations. */
  readonly readers: readonly Reader[];
}

function findingId(parts: unknown): string {
  return `f_${digest(parts).slice(0, 16)}`;
}

function readerName(readers: readonly Reader[], id: string): string {
  return readers.find((r) => r.id === id)?.name ?? id;
}

/** Stored explanation text mirroring the deterministic display copy. */
function differenceExplanation(
  left: readonly Occurrence[],
  right: readonly Occurrence[],
  readers: readonly Reader[],
): string {
  const a = left[0];
  const b = right[0];
  if (!a || !b) return "The compared readings differ.";
  return `${readerName(readers, a.reader_id)} returned “${a.raw_text}”. ` +
    `${readerName(readers, b.reader_id)} returned “${b.raw_text}”.`;
}

function groupText(occs: readonly Occurrence[]): string {
  return [...occs]
    .sort((a, b) => a.ordinal - b.ordinal)
    .map((o) => o.normalized_text)
    .join(" ")
    .trim();
}

export function deriveFindings(input: FindingsInput): Finding[] {
  const { checks, occurrences, plansById, regionsById, alignments, readers } =
    input;
  const occById = new Map(occurrences.map((o) => [o.id, o]));
  const checkById = new Map(checks.map((c) => [c.id, c]));
  const findings: Finding[] = [];

  const pages = new Set<number>();
  for (const check of checks) {
    const plan = plansById.get(check.id);
    if (plan) pages.add(plan.page_index);
  }

  for (const page of [...pages].sort((a, b) => a - b)) {
    const pageChecks = checks.filter(
      (c) => plansById.get(c.id)?.page_index === page,
    );
    const textCheck = pageChecks.find(
      (c) => plansById.get(c.id)?.capability === "native_text",
    );
    const ocrCheck = pageChecks.find(
      (c) => plansById.get(c.id)?.capability === "ocr",
    );
    const alignCheck = pageChecks.find(
      (c) => plansById.get(c.id)?.capability === "alignment",
    );

    // -- incomplete coverage: every non-completed check stays visible ----
    for (const check of pageChecks) {
      if (check.status === "completed") continue;
      const plan = plansById.get(check.id)!;
      const retained = check.retained_occurrence_ids.filter((id) =>
        occById.has(id),
      );
      findings.push({
        id: findingId({ incomplete: check.id, status: check.status }),
        kind: "incomplete_check",
        title: "Incomplete check result",
        explanation:
          `${plan.capability} check on page ${page + 1} ended as ` +
          `${check.status}${check.reason ? ` (${check.reason})` : ""}.`,
        page_index: page,
        occurrence_ids: retained,
        check_ids: [check.id],
        alignment: "not_applicable",
        region_id: plan.region_id,
        priority: "informational",
        basis: `Terminal check result ${check.status}; recorded without retry or substitution.`,
        limitations: ["Incomplete coverage is not a clean result."],
      });
    }

    const result =
      alignCheck && alignCheck.status === "completed"
        ? alignments.get(alignCheck.id)
        : undefined;

    const leftOccs = (textCheck?.retained_occurrence_ids ?? [])
      .map((id) => occById.get(id))
      .filter((o): o is Occurrence => o !== undefined);
    const rightOccs = (ocrCheck?.retained_occurrence_ids ?? [])
      .map((id) => occById.get(id))
      .filter((o): o is Occurrence => o !== undefined);

    if (result === undefined) {
      // Comparison never ran — report one-sided readings without
      // upgrading them to a two-reader difference (I11).
      if (
        textCheck?.status === "completed" &&
        rightOccs.length === 0 &&
        leftOccs.length > 0
      ) {
        findings.push(oneSided(leftOccs, textCheck.id, page, plansById, regionsById, "observed_structure"));
      }
      if (
        ocrCheck?.status === "completed" &&
        leftOccs.length === 0 &&
        rightOccs.length > 0
      ) {
        findings.push(oneSided(rightOccs, ocrCheck.id, page, plansById, regionsById, "ocr_interpretation"));
      }
      continue;
    }

    const regionId = plansById.get(alignCheck.id)?.region_id ?? null;
    const regionPolygon =
      regionId === null ? null : (regionsById.get(regionId)?.geometry.polygon ?? null);
    const uniqueOk =
      regionId !== null && regionPolygon !== null;
    const checkIds = [textCheck?.id, ocrCheck?.id].filter(
      (id): id is string => id !== undefined,
    );

    // -- accepted matches: only actual text divergence is a difference --
    for (const [i, match] of result.matches.entries()) {
      const left = match.left_occurrence_ids
        .map((id) => occById.get(id))
        .filter((o): o is Occurrence => o !== undefined);
      const right = match.right_occurrence_ids
        .map((id) => occById.get(id))
        .filter((o): o is Occurrence => o !== undefined);
      if (left.length === 0 || right.length === 0) continue;
      if (groupText(left) === groupText(right)) continue; // agreement
      const allLocalized = [...left, ...right].every(
        (o) => o.geometry.polygon !== null,
      );
      const readings = [...left, ...right].map((o) => ({
        readerId: o.reader_id,
        readerName: readerName(readers, o.reader_id),
        readerVersion: readers.find((r) => r.id === o.reader_id)?.version ?? "",
        readingText: o.raw_text,
        occurrenceId: o.id,
        ordinal: o.ordinal,
      }));
      const material = isMaterialTokenDifference(readings);
      findings.push({
        id: findingId({ diff: alignCheck.id, match: i }),
        kind: "reading_difference",
        title: material
          ? "This amount reads differently"
          : "These readings differ here",
        explanation: differenceExplanation(left, right, readers),
        page_index: page,
        occurrence_ids: [...match.left_occurrence_ids, ...match.right_occurrence_ids],
        check_ids: checkIds,
        alignment: uniqueOk && allLocalized ? "unique" : "page_level",
        region_id: uniqueOk && allLocalized ? regionId : null,
        priority: regionId !== null
          ? "selected"
          : material
            ? "material_token"
            : "ordinary",
        basis: `${ALIGNMENT_BASIS}; match cost ${match.components.cost.toFixed(4)}.`,
        limitations: [DIFFERENCE_DISCLAIMER],
      });
    }

    // -- ambiguous units: abstention, never first-match-wins ------------
    for (const [i, entry] of result.ambiguous.entries()) {
      findings.push({
        id: findingId({ ambiguous: alignCheck.id, entry: i }),
        kind: "reading_difference",
        title: "Several locations could match this reading",
        explanation:
          "We could not select one location reliably. Compare the candidates without a precise-match claim.",
        page_index: page,
        occurrence_ids: [
          ...entry.left_occurrence_ids,
          ...entry.right_occurrence_ids,
        ],
        check_ids: checkIds,
        alignment: "ambiguous",
        region_id: regionId,
        priority: regionId !== null ? "selected" : "ordinary",
        basis: `${ALIGNMENT_BASIS}; ambiguity reason ${entry.reason}.`,
        limitations: [DIFFERENCE_DISCLAIMER],
      });
    }

    // -- bounded-work abstentions stay visibly incomplete ---------------
    for (const [i, entry] of result.abstentions.entries()) {
      findings.push({
        id: findingId({ abstained: alignCheck.id, entry: i }),
        kind: "incomplete_check",
        title: "Incomplete check result",
        explanation:
          "Alignment abstained on this span: the bounded-matching cap was reached. " +
          "The readings were not silently paired.",
        page_index: page,
        occurrence_ids: [
          ...entry.left_occurrence_ids,
          ...entry.right_occurrence_ids,
        ],
        check_ids: checkIds,
        alignment: "not_applicable",
        region_id: regionId,
        priority: "informational",
        basis: `${ALIGNMENT_BASIS}; abstention ${entry.reason}.`,
        limitations: ["Incomplete coverage is not a clean result."],
      });
    }

    // -- one-sided unmatched readings ------------------------------------
    const unmatchedLeft = result.left
      .filter((o) => o.status === "unmatched")
      .map((o) => o.occurrence_id)
      .filter((id) => occById.has(id));
    const unmatchedRight = result.right
      .filter((o) => o.status === "unmatched")
      .map((o) => o.occurrence_id)
      .filter((id) => occById.has(id));
    if (unmatchedLeft.length > 0 && textCheck) {
      findings.push(
        unmatchedFinding(
          unmatchedLeft,
          textCheck.id,
          page,
          regionId,
          "observed_structure",
          occById,
        ),
      );
    }
    if (unmatchedRight.length > 0 && ocrCheck) {
      findings.push(
        unmatchedFinding(
          unmatchedRight,
          ocrCheck.id,
          page,
          regionId,
          "ocr_interpretation",
          occById,
        ),
      );
    }

    // -- page-level readings compared as whole-page text -----------------
    const plLeft = result.page_level.left_occurrence_ids
      .map((id) => occById.get(id))
      .filter((o): o is Occurrence => o !== undefined);
    const plRight = result.page_level.right_occurrence_ids
      .map((id) => occById.get(id))
      .filter((o): o is Occurrence => o !== undefined);
    if (
      plLeft.length > 0 &&
      plRight.length > 0 &&
      groupText(plLeft) !== groupText(plRight)
    ) {
      findings.push({
        id: findingId({ pageLevel: alignCheck.id }),
        kind: "reading_difference",
        title: "These readings differ here",
        explanation: differenceExplanation(plLeft, plRight, readers),
        page_index: page,
        occurrence_ids: [
          ...result.page_level.left_occurrence_ids,
          ...result.page_level.right_occurrence_ids,
        ],
        check_ids: checkIds,
        alignment: "page_level",
        region_id: null,
        priority: "ordinary",
        basis: `${ALIGNMENT_BASIS}; page-level reading comparison.`,
        limitations: [DIFFERENCE_DISCLAIMER],
      });
    }
  }

  return findings;
}

function oneSided(
  occs: readonly Occurrence[],
  checkId: string,
  page: number,
  plansById: ReadonlyMap<string, CheckPlan>,
  regionsById: ReadonlyMap<string, ContractRegion>,
  kind: Finding["kind"],
): Finding {
  const plan = plansById.get(checkId);
  const regionId = plan?.region_id ?? null;
  const regionPolygon =
    regionId === null ? null : (regionsById.get(regionId)?.geometry.polygon ?? null);
  const localized =
    regionPolygon !== null && occs.every((o) => o.geometry.polygon !== null);
  return {
    id: findingId({ oneSided: checkId, occs: occs.map((o) => o.id) }),
    kind,
    title:
      kind === "ocr_interpretation"
        ? "OCR reading interpretation"
        : "No matching reading found here",
    explanation:
      kind === "ocr_interpretation"
        ? `The OCR reader produced ${occs.length} reading(s); no text-layer reading was available to compare.`
        : `The text reader produced ${occs.length} reading(s); no OCR reading was available to compare.`,
    page_index: page,
    occurrence_ids: occs.map((o) => o.id),
    check_ids: [checkId],
    alignment: localized ? "unique" : "page_level",
    region_id: localized ? regionId : null,
    priority: regionId !== null ? "selected" : "informational",
    basis: "One-sided retained reading; the comparison check did not run.",
    limitations: ["A single reader's output is not a comparison result."],
  };
}

function unmatchedFinding(
  occIds: readonly string[],
  checkId: string,
  page: number,
  regionId: string | null,
  kind: Finding["kind"],
  occById: ReadonlyMap<string, Occurrence>,
): Finding {
  const allLocalized = occIds.every(
    (id) => occById.get(id)?.geometry.polygon !== null,
  );
  return {
    id: findingId({ unmatched: checkId, occs: occIds }),
    kind,
    title: "No matching reading found here",
    explanation:
      "This may be a reader omission or an alignment limitation. It does not prove the document has missing text.",
    page_index: page,
    occurrence_ids: [...occIds],
    check_ids: [checkId],
    alignment: "unmatched",
    region_id: allLocalized ? regionId : null,
    priority: regionId !== null ? "selected" : "informational",
    basis: "region-match-v1 retained this occurrence without a counterpart.",
    limitations: ["An unmatched reading is not proof of missing content."],
  };
}
