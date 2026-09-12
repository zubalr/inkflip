// TEST-31 — shared Node comparison bridge, entrypoint side.
//
// The fixed installed entrypoint `packages/compare/node/bridge.mjs`
// must produce results identical to calling the shared @inkflip/compare
// operations in-process — the same code the browser uses. Golden cases
// come from tests/bridge/cases.json and are also exercised through the
// Python->Node bridge in native/tests/bridge, so all three legs agree
// on exactly the same normalized output and geometry.
//
// Fixture dimensions: F11 (identical text at distinct positions stays
// separate occurrences), F12 (changed column emission order is
// reported, never hidden), F23-flavor (page_only/unknown geometry is
// never rescued by matching text elsewhere — missing stays missing),
// F15 (digit/sign differences are never normalized away).
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { opAlign, opDescribe, opNormalize } from "../../packages/compare/node/protocol.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ENTRYPOINT = path.resolve(HERE, "../../packages/compare/node/bridge.mjs");
const CASES = JSON.parse(readFileSync(path.join(HERE, "cases.json"), "utf8"));

const PROTOCOL = "inkflip-compare-bridge";

// --- helpers ---------------------------------------------------------------

const geometryFor = (spec) => ({
  precision: spec.precision ?? "exact",
  space: "canonical_page",
  polygon:
    spec.box === null || spec.box === undefined
      ? null
      : [
          [spec.box[0], spec.box[1]],
          [spec.box[2], spec.box[1]],
          [spec.box[2], spec.box[3]],
          [spec.box[0], spec.box[3]],
        ],
  transform_ids: [],
  basis: "golden case",
});

const expandOccurrence = (spec) => {
  const out = {
    id: spec.id,
    page_index: spec.page_index,
    ordinal: spec.ordinal,
    geometry: geometryFor(spec),
  };
  if (spec.raw !== undefined) out.raw = spec.raw;
  if (spec.normalized_text !== undefined) out.normalized_text = spec.normalized_text;
  return out;
};

const expandPage = (spec) => {
  const page = {
    left: spec.left.map(expandOccurrence),
    right: spec.right.map(expandOccurrence),
  };
  if (spec.page_index !== undefined) page.page_index = spec.page_index;
  if (spec.region !== undefined) {
    const b = spec.region;
    page.region = {
      polygon: [
        [b[0], b[1]],
        [b[2], b[1]],
        [b[2], b[3]],
        [b[0], b[3]],
      ],
    };
  }
  return page;
};

/** Spawn the fixed entrypoint with one JSON request; return its response. */
const callBridge = (request) => {
  const spawned = spawnSync(process.execPath, [ENTRYPOINT], {
    input: JSON.stringify(request),
    encoding: "utf8",
    maxBuffer: 128 * 1024 * 1024,
  });
  assert.equal(spawned.error, undefined, "entrypoint must spawn");
  assert.equal(
    spawned.status,
    0,
    `entrypoint exited ${spawned.status}: ${String(spawned.stderr).slice(0, 300)}`,
  );
  const stdout = spawned.stdout.trim();
  const response = JSON.parse(stdout);
  assert.equal(response.protocol, PROTOCOL);
  assert.equal(response.version, 1);
  return response;
};

// --- golden cross-path agreement --------------------------------------------

test("golden: normalize through the entrypoint equals in-process shared code", () => {
  const raws = CASES.normalize.map((c) => c.raw);
  const direct = opNormalize({ raws });
  const spawned = callBridge({ protocol: PROTOCOL, version: 1, op: "normalize", raws });
  assert.equal(spawned.ok, true);
  // The full result payload must agree exactly — normalized text and the
  // reversible raw map, not an approximation of either.
  assert.deepEqual(spawned.result, JSON.parse(JSON.stringify(direct)));
});

