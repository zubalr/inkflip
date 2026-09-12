/**
 * @inkflip/reports — validation surface (T24).
 *
 * Hardened import boundary for untrusted report bytes: container/kind
 * sniffing, import-profile string/asset accounting, prototype-key
 * rejection, decoded-asset auditing, bounded PNG decode/re-encode and
 * the script-free HTML export guard. Builds on `@inkflip/contracts`
 * (`loadsStrict`, `validate`) — it does not re-implement the strict
 * parser or the closed schema.
 *
 * Entry point for untrusted import bytes: {@link importReport}.
 */
export { IMPORT_LIMITS, MAX_BASE64_CHARS, base64DecodedLength } from './limits.ts';
export {
  importArtifact,
  importReport,
  importStringBounds,
  sniffImportKind,
} from './import_gate.ts';
export type { ImportResult } from './import_gate.ts';
export {
  auditAssets,
  decodeBase64,
  hasPngSignature,
  preAuditAssets,
} from './assets.ts';
export type { AssetAudit } from './assets.ts';
export {
  crc32,
  decodePng,
  encodePngRgba,
  PNG_SIG,
  sanitizePng,
} from './png.ts';
export type { DecodedPng, PngInfo, SanitizedPng } from './png.ts';
export { adler32, inflateZlib, zlibEncodeStored } from './inflate.ts';
export {
  assertSafeRelativePath,
  auditPrototypeKeys,
  isSafeRelativePath,
  safeFileName,
} from './names.ts';
export { assertScriptFreeHtml, escapeHtml } from './html_guard.ts';
