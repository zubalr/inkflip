// T16 / TEST-16 — portable JSON + escaped HTML export foundation.
//
// Registered command: node --test tests/reports/export.test.mjs
//
// Fixture coverage:
//   F01 (public/mapping-amount.pdf) — the example reports' document; its
//     real bytes drive the explicit source-PDF opt-in assertions.
//   F24 (overlap-ink, specified-not-generated) — exercised through a
//     constructed paint_overlap check + ink-in-box occurrence variant of
//     the delivered example report.
//   F25 (annotation-mode, specified-not-generated) — exercised through a
//     static_appearance reader setting + unsupported actions/XFA check +
//     human-entered annotations on the opt-in path.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { createHash } from "node:crypto";
import {
  ContractError,
  loadsStrict,
  normalize,
  seal,
  validate,
} from "../../packages/contracts/src/index.ts";
import {
  assertScriptFreeHtml,
  escapeHtml,
  importReport,
  sanitizePng,
} from "../../packages/reports/validation/index.ts";
import {
  buildExportPreview,
  exportFileName,
  projectReport,
  renderReportHtml,
  serializeReportJson,
} from "../../packages/reports/export/index.ts";
import { makePng, patternRgba, rowsFor } from "../security/import/png_helpers.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const VALID_DIR = join(ROOT, "planning/contracts/examples/valid");
const F01 = readFileSync(join(ROOT, "fixtures/public/mapping-amount.pdf"));
const F01_SHA256 = createHash("sha256").update(F01).digest("hex");

const loadExample = (name) => JSON.parse(readFileSync(join(VALID_DIR, name), "utf8"));
const code = (fn) => {
  try {
    fn();
  } catch (e) {
    if (e instanceof ContractError) return e.code;
    throw e;
  }
  return null;
};
const decode = (text) => loadsStrict(text);

// ---------------------------------------------------------------------------
// Report variants
// ---------------------------------------------------------------------------

// F25 annotation-mode semantics: static appearance recorded, actions/XFA
// unsupported, plus a human note that only the opt-in may export.
function annotationModeReport() {
  const r = structuredClone(loadExample("native-evidence.inkflip.json"));
  r.readers[0].settings.annotation_mode = "static_appearance";
  r.readers[0].capabilities.push({
    name: "object_render_mode",
    support: "approximate",
    limits: ["Actions and XFA are unsupported; static appearance only."],
  });
  r.plan.checks.push({
    id: "c_annot",
    page_index: 0,
    reader_ids: ["r_pdfium"],
    capability: "object_render_mode",
    region_id: null,
  });
  r.checks.push({
    id: "c_annot",
    status: "unsupported",
    reason: "Actions/XFA unsupported; static annotation appearance recorded.",
    produced_occurrence_count: 0,
    retained_occurrence_ids: [],
  });
  r.annotations.push({
    id: "n_review",
    finding_id: "f_amount",
    page_index: 0,
    text: "Check the $1,000 reading against the source.",
    author_label: "reviewer a",
    origin: "human_entered",
  });
  r.execution.status = "partial"; // already partial; kept explicit
  seal(r);
  return r;
}

// F24 overlap-ink semantics: a paint_overlap check and an ink-in-box
// occurrence whose estimated geometry survives the export.
function overlapInkReport() {
  const r = structuredClone(loadExample("native-evidence.inkflip.json"));
  const raw = "TOTAL DUE";
  const n = normalize(raw);
  r.occurrences.push({
    id: "o_overlap",
    reader_id: "r_pdfium",
    page_index: 0,
    ordinal: 117,
    raw_text: raw,
    normalized_text: n.text,
    normalization_map: n.map,
    geometry: {
      precision: "estimated",
      space: "canonical_page",
      polygon: [
        [44, 128],
        [196, 128],
        [196, 190],
        [44, 190],
      ],
      transform_ids: ["t_canonical"],
      basis: "Estimated extent of a span intersecting a visible border.",
    },
    engine_score: null,
    source_asset_id: null,
    raw_source_locator: "synthetic overlap-ink span (F24 family)",
    limitations: [],
  });
  r.plan.checks.push({
    id: "c_overlap",
    page_index: 0,
    reader_ids: ["r_pdfium"],
    capability: "paint_overlap",
    region_id: "region_amount",
  });
  r.checks.push({
    id: "c_overlap",
    status: "completed",
    reason: null,
    produced_occurrence_count: 1,
    retained_occurrence_ids: ["o_overlap"],
  });
  r.findings.push({
    id: "f_overlap",
    kind: "observed_structure",
    title: "Span ink intersects a painted border",
    explanation:
      "A span's ink overlaps a visible border; ink-in-box does not prove glyph visibility.",
    page_index: 0,
    occurrence_ids: ["o_overlap"],
    check_ids: ["c_overlap"],
    alignment: "not_applicable",
    region_id: "region_amount",
    priority: "informational",
    basis: "Constructed F24-family variant on the delivered example report.",
    limitations: ["Constructed, not generator output."],
  });
  seal(r);
  return r;
}

