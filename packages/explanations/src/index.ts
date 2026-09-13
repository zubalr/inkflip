/**
 * @inkflip/explanations
 *
 * Deterministic, evidence-bound plain explanations and coverage accounting
 * over PDF reading comparison results.
 *
 * Requirements:
 * - Normal invisible scan has no warning solely for invisibility (I11).
 * - Timed-out, model-missing, and unsupported are strictly distinct categories (I05).
 * - Zero findings cannot display "clean" or "safe"; displays I06 disclaimer.
 * - Explanations come from deterministic templates and actual recorded evidence,
 *   never generated truth claims or probabilistic guessing.
 */

import type {
  Finding,
  Occurrence,
  Reader,
  CheckResult,
  Plan,
  Page,
} from "../../contracts/src/index.ts";

export const COPY = {
  "finding.difference": "These readings differ here",
  "finding.amount": "This amount reads differently",
  "finding.readers": "{readerA} returned “{readingA}”. {readerB} returned “{readingB}”.",
  "finding.limit": "A difference does not establish which reading is correct.",
  "finding.ocr": "{reader} reads the rendered region as “{reading}”.",
  "finding.ambiguous": "Several locations could match this reading",
  "finding.ambiguous.body":
    "We could not select one location reliably. Compare the candidates without a precise-match claim.",
  "finding.unmatched": "No matching reading found here",
  "finding.unmatched.body":
    "This may be a reader omission or an alignment limitation. It does not prove the document has missing text.",
  "finding.structural": "A supported structural check found this property",
  "finding.hypothesis": "Possible explanation · not established by this check",
  "finding.details": "How this was checked",
  "finding.note": "Add a local note",
  "finding.note.label": "Your interpretation (not a reader result)",
  "finding.note.disclosure": "Notes remain local and are included in exports only when selected.",
  "coverage.title": "What was checked",
  "coverage.summary": "{completed} checks completed · {incomplete} incomplete or unsupported",
  "coverage.pages": "{selected} of {total} pages included in this run",
  "coverage.agreement": "These readers agree in the checked region.",
  "coverage.noalert":
    "No localized differences were found in completed comparisons. This is not a document safety or correctness check.",
  "coverage.ocr.notrun":
    "Extracted text is ready. The rendered page has not been compared with OCR.",
  "coverage.empty": "This reader returned no text from the checked page.",
  "coverage.normal_scan":
    "Searchable scans can contain invisible OCR text. That alone is not a problem.",
  "coverage.unsupported": "Not supported by this reader",
  "coverage.unchecked": "Not checked",
  "coverage.skipped": "Not run: {reason}",
  "progress.timeout": "This check reached its local time limit. Other completed results are kept.",
  "model.failure": "OCR could not start. This is a reader error, not an unreadable-page result.",
  "model.offline": "OCR data is not available offline yet. Extracted text remains available.",
  "progress.cancelled": "Cancelled — completed results kept.",
  "progress.failed": "No requested check completed successfully.",
} as const;

export type TerminalStatusCategory =
  | "completed"
  | "timeout"
  | "model_missing"
  | "unsupported"
  | "failed"
  | "cancelled"
  | "skipped";

export interface StatusDetail {
  checkId?: string | undefined;
  category: TerminalStatusCategory;
  label: string;
  description: string;
  reason?: string | null;
  isError: boolean;
  isIncomplete: boolean;
}

export function categorizeCheckStatus(
  status: string,
  reason?: string | null,
  checkId?: string,
): StatusDetail {
  const normStatus = status.toLowerCase();
  const reasonText = (reason || "").toLowerCase();

  if (normStatus === "completed") {
    return {
      checkId,
      category: "completed",
      label: "Completed",
      description: "Requested check finished successfully.",
      reason: null,
      isError: false,
      isIncomplete: false,
    };
  }

  if (normStatus === "timeout") {
    return {
      checkId,
      category: "timeout",
      label: "Timed out",
      description: COPY["progress.timeout"],
      reason: reason || null,
      isError: true,
      isIncomplete: true,
    };
  }

  if (normStatus === "unsupported") {
    return {
      checkId,
      category: "unsupported",
      label: "Unsupported",
      description: COPY["coverage.unsupported"],
      reason: reason || null,
      isError: false,
      isIncomplete: true,
    };
  }

  if (normStatus === "cancelled") {
    return {
      checkId,
      category: "cancelled",
      label: "Cancelled",
      description: COPY["progress.cancelled"],
      reason: reason || null,
      isError: false,
      isIncomplete: true,
    };
  }

  if (normStatus === "skipped") {
    return {
      checkId,
      category: "skipped",
      label: "Skipped",
      description: reason
        ? COPY["coverage.skipped"].replace("{reason}", reason)
        : COPY["coverage.unchecked"],
      reason: reason || null,
      isError: false,
      isIncomplete: true,
    };
  }

  // Model-missing check within failed
  if (
    reasonText.includes("model") ||
    reasonText.includes("asset") ||
    reasonText.includes("tessdata") ||
    reasonText.includes("offline") ||
    reasonText.includes("checksum")
  ) {
    return {
      checkId,
      category: "model_missing",
      label: "Model missing",
      description: reasonText.includes("offline") ? COPY["model.offline"] : COPY["model.failure"],
      reason: reason || null,
      isError: true,
      isIncomplete: true,
    };
  }

  return {
    checkId,
    category: "failed",
    label: "Failed",
    description: reason || COPY["progress.failed"],
    reason: reason || null,
    isError: true,
    isIncomplete: true,
  };
}

