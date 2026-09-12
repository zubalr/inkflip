/**
 * Selection projection for portable evidence export (I09).
 *
 * `projectReport` derives a new contract-valid `Report` from a recorded run
 * report and an explicit inclusion request. It never invents data: retained
 * occurrences keep raw text, normalization maps, geometry and scores; check
 * results keep their original `produced_occurrence_count` while
 * `retained_occurrence_ids` is pruned to the kept set; check plans, page
 * scope, budgets and reader identity are preserved whole.
 *
 * Inclusion allowlist (defaults follow REPORT_EXPORT_IMPORT.md):
 *   on  — selected_text (retained occurrences), crops, document_hash,
 *         settings, coverage.
 *   off — source_pdf, filename, annotations, page_renders. Each requires an
 *         explicit opt-in; `sourcePdf` must carry the actual original bytes
 *         (or `'carry'` an already-embedded source asset), which are
 *         hash/length-bound to the document before inclusion.
 *
 * Context required to understand kept evidence is kept: selected findings
 * pull in every occurrence they cite, and crops that produced a retained
 * reading are never orphaned (the occurrence's `source_asset_id` must
 * resolve). Those required retentions are reported through
 * {@link ProjectionNotices} so the preview can disclose them.
 *
 * Missing bytes stay missing (I11): an asset whose payload fails decode or
 * hash verification is dropped, the omission is recorded and the export is
 * marked evidence-only — it never upgrades to `replayable`.
 */
import {
  ContractError,
  reportDigest,
  runKey,
  seal,
  sha256,
  validate,
} from "../../contracts/src/index.ts";
import type { Asset, CheckResult, Finding, Report } from "../../contracts/src/index.ts";
import { decodeBase64 } from "../validation/assets.ts";
import { encodeBase64 } from "./serialize.ts";

function fail(code: string, message: string): never {
  throw new ContractError(code, message);
}

const ZERO64 = "0".repeat(64);
const HEX64 = /^[a-f0-9]{64}$/;

function toHex(data: Uint8Array): string {
  let s = "";
  for (const b of data) s += b.toString(16).padStart(2, "0");
  return s;
}

/** How much of the run's recorded findings to retain. */
export type FindingSelection = "all" | readonly string[];
/**
 * Which occurrences to retain. `'all'` keeps every produced occurrence,
 * `'cited'` keeps only occurrences cited by retained findings (plus their
 * required context), `'none'` keeps none (screenshot-only diagnostic
 * profile), and an explicit list retains exactly those ids — in every case
 * occurrences cited by retained findings are unioned in, because a finding
 * may never be exported while silently dropping the reading it asserts.
 */
export type OccurrenceSelection = "all" | "cited" | "none" | readonly string[];
/** Asset selection by purpose: `'all'`, `'none'` or explicit asset ids. */
export type AssetSelection = "all" | "none" | readonly string[];

/**
 * Inclusion request for one export. Anything not listed defaults to the
 * privacy-preserving profile: source PDF, filename, notes and page renders
 * stay out.
 */
export interface ExportRequest {
  /** `selection` (default) or `run` — the recorded export.scope. */
  readonly scope?: "selection" | "run";
  /** Findings to carry; default `'all'`. */
  readonly findings?: FindingSelection;
  /** Occurrences to carry; default `'cited'` for selection, `'all'` for run. */
  readonly occurrences?: OccurrenceSelection;
  /** Crop assets to carry; default `'all'` on retained pages. */
  readonly crops?: AssetSelection;
  /** Page-render assets to carry; default `'none'` (explicit opt-in). */
  readonly pageRenders?: AssetSelection;
  /** Human-entered annotations; default `false` (off). */
  readonly annotations?: boolean;
  /** Original filename; default `false` (off). */
  readonly filename?: boolean;
  /**
   * Explicit source-PDF opt-in: the original bytes themselves, or `'carry'`
   * to retain a source_pdf asset already embedded in the source report.
   * Bytes are verified against `document.sha256`/`byte_length` before
   * inclusion — mismatched bytes are rejected, never silently attached.
   */
  readonly sourcePdf?: Uint8Array | "carry" | null;
}