test("golden: align through the entrypoint equals in-process shared code", () => {
  const pages = CASES.align.map(expandPage);
  const direct = opAlign({ pages });
  const spawned = callBridge({ protocol: PROTOCOL, version: 1, op: "align", pages });
  assert.equal(spawned.ok, true);
  assert.deepEqual(spawned.result, JSON.parse(JSON.stringify(direct)));
});

// --- case semantics (the cases must mean what they claim) -------------------

test("golden cases carry their claimed semantics", () => {
  const pages = CASES.align.map(expandPage);
  const { results } = opAlign({ pages });
  const byId = Object.fromEntries(CASES.align.map((c, i) => [c.id, results[i]]));

  const unique = byId["exact-unique"];
  assert.equal(unique.matches.length, 2);
  assert.ok(unique.matches.every((m) => m.provenance === "one_to_one"));
  assert.ok(unique.matches.every((m) => m.components.text_distance === 0));

  const split = byId["split-merge-provenance"];
  assert.equal(split.matches.length, 1);
  assert.equal(split.matches[0].provenance, "many_to_one");
  assert.deepEqual([...split.matches[0].left_occurrence_ids].sort(), ["l0", "l1"]);

  // F15: a digit->letter substitution is a real text-distance cost, yet
  // geometry still localizes the pair as unique (never normalized away).
  const material = byId["material-text-difference"];
  assert.equal(material.matches.length, 2);
  const diff = material.matches.find((m) => m.left_occurrence_ids.includes("l0"));
  assert.ok(diff.components.text_distance > 0);
  const clean = material.matches.find((m) => m.left_occurrence_ids.includes("l1"));
  assert.equal(clean.components.text_distance, 0);

  // F11: identical text at four positions binds each occurrence to its
  // own position — never deduplicated by value or first-match-wins.
  const dup = byId["duplicate-positions"];
  assert.equal(dup.matches.length, 4);
  const boundRight = dup.matches.map((m) => m.right_occurrence_ids[0]);
  assert.deepEqual([...boundRight].sort(), ["r0", "r1", "r2", "r3"]);

  // F12: identical layout, changed emission order — order_differences
  // reports the inversion; all four still match uniquely.
  const order = byId["column-order-differs"];
  assert.equal(order.matches.length, 4);
  assert.ok(order.order_differences.length > 0);

  // I04/F23: page_only geometry is never rescued by identical text
  // elsewhere — it stays page_level and the precise right occurrence is
  // unmatched rather than bound to geometry it cannot claim.
  const pageLevel = byId["page-level-no-rescue"];
  const l0 = pageLevel.left.find((o) => o.occurrence_id === "l0");
  assert.equal(l0.status, "page_level");
  const r0 = pageLevel.right.find((o) => o.occurrence_id === "r0");
  assert.notEqual(r0.status, "unique");

  // A selected region is a hard scope: the outside pair never enters
  // localized matching.
  const region = byId["region-scoped"];
  assert.equal(region.region_scoped, true);
  const outL = region.left.find((o) => o.occurrence_id === "l1");
  assert.equal(outL.status, "out_of_scope");
  const inL = region.left.find((o) => o.occurrence_id === "l0");
  assert.equal(inL.status, "unique");

  const extra = byId["unmatched-extra"];
  const l1 = extra.left.find((o) => o.occurrence_id === "l1");
  assert.equal(l1.status, "unmatched");

  // A tie abstains as ambiguous with every candidate kept accessible —
  // never first-match-wins.
  const tie = byId["ambiguous-tie"];
  assert.equal(tie.matches.length, 0);
  assert.ok(tie.ambiguous.length > 0);
  for (const entry of tie.ambiguous) {
    assert.equal(entry.reason, "tie");
    assert.ok(entry.candidates.length >= 2);
  }
  for (const s of [...tie.left, ...tie.right]) {
    assert.equal(s.status, "ambiguous");
  }

  // Contract normalized_text supplied verbatim is honored (and checked
  // for parity when raw accompanies it).
  const supplied = byId["normalized-text-supplied"];
  assert.equal(supplied.matches.length, 1);
});

