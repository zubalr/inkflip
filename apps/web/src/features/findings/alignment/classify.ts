/**
 * Finding → alignment semantics (T20).
 *
 * Pure derivation over the sealed report surface — a Finding plus the
 * occurrences it names. Never resolves an occurrence by text: every
 * candidate is addressed by its occurrence id, so four identical strings
 * at four positions stay four distinct candidates.
 *
 * Classes:
 * - `order_only`   — same readings, different emitted order (never a
 *                    text difference and never an accessibility verdict).
 * - `ambiguous`    — the alignment engine abstained; every evaluated
 *                    candidate stays exposed, none is pre-picked.
 * - `unmatched`    — one-sided reading; may be omission, extra output or
 *                    an alignment limit — never "missing text".
 * - `page_level`   — compared at page level only; no localized claim.
 * - `incomplete`   — a check did not complete; retained readings are
 *                    evidence of partial coverage, not a clean result.
 * - `one_sided`    — a single reader's output; no comparison ran.
 * - `difference`   — a settled unique/paired difference.
 */
import type {
  Finding,
  Occurrence,
  Reader,
} from "../../../../../../packages/contracts/src/index.ts";

export type AlignmentClass =
  | "difference"
  | "order_only"
  | "ambiguous"
  | "unmatched"
  | "page_level"
  | "incomplete"
  | "one_sided";

export interface CandidateReading {
  readonly occurrence: Occurrence;
  readonly readerName: string;
  /**
   * Count of *other* named candidates whose normalized text is identical.
   * >0 means identical strings exist at distinct positions — the UI must
   * keep them individually addressable and must not collapse them.
   */
  readonly identicalSiblings: number;
  /**
   * How many candidates (including this one) share the identical
   * normalized text — used for "candidate k of n" labeling.
   */
  readonly identicalRank: number;
}

export interface FindingSemantics {
  readonly classification: AlignmentClass;
  /** Short label for the badge — always honest about scope. */
  readonly badge: string;
  /** One-line semantic statement, never a correctness verdict. */
  readonly body: string;
  /** Every occurrence the finding names, resolved by id. */
  readonly candidates: readonly CandidateReading[];
  /** Named ids that could not be resolved in the occurrence set. */
  readonly unresolvedIds: readonly string[];
}

const ORDER_ONLY_MARKER = "order-only difference";

export function isOrderOnlyFinding(finding: Finding): boolean {
  return finding.kind === "observed_structure" && finding.basis.includes(ORDER_ONLY_MARKER);
}

function classify(finding: Finding): AlignmentClass {
  if (finding.kind === "incomplete_check") return "incomplete";
  if (isOrderOnlyFinding(finding)) return "order_only";
  if (finding.alignment === "ambiguous") return "ambiguous";
  if (finding.alignment === "unmatched") return "unmatched";
  // One-sided readings never ran a comparison — their `page_level`/
  // `unique` alignment only describes localization, so the kind check
  // must come before the page_level label (which claims a comparison).
  if (
    finding.kind === "ocr_interpretation" ||
    finding.kind === "observed_structure"
  ) {
    return "one_sided";
  }
  if (finding.alignment === "page_level") return "page_level";
  return "difference";
}

const CLASS_BADGE: Record<AlignmentClass, string> = {
  difference: "Readings differ",
  order_only: "Order-only difference",
  ambiguous: "Ambiguous, candidates kept",
  unmatched: "No matching reading",
  page_level: "Page-level only",
  incomplete: "Incomplete coverage",
  one_sided: "One reader only",
};

const CLASS_BODY: Record<AlignmentClass, string> = {
  difference:
    "These named readings differ at this location. The difference does not establish which reading is correct.",
  order_only:
    "The compared readers produced the same readings in a different emitted sequence. This is an order difference, not a text difference, and not by itself an accessibility verdict.",
  ambiguous:
    "The alignment engine could not settle one pairing; every evaluated candidate remains listed. No candidate is pre-selected. Picking one is a navigation choice, not a match claim.",
  unmatched:
    "This reading has no aligned counterpart. It may be a reader omission, extra output, or an alignment limit. It is not proof of missing document text.",
  page_level: "This comparison is page-level: no localized coordinates support a narrower claim.",
  incomplete:
    "The planned check did not complete, so coverage here is partial. Retained readings are shown for inspection. They are not a complete result.",
  one_sided:
    "Only one reader produced a reading here; no comparison ran. A single reader's output is not a comparison result.",
};

export function classifyFinding(
  finding: Finding,
  occurrences: readonly Occurrence[],
  readers: readonly Reader[],
): FindingSemantics {
  const occById = new Map(occurrences.map((o) => [o.id, o]));
  const readerName = new Map(readers.map((r) => [r.id, r.name]));
  const resolved: Occurrence[] = [];
  const unresolved: string[] = [];
  for (const id of finding.occurrence_ids) {
    const occ = occById.get(id);
    if (occ) resolved.push(occ);
    else unresolved.push(id);
  }
  // Identical-text sibling bookkeeping: candidates sharing normalized
  // text are ranked in the finding's named order — stable, and never
  // text-addressed.
  const byText = new Map<string, Occurrence[]>();
  for (const occ of resolved) {
    const list = byText.get(occ.normalized_text) ?? [];
    list.push(occ);
    byText.set(occ.normalized_text, list);
  }
  const candidates: CandidateReading[] = resolved.map((occ) => {
    const siblings = byText.get(occ.normalized_text) ?? [];
    return {
      occurrence: occ,
      readerName: readerName.get(occ.reader_id) ?? occ.reader_id,
      identicalSiblings: siblings.length - 1,
      identicalRank: siblings.findIndex((s) => s.id === occ.id) + 1,
    };
  });
  const classification = classify(finding);
  return {
    classification,
    badge: CLASS_BADGE[classification],
    body: CLASS_BODY[classification],
    candidates,
    unresolvedIds: unresolved,
  };
}