/** Facts the preview discloses about what the projection did. */
export interface ProjectionNotices {
  /** Occurrence ids dropped by the selection (produced minus retained). */
  readonly omittedOccurrenceCount: number;
  /** Findings dropped because the selection cannot support them. */
  readonly omittedFindingIds: readonly string[];
  /** Asset ids dropped because their bytes were missing or did not verify. */
  readonly missingAssetIds: readonly string[];
  /**
   * Asset ids retained only because retained occurrences were read from
   * them (required context) even though the request excluded that category.
   */
  readonly requiredContextAssetIds: readonly string[];
  /** Occurrence ids whose raster reference was missing; link nulled+noted. */
  readonly unlinkedOccurrenceIds: readonly string[];
  /**
   * Source opt-in was requested but no usable original bytes existed —
   * the export is marked evidence-only, never replayable.
   */
  readonly requestedSourceMissing: boolean;
  /** Human-readable omission lines recorded in export.omissions. */
  readonly omissions: readonly string[];
}

export interface ProjectionResult {
  /** The new sealed report. Its `report_id` is a fresh canonical digest. */
  readonly report: Report;
  readonly notices: ProjectionNotices;
}

interface IdSet {
  readonly all: boolean;
  readonly ids: ReadonlySet<string>;
}

function resolveIds(
  selection: "all" | "none" | readonly string[],
  known: ReadonlySet<string>,
  what: string,
): IdSet {
  if (selection === "all") return { all: true, ids: known };
  if (selection === "none") return { all: false, ids: new Set() };
  const ids = new Set<string>();
  for (const id of selection) {
    if (!known.has(id)) fail("SELECTION", `Unknown ${what} id ${id}`);
    ids.add(id);
  }
  return { all: false, ids };
}

/** Decode + re-hash an asset payload; `null` means the bytes are missing. */
function usablePayload(asset: Asset): Uint8Array | null {
  try {
    const data = decodeBase64(asset.data_base64);
    if (data.length !== asset.byte_length) return null;
    if (toHex(sha256(data)) !== asset.sha256) return null;
    return data;
  } catch {
    return null;
  }
}

/**
 * Derive the export disclosure block from the *projected* content — never
 * from the request — so `export.included` always matches actual bytes (I09).
 */
function disclosure(
  report: Report,
  mode: "evidence" | "replayable" | "diagnostic",
  scope: "selection" | "run",
  replay: Report["export"]["replay"],
  originReportId: string | null,
  omissions: readonly string[],
): Report["export"] {
  const included: Report["export"]["included"] = [];
  const hasPurpose = (p: Asset["purpose"]) => report.assets.some((a) => a.purpose === p);
  if (report.occurrences.length > 0) included.push("selected_text");
  if (hasPurpose("crop")) included.push("crops");
  if (hasPurpose("page_render")) included.push("page_renders");
  included.push("document_hash", "settings", "coverage");
  if (report.annotations.length > 0) included.push("annotations");
  if (report.document.display_name !== null) included.push("filename");
  if (hasPurpose("source_pdf")) included.push("source_pdf");
  return {
    mode,
    scope,
    included,
    omissions: [...omissions],
    replay,
    origin_report_id: originReportId,
  };
}

/**
 * Project `source` into a new sealed export report.
 *
 * The source must be a structurally valid report; when it is sealed its
 * identity becomes `origin_report_id`. The projection is re-sealed
 * (`run_key` is recomputed — identical whenever document/readers/plan are
 * preserved — and `report_id` becomes a fresh digest over the projection)
 * and fully re-validated before it is returned.
 */
