/**
 * Prototype-key auditing and safe-name handling for imported reports.
 *
 * Two distinct hazards:
 *
 * 1. Prototype keys. `loadsStrict` already materializes `__proto__` as an
 *    own enumerable property (never as the prototype), so a hostile
 *    `{"__proto__": …}` cannot pollute object lookups. This audit adds a
 *    dedicated, early `PROTOTYPE` rejection for the three keys that
 *    collide with `Object.prototype` machinery — before schema validation
 *    and before any downstream code can merge, spread or index the value.
 *    (The closed schema would reject them anyway; the dedicated code makes
 *    the security boundary explicit in receipts.)
 *
 * 2. Names used as paths/filenames. A report `display_name` is untrusted
 *    text that downstream code may offer as a download filename, and
 *    corpus manifests carry relative `source_path` strings. Neither may
 *    ever traverse or escape a chosen directory (I10: no dangerous file
 *    paths). `safeFileName` maps arbitrary text to a deterministic safe
 *    basename; `assertSafeRelativePath` rejects traversal/absolutes.
 */
import { ContractError, require } from '../../contracts/src/index.ts';
import { IMPORT_LIMITS } from './limits.ts';

/** Own-key names that alias Object.prototype internals. */
const PROTOTYPE_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

/**
 * Walk a strictly-parsed JSON value and reject objects carrying
 * `__proto__`/`constructor`/`prototype` own keys. Depth is already bounded
 * by `loadsStrict`/`bounded`; the explicit depth guard stays so this audit
 * is safe to call on programmatically built values too.
 */
export function auditPrototypeKeys(value: unknown, depth = 0): void {
  require(depth <= IMPORT_LIMITS.maxDepth, 'DEPTH', 'Nesting exceeds limit');
  if (Array.isArray(value)) {
    for (const item of value) auditPrototypeKeys(item, depth + 1);
    return;
  }
  if (typeof value !== 'object' || value === null) return;
  const record = value as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    if (PROTOTYPE_KEYS.has(key)) {
      throw new ContractError(
        'PROTOTYPE',
        `Forbidden object member "${key}"`,
      );
    }
    auditPrototypeKeys(record[key], depth + 1);
  }
}

// ---------------------------------------------------------------------------
// Safe names and relative paths
// ---------------------------------------------------------------------------

/** Windows-reserved basenames that must never become file names. */
const DOS_DEVICES = new Set([
  'con', 'prn', 'aux', 'nul',
  'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
  'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9',
]);

const MAX_NAME_CHARS = 120;

/**
 * Deterministically map untrusted display text to a safe basename:
 * ASCII letters/digits plus `.` `_` `-` are kept, everything else —
 * separators, control characters, Unicode — becomes `_`. Leading dots and
 * dashes are removed, repeats collapse, the result is length-capped, can
 * never be `.`/`..`/empty, and can never be a DOS device name. A name
 * that reduces to nothing falls back to `fallback`.
 */
export function safeFileName(raw: string, fallback = 'report'): string {
  let out = '';
  for (const ch of raw) {
    const code = ch.codePointAt(0)!;
    const ok =
      (code >= 0x30 && code <= 0x39) || // 0-9
      (code >= 0x41 && code <= 0x5a) || // A-Z
      (code >= 0x61 && code <= 0x7a) || // a-z
      ch === '.' ||
      ch === '_' ||
      ch === '-';
    out += ok ? ch : '_';
  }
  // Collapse runs of '_' and strip leading dots/dashes/underscores so the
  // name can never start as a hidden file, an option, or '..'.
  out = out.replace(/_+/g, '_').replace(/^[._-]+/, '');
  // Never end in '.' or ' ' semantics (dot-only endings confuse win32).
  out = out.replace(/[.]+$/, '');
  if (out.length > MAX_NAME_CHARS) {
    out = out.slice(0, MAX_NAME_CHARS).replace(/[._-]+$/, '');
  }
  if (out === '' || out === '.' || out === '..') out = fallback;
  if (DOS_DEVICES.has(out.split('.')[0]!.toLowerCase())) {
    out = '_' + out;
  }
  return out;
}

/**
 * True when `path` is a portable relative path that cannot escape its
 * root: no absolute prefix, no drive letter, no backslashes, no NUL, no
 * `.`/`..`/empty segments. This matches the corpus-manifest PATH rule in
 * `@inkflip/contracts` and is the required shape for any future
 * report-carried relative path.
 */
export function isSafeRelativePath(path: string): boolean {
  if (typeof path !== 'string' || path.length === 0) return false;
  if (path.includes('\0')) return false;
  if (path.startsWith('/') || path.startsWith('\\')) return false;
  if (path.includes('\\') || path.includes(':')) return false;
  const parts = path.split('/');
  if (parts.some((p) => p === '' || p === '.' || p === '..')) return false;
  return true;
}

/** Assert {@link isSafeRelativePath}; throws ContractError('PATH'). */
export function assertSafeRelativePath(path: string): void {
  require(isSafeRelativePath(path), 'PATH', 'Unsafe relative path');
}
