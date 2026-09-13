// TEST-34 — acceptance-rule evaluation and comparison exit policy.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  EXIT_INCOMPARABLE,
  EXIT_OK,
  EXIT_REGRESSION,
  evaluateReportPair,
} from "../../packages/compare/regression/index.ts";

const AMOUNT = "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80";
const CONTROL = "19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed";

function report(sha, text, extras = {}) {
  return {
    document: { sha256: sha },
    readers: [{ id: "pypdf-native" }],
    occurrences: [
      {
        id: "occ_0",
        reader_id: "pypdf-native",
        page_index: 0,
        raw_text: text,
      },
    ],
    checks: [
      {
        id: "chk_pypdf_text_p0",
        status: extras.checkStatus || "completed",
        retained_occurrence_ids: ["occ_0"],
      },
    ],
    plan: {
      checks: [
        {
          id: "chk_pypdf_text_p0",
          page_index: 0,
          capability: "native_text",
          reader_ids: ["pypdf-native"],
          region_id: extras.regionId || null,
        },
      ],
    },
    ...extras.report,
  };
}

function rules(items) {
  return {
    kind: "acceptance_rules",
    schema_version: "1.0.0",
    rules: items,
    policy: {
      fail_on_coverage_loss: true,
      fail_on_error: true,
      unruled_change: "changed",
    },
  };
}

test("no-rule text difference is informational changed/0", () => {
  const left = report(AMOUNT, "$1,000");
  const right = report(AMOUNT, "$1,000 extra");
  const outcome = evaluateReportPair(left, right, null);
  assert.equal(outcome.status, "changed");
  assert.equal(outcome.exitCode, EXIT_OK);
});

test("declared expected_text regression exits 5", () => {
  const left = report(CONTROL, "keep $100");
  const right = report(CONTROL, "keep $999");
  const outcome = evaluateReportPair(
    left,
    right,
    rules([
      {
        id: "control-text",
        type: "expected_text",
        document_sha256: CONTROL,
        page_index: 0,
        reader_id: null,
        region_id: null,
        expected_text: "$100",
        expected_count: null,
        max_delta_pt: null,
        capability: null,
        explanation: "amount",
      },
    ]),
  );
  assert.equal(outcome.status, "regressed");
  assert.equal(outcome.exitCode, EXIT_REGRESSION);
});

test("unrelated document rule does not fire", () => {
  const left = report(AMOUNT, "$1,000");
  const right = report(AMOUNT, "$1,000");
  const outcome = evaluateReportPair(
    left,
    right,
    rules([
      {
        id: "other-doc",
        type: "expected_text",
        document_sha256: CONTROL,
        page_index: 0,
        reader_id: null,
        region_id: null,
        expected_text: "absent",
        expected_count: null,
        max_delta_pt: null,
        capability: null,
        explanation: "wrong document",
      },
    ]),
  );
  assert.equal(outcome.status, "unchanged");
  assert.equal(outcome.exitCode, EXIT_OK);
});

test("lost coverage cannot count as improvement", () => {
  const left = report(AMOUNT, "$1,000");
  const right = {
    ...report(AMOUNT, "$1,000"),
    occurrences: [],
    checks: [{ id: "chk_pypdf_text_p0", status: "failed", retained_occurrence_ids: [] }],
  };
  const outcome = evaluateReportPair(left, right, null);
  assert.equal(outcome.coverageLost, true);
  assert.notEqual(outcome.status, "improved");
  const withPolicy = evaluateReportPair(
    left,
    right,
    rules([
      {
        id: "need-coverage",
        type: "required_coverage",
        document_sha256: AMOUNT,
        page_index: 0,
        reader_id: null,
        region_id: null,
        expected_text: null,
        expected_count: null,
        max_delta_pt: null,
        capability: "native_text",
        explanation: "must complete",
      },
    ]),
  );
  assert.equal(withPolicy.exitCode, EXIT_REGRESSION);
});

test("different documents are incomparable", () => {
  const outcome = evaluateReportPair(report(AMOUNT, "a"), report(CONTROL, "a"), null);
  assert.equal(outcome.status, "incomparable");
  assert.equal(outcome.exitCode, EXIT_INCOMPARABLE);
});

test("check-plan coverage uses terminal status not occurrence counts", () => {
  const left = report(AMOUNT, "$1,000");
  const right = {
    ...report(AMOUNT, "$1,000 $1,000"),
    occurrences: [
      { id: "occ_0", reader_id: "pypdf-native", page_index: 0, raw_text: "$1,000" },
      { id: "occ_1", reader_id: "pypdf-native", page_index: 0, raw_text: "$1,000" },
    ],
    checks: [{ id: "chk_pypdf_text_p0", status: "failed", retained_occurrence_ids: [] }],
  };
  const outcome = evaluateReportPair(
    left,
    right,
    rules([
      {
        id: "cov",
        type: "required_coverage",
        document_sha256: AMOUNT,
        page_index: 0,
        reader_id: null,
        region_id: null,
        expected_text: null,
        expected_count: null,
        max_delta_pt: null,
        capability: "native_text",
        explanation: "status not count",
      },
    ]),
  );
  assert.equal(outcome.exitCode, EXIT_REGRESSION);
});

test("region scope ignores occurrences outside the region", () => {
  const left = report(AMOUNT, "$1,000", { regionId: "region_selected" });
  const right = report(AMOUNT, "other", { regionId: "region_selected" });
  right.plan.checks[0].region_id = "region_selected";
  right.checks[0].retained_occurrence_ids = [];
  const outcome = evaluateReportPair(
    left,
    right,
    rules([
      {
        id: "region-text",
        type: "expected_text",
        document_sha256: AMOUNT,
        page_index: 0,
        reader_id: "pypdf-native",
        region_id: "region_selected",
        expected_text: "$1,000",
        expected_count: null,
        max_delta_pt: null,
        capability: "native_text",
        explanation: "only region-retained text",
      },
    ]),
  );
  assert.equal(outcome.exitCode, EXIT_REGRESSION);
});
