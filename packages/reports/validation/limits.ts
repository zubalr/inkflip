/**
 * Import-boundary resource limits for untrusted report data.
 *
 * Values mirror `planning/config/settings.json` (`import` profile plus the
 * browser raster edge cap) and the contract constants in
 * `@inkflip/contracts`. They are copied here as literals because the
 * planning package is frozen input, not a runtime dependency; the tests in
 * `tests/security/import/` pin them against the delivered settings file.
 *
 * Ordering rule (I10): every check that can reject input *before* an
 * expensive step must run first — byte size before UTF-8 decode, declared
 * base64 length before decoding, IHDR dimensions before inflating IDAT,
 * and the expected raster size as a hard inflate cap before pixel
 * allocation.
 */
export const IMPORT_LIMITS = {
  /** settings.json import.max_json_bytes — whole import file. */
  maxJsonBytes: 32 * 1024 * 1024,
  /** settings.json import.max_depth — matches contracts MAX_DEPTH. */
  maxDepth: 24,
  /**
   * settings.json import.max_string_chars — per-string cap for every JSON
   * string that is not an asset `data_base64` payload. Asset payloads are
   * accounted in decoded bytes instead (maxAssetBytes).
   */
  maxStringChars: 2_000_000,
  /** settings.json import.max_assets. */
  maxAssets: 128,
  /** settings.json import.max_asset_bytes — decoded, per asset. */
  maxAssetBytes: 20 * 1024 * 1024,
  /** settings.json import.max_total_decoded_assets_bytes. */
  maxAssetTotalBytes: 20 * 1024 * 1024,
  /** settings.json import.max_png_pixels — decoded PNG pixel cap. */
  maxPngPixels: 4_000_000,
  /** settings.json browser.max_raster_edge — decoded PNG edge cap. */
  maxPngEdge: 8192,
  /** settings.json import.archive_import — there is no archive surface. */
  archiveImport: false,
} as const;

/**
 * Largest base64 character count that can decode to `maxAssetBytes`
 * (20 MiB): ceil(20971520 / 3) * 4 = 27962028, plus it may carry up to two
 * '=' pad characters inside that count. Any longer payload can never be a
 * legal asset, so it is rejected before a decoding buffer exists.
 */
export const MAX_BASE64_CHARS =
  Math.ceil(IMPORT_LIMITS.maxAssetBytes / 3) * 4;

/** Decoded length implied by a strict base64 string of `chars` characters. */
export function base64DecodedLength(chars: number, pad: number): number {
  return Math.floor(chars / 4) * 3 - pad;
}
