/**
 * Frozen third-party asset identity for the public inspection session.
 *
 * Values mirror `config/resolved-assets.json` exactly — the staged
 * same-origin worker/core/model files under `apps/web/public` that the
 * OCR reader is allowed to load. Nothing here may point at a CDN: the
 * reader only ever fetches same-origin paths, and every loaded byte is
 * SHA-256-verified against the digests below before use (I13).
 */

/** Pinned traineddata identity — `tessdata-fast-eng` from resolved-assets. */
export const OCR_MODEL = {
  id: "tessdata-fast-eng",
  version: "65727574dfcd264acbb0c3e07860e4e9e9b22185",
  sha256: "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
  byteLength: 4113088,
  sourcePath: "/models/tessdata-fast-eng/7d4322bd/eng.traineddata",
  lang: "eng",
  license: "Apache-2.0",
  cachePath: "inkflip/models",
} as const;

/** Explicit same-origin staged paths (the adapter never builds CDN URLs). */
export const OCR_PATHS = {
  workerPath: "/assets/tesseract/7.0.0/worker.min.js",
  corePath: "/assets/tesseract-core/7.0.0/",
  langPath: "/models/tessdata-fast-eng/7d4322bd/",
  cachePath: "inkflip/models",
} as const;

/** SHA-256 of every staged byte the reader may load (resolved-assets.json). */
export const OCR_ASSET_HASHES = [
  "576b7df7e3393e137e51849357c9adb53fe7ac1bb69bfa06cf3d61520f182c6d",
  "0bc6ce3e5fbbd0cd89706cf2fd70960e3372f4f01ee24265b26990808aaeb286",
  "eef5f8b2f8e20e150680b20adaec4a60babafee3adbe8a94583c81fee46e8680",
  "6b61ef4e911b5cf57e656bbfe983d6e2b3711a02dd164154ddda064566e8e09d",
  "c58b46a4c796c0b8afccf77591d5b875b6896b45d402bbce8caa6f5362447b38",
  "843074aa5bad1cc6421b74a86201768ced9f244795e4d81435435a61a40ce535",
  "861a536cf9ef8e63cb644d57bab39c388f37f7d6b6f60024b741c5f6b39a59b3",
  OCR_MODEL.sha256,
] as const;

/** Published engine package version (package.json pin, tesseract.js). */
export const OCR_ENGINE_VERSION = "7.0.0";

/** Feature-detected core build label recorded on the Reader record. */
export const OCR_CORE_BUILD = "feature-detected single-threaded lstm";
