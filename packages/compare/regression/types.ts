export type ComparisonStatus =
  | "unchanged"
  | "changed"
  | "improved"
  | "regressed"
  | "unsupported"
  | "errored"
  | "incomparable";

export interface Rule {
  id: string;
  type:
    | "required_coverage"
    | "expected_text"
    | "expected_occurrence_count"
    | "max_geometry_delta"
    | "stable_reading";
  document_sha256: string;
  page_index: number;
  reader_id: string | null;
  region_id: string | null;
  expected_text: string | null;
  expected_count: number | null;
  max_delta_pt: number | null;
  capability: string | null;
  explanation: string;
}

export interface AcceptanceRules {
  kind: "acceptance_rules";
  schema_version: "1.0.0";
  rules: Rule[];
  policy: {
    fail_on_coverage_loss: true;
    fail_on_error: true;
    unruled_change: "changed";
  };
}

export interface OccurrenceChange {
  id: string;
  kind: "text" | "geometry" | "order" | "coverage" | "error" | "configuration";
  page_index: number | null;
  left_occurrence_ids: string[];
  right_occurrence_ids: string[];
  status: ComparisonStatus;
  rule_id: string | null;
  explanation: string;
}

export interface EvaluationOutcome {
  status: ComparisonStatus;
  exitCode: number;
  changes: OccurrenceChange[];
  violations: string[];
  limitations: string[];
  coverageLost: boolean;
}
