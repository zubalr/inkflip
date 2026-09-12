/**
 * Import gate for untrusted `.inkflip.json` report bytes.
 *
 * Pipeline order is the security contract — every stage can reject before
 * the next stage's resource use exists:
 *
 *   1. byte length ≤ 32 MiB and container/content sniffing — ZIP, gzip,
 *      7z, RAR, xz, bzip2, zstd, tar, OLE/CFB, a bare PDF, UTF-16 BOMs and
 *      HTML/XML/SVG-shaped input are rejected here. There is no archive
 *      decompression surface at all (I10).
 *   2. `loadsStrict` — strict UTF-8 JSON with duplicate-key, depth (≤24),
 *      per-string, nonfinite and unsafe-integer rejection; `__proto__`
 *      parses as an inert own property.
 *   3. Import-profile bounds — non-payload strings ≤ 2 000 000 code
 *      points (settings.json `import.max_string_chars`), encoded asset
 *      count/size estimates (`preAuditAssets`).
 *   4. Prototype-key audit — `__proto__`/`constructor`/`prototype` object
 *      members rejected with `PROTOTYPE`.
 *   5. `validate` — closed-schema check (unknown fields such as
 *      executable/plugin/command strings cannot exist) plus full semantic
 *      and hash verification. A report cannot select reader executables.
 *   6. `auditAssets` — decoded-asset accounting plus bounded PNG
 *      decode/re-encode.
 *
 * The gate performs no I/O, no network access, no code execution and no
 * schema compilation; reports can never trigger a fetch or pick an
 * executable (I09/I10/I11).
 */
import {
  ContractError,
  loadsStrict,
  require,
  validate,
} from '../../contracts/src/index.ts';
import type { Report } from '../../contracts/src/index.ts';
import { IMPORT_LIMITS, MAX_BASE64_CHARS } from './limits.ts';
import { auditPrototypeKeys } from './names.ts';
import { auditAssets, preAuditAssets } from './assets.ts';
import type { AssetAudit } from './assets.ts';

const TE = new TextEncoder();

/** Archive/container signatures rejected at the byte boundary. */
const ARCHIVE_MAGICS: ReadonlyArray<readonly number[]> = [
  [0x50, 0x4b, 0x03, 0x04], // ZIP (also docx/jar/apk, all archives here)
  [0x50, 0x4b, 0x05, 0x06], // ZIP end-of-central-directory (empty archive)
  [0x50, 0x4b, 0x07, 0x08], // ZIP spanning marker
  [0x1f, 0x8b], // gzip
  [0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c], // 7z
  [0x52, 0x61, 0x72, 0x21], // RAR
  [0xfd, 0x37, 0x7a, 0x58, 0x5a], // xz
  [0x42, 0x5a, 0x68], // bzip2
  [0x28, 0xb5, 0x2f, 0xfd], // zstd
  [0x4d, 0x53, 0x43, 0x46], // MS-CAB
  [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1], // OLE/CFB container
];

const PDF_MAGIC = [0x25, 0x50, 0x44, 0x46, 0x2d]; // "%PDF-"
const UTF16_BOMS = [
  [0xff, 0xfe],
  [0xfe, 0xff],
  [0xff, 0xfe, 0x00, 0x00],
  [0x00, 0x00, 0xfe, 0xff],
];

function startsWith(data: Uint8Array, magic: readonly number[]): boolean {
  if (data.length < magic.length) return false;
  return magic.every((b, i) => data[i] === b);
}

/**
 * Reject non-JSON inputs at the byte boundary, before UTF-8 decoding.
 * Archives get `ARCHIVE` — there is deliberately no way to import a ZIP,
 * tarball or compressed bundle, matching `import.archive_import: false`.
 * HTML/XML/SVG-shaped input gets `KIND`; so does a bare source PDF, which
 * is a document, never a report. UTF-16 BOMs get `UNICODE`.
 */
