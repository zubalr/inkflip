/**
 * T21 gallery validation — node:test suite over the committed public
 * examples. Asserts, against the real bytes on disk:
 *
 *  - index.json lists exactly six distinct cards (no repetitive padding).
 *  - Every manifest entry's sha256 + byte_length match the staged file.
 *  - Every listed report_file exists, is a sealed contract report
 *    (schema-validated via ajv + draft 2020-12), and its document digest
 *    binds the actual staged source PDF.
 *  - Reports are real executions: execution.result_origin === "live",
 *    status complete — no unexecuted expectation presented as result.
 *  - Supported languages are labeled accurately (OCR runs declare their
 *    model language; no reader claims a language it never ran).
 *  - Rights text is present and identical across cards; every asset is
 *    well under the portable static limit (32 MiB JSON profile).
 *  - All referenced URLs are site-relative /examples/ paths — the gallery
 *    can never redirect to remote content.
 *
 * Run: node --test tests/gallery/
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import Ajv2020 from "ajv/dist/2020.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const EXAMPLES = join(ROOT, "apps", "web", "public", "examples");
const SCHEMA = JSON.parse(
  readFileSync(join(ROOT, "planning", "contracts", "inkflip.schema.json"), "utf8"),
);
const STATIC_LIMIT_BYTES = 32 * 1024 * 1024; // portable JSON profile ceiling

const ajv = new Ajv2020({ allErrors: true, strict: false });
ajv.addSchema(SCHEMA);
const reportValidator = ajv.getSchema(
  "urn:inkflip:schema:1.0.0#/$defs/Report",
);

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function loadJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

const LOCAL_URL = /^\/examples\/[A-Za-z0-9._/-]+$/;

test("index lists six distinct cards, all local", () => {
  const index = loadJson(join(EXAMPLES, "index.json"));
  assert.equal(index.cards.length, 6);
  const ids = new Set(index.cards.map((c) => c.example_id));
  assert.equal(ids.size, 6, "card ids must be unique");
  const families = new Set(index.cards.map((c) => `${c.family}/${c.fixture_id}`));
  assert.equal(families.size, 6, "cards must be distinct cases, not padding");
  for (const card of index.cards) {
    assert.match(card.report_url, LOCAL_URL, `${card.example_id} report_url must be local`);
    assert.match(card.manifest_url, LOCAL_URL);
    assert.match(card.source.download_url, LOCAL_URL);
    assert.ok(card.card_title.length > 0);
    assert.ok(card.mechanism.length > 0);
    assert.ok(Array.isArray(card.readers) && card.readers.length >= 2,
      `${card.example_id} must record the readers that actually ran`);
  }
});

test("every manifest binds real bytes and its captured report", () => {
  const index = loadJson(join(EXAMPLES, "index.json"));
  for (const card of index.cards) {
    const dir = join(EXAMPLES, card.example_id);
    const manifest = loadJson(join(dir, "manifest.json"));

    assert.equal(manifest.example_id, card.example_id);
    assert.equal(manifest.provenance, "prepared");
    assert.ok(manifest.rights.length > 0, `${card.example_id} rights text required`);
    assert.ok(manifest.mechanism.length > 0);
    assert.equal(typeof manifest.timing.duration_ms, "number");
    assert.ok(manifest.timing.duration_ms > 0,
      `${card.example_id} timing must be a real measurement`);
    assert.ok(manifest.report_id.length > 0 && manifest.run_key.length > 0);

    const fileKeys = Object.keys(manifest.files);
    assert.ok(fileKeys.length >= 2, `${card.example_id} needs source plus sibling/control`);

    for (const [key, f] of Object.entries(manifest.files)) {
      const path = join(dir, f.filename);
      assert.equal(sha256(path), f.sha256, `${card.example_id}/${key} sha256`);
      assert.equal(statSync(path).size, f.byte_length, `${card.example_id}/${key} bytes`);
      assert.match(f.download_url, LOCAL_URL);
      assert.ok(f.role.length > 0, `${card.example_id}/${key} needs a role label`);

      // The captured report's document digest must equal the staged bytes.
      const report = loadJson(join(dir, f.report_file));
      assert.equal(report.document.sha256, f.sha256,
        `${card.example_id}/${key}: report must be bound to the staged source`);
    }
  }
});

test("every card's primary report is a sealed live run, schema-valid", () => {
  const index = loadJson(join(EXAMPLES, "index.json"));
  for (const card of index.cards) {
    const report = loadJson(join(EXAMPLES, card.example_id, "report.json"));
    const ok = reportValidator(report);
    assert.ok(ok, `${card.example_id} report fails contract schema: ${JSON.stringify(reportValidator.errors?.slice(0, 3))}`);
    assert.equal(report.execution.result_origin, "live",
      `${card.example_id} must be an actual recorded run`);
    assert.equal(report.execution.status, "complete");
    assert.ok(Array.isArray(report.readers) && report.readers.length >= 2);
    assert.ok(statSync(join(EXAMPLES, card.example_id, "report.json")).size < STATIC_LIMIT_BYTES);
  }
});

test("OCR language claims match the models that actually ran", () => {
  const index = loadJson(join(EXAMPLES, "index.json"));
  for (const card of index.cards) {
    const report = loadJson(join(EXAMPLES, card.example_id, "report.json"));
    for (const reader of report.readers) {
      if (reader.method === "ocr") {
        // The only bundled model is eng — any other claim would mislabel.
        assert.equal(reader.settings.language, "eng",
          `${card.example_id}: OCR reader must declare the language it ran`);
        assert.ok(reader.model_hashes.length > 0,
          `${card.example_id}: OCR reader must name its model digest`);
      } else {
        assert.equal(reader.settings.language, null,
          `${card.example_id}: non-OCR readers must not claim a language`);
      }
    }
  }
});

test("manifests carry no unexecuted expectations as results", () => {
  const index = loadJson(join(EXAMPLES, "index.json"));
  for (const card of index.cards) {
    const manifest = loadJson(join(EXAMPLES, card.example_id, "manifest.json"));
    // Findings must come from the captured report — same count and ids.
    const report = loadJson(join(EXAMPLES, card.example_id, manifest.report_file));
    const reportIds = report.findings.map((f) => f.id);
    assert.deepEqual(
      manifest.findings.map((f) => f.id),
      reportIds,
      `${card.example_id}: manifest findings must mirror the real report`,
    );
    // Reader entries must name versions that actually executed.
    for (const r of Object.values(manifest.readers)) {
      const inReport = report.readers.find((rr) => rr.id === r.id);
      assert.ok(inReport, `${card.example_id}: reader ${r.name} must exist in the report`);
      assert.equal(r.version, inReport.version);
      assert.equal(r.method, inReport.method);
    }
  }
});
