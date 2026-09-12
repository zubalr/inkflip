/**
 * `openReport` — the single entry for untrusted `.inkflip.json` bytes.
 *
 * It is a thin orchestration layer over the T24 gate (`importReport`):
 * the gate performs every parse, bound, prototype-key, schema, semantic,
 * hash and asset-signature check and returns a fully validated report
 * plus sanitized PNG re-encodes. This module only derives the two
 * things the reopen flow needs and the gate deliberately does not own:
 *
 * - `source` — where the original document bytes stand for replay:
 *   `embedded` (a verified `source_pdf` asset is present),
 *   `required` (evidence export; the matching original must be chosen
 *   locally), or `not_applicable` (diagnostic export; no replay path).
 * - `scope` — the producer-declared disclosure block (`export.mode`,
 *   `export.scope`, `export.replay`, `included`, `omissions`) copied out
 *   verbatim for display.
 *
 * Nothing here performs I/O, fetches, executes, or interprets report
 * strings as code, commands, paths, or URLs (I09/I10).
 */
import type { Report } from "../../contracts/src/index.ts";
import { importReport } from "../validation/import_gate.ts";
import type { AssetAudit } from "../validation/assets.ts";
import { IMPORT_LIMITS } from "../validation/limits.ts";
import { classifyImportFailure } from "./errors.ts";
import type { ImportFailure } from "./errors.ts";

export type SourceState =
  | {
      readonly kind: "embedded";
      readonly assetId: string;
      readonly byteLength: number;
    }
  | { readonly kind: "required" }
  | { readonly kind: "not_applicable" };

/** Producer-declared export disclosure, surfaced verbatim. */
export interface ScopeDisclosure {
  readonly mode: Report["export"]["mode"];
  readonly scope: Report["export"]["scope"];
  readonly replay: Report["export"]["replay"];
  readonly included: readonly string[];
  readonly omissions: readonly string[];
}

export interface ImportedReport {
  /** The gate-validated report — immutable evidence, never mutated. */
  readonly report: Report;
  /** Decoded-asset accounting and sanitized PNG re-encodes. */
  readonly audit: AssetAudit;
  readonly source: SourceState;
  readonly scope: ScopeDisclosure;
}

export type ImportOutcome =
  | { readonly ok: true; readonly imported: ImportedReport }
  | { readonly ok: false; readonly failure: ImportFailure };

/** Largest `.inkflip.json` body the gate will read — mirror for callers. */
export const IMPORT_JSON_LIMIT = IMPORT_LIMITS.maxJsonBytes;

export function openReport(data: string | Uint8Array): ImportOutcome {
  try {
    const { report, assets } = importReport(data);
    const exported = report.export;
    const source: SourceState =
      report.document.source_asset_id !== null
        ? {
            kind: "embedded",
            assetId: report.document.source_asset_id,
            byteLength: report.document.byte_length,
          }
        : exported.replay === "requires_original"
          ? { kind: "required" }
          : { kind: "not_applicable" };
    return {
      ok: true,
      imported: {
        report,
        audit: assets,
        source,
        scope: {
          mode: exported.mode,
          scope: exported.scope,
          replay: exported.replay,
          included: [...exported.included],
          omissions: [...exported.omissions],
        },
      },
    };
  } catch (error) {
    return { ok: false, failure: classifyImportFailure(error, data) };
  }
}
