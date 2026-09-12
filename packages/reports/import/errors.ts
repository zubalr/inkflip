/**
 * Stable UI-facing classification over the T24 import gate's
 * `ContractError` codes. The gate throws machine codes; this module maps
 * them onto the four honest categories the interface can act on without
 * re-inspecting message text.
 *
 * - `not_a_report` — the input is not an `.inkflip.json` report at all:
 *   archive/container bytes, markup, a bare PDF, non-JSON text, wrong
 *   artifact kind, or structural parse violations. Nothing in it is
 *   ever executed.
 * - `unsupported_version` — the input is well-formed JSON declaring a
 *   `schema_version` other than the supported one. Named separately so
 *   the interface can use the explicit version copy instead of the
 *   generic invalid message.
 * - `too_large` — the JSON bytes, a string, or decoded assets exceeded a
 *   declared import bound.
 * - `invalid` — the artifact is report-shaped but failed schema,
 *   semantic, hash, or asset verification. Includes tampering.
 */
import { ContractError, SCHEMA_VERSION, loadsStrict } from "../../contracts/src/index.ts";

export type ImportFailureKind = "not_a_report" | "unsupported_version" | "too_large" | "invalid";

export interface ImportFailure {
  readonly kind: ImportFailureKind;
  /** The gate's contract code (ARCHIVE, KIND, SCHEMA, HASH, ...). */
  readonly code: string;
  /** Public-safe detail — bounded coded message, never a stack. */
  readonly detail: string;
  /** Declared schema_version, present only for `unsupported_version`. */
  readonly version: string | null;
}

/**
 * Inputs rejected before any report semantics exist: container magic,
 * markup, wrong artifact kind, malformed/bound-violating JSON.
 */
const STRUCTURAL_CODES = new Set([
  "ARCHIVE",
  "KIND",
  "JSON",
  "UNICODE",
  "DUPLICATE_KEY",
  "DEPTH",
  "NONFINITE",
  "NUMBER",
  "PROTOTYPE",
  "PATH",
]);

export function classifyImportFailure(error: unknown, data: string | Uint8Array): ImportFailure {
  const code = error instanceof ContractError ? error.code : "INTERNAL";
  const detail = (error instanceof Error ? error.message : "import failed").slice(0, 240);
  if (STRUCTURAL_CODES.has(code)) {
    return { kind: "not_a_report", code, detail, version: null };
  }
  if (code === "SIZE") {
    return { kind: "too_large", code, detail, version: null };
  }
  if (code === "SCHEMA") {
    const version = sniffSchemaVersion(data);
    if (version !== null) {
      return { kind: "unsupported_version", code, detail, version };
    }
  }
  return { kind: "invalid", code, detail, version: null };
}

/**
 * Extract a declared non-`SCHEMA_VERSION` `schema_version` from input
 * that already passed the strict parser upstream (the gate only reaches
 * SCHEMA rejection after `loadsStrict` succeeded). Returns null for any
 * other shape — classification falls back to `invalid`.
 */
function sniffSchemaVersion(data: string | Uint8Array): string | null {
  try {
    const value = loadsStrict(data);
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return null;
    }
    const version = (value as Record<string, unknown>).schema_version;
    if (typeof version !== "string" || version === SCHEMA_VERSION) {
      return null;
    }
    return version.length > 40 ? version.slice(0, 40) : version;
  } catch {
    return null;
  }
}
