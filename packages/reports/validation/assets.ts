/**
 * Decoded-asset accounting for imported reports.
 *
 * Two layers, ordered so that rejections land before resource use:
 *
 * `preAuditAssets` runs on the freshly parsed value — before schema and
 * semantic validation — using only string lengths and counts. It enforces
 * the import profile's asset count (≤128) and the encoded-size ceiling
 * (a base64 string that can only decode past 20 MiB, or a payload set
 * whose estimated decoded total exceeds 20 MiB, is rejected before a
 * single decoding buffer exists).
 *
 * `auditAssets` runs after `validate()` has already confirmed syntax,
 * SHA-256 and byte_length. It decodes each asset exactly once more for
 * deep content checks: PNG payloads are fully decoded and re-encoded
 * (`sanitizePng`) under pixel/edge limits and must match the declared
 * `pixel_size`; PDF payloads re-verify the `%PDF-` signature; decoded
 * totals are recomputed for receipts.
 *
 * Nothing here interprets ancillary PNG metadata, archive members, HTML,
 * SVG or executable content — no decompression surface other than the
 * bounded PNG IDAT inflate exists (I10).
 */
import {
  ContractError,
  require,
  sha256,
} from '../../contracts/src/index.ts';
import type { Report } from '../../contracts/src/index.ts';
import {
  IMPORT_LIMITS,
  MAX_BASE64_CHARS,
  base64DecodedLength,
} from './limits.ts';
import { sanitizePng, PNG_SIG } from './png.ts';
import type { SanitizedPng } from './png.ts';

const B64_RE = /^[A-Za-z0-9+/]*={0,2}$/;

/** Strict base64 decode; identical alphabet/padding rules to contracts. */
export function decodeBase64(s: string): Uint8Array {
  if (s.length % 4 !== 0 || !B64_RE.test(s)) {
    throw new ContractError('ASSET', 'Invalid base64');
  }
  const alphabet =
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const pad = s.endsWith('==') ? 2 : s.endsWith('=') ? 1 : 0;
  const out = new Uint8Array((s.length / 4) * 3 - pad);
  let acc = 0;
  let bits = 0;
  let o = 0;
  for (const ch of s) {
    if (ch === '=') break;
    const v = alphabet.indexOf(ch);
    acc = (acc << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      if (o < out.length) out[o++] = (acc >> bits) & 0xff;
    }
  }
  return out;
}

interface AssetLike {
  data_base64?: unknown;
}

/**
 * Encoded-size accounting on the parsed value, before validation. Only
 * inspects `value.assets` when it is an array — all deeper shape errors
 * belong to schema validation.
 */
export function preAuditAssets(value: unknown): void {
  if (typeof value !== 'object' || value === null) return;
  const assets = (value as Record<string, unknown>).assets;
  if (!Array.isArray(assets)) return;
  require(
    assets.length <= IMPORT_LIMITS.maxAssets,
    'SIZE',
    `Asset count ${assets.length} exceeds ${IMPORT_LIMITS.maxAssets}`,
  );
  let estimatedTotal = 0;
  for (const item of assets as AssetLike[]) {
    if (typeof item !== 'object' || item === null) continue;
    const payload = item.data_base64;
    if (typeof payload !== 'string') continue; // schema reports the type
    require(
      payload.length <= MAX_BASE64_CHARS,
      'SIZE',
      'Encoded asset exceeds per-asset limit',
    );
    if (payload.length % 4 === 0 && B64_RE.test(payload)) {
      const pad = payload.endsWith('==') ? 2 : payload.endsWith('=') ? 1 : 0;
      estimatedTotal += base64DecodedLength(payload.length, pad);
      require(
        estimatedTotal <= IMPORT_LIMITS.maxAssetTotalBytes,
        'SIZE',
        'Encoded assets exceed total decoded limit',
      );
    }
  }
}

export interface AssetAudit {
  count: number;
  totalDecoded: number;
  /** asset id → clean re-encoded PNG for image/png assets. */
  sanitizedPngs: Map<string, SanitizedPng>;
}

const PDF_SIG = [0x25, 0x50, 0x44, 0x46, 0x2d]; // "%PDF-"

/**
 * Deep asset validation on a contract-valid report: MIME-vs-signature,
 * hash/length recomputation, decoded totals, and full PNG decode +
 * re-encode with pixel/edge limits.
 */
export function auditAssets(
  report: Report,
  limits: {
    maxAssets?: number;
    maxAssetBytes?: number;
    maxAssetTotalBytes?: number;
    maxPngPixels?: number;
    maxPngEdge?: number;
  } = {},
): AssetAudit {
  const maxAssets = limits.maxAssets ?? IMPORT_LIMITS.maxAssets;
  const maxAssetBytes = limits.maxAssetBytes ?? IMPORT_LIMITS.maxAssetBytes;
  const maxTotal = limits.maxAssetTotalBytes ?? IMPORT_LIMITS.maxAssetTotalBytes;
  require(
    report.assets.length <= maxAssets,
    'SIZE',
    `Asset count ${report.assets.length} exceeds ${maxAssets}`,
  );
  const sanitizedPngs = new Map<string, SanitizedPng>();
  let total = 0;
  for (const asset of report.assets) {
    // Encoded ceiling first: no decoding buffer exists before this check.
    require(
      asset.data_base64.length <= MAX_BASE64_CHARS,
      'SIZE',
      `Asset ${asset.id} payload exceeds per-asset limit`,
    );
    const data = decodeBase64(asset.data_base64);
    require(
      data.length <= maxAssetBytes,
      'SIZE',
      `Asset ${asset.id} decoded bytes exceed limit`,
    );
    total += data.length;
    require(
      total <= maxTotal,
      'SIZE',
      'Decoded asset total exceeds limit',
    );
    // Hash/length are re-derived here too — a validator must not trust
    // declared metadata even though validate() already checked them.
    const hex = [...sha256(data)]
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
    require(
      data.length === asset.byte_length && hex === asset.sha256,
      'ASSET',
      `Asset ${asset.id} hash/length mismatch`,
    );
    if (asset.media_type === 'image/png') {
      const clean = sanitizePng(data, {
        maxPixels: limits.maxPngPixels ?? IMPORT_LIMITS.maxPngPixels,
        maxEdge: limits.maxPngEdge ?? IMPORT_LIMITS.maxPngEdge,
      });
      require(
        asset.pixel_size !== null &&
          asset.pixel_size[0] === clean.width &&
          asset.pixel_size[1] === clean.height,
        'ASSET',
        `Asset ${asset.id} pixel_size does not match decoded PNG`,
      );
      sanitizedPngs.set(asset.id, clean);
    } else if (asset.media_type === 'application/pdf') {
      require(
        data.length >= 5 && PDF_SIG.every((b, i) => data[i] === b),
        'ASSET',
        `Asset ${asset.id} is not a PDF`,
      );
    }
    // Any other media_type was already rejected by the closed enum.
  }
  return { count: report.assets.length, totalDecoded: total, sanitizedPngs };
}

/** Raw PNG signature check for callers that only need the envelope. */
export function hasPngSignature(data: Uint8Array): boolean {
  return data.length >= 8 && PNG_SIG.every((b, i) => data[i] === b);
}