// --- protocol surface --------------------------------------------------------

test("describe returns comparator identity for manifests (I13)", () => {
  const spawned = callBridge({ protocol: PROTOCOL, version: 1, op: "describe" });
  assert.equal(spawned.ok, true);
  const c = spawned.comparator;
  assert.equal(c.package, "@inkflip/compare");
  assert.equal(c.protocol, PROTOCOL);
  assert.equal(c.protocol_version, 1);
  assert.equal(c.normalization, "scalar-whitespace-v1");
  assert.equal(c.alignment, "region-match-v1");
  assert.equal(c.score_semantics, "algorithm_diagnostics_not_probability");
  assert.equal(c.node, process.version);
  assert.deepEqual(spawned.result, { comparator: c });
  const direct = opDescribe();
  assert.deepEqual(direct.comparator, c);
});

test("every response carries comparator identity", () => {
  const spawned = callBridge({
    protocol: PROTOCOL,
    version: 1,
    op: "normalize",
    raws: ["x"],
  });
  assert.equal(spawned.comparator.alignment, "region-match-v1");
});

test("closed envelope rejects unknown and foreign fields", () => {
  for (const request of [
    { protocol: PROTOCOL, version: 1, op: "align", pages: [], extra: 1 },
    { protocol: PROTOCOL, version: 1, op: "normalize", raws: [], pages: [] },
    { protocol: PROTOCOL, version: 1, op: "describe", exec: "id" },
    { protocol: PROTOCOL, version: 1, op: "normalize", raws: [], shell: true },
    { protocol: PROTOCOL, version: 1, op: "normalize", raws: [], profile: "x" },
    { protocol: PROTOCOL, version: 1, op: "normalize", raws: [], argv: [] },
  ]) {
    const spawned = callBridge(request);
    assert.equal(spawned.ok, false, JSON.stringify(request));
    assert.equal(spawned.error.code, "FIELD");
  }
});

test("unknown op, wrong protocol and wrong version reject cleanly", () => {
  assert.equal(callBridge({ protocol: PROTOCOL, version: 1, op: "exec" }).error.code, "OP");
  assert.equal(
    callBridge({ protocol: "other", version: 1, op: "describe" }).error.code,
    "PROTOCOL",
  );
  assert.equal(
    callBridge({ protocol: PROTOCOL, version: 99, op: "describe" }).error.code,
    "VERSION",
  );
});

test("malformed JSON and non-object requests reject cleanly", () => {
  const bad = spawnSync(process.execPath, [ENTRYPOINT], {
    input: "this is not json",
    encoding: "utf8",
  });
  assert.equal(bad.status, 0);
  assert.equal(JSON.parse(bad.stdout).error.code, "JSON");
  for (const body of ["[1,2]", '"s"', "5", "null"]) {
    const spawned = spawnSync(process.execPath, [ENTRYPOINT], {
      input: body,
      encoding: "utf8",
    });
    assert.equal(spawned.status, 0);
    assert.equal(JSON.parse(spawned.stdout).error.code, "TYPE");
  }
});

test("invalid UTF-8 rejects cleanly", () => {
  const spawned = spawnSync(process.execPath, [ENTRYPOINT], {
    input: Buffer.from([0x7b, 0xff, 0xfe, 0x7d]),
    encoding: "buffer",
    maxBuffer: 1024,
  });
  assert.equal(spawned.status, 0);
  const response = JSON.parse(spawned.stdout.toString("utf8"));
  assert.equal(response.ok, false);
  assert.equal(response.error.code, "UNICODE");
});

test("oversized stdin is rejected, not partially read", () => {
  const big = JSON.stringify({
    protocol: PROTOCOL,
    version: 1,
    op: "normalize",
    raws: ["x".repeat(40 * 1024 * 1024)],
  });
  const spawned = spawnSync(process.execPath, [ENTRYPOINT], {
    input: big,
    encoding: "utf8",
    maxBuffer: 128 * 1024 * 1024,
  });
  assert.equal(spawned.status, 0);
  const response = JSON.parse(spawned.stdout);
  assert.equal(response.ok, false);
  assert.equal(response.error.code, "SIZE");
});