// ---------------------------------------------------------------------------
// Criterion: preview equals decoded contents
// ---------------------------------------------------------------------------

test("preview is measured on the projected object and equals decoded contents", () => {
  const source = annotationModeReport();
  const { report, notices } = projectReport(source, {
    annotations: true,
    pageRenders: "none",
  });
  const json = serializeReportJson(report);
  const html = renderReportHtml(report);
  const preview = buildExportPreview(report, { notices, html });
  const decoded = decode(json); // the artifact a second person receives

  // Categories/omissions are the decoded payload's own disclosure.
  assert.deepEqual([...preview.included], decoded.export.included);
  assert.deepEqual([...preview.omissions], decoded.export.omissions);
  assert.equal(preview.mode, decoded.export.mode);
  assert.equal(preview.replay, decoded.export.replay);
  assert.equal(preview.reportId, decoded.report_id);
  assert.equal(preview.documentSha256, decoded.document.sha256);

  // Counts equal what a decoder sees.
  const c = preview.counts;
  assert.equal(c.findings, decoded.findings.length);
  assert.equal(c.occurrences, decoded.occurrences.length);
  assert.equal(
    c.producedOccurrences,
    decoded.checks.reduce((n, x) => n + x.produced_occurrence_count, 0),
  );
  assert.equal(
    c.retainedOccurrences,
    decoded.checks.reduce((n, x) => n + x.retained_occurrence_ids.length, 0),
  );
  assert.equal(c.checks, decoded.checks.length);
  assert.equal(c.checksCompleted, decoded.checks.filter((x) => x.status === "completed").length);
  assert.equal(c.pagesSelected, decoded.plan.selected_pages.length);
  assert.equal(c.pageCount, decoded.document.page_count);
  assert.equal(c.crops, decoded.assets.filter((a) => a.purpose === "crop").length);
  assert.equal(c.annotations, decoded.annotations.length);

  // Bytes equal the actual decoded payload, never an estimate.
  assert.equal(preview.bytes.jsonBytes, new TextEncoder().encode(json).length);
  assert.equal(preview.bytes.htmlBytes, new TextEncoder().encode(html).length);
  let decodedTotal = 0;
  for (const a of decoded.assets) {
    const bin = Buffer.from(a.data_base64, "base64");
    decodedTotal += bin.length;
    const pa = preview.bytes.assets.find((x) => x.id === a.id);
    assert.equal(pa.decodedBytes, bin.length, `asset ${a.id} bytes`);
    assert.equal(pa.encodedChars, a.data_base64.length);
  }
  assert.equal(preview.bytes.decodedAssetBytes, decodedTotal);
  assert.equal(preview.sourcePdfIncluded, decoded.document.source_asset_id !== null);
  assert.equal(preview.filenameIncluded, decoded.document.display_name !== null);
  assert.equal(preview.annotationsIncluded, decoded.annotations.length > 0);
});

// ---------------------------------------------------------------------------
// Criterion: raw text/geometry/coverage survive
// ---------------------------------------------------------------------------

