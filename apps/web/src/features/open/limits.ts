/**
 * Runtime safety profiles for the open feature (T08).
 *
 * Values mirror the `browser` and `mobile` profiles of
 * `planning/config/settings.json` — canonical limits, not tuning knobs.
 * The mobile profile is selected by an injected environment predicate so
 * tests can exercise it deterministically; the default predicate uses a
 * coarse pointer or a narrow viewport (CAPABILITIES.md narrow-screen
 * support), never device memory as a reliable signal.
 */
import { byteLimitLabel } from "./copy";

export interface OpenProfile {
  readonly id: "desktop" | "mobile";
  /** settings browser.max_file_bytes / mobile.max_file_bytes. */
  readonly maxFileBytes: number;
  /** settings browser.max_document_pages. */
  readonly maxDocumentPages: number;
  /** settings *.max_native_pages_per_run — selection cap per run. */
  readonly maxNativePagesPerRun: number;
  /** settings *.max_ocr_pages_per_run. */
  readonly maxOcrPagesPerRun: number;
  /** settings *.max_raster_pixels — per-raster pixel cap. */
  readonly maxRasterPixels: number;
}

export const DESKTOP_PROFILE: OpenProfile = {
  id: "desktop",
  maxFileBytes: 20_971_520,
  maxDocumentPages: 1_000,
  maxNativePagesPerRun: 20,
  maxOcrPagesPerRun: 5,
  maxRasterPixels: 4_000_000,
};

export const MOBILE_PROFILE: OpenProfile = {
  id: "mobile",
  maxFileBytes: 10_485_760,
  maxDocumentPages: 1_000,
  maxNativePagesPerRun: 5,
  maxOcrPagesPerRun: 1,
  maxRasterPixels: 2_000_000,
};

/** Environment hints the caller can inject (tests pin them explicitly). */
export interface ProfileEnvironment {
  /** e.g. matchMedia("(pointer: coarse)").matches */
  readonly coarsePointer?: boolean;
  /** e.g. window.innerWidth < 768 */
  readonly narrowViewport?: boolean;
}

/**
 * Default environment probe: a coarse pointer or a sub-768px viewport selects
 * the lighter profile. Deliberately conservative — it only ever tightens
 * limits, it cannot widen them.
 */
export function defaultEnvironment(): Required<ProfileEnvironment> {
  const g = globalThis as {
    matchMedia?: (q: string) => { matches: boolean };
    innerWidth?: number;
  };
  const coarse =
    typeof g.matchMedia === "function" &&
    (g.matchMedia("(pointer: coarse)").matches ||
      g.matchMedia("(pointer: none)").matches);
  const narrow =
    typeof g.innerWidth === "number" && g.innerWidth > 0 && g.innerWidth < 768;
  return { coarsePointer: coarse, narrowViewport: narrow };
}

export function resolveProfile(
  env: ProfileEnvironment = defaultEnvironment(),
): OpenProfile {
  return env.coarsePointer === true || env.narrowViewport === true
    ? MOBILE_PROFILE
    : DESKTOP_PROFILE;
}

/** The profile's file-size limit as user-facing text ("20 MiB"/"10 MiB"). */
export function profileSizeLimitLabel(profile: OpenProfile): string {
  return byteLimitLabel(profile.maxFileBytes);
}