test("raw/normalized_text disagreement is a NORMALIZATION rejection", () => {
  const spawned = callBridge({
    protocol: PROTOCOL,
    version: 1,
    op: "align",
    pages: [
      {
        left: [
          {
            id: "l0",
            page_index: 0,
            ordinal: 0,
            raw: "Total  due",
            normalized_text: "Total-due", // wrong on purpose
            geometry: {
              precision: "exact",
              space: "canonical_page",
              polygon: [
                [10, 20],
                [80, 20],
                [80, 32],
                [10, 32],
              ],
              transform_ids: [],
              basis: "t",
            },
          },
        ],
        right: [],
      },
    ],
  });
  assert.equal(spawned.ok, false);
  assert.equal(spawned.error.code, "NORMALIZATION");
});

test("page objects are a closed schema", () => {
  const spawned = callBridge({
    protocol: PROTOCOL,
    version: 1,
    op: "align",
    pages: [{ left: [], right: [], command: "rm -rf /" }],
  });
  assert.equal(spawned.ok, false);
  assert.equal(spawned.error.code, "FIELD");
});

test("malformed occurrences surface contract codes", () => {
  const page = (occ) => ({
    left: [occ],
    right: [],
  });
  const missing = callBridge({
    protocol: PROTOCOL,
    version: 1,
    op: "align",
    pages: [page({ id: "x" })],
  });
  assert.equal(missing.ok, false);
  assert.equal(missing.error.code, "TYPE");
  const badGeometry = callBridge({
    protocol: PROTOCOL,
    version: 1,
    op: "align",
    pages: [
      page({
        id: "x",
        page_index: 0,
        ordinal: 0,
        raw: "t",
        geometry: "not-geometry",
      }),
    ],
  });
  assert.equal(badGeometry.ok, false);
  assert.equal(badGeometry.error.code, "GEOMETRY");
});

test("alignment needs page_index when inputs span pages", () => {
  const geo = {
    precision: "exact",
    space: "canonical_page",
    polygon: [
      [10, 20],
      [80, 20],
      [80, 32],
      [10, 32],
    ],
    transform_ids: [],
    basis: "t",
  };
  const spawned = callBridge({
    protocol: PROTOCOL,
    version: 1,
    op: "align",
    pages: [
      {
        left: [{ id: "l0", page_index: 0, ordinal: 0, raw: "a", geometry: geo }],
        right: [{ id: "r0", page_index: 1, ordinal: 0, raw: "a", geometry: geo }],
      },
    ],
  });
  assert.equal(spawned.ok, false);
  assert.equal(spawned.error.code, "PAGE");
});

test("dispatch is a pure function of the request", () => {
  // A second in-process call of the same shared code agrees with itself —
  // results are deterministic, not runtime-dependent.
  const pages = CASES.align.map(expandPage);
  const a = opAlign({ pages });
  const b = opAlign({ pages });
  assert.deepEqual(a, b);
});

test("ContractError code reaches the error envelope verbatim", () => {
  // Envelope-level contract failures keep the shared code's stable
  // machine-readable reason — Python maps it to remote_<code>.
  const spawned = callBridge({
    protocol: PROTOCOL,
    version: 1,
    op: "normalize",
    raws: [5],
  });
  assert.equal(spawned.ok, false);
  assert.equal(spawned.error.code, "TYPE");
});

test("entrypoint honors a non-string raw element rejection", () => {
  const spawned = callBridge({
    protocol: PROTOCOL,
    version: 1,
    op: "normalize",
    raws: ["ok", { not: "a string" }],
  });
  assert.equal(spawned.ok, false);
  assert.equal(spawned.error.code, "TYPE");
});