test("raw text, geometry and coverage denominators survive the export", () => {
  const source = overlapInkReport();
  const { report } = projectReport(source, { occurrences: "all" });
  const json = serializeReportJson(report);
  const decoded = decode(json);

  // Every produced occurrence survives with byte-identical raw text.
  assert.equal(decoded.occurrences.length, source.occurrences.length);
  for (const src of source.occurrences) {
    const got = decoded.occurrences.find((o) => o.id === src.id);
    assert.ok(got, `occurrence ${src.id} retained`);
    assert.equal(got.raw_text, src.raw_text);
    const n = normalize(src.raw_text);
    assert.equal(got.normalized_text, n.text);
    assert.deepEqual(got.normalization_map, n.map);
    assert.deepEqual(got.geometry, src.geometry); // polygons + precision + basis
    assert.deepEqual(got.geometry.transform_ids, src.geometry.transform_ids);
  }

  // Check denominators: produced counts unchanged, retained pruned to kept.
  for (const c of decoded.checks) {
    const src = source.checks.find((x) => x.id === c.id);
    assert.equal(c.produced_occurrence_count, src.produced_occurrence_count, c.id);
    assert.equal(c.status, src.status, c.id);
    assert.equal(c.reason, src.reason, c.id);
  }
  // c_native produced 118 readings; retained list carries the kept ids only.
  const native = decoded.checks.find((c) => c.id === "c_native");
  assert.equal(native.produced_occurrence_count, 118);
  assert.deepEqual(native.retained_occurrence_ids, ["o_pdfium_amount"]);

  // Check scope/context: plan, selected pages, regions, transforms survive.
  assert.deepEqual(decoded.plan.selected_pages, source.plan.selected_pages);
  assert.deepEqual(decoded.plan.checks, source.plan.checks);
  assert.equal(decoded.plan.normalization_version, "scalar-whitespace-v1");
  assert.equal(decoded.plan.alignment_version, "region-match-v1");
  assert.deepEqual(decoded.plan.budget, source.plan.budget);
  const overlap = decoded.occurrences.find((o) => o.id === "o_overlap");
  assert.equal(overlap.geometry.precision, "estimated");
  assert.ok(overlap.geometry.polygon !== null);
  for (const p of decoded.pages) {
    assert.ok(decoded.transforms.some((t) => t.id === p.raw_to_canonical_transform_id));
  }

  // Engine/settings/hashes/limits travel with the report.
  const reader = decoded.readers.find((r) => r.id === "r_pdfium");
  assert.equal(reader.name, "PDFium via pypdfium2");
  assert.equal(reader.settings.normalization, "scalar-whitespace-v1");
  assert.equal(decoded.document.sha256, F01_SHA256);
  assert.equal(decoded.document.byte_length, F01.length);
  assert.equal(decoded.execution.run_key, source.execution.run_key);
  assert.notEqual(decoded.report_id, source.report_id); // new digest
  assert.equal(decoded.export.origin_report_id, source.report_id);

  // The exported artifact passes the same contract + hardened import gate.
  validate(decoded);
  const imported = importReport(json);
  assert.equal(imported.report.report_id, decoded.report_id);
});

test("selection projection prunes retained ids and keeps produced counts honest", () => {
  const source = overlapInkReport();
  const { report, notices } = projectReport(source, {
    findings: ["f_amount"], // drop f_overlap
    occurrences: "cited",
  });
  const decoded = decode(serializeReportJson(report));
  assert.deepEqual(
    decoded.findings.map((f) => f.id),
    ["f_amount"],
  );
  // o_overlap was dropped; every check still reports its produced count.
  assert.ok(!decoded.occurrences.some((o) => o.id === "o_overlap"));
  const overlap = decoded.checks.find((c) => c.id === "c_overlap");
  assert.equal(overlap.produced_occurrence_count, 1);
  assert.deepEqual(overlap.retained_occurrence_ids, []);
  assert.equal(notices.omittedOccurrenceCount, 1);
  assert.ok(decoded.export.omissions.includes("Other extracted source occurrences excluded."));
  validate(decoded);
});

// ---------------------------------------------------------------------------
// Criterion: no source PDF without explicit opt-in
// ---------------------------------------------------------------------------