export interface ReadingItem {
  readerId: string;
  readerName: string;
  readerVersion: string;
  readingText: string;
  occurrenceId: string;
  ordinal: number;
}

export interface FindingExplanation {
  title: string;
  explanation: string;
  readings: ReadingItem[];
  disclaimer: string;
  details: string;
  basis: string;
  limitations: string[];
  isMaterialToken: boolean;
  alignmentLabel: string;
}

const MATERIAL_TOKEN_RE = /[$€£¥₹\d+-]/;

export function isMaterialTokenDifference(
  readings: ReadingItem[],
  findingPriority?: string,
): boolean {
  if (findingPriority) {
    return findingPriority === "material_token";
  }
  if (readings.length < 2) return false;
  // Inspect only the tokens that actually differ between comparative readings
  const first = readings[0];
  if (first === undefined) return false;
  const text0 = first.readingText;
  const differing = readings.slice(1).some((r) => r.readingText !== text0);
  if (!differing) return false;

  const tokens0 = new Set(text0.split(/\s+/));
  for (let i = 1; i < readings.length; i++) {
    const item = readings[i];
    if (item === undefined) continue;
    const tokensI = item.readingText.split(/\s+/);
    for (const t of tokensI) {
      if (!tokens0.has(t) && MATERIAL_TOKEN_RE.test(t)) {
        return true;
      }
    }
    const setI = new Set(tokensI);
    for (const t of tokens0) {
      if (!setI.has(t) && MATERIAL_TOKEN_RE.test(t)) {
        return true;
      }
    }
  }
  return false;
}

export function explainFinding(
  finding: Finding,
  occurrences: Occurrence[],
  readers: Reader[],
): FindingExplanation {
  const readerMap = new Map<string, Reader>();
  for (const r of readers) {
    readerMap.set(r.id, r);
  }

  const occurrenceMap = new Map<string, Occurrence>();
  for (const occ of occurrences) {
    occurrenceMap.set(occ.id, occ);
  }

  const findingOccurrences: Occurrence[] = [];
  for (const id of finding.occurrence_ids) {
    const occ = occurrenceMap.get(id);
    if (occ) {
      findingOccurrences.push(occ);
    }
  }

  const readings: ReadingItem[] = findingOccurrences.map((occ) => {
    const reader = readerMap.get(occ.reader_id);
    return {
      readerId: occ.reader_id,
      readerName: reader ? reader.name : occ.reader_id,
      readerVersion: reader ? reader.version : "",
      readingText: occ.raw_text,
      occurrenceId: occ.id,
      ordinal: occ.ordinal,
    };
  });

  const isMaterial =
    finding.priority === "material_token" ||
    (finding.priority !== "ordinary" && isMaterialTokenDifference(readings, finding.priority));

  let title = finding.title;
  let explanation = finding.explanation;

  if (finding.kind === "reading_difference") {
    title = isMaterial ? COPY["finding.amount"] : COPY["finding.difference"];
    if (readings.length >= 2 && readings[0] && readings[1]) {
      explanation = COPY["finding.readers"]
        .replace("{readerA}", readings[0].readerName)
        .replace("{readingA}", readings[0].readingText)
        .replace("{readerB}", readings[1].readerName)
        .replace("{readingB}", readings[1].readingText);
    }
  } else if (finding.kind === "ocr_interpretation") {
    title = "OCR reading interpretation";
    if (readings.length >= 1 && readings[0]) {
      explanation = COPY["finding.ocr"]
        .replace("{reader}", readings[0].readerName)
        .replace("{reading}", readings[0].readingText);
    }
  } else if (finding.kind === "observed_structure") {
    title = COPY["finding.structural"];
  } else if (finding.kind === "mechanism_hypothesis") {
    title = COPY["finding.hypothesis"];
  } else if (finding.kind === "incomplete_check") {
    title = "Incomplete check result";
  }

  if (finding.alignment === "ambiguous") {
    title = COPY["finding.ambiguous"];
    explanation = COPY["finding.ambiguous.body"];
  } else if (finding.alignment === "unmatched") {
    title = COPY["finding.unmatched"];
    explanation = COPY["finding.unmatched.body"];
  }

  let alignmentLabel = "Unique alignment";
  if (finding.alignment === "ambiguous") alignmentLabel = "Ambiguous alignment";
  else if (finding.alignment === "unmatched") alignmentLabel = "Unmatched reading";
  else if (finding.alignment === "page_level") alignmentLabel = "Page-level reading";
  else if (finding.alignment === "not_applicable") alignmentLabel = "Not applicable";

  return {
    title,
    explanation,
    readings,
    disclaimer: COPY["finding.limit"],
    details: finding.basis ? `How this was checked: ${finding.basis}` : COPY["finding.details"],
    basis: finding.basis,
    limitations: finding.limitations || [],
    isMaterialToken: isMaterial,
    alignmentLabel,
  };
}