export function sniffImportKind(data: Uint8Array): void {
  for (const magic of UTF16_BOMS) {
    if (startsWith(data, magic)) {
      throw new ContractError('UNICODE', 'Report JSON must be UTF-8');
    }
  }
  for (const magic of ARCHIVE_MAGICS) {
    if (startsWith(data, magic)) {
      throw new ContractError(
        'ARCHIVE',
        'Archive/container input has no import path',
      );
    }
  }
  // tar: 'ustar' magic at offset 257.
  if (
    data.length >= 262 &&
    data[257] === 0x75 &&
    data[258] === 0x73 &&
    data[259] === 0x74 &&
    data[260] === 0x61 &&
    data[261] === 0x72
  ) {
    throw new ContractError(
      'ARCHIVE',
      'Archive/container input has no import path',
    );
  }
  if (startsWith(data, PDF_MAGIC)) {
    throw new ContractError(
      'KIND',
      'A PDF is a source document, not a report',
    );
  }
  // HTML/XML/SVG: first non-whitespace byte '<' cannot be JSON.
  let i = 0;
  while (
    i < data.length &&
    (data[i] === 0x20 || data[i] === 0x09 || data[i] === 0x0a || data[i] === 0x0d)
  ) {
    i++;
  }
  if (i < data.length && data[i] === 0x3c) {
    throw new ContractError(
      'KIND',
      'Markup input is not a report (no HTML/SVG import)',
    );
  }
}

/**
 * Enforce the import profile's per-string cap on every JSON string except
 * asset `data_base64` payloads (which are accounted in decoded bytes by
 * `preAuditAssets`/`auditAssets`). Depth was already bounded by
 * `loadsStrict`.
 */
export function importStringBounds(value: unknown, depth = 0): void {
  require(depth <= IMPORT_LIMITS.maxDepth, 'DEPTH', 'Nesting exceeds limit');
  if (Array.isArray(value)) {
    for (const item of value) importStringBounds(item, depth + 1);
    return;
  }
  if (typeof value !== 'object' || value === null) return;
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (typeof item === 'string') {
      if (key === 'data_base64') {
        require(
          item.length <= MAX_BASE64_CHARS,
          'SIZE',
          'Encoded asset exceeds per-asset limit',
        );
        continue;
      }
      let count = 0;
      for (const _ch of item) count++;
      require(
        count <= IMPORT_LIMITS.maxStringChars,
        'SIZE',
        `String exceeds ${IMPORT_LIMITS.maxStringChars} characters`,
      );
    } else {
      importStringBounds(item, depth + 1);
    }
  }
}

/**
 * Shared gate pipeline for any contract artifact kind: size, kind
 * sniffing, strict parse, import string/asset bounds, prototype audit,
 * then full schema + semantic + hash validation. Returns the validated
 * value. Used by `importReport` and by security tooling that must
 * exercise the identical boundary for non-report artifacts (for example
 * corpus manifests, whose relative paths are contract-checked).
 */
export function importArtifact(
  data: string | Uint8Array,
  checkHashes = true,
): unknown {
  const bytes = typeof data === 'string' ? TE.encode(data) : data;
  require(
    bytes.length <= IMPORT_LIMITS.maxJsonBytes,
    'SIZE',
    'JSON too large',
  );
  sniffImportKind(bytes);
  const value = loadsStrict(bytes);
  importStringBounds(value);
  preAuditAssets(value);
  auditPrototypeKeys(value);
  validate(value, checkHashes);
  return value;
}

export interface ImportResult {
  /** The fully validated report (identity/hash verified by default). */
  report: Report;
  /** Decoded-asset accounting and sanitized PNG re-encodes by asset id. */
  assets: AssetAudit;
}

/**
 * Full import pipeline for an untrusted report artifact. `checkHashes`
 * mirrors `validate` — it exists for producer-side tooling; the import
 * boundary should always leave it enabled.
 */
export function importReport(
  data: string | Uint8Array,
  checkHashes = true,
): ImportResult {
  const report = importArtifact(data, checkHashes) as Report;
  require(report.kind === 'report', 'KIND', 'Import accepts reports only');
  const assets = auditAssets(report);
  return { report, assets };
}
