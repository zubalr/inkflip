/**
 * Deterministic `.inkflip.json` serialization.
 *
 * `JSON.stringify` preserves object insertion order, so two semantically
 * identical reports whose members were assembled differently serialize
 * differently. The portable export is a *canonical* byte stream: every
 * contract object is re-emitted in the schema-declared member order via
 * the explicit tables below (the schema is closed — no unknown member can
 * appear in a validated report), arrays keep their stored order and
 * numbers keep `JSON.stringify`'s shortest round-trip form.
 *
 * Byte-stability rule: identical report values produce byte-identical
 * output. `execution.execution_id`/`started_at`/`duration_ms` and
 * `report_id` are the only run-timing/identity fields, and they are
 * excluded from the canonical digest (`reportDigest` in
 * `@inkflip/contracts`) — so exports of runs that differ only in timing
 * still share one evidence identity while remaining honest records of the
 * actual recorded run.
 */
import { ContractError } from "../../contracts/src/index.ts";
import type { Report } from "../../contracts/src/index.ts";

/** Schema-declared member order for every object shape inside a Report. */
const MEMBER_ORDER: Record<string, readonly string[]> = {
  Report: [
    "kind",
    "schema_version",
    "report_id",
    "document",
    "readers",
    "pages",
    "transforms",
    "occurrences",
    "findings",
    "annotations",
    "plan",
    "checks",
    "execution",
    "export",
    "assets",
    "limitations",
  ],
  Document: ["sha256", "byte_length", "page_count", "display_name", "source_asset_id"],
  Reader: [
    "id",
    "name",
    "version",
    "build",
    "adapter_version",
    "method",
    "environment",
    "settings",
    "capabilities",
    "model_hashes",
    "limitations",
  ],
  ReaderSettings: [
    "normalization",
    "language",
    "psm",
    "render_reader_id",
    "raster_dpi",
    "annotation_mode",
  ],
  Capability: ["name", "support", "limits"],
  Page: [
    "index",
    "media_box",
    "crop_box",
    "effective_view_box",
    "box_source",
    "user_unit",
    "rotation",
    "canonical_size_pt",
    "raw_to_canonical_transform_id",
    "limitations",
  ],
  Transform: [
    "id",
    "page_index",
    "from_space",
    "to_space",
    "matrix",
    "inverse",
    "operation",
    "precision",
    "source",
  ],
  Geometry: ["precision", "space", "polygon", "transform_ids", "basis"],
  Occurrence: [
    "id",
    "reader_id",
    "page_index",
    "ordinal",
    "raw_text",
    "normalized_text",
    "normalization_map",
    "geometry",
    "engine_score",
    "source_asset_id",
    "raw_source_locator",
    "limitations",
  ],
  RawMap: ["raw_start", "raw_end", "normalized_start", "normalized_end", "operation"],
  EngineScore: ["value", "scale_min", "scale_max", "meaning"],
  Region: ["id", "page_index", "geometry", "label"],
  Finding: [
    "id",
    "kind",
    "title",
    "explanation",
    "page_index",
    "occurrence_ids",
    "check_ids",
    "alignment",
    "region_id",
    "priority",
    "basis",
    "limitations",
  ],
  Annotation: ["id", "finding_id", "page_index", "text", "author_label", "origin"],
  CheckPlan: ["id", "page_index", "reader_ids", "capability", "region_id"],
  Plan: [
    "version",
    "selected_pages",
    "regions",
    "checks",
    "normalization_version",
    "alignment_version",
    "profile",
    "budget",
  ],
  Budget: ["max_raster_pixels", "max_run_ocr_pixels", "timeout_ms", "max_retries"],
  CheckResult: ["id", "status", "reason", "produced_occurrence_count", "retained_occurrence_ids"],
  Execution: [
    "execution_id",
    "run_key",
    "status",
    "started_at",
    "duration_ms",
    "environment",
    "result_origin",
    "errors",
  ],
  Export: ["mode", "scope", "included", "omissions", "replay", "origin_report_id"],
  Asset: [
    "id",
    "media_type",
    "sha256",
    "byte_length",
    "purpose",
    "data_base64",
    "pixel_size",
    "page_index",
    "geometry",
  ],
};