test("source PDF stays out by default and enters only on explicit verified opt-in", () => {
  const source = loadExample("native-evidence.inkflip.json");
  const def = projectReport(source, {});
  const d = def.report;
  assert.equal(d.export.mode, "evidence");
  assert.equal(d.export.replay, "requires_original");
  assert.equal(d.document.source_asset_id, null);
  assert.ok(!d.export.included.includes("source_pdf"));
  assert.ok(!d.assets.some((a) => a.purpose === "source_pdf"));
  assert.ok(d.export.omissions.includes("Original PDF excluded."));

  // Explicit opt-in binds the actual F01 bytes to the document digest.
  const opt = projectReport(source, { sourcePdf: F01 });
  const r = opt.report;
  assert.equal(r.export.mode, "replayable");
  assert.equal(r.export.replay, "source_included_environment_required");
  assert.ok(r.export.included.includes("source_pdf"));
  const asset = r.assets.find((a) => a.id === r.document.source_asset_id);
  assert.equal(asset.purpose, "source_pdf");
  assert.equal(asset.media_type, "application/pdf");
  assert.equal(asset.sha256, F01_SHA256);
  assert.equal(asset.byte_length, F01.length);
  assert.equal(
    Buffer.from(asset.data_base64, "base64").compare(F01),
    0,
    "payload is the exact original bytes",
  );
  validate(r);
  importReport(serializeReportJson(r));

  // Mismatched bytes are rejected, never silently attached.
  const other = readFileSync(join(ROOT, "fixtures/public/mapping-control.pdf"));
  assert.equal(
    code(() => projectReport(source, { sourcePdf: other })),
    "SOURCE",
  );
  const tampered = Uint8Array.from(F01);
  tampered[100] ^= 0xff;
  assert.equal(
    code(() => projectReport(source, { sourcePdf: tampered })),
    "SOURCE",
  );

  // 'carry' with no usable source asset marks evidence-only (see the
  // missing-bytes criterion below), never a silent replayable.
  const replay = loadExample("native-replay.inkflip.json");
  const carried = projectReport(replay, { sourcePdf: "carry" });
  assert.equal(carried.report.export.mode, "replayable");
  assert.equal(
    carried.report.assets.find((a) => a.purpose === "source_pdf").sha256,
    replay.document.sha256,
  );

  // The HTML never embeds source bytes — no PDF data URL, no %PDF base64.
  const html = renderReportHtml(r);
  assert.ok(!html.includes("data:application/pdf"));
  assert.ok(!html.includes("JVBER")); // "%PDF" base64 prefix
  assert.ok(!html.includes("<embed") && !html.includes("<object"));
});

// ---------------------------------------------------------------------------
// Criterion: script-like strings escaped
// ---------------------------------------------------------------------------

const PAYLOADS = [
  "</title><script>alert(document.domain)</script>",
  "<img src=x onerror=alert(1)>",
  "<svg onload=alert(1)>",
  "javascript:alert(1)",
  '"><script>alert(1)</script><"',
  '<iframe src="https://evil.example"></iframe>',
  '<a href="javascript:alert(1)">click</a>',
  "<!--[if IE]><script>alert(1)</script><![endif]-->",
  '</pre><img src="data:image/svg+xml,<svg onload=alert(1)>">',
];

test("script-like report strings are inert in JSON and escaped in HTML", () => {
  const base = loadExample("native-evidence.inkflip.json");
  for (const [i, payload] of PAYLOADS.entries()) {
    const r = structuredClone(base);
    const slot = i % 4;
    if (slot === 0) r.findings[0].title = payload;
    if (slot === 1) r.findings[0].explanation = payload;
    if (slot === 2) r.readers[0].name = payload.slice(0, 100);
    if (slot === 3) {
      r.occurrences[0].raw_text = payload;
      const n = normalize(payload);
      r.occurrences[0].normalized_text = n.text;
      r.occurrences[0].normalization_map = n.map;
    }
    r.annotations.push({
      id: "n_hostile",
      finding_id: "f_amount",
      page_index: 0,
      text: payload.slice(0, 200),
      author_label: payload.slice(0, 50),
      origin: "human_entered",
    });
    seal(r);
    const { report } = projectReport(r, { annotations: true });
    const json = serializeReportJson(report);
    const decoded = decode(json);
    // JSON keeps the raw bytes — escaping is an HTML-view concern only.
    if (slot === 0) assert.equal(decoded.findings[0].title, payload);
    if (slot === 3) assert.equal(decoded.occurrences[0].raw_text, payload);
    assert.equal(decoded.annotations[0].text, payload.slice(0, 200));

    const html = renderReportHtml(report);
    assertScriptFreeHtml(html); // would throw on any active construct
    for (const tag of ["<script", "<svg", "<iframe", "<form", "<object", "<a "]) {
      assert.ok(!html.includes(tag), `${tag} leaked via ${payload}`);
    }
    if (escapeHtml(payload) !== payload) {
      assert.ok(!html.includes(payload), `raw payload leaked: ${payload}`);
    }
    if (slot === 0) {
      assert.ok(html.includes(escapeHtml(payload)), `escaped form missing for ${payload}`);
    }
    assert.ok(
      html.includes(escapeHtml(payload.slice(0, 200))) || !payload.slice(0, 200).includes("<"),
      `escaped annotation missing for ${payload}`,
    );
  }
});