export function projectReport(source: Report, request: ExportRequest = {}): ProjectionResult {
  if (typeof source !== "object" || source === null || source.kind !== "report") {
    fail("KIND", "Export projects report artifacts only");
  }
  const src = structuredClone(source);
  const scope = request.scope ?? "selection";
  const omissions: string[] = [];

  // --- asset payload audit: missing/unverifiable bytes stay missing (I11)
  const payloadById = new Map<string, Uint8Array>();
  const missingAssetIds: string[] = [];
  for (const asset of src.assets) {
    const data = usablePayload(asset);
    if (data === null) {
      missingAssetIds.push(asset.id);
      continue;
    }
    payloadById.set(asset.id, data);
  }

  // --- document / source opt-in ------------------------------------------
  const doc = src.document;
  let sourceAsset: Asset | null = null;
  let requestedSourceMissing = false;
  if (request.sourcePdf === "carry") {
    const existing = src.assets.find((a) => a.purpose === "source_pdf" && payloadById.has(a.id));
    if (existing === undefined) {
      // Explicit opt-in cannot be satisfied: the missing bytes mark the
      // export evidence-only rather than blocking unrelated evidence (I11).
      requestedSourceMissing = true;
    } else {
      sourceAsset = existing;
    }
  } else if (request.sourcePdf instanceof Uint8Array) {
    const bytes = request.sourcePdf;
    if (bytes.length !== doc.byte_length || toHex(sha256(bytes)) !== doc.sha256) {
      fail(
        "SOURCE",
        "Supplied bytes do not match the document hash/length — never attach mismatched originals",
      );
    }
    sourceAsset = {
      id: "a_source",
      media_type: "application/pdf",
      sha256: doc.sha256,
      byte_length: doc.byte_length,
      purpose: "source_pdf",
      data_base64: encodeBase64(bytes),
      pixel_size: null,
      page_index: null,
      geometry: null,
    };
  } else if (request.sourcePdf !== undefined && request.sourcePdf !== null) {
    fail("TYPE", 'sourcePdf must be Uint8Array, "carry" or null');
  }
  if (sourceAsset !== null) {
    if (
      sourceAsset.media_type !== "application/pdf" ||
      sourceAsset.sha256 !== doc.sha256 ||
      sourceAsset.byte_length !== doc.byte_length
    ) {
      fail("SOURCE", "Source asset is not bound to the document");
    }
    doc.source_asset_id = sourceAsset.id;
  } else {
    doc.source_asset_id = null;
    omissions.push("Original PDF excluded.");
    if (requestedSourceMissing) {
      omissions.push("Requested original bytes unavailable — evidence only.");
    }
  }

  doc.display_name = request.filename === true ? doc.display_name : null;
  if (doc.display_name === null) omissions.push("Filename excluded.");

  // --- findings and occurrences ------------------------------------------
  const knownFindings = new Map(src.findings.map((f) => [f.id, f]));
  const findingSel = resolveIds(
    request.findings ?? "all",
    new Set(knownFindings.keys()),
    "finding",
  );
  const keptFindings = src.findings.filter((f) => findingSel.all || findingSel.ids.has(f.id));

  const knownOccurrences = new Map(src.occurrences.map((o) => [o.id, o]));
  const occRequest = request.occurrences ?? (scope === "run" ? "all" : "cited");
  let wantedOccurrenceIds: Set<string>;
  if (occRequest === "all") {
    wantedOccurrenceIds = new Set(knownOccurrences.keys());
  } else if (occRequest === "none") {
    wantedOccurrenceIds = new Set();
  } else if (occRequest === "cited") {
    wantedOccurrenceIds = new Set();
    for (const f of keptFindings) {
      for (const oid of f.occurrence_ids) wantedOccurrenceIds.add(oid);
    }
  } else {
    wantedOccurrenceIds = new Set(
      resolveIds(occRequest, new Set(knownOccurrences.keys()), "occurrence").ids,
    );
    // Required context: a finding can never export while silently omitting
    // a reading it asserts.
    for (const f of keptFindings) {
      for (const oid of f.occurrence_ids) wantedOccurrenceIds.add(oid);
    }
  }
  const keptOccurrences = src.occurrences.filter((o) => wantedOccurrenceIds.has(o.id));
  const keptOccurrenceIds = new Set(keptOccurrences.map((o) => o.id));

  // Findings the retained set cannot support stay out and are disclosed —
  // no finding is rewritten to fit the selection.
  const supportedFindings: Finding[] = [];
  const omittedFindingIds: string[] = [];
  for (const f of keptFindings) {
    if (f.occurrence_ids.every((oid) => keptOccurrenceIds.has(oid))) {
      supportedFindings.push(f);
    } else {
      omittedFindingIds.push(f.id);
    }
  }
  if (omittedFindingIds.length > 0) {
    omissions.push(
      `${omittedFindingIds.length} finding(s) omitted: the selection does not retain the readings they cite.`,
    );
  }
  const omittedOccurrenceCount = src.occurrences.length - keptOccurrences.length;
  if (omittedOccurrenceCount > 0) {
    omissions.push("Other extracted source occurrences excluded.");
  }

  // --- checks: scope and results preserved; retained ids pruned ----------
  const checks: CheckResult[] = src.checks.map((c) => ({
    ...c,
    retained_occurrence_ids: c.retained_occurrence_ids.filter((oid) => keptOccurrenceIds.has(oid)),
  }));

  // --- annotations: opt-in only ------------------------------------------
  const keptFindingIds = new Set(supportedFindings.map((f) => f.id));
  let annotations = src.annotations;
  if (request.annotations === true) {
    annotations = annotations.filter(
      (a) => a.finding_id === null || keptFindingIds.has(a.finding_id),
    );
  } else {
    annotations = [];
  }
  if (src.annotations.length > 0 && annotations.length === 0) {
    omissions.push("Notes excluded.");
  }

  // --- plan regions: pruned to what kept checks/findings still cite ------
  // Check scope is preserved (plan.selected_pages / plan.checks stay
  // intact); unreferenced regions are dropped and disclosed, never kept
  // just because they exist in memory.
  const referencedRegionIds = new Set<string>();
  for (const p of src.plan.checks) {
    if (p.region_id !== null) referencedRegionIds.add(p.region_id);
  }
  for (const f of supportedFindings) {
    if (f.region_id !== null) referencedRegionIds.add(f.region_id);
  }
  const keptRegions = src.plan.regions.filter((r) => referencedRegionIds.has(r.id));
  const droppedRegionCount = src.plan.regions.length - keptRegions.length;
  if (droppedRegionCount > 0) {
    omissions.push(`${droppedRegionCount} unreferenced region(s) excluded.`);
  }
  const plan = droppedRegionCount === 0 ? src.plan : { ...src.plan, regions: keptRegions };

  // --- retained pages: selected scope plus every kept evidence page ------
  const keptPages = new Set(src.plan.selected_pages);
  const referencedAssetIds = new Set<string>();
  for (const o of keptOccurrences) {
    keptPages.add(o.page_index);
    if (o.source_asset_id !== null) referencedAssetIds.add(o.source_asset_id);
  }
  for (const f of supportedFindings) keptPages.add(f.page_index);
  for (const a of annotations) keptPages.add(a.page_index);
  for (const r of keptRegions) keptPages.add(r.page_index);

  // --- assets: crops on by default, page renders opt-in -------------------
  const cropSel = resolveIds(
    request.crops ?? "all",
    new Set(src.assets.filter((a) => a.purpose === "crop").map((a) => a.id)),
    "crop",
  );
  const renderSel = resolveIds(
    request.pageRenders ?? "none",
    new Set(src.assets.filter((a) => a.purpose === "page_render").map((a) => a.id)),
    "page render",
  );
  const keptAssets: Asset[] = [];
  const requiredContextAssetIds: string[] = [];
  let excludedRenders = 0;
  for (const asset of src.assets) {
    if (asset.purpose === "source_pdf") continue; // handled via doc opt-in
    const wanted =
      asset.purpose === "crop"
        ? cropSel.all
          ? asset.page_index !== null && keptPages.has(asset.page_index)
          : cropSel.ids.has(asset.id)
        : renderSel.all
          ? asset.page_index !== null && keptPages.has(asset.page_index)
          : renderSel.ids.has(asset.id);
    const required = referencedAssetIds.has(asset.id);
    if (missingAssetIds.includes(asset.id)) continue;
    if (wanted || required) {
      keptAssets.push(asset);
      if (!wanted && required) requiredContextAssetIds.push(asset.id);
    } else if (asset.purpose === "page_render") {
      excludedRenders++;
    }
  }
  if (excludedRenders > 0) {
    omissions.push("Full-page images excluded.");
  }
  if (missingAssetIds.length > 0) {
    omissions.push(
      `${missingAssetIds.length} asset(s) omitted: bytes unavailable — evidence only.`,
    );
  }
  if (sourceAsset !== null) keptAssets.push(sourceAsset);

  // Occurrences whose raster reference could not be retained keep their
  // reading; the missing link is nulled and disclosed, never guessed (I11).
  const keptAssetIds = new Set(keptAssets.map((a) => a.id));
  const unlinkedOccurrenceIds: string[] = [];
  for (const o of keptOccurrences) {
    if (o.source_asset_id !== null && !keptAssetIds.has(o.source_asset_id)) {
      unlinkedOccurrenceIds.push(o.id);
      o.source_asset_id = null;
    }
  }
  if (unlinkedOccurrenceIds.length > 0) {
    omissions.push(
      `${unlinkedOccurrenceIds.length} occurrence(s) lost their raster reference (bytes unavailable).`,
    );
  }

  // --- retained context: pages, transforms, readers ----------------------
  for (const a of keptAssets) {
    if (a.page_index !== null) keptPages.add(a.page_index);
  }
  const transformIds = new Set<string>();
  const pages = src.pages.filter((p) => keptPages.has(p.index));
  for (const p of pages) transformIds.add(p.raw_to_canonical_transform_id);
  const geometries = [
    ...keptOccurrences.map((o) => o.geometry),
    ...keptRegions.map((r) => r.geometry),
    ...keptAssets.map((a) => a.geometry).filter((g): g is NonNullable<typeof g> => g !== null),
  ];
  for (const g of geometries) {
    for (const id of g.transform_ids) transformIds.add(id);
  }
  const transforms = src.transforms.filter((t) => transformIds.has(t.id));

  // --- mode / replay derived from actual content --------------------------
  const mode: Report["export"]["mode"] =
    sourceAsset !== null
      ? "replayable"
      : keptOccurrences.length === 0 && keptAssets.some((a) => a.media_type === "image/png")
        ? "diagnostic"
        : "evidence";
  const replay: Report["export"]["replay"] =
    sourceAsset !== null
      ? "source_included_environment_required"
      : mode === "diagnostic"
        ? "not_replayable"
        : "requires_original";
  if (sourceAsset !== null) {
    omissions.push("Compatible reader runtime and model must be installed separately.");
  }
  omissions.push("Reader runtime binaries and model bytes excluded.");

  const originReportId =
    HEX64.test(src.report_id) && src.report_id !== ZERO64 ? src.report_id : null;

  const limitations = [...src.limitations];
  if (limitations.length === 0) {
    limitations.push("Selection projection of a recorded run.");
  }
  if (omittedOccurrenceCount > 0 || omittedFindingIds.length > 0) {
    limitations.push(
      `Selection projection: ${keptOccurrences.length} of ${src.occurrences.length} produced occurrences retained; check scope and produced counts are unchanged.`,
    );
  }

  const projected: Report = {
    kind: "report",
    schema_version: src.schema_version,
    report_id: ZERO64,
    document: doc,
    readers: src.readers,
    pages,
    transforms,
    occurrences: keptOccurrences,
    findings: supportedFindings,
    annotations,
    plan,
    checks,
    execution: src.execution,
    export: {
      mode,
      scope,
      included: [],
      omissions: [],
      replay,
      origin_report_id: originReportId,
    },
    assets: keptAssets,
    limitations,
  };
  // The disclosure block is derived from the projected object itself so the
  // recorded inclusion allowlist always matches the actual bytes (I09).
  projected.export = disclosure(projected, mode, scope, replay, originReportId, omissions);
  seal(projected);
  validate(projected);
  return {
    report: projected,
    notices: {
      omittedOccurrenceCount,
      omittedFindingIds,
      missingAssetIds,
      requiredContextAssetIds,
      unlinkedOccurrenceIds,
      requestedSourceMissing,
      omissions,
    },
  };
}

export { reportDigest, runKey };