export interface CoverageBreakdown {
  completed: number;
  timeout: number;
  model_missing: number;
  unsupported: number;
  failed: number;
  cancelled: number;
  skipped: number;
}

export interface CoverageStats {
  totalPlanned: number;
  completed: number;
  incomplete: number;
  selectedPages: number;
  totalPages: number;
  breakdown: CoverageBreakdown;
}

export interface CoverageExplanation {
  title: string;
  summary: string;
  pagesSummary: string;
  agreementMessage: string | null;
  noAlertDisclaimer: string;
  normalScanNotice: string | null;
  stats: CoverageStats;
  statusDetails: StatusDetail[];
  isFullyComplete: boolean;
  hasIncomplete: boolean;
}

export interface ExplainCoverageOptions {
  ocrRun?: boolean;
  hasInvisibleTextScan?: boolean;
  findingsCount?: number;
}

export function explainCoverage(
  plan: Plan,
  checks: CheckResult[],
  pages: Page[],
  options?: ExplainCoverageOptions,
): CoverageExplanation {
  const ocrRun = options?.ocrRun ?? true;
  const hasInvisibleTextScan = options?.hasInvisibleTextScan ?? false;
  const findingsCount = options?.findingsCount ?? 0;

  const breakdown: CoverageBreakdown = {
    completed: 0,
    timeout: 0,
    model_missing: 0,
    unsupported: 0,
    failed: 0,
    cancelled: 0,
    skipped: 0,
  };

  const statusDetails: StatusDetail[] = [];

  for (const chk of checks) {
    const detail = categorizeCheckStatus(chk.status, chk.reason, chk.id);
    statusDetails.push(detail);
    breakdown[detail.category] = (breakdown[detail.category] || 0) + 1;
  }

  const completed = breakdown.completed;
  const incomplete =
    breakdown.timeout +
    breakdown.model_missing +
    breakdown.unsupported +
    breakdown.failed +
    breakdown.cancelled +
    breakdown.skipped;

  const totalPlanned = plan.checks.length;
  const selectedPages = plan.selected_pages.length;
  const totalPages = pages.length > 0 ? pages.length : selectedPages;

  const summary = COPY["coverage.summary"]
    .replace("{completed}", String(completed))
    .replace("{incomplete}", String(incomplete));

  const pagesSummary = COPY["coverage.pages"]
    .replace("{selected}", String(selectedPages))
    .replace("{total}", String(totalPages));

  let agreementMessage: string | null = null;
  if (findingsCount === 0 && completed > 0) {
    if (!ocrRun) {
      agreementMessage = COPY["coverage.ocr.notrun"];
    } else {
      agreementMessage = COPY["coverage.agreement"];
    }
  }

  const normalScanNotice = hasInvisibleTextScan ? COPY["coverage.normal_scan"] : null;

  return {
    title: COPY["coverage.title"],
    summary,
    pagesSummary,
    agreementMessage,
    noAlertDisclaimer: COPY["coverage.noalert"],
    normalScanNotice,
    stats: {
      totalPlanned,
      completed,
      incomplete,
      selectedPages,
      totalPages,
      breakdown,
    },
    statusDetails,
    isFullyComplete: incomplete === 0 && completed > 0,
    hasIncomplete: incomplete > 0,
  };
}

export function sortFindingsByPriority(findings: Finding[]): Finding[] {
  const rank: Record<Finding["priority"], number> = {
    selected: 0,
    material_token: 1,
    ordinary: 2,
    informational: 3,
  };

  return [...findings].sort((a, b) => {
    const rankA = rank[a.priority] ?? 99;
    const rankB = rank[b.priority] ?? 99;
    const rankDiff = rankA - rankB;
    if (rankDiff !== 0) return rankDiff;
    if (a.page_index !== b.page_index) return a.page_index - b.page_index;
    return a.id.localeCompare(b.id);
  });
}

export function groupFindings(
  findings: Finding[],
): Map<string, { pageIndex: number; regionId: string | null; items: Finding[] }> {
  const groups = new Map<
    string,
    { pageIndex: number; regionId: string | null; items: Finding[] }
  >();

  for (const f of sortFindingsByPriority(findings)) {
    const key = `p${f.page_index}_r${f.region_id || "full"}`;
    const existing = groups.get(key);
    if (existing) {
      existing.items.push(f);
    } else {
      groups.set(key, {
        pageIndex: f.page_index,
        regionId: f.region_id,
        items: [f],
      });
    }
  }

  return groups;
}