test("exported HTML of every delivered example passes the script-free guard", () => {
  for (const name of [
    "native-evidence.inkflip.json",
    "native-replay.inkflip.json",
    "empty-completed.json",
    "cancelled.json",
    "failed.json",
    "repeated-occurrences.json",
  ]) {
    const { report } = projectReport(loadExample(name), {
      sourcePdf: name === "native-replay.inkflip.json" ? "carry" : null,
    });
    assert.doesNotThrow(() => assertScriptFreeHtml(renderReportHtml(report)), name);
  }
});

// ---------------------------------------------------------------------------
// Criterion: missing bytes marked evidence-only
// ---------------------------------------------------------------------------

test("missing or unverifiable asset bytes mark the export evidence-only", () => {
  const source = loadExample("native-evidence.inkflip.json");
  const broken = structuredClone(source);
  broken.assets[0].data_base64 = "AAAA"; // payload no longer matches hash
  const { report, notices } = projectReport(broken, {});
  assert.deepEqual(notices.missingAssetIds, ["a_crop"]);
  assert.equal(report.export.mode, "evidence");
  assert.equal(report.export.replay, "requires_original");
  assert.ok(
    report.export.omissions.some((o) => o.includes("bytes unavailable")),
    "omission marks the missing bytes",
  );
  // The reading survives; the missing raster link is nulled and disclosed.
  const o = report.occurrences.find((x) => x.id === "o_tess_amount");
  assert.equal(o.source_asset_id, null);
  assert.deepEqual(notices.unlinkedOccurrenceIds, ["o_tess_amount"]);
  assert.ok(!report.assets.some((a) => a.id === "a_crop"));
  validate(report);

  // Preview surfaces the evidence-only state.
  const preview = buildExportPreview(report, { notices });
  assert.ok(preview.warnings.some((w) => w.includes("evidence-only")));

  // A requested source opt-in without usable bytes cannot become replayable.
  const replay = structuredClone(loadExample("native-replay.inkflip.json"));
  replay.assets.find((a) => a.purpose === "source_pdf").data_base64 = "AA==";
  const { report: stillEvidence, notices: n2 } = projectReport(replay, {
    sourcePdf: "carry",
  });
  assert.notEqual(stillEvidence.export.mode, "replayable");
  assert.equal(stillEvidence.document.source_asset_id, null);
  assert.ok(n2.missingAssetIds.includes("a_source"));
});

// ---------------------------------------------------------------------------
// Criterion: export deterministic aside from excluded run timing fields
// ---------------------------------------------------------------------------

test("identical inputs give byte-identical JSON and HTML; timing fields are the only permitted delta", () => {
  const source = annotationModeReport();
  const a = projectReport(source, { annotations: true });
  const b = projectReport(structuredClone(source), { annotations: true });
  assert.equal(serializeReportJson(a.report), serializeReportJson(b.report));
  assert.equal(renderReportHtml(a.report), renderReportHtml(b.report));
  assert.equal(a.report.report_id, b.report.report_id);

  // Two runs differing only in run timing share one export identity.
  const c = structuredClone(source);
  c.execution.execution_id = "99999999-8888-4777-8666-555555555555";
  c.execution.started_at = "2020-01-01T00:00:00+00:00";
  c.execution.duration_ms = 99999;
  seal(c);
  const pa = projectReport(source, { annotations: true });
  const pc = projectReport(c, { annotations: true });
  assert.equal(pa.report.report_id, pc.report.report_id, "digest excludes timing");
  assert.equal(pa.report.execution.run_key, pc.report.execution.run_key);
  const ja = serializeReportJson(pa.report);
  const jc = serializeReportJson(pc.report);
  const stripTiming = (s) =>
    s
      .replace(c.execution.execution_id, "<EXEC>")
      .replace(c.execution.started_at, "<AT>")
      .replace(String(c.execution.duration_ms), "<MS>")
      .replace(source.execution.execution_id, "<EXEC>")
      .replace(source.execution.started_at, "<AT>")
      .replace(String(source.execution.duration_ms), "<MS>");
  assert.equal(stripTiming(ja), stripTiming(jc), "only timing fields differ");
  // HTML does not render run timing at all — fully identical.
  assert.equal(renderReportHtml(pa.report), renderReportHtml(pc.report));
});