/** Member containers nested inside each schema def. */
const CHILD_DEF: Record<string, Record<string, string>> = {
  Report: {
    document: "Document",
    readers: "Reader",
    pages: "Page",
    transforms: "Transform",
    occurrences: "Occurrence",
    findings: "Finding",
    annotations: "Annotation",
    plan: "Plan",
    checks: "CheckResult",
    execution: "Execution",
    export: "Export",
    assets: "Asset",
  },
  Reader: { settings: "ReaderSettings", capabilities: "Capability" },
  Page: {},
  Occurrence: {
    normalization_map: "RawMap",
    geometry: "Geometry",
    engine_score: "EngineScore",
  },
  Finding: {},
  Annotation: {},
  Plan: { regions: "Region", checks: "CheckPlan", budget: "Budget" },
  Region: { geometry: "Geometry" },
  CheckPlan: {},
  Asset: { geometry: "Geometry" },
  Document: {},
  CheckResult: {},
  Execution: {},
  Export: {},
  Transform: {},
  Geometry: {},
  ReaderSettings: {},
  Capability: {},
  RawMap: {},
  EngineScore: {},
  Budget: {},
};

function orderMembers(value: unknown, def: string): unknown {
  if (value === null || typeof value !== "object") return value;
  if (Array.isArray(value)) {
    return value.map((item) => orderMembers(item, def));
  }
  const record = value as Record<string, unknown>;
  const order = MEMBER_ORDER[def];
  const out: Record<string, unknown> = {};
  const childDef = CHILD_DEF[def] ?? {};
  if (order !== undefined) {
    for (const key of order) {
      if (Object.prototype.hasOwnProperty.call(record, key)) {
        const member = record[key];
        const child = childDef[key];
        out[key] = child !== undefined ? orderMembers(member, child) : member;
      }
    }
    // A validated report cannot hold members outside this table; keep the
    // serializer total by appending leftovers deterministically anyway.
    for (const key of Object.keys(record).sort()) {
      if (!Object.prototype.hasOwnProperty.call(out, key)) {
        out[key] = record[key];
      }
    }
    return out;
  }
  for (const key of Object.keys(record).sort()) {
    out[key] = record[key];
  }
  return out;
}

/**
 * Canonical `.inkflip.json` text: schema-ordered members, two-space indent,
 * UTF-8 (no ASCII escaping) and a trailing LF. Deterministic for identical
 * report values; array order is part of the evidence and preserved.
 */
export function serializeReportJson(report: Report): string {
  const ordered = orderMembers(report, "Report");
  return JSON.stringify(ordered, null, 2) + "\n";
}

/** Serialized UTF-8 bytes of the canonical JSON text. */
export function reportJsonBytes(report: Report): Uint8Array {
  return new TextEncoder().encode(serializeReportJson(report));
}

const B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/** Standards-base64 encode; padded, no line breaks. */
export function encodeBase64(data: Uint8Array): string {
  let out = "";
  for (let i = 0; i < data.length; i += 3) {
    const b0 = data[i]!;
    const b1 = i + 1 < data.length ? data[i + 1]! : 0;
    const b2 = i + 2 < data.length ? data[i + 2]! : 0;
    const n = (b0 << 16) | (b1 << 8) | b2;
    out += B64_ALPHABET[(n >> 18) & 63];
    out += B64_ALPHABET[(n >> 12) & 63];
    out += i + 1 < data.length ? B64_ALPHABET[(n >> 6) & 63] : "=";
    out += i + 2 < data.length ? B64_ALPHABET[n & 63] : "=";
  }
  return out;
}

/**
 * Safe download name for an export artifact: fixed prefix plus the short
 * report identity — never the original filename or document text.
 */
export function exportFileName(report: Report, format: "json" | "html"): string {
  if (!/^[a-f0-9]{64}$/.test(report.report_id)) {
    throw new ContractError("ID", "Export requires a sealed report id");
  }
  const base = `inkflip-${report.export.mode}-${report.report_id.slice(0, 12)}`;
  return format === "json" ? `${base}.inkflip.json` : `${base}.html`;
}