test("canonical serialization is byte-stable under member reordering", () => {
  const source = loadExample("native-evidence.inkflip.json");
  const { report } = projectReport(source, {});
  const j1 = serializeReportJson(report);

  // Permutation 1: Reversing keys of every nested object.
  const reverseKeys = (v) => {
    if (Array.isArray(v)) return v.map(reverseKeys);
    if (v && typeof v === "object") {
      const out = {};
      const keys = Object.keys(v).reverse();
      for (const k of keys) out[k] = reverseKeys(v[k]);
      return out;
    }
    return v;
  };

  // Permutation 2: Interleaving keys (odd-indexed keys, then even-indexed keys).
  const interleaveKeys = (v) => {
    if (Array.isArray(v)) return v.map(interleaveKeys);
    if (v && typeof v === "object") {
      const keys = Object.keys(v);
      const evens = keys.filter((_, i) => i % 2 === 0);
      const odds = keys.filter((_, i) => i % 2 === 1);
      const out = {};
      for (const k of [...odds, ...evens]) out[k] = interleaveKeys(v[k]);
      return out;
    }
    return v;
  };

  // Permutation 3: Alphabetical sort of keys.
  const sortKeys = (v) => {
    if (Array.isArray(v)) return v.map(sortKeys);
    if (v && typeof v === "object") {
      const out = {};
      for (const k of Object.keys(v).sort()) out[k] = sortKeys(v[k]);
      return out;
    }
    return v;
  };

  // Permutation 4: Cyclic shift of keys by 1.
  const rotateKeys = (v) => {
    if (Array.isArray(v)) return v.map(rotateKeys);
    if (v && typeof v === "object") {
      const keys = Object.keys(v);
      const rotated = keys.length > 1 ? [...keys.slice(1), keys[0]] : keys;
      const out = {};
      for (const k of rotated) out[k] = rotateKeys(v[k]);
      return out;
    }
    return v;
  };

  const reversed = reverseKeys(structuredClone(report));
  const interleaved = interleaveKeys(structuredClone(report));
  const sorted = sortKeys(structuredClone(report));
  const rotated = rotateKeys(structuredClone(report));

  // Assert that permutations genuinely reordered object keys (not vacuous).
  const rawJson = JSON.stringify(report);
  assert.notEqual(JSON.stringify(reversed), rawJson, "reverseKeys changed object insertion order");
  assert.notEqual(JSON.stringify(interleaved), rawJson, "interleaveKeys changed object insertion order");
  assert.notEqual(JSON.stringify(rotated), rawJson, "rotateKeys changed object insertion order");

  // Every deterministic permutation must serialize to byte-identical canonical JSON.
  assert.equal(serializeReportJson(reversed), j1, "reverseKeys byte-stable");
  assert.equal(serializeReportJson(interleaved), j1, "interleaveKeys byte-stable");
  assert.equal(serializeReportJson(sorted), j1, "sortKeys byte-stable");
  assert.equal(serializeReportJson(rotated), j1, "rotateKeys byte-stable");
});

// ---------------------------------------------------------------------------
// Foundation guarantees behind the criteria
// ---------------------------------------------------------------------------

test("crops are default-on but a reading's source crop is never orphaned", () => {
  const source = loadExample("native-evidence.inkflip.json");
  // crops 'none' cannot drop the crop o_tess_amount was read from.
  const { report, notices } = projectReport(source, { crops: "none" });
  assert.deepEqual(notices.requiredContextAssetIds, ["a_crop"]);
  assert.ok(report.assets.some((a) => a.id === "a_crop"));
  assert.ok(report.export.included.includes("crops"));
  validate(report);
});

test("screenshot-only diagnostic profile carries no readings", () => {
  const source = loadExample("native-evidence.inkflip.json");
  const { report, notices } = projectReport(source, { occurrences: "none" });
  assert.equal(report.export.mode, "diagnostic");
  assert.equal(report.export.replay, "not_replayable");
  assert.equal(report.occurrences.length, 0);
  assert.ok(notices.omittedFindingIds.includes("f_amount"));
  assert.ok(report.export.omissions.some((o) => o.includes("finding(s) omitted")));
  validate(report);
});

test("filename and notes stay off by default and honor opt-in", () => {
  const source = annotationModeReport();
  const named = structuredClone(source);
  named.document.display_name = "statement <b>2026</b>.pdf";
  seal(named);
  const def = projectReport(named, {});
  assert.equal(def.report.document.display_name, null);
  assert.equal(def.report.annotations.length, 0);
  assert.ok(!def.report.export.included.includes("filename"));
  assert.ok(!def.report.export.included.includes("annotations"));
  const opt = projectReport(named, { filename: true, annotations: true });
  assert.equal(opt.report.document.display_name, "statement <b>2026</b>.pdf");
  assert.equal(opt.report.annotations.length, 1);
  assert.ok(opt.report.export.included.includes("filename"));
  assert.ok(opt.report.export.included.includes("annotations"));
  const html = renderReportHtml(opt.report);
  assert.ok(!html.includes("statement <b>2026</b>.pdf"));
  assert.ok(html.includes("statement &lt;b&gt;2026&lt;/b&gt;.pdf"));
  validate(opt.report);
});

test("embedded crops are sanitized re-encodes, never the stored bytes", () => {
  const r = structuredClone(loadExample("native-evidence.inkflip.json"));
  // Give the crop a hostile ancillary chunk; the export must re-encode.
  const tEXt = new TextEncoder().encode("evil\u0000<script>alert(1)</script>");
  const png = makePng({
    width: 4,
    height: 4,
    colorType: 6,
    bitDepth: 8,
    pixelRows: rowsFor(patternRgba(4, 4), 4, 4, 6, 8),
    preIdat: [{ type: "tEXt", data: tEXt }],
  });
  const a = r.assets[0];
  a.sha256 = createHash("sha256").update(png).digest("hex");
  a.byte_length = png.length;
  a.pixel_size = [4, 4];
  a.data_base64 = Buffer.from(png).toString("base64");
  seal(r);
  const { report } = projectReport(r, {});
  const html = renderReportHtml(report);
  assertScriptFreeHtml(html);
  // The stored payload (with its hostile chunk) is not what was embedded.
  const embedded = /src="data:image\/png;base64,([A-Za-z0-9+/=]+)"/.exec(html);
  assert.ok(embedded, "embedded PNG data URL present");
  const clean = sanitizePng(new Uint8Array(png));
  assert.equal(embedded[1], Buffer.from(clean.png).toString("base64"));
  assert.notEqual(embedded[1], a.data_base64);
  assert.ok(!html.includes("<script"));
});

test("export filenames derive from report identity, never user data", () => {
  const { report } = projectReport(loadExample("native-evidence.inkflip.json"), {});
  const j = exportFileName(report, "json");
  const h = exportFileName(report, "html");
  assert.match(j, /^inkflip-evidence-[a-f0-9]{12}\.inkflip\.json$/);
  assert.match(h, /^inkflip-evidence-[a-f0-9]{12}\.html$/);
});

test("selection refusing an unknown id fails closed", () => {
  const source = loadExample("native-evidence.inkflip.json");
  assert.equal(
    code(() => projectReport(source, { findings: ["f_nope"] })),
    "SELECTION",
  );
  assert.equal(
    code(() => projectReport(source, { occurrences: ["o_nope"] })),
    "SELECTION",
  );
  assert.equal(
    code(() => projectReport(source, { crops: ["a_nope"] })),
    "SELECTION",
  );
});

test("omissions disclose excluded crops and explicitly deselected findings (F2)", () => {
  const source = loadExample("native-evidence.inkflip.json");

  // When crops='none' and occurrences='none', the crop is dropped and disclosed in omissions.
  const { report: noCrops, notices: n1 } = projectReport(source, {
    crops: "none",
    occurrences: "none",
  });
  assert.equal(noCrops.assets.filter((a) => a.purpose === "crop").length, 0);
  assert.ok(
    noCrops.export.omissions.includes("Crops excluded."),
    "omissions must include 'Crops excluded.' line",
  );
  validate(noCrops);

  // When findings are explicitly deselected (e.g. findings=[]), disclose accurately.
  const { report: noFindings, notices: n2 } = projectReport(source, {
    findings: [],
  });
  assert.equal(noFindings.findings.length, 0);
  assert.deepEqual(n2.deselectedFindingIds, ["f_amount"]);
  assert.ok(
    noFindings.export.omissions.some((o) => o.includes("1 finding(s) excluded by selection.")),
    "omissions must include deselected finding line",
  );
  validate(noFindings);
});

test("preview limit reporting honestly enforces PNG pixel, edge, and asset limits (F4)", () => {
  const source = loadExample("native-evidence.inkflip.json");
  const { report } = projectReport(source, {});

  // Normal preview is within limits
  const pOk = buildExportPreview(report);
  assert.equal(pOk.withinLimits, true);

  // Modify asset pixel_size to exceed maxPngPixels (4,000,000)
  const overPixels = structuredClone(report);
  overPixels.assets[0].pixel_size = [2500, 2000]; // 5,000,000 pixels > 4,000,000
  const pPixels = buildExportPreview(overPixels);
  assert.equal(pPixels.withinLimits, false);
  assert.ok(
    pPixels.warnings.some((w) => w.includes("exceeds PNG pixel limit")),
    "preview must warn about exceeded PNG pixel cap",
  );

  // Modify asset pixel_size to exceed maxPngEdge (8192)
  const overEdge = structuredClone(report);
  overEdge.assets[0].pixel_size = [8500, 100];
  const pEdge = buildExportPreview(overEdge);
  assert.equal(pEdge.withinLimits, false);
  assert.ok(
    pEdge.warnings.some((w) => w.includes("exceeds PNG dimension edge limit")),
    "preview must warn about exceeded PNG edge cap",
  );
});

test("source requested but unavailable is distinguished from source not requested (F8)", () => {
  const source = loadExample("native-evidence.inkflip.json");

  // Not requested: sourcePdf is null (default)
  const { report: notReq, notices: nNotReq } = projectReport(source, { sourcePdf: null });
  assert.equal(nNotReq.requestedSourceMissing, false);
  assert.ok(notReq.export.omissions.includes("Original PDF excluded."));
  assert.ok(
    !notReq.export.omissions.includes("Requested original bytes unavailable — evidence only."),
  );

  // Requested but unavailable: sourcePdf is 'carry' but report has no source_pdf asset
  const { report: reqMissing, notices: nReqMissing } = projectReport(source, { sourcePdf: "carry" });
  assert.equal(nReqMissing.requestedSourceMissing, true);
  assert.ok(reqMissing.export.omissions.includes("Original PDF excluded."));
  assert.ok(
    reqMissing.export.omissions.includes("Requested original bytes unavailable — evidence only."),
  );
  assert.equal(reqMissing.export.mode, "evidence");
});

test("oversized source inclusion fails with understandable explanation and evidence-only advice (F9)", () => {
  const source = loadExample("native-evidence.inkflip.json");
  const oversizedLength = 20 * 1024 * 1024 + 1; // 20 MiB + 1 byte
  const fakeBytes = new Uint8Array(oversizedLength);
  const fakeSha = createHash("sha256").update(fakeBytes).digest("hex");

  const oversizedDoc = structuredClone(source);
  oversizedDoc.document.byte_length = oversizedLength;
  oversizedDoc.document.sha256 = fakeSha;
  seal(oversizedDoc);

  let caughtErr = null;
  try {
    projectReport(oversizedDoc, { sourcePdf: fakeBytes });
  } catch (err) {
    caughtErr = err;
  }
  assert.ok(caughtErr instanceof ContractError);
  assert.equal(caughtErr.code, "SIZE");
  assert.match(caughtErr.message, /exceeds the 20971520 byte embed limit/);
  assert.match(caughtErr.message, /evidence-only/);

  // Deselecting sourcePdf (sourcePdf: null) allows export of evidence-only bundle
  const { report: evidenceOnly } = projectReport(oversizedDoc, { sourcePdf: null });
  assert.equal(evidenceOnly.document.source_asset_id, null);
  assert.equal(evidenceOnly.export.mode, "evidence");
  validate(evidenceOnly);
});
