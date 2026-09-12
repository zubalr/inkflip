/**
 * Reader identity and manifest construction (T10).
 *
 * READER_ADAPTER_CONTRACT: a reader instance is identified by engine
 * name/version, binary build, adapter version, normalized
 * configuration, model hashes and rendering dependency. The same
 * engine with a different OCR crop/PSM or raster source is a distinct
 * configured reading — so the page (PSM 6) and single-line (PSM 7)
 * profiles emit separate `Reader` records, and the renderer that
 * produced the input raster is bound in `render_reader_id` (I13).
 */
import type {
  Capability,
  Reader,
  ReaderManifest,
} from '../../contracts/src/index.ts';
import type { ModelIdentity } from './model-cache.ts';
import type { OcrPsm } from './engine.ts';

/** Adapter implementation version (contract adapter version 1.0.0). */
export const ADAPTER_VERSION = '1.0.0' as const;
export const ENGINE_NAME = 'tesseract.js';
/** PSM used for a full selected page. */
export const PAGE_PSM = 6;
/** PSM used for a deliberately single-line user region. */
export const LINE_PSM = 7;

export interface ReaderIdentityInput {
  /** Resolved npm package version, e.g. `7.0.0` (frozen manifest). */
  readonly engineVersion: string;
  /** Feature-detected core build label, e.g. `relaxedsimd-lstm`. */
  readonly coreBuild: string;
  readonly model: ModelIdentity;
  /** Reader id of the raster producer bound into this reading. */
  readonly renderReaderId: string;
  /** Effective raster scale in DPI (scale_px_per_pt × 72). */
  readonly rasterDpi: number;
  /** Check kind this reader record serves. */
  readonly psm: OcrPsm;
  /** Deployment profile for the id namespace. */
  readonly profile: 'desktop' | 'mobile';
  readonly limitations?: readonly string[];
}

/** Deterministic reader id for one configured OCR reading. */
export function ocrReaderId(input: {
  readonly profile: string;
  readonly psm: number | string;
  readonly renderReaderId: string;
}): string {
  const render = input.renderReaderId.replace(/[^a-z0-9_-]/g, '_');
  const id = `rdr_tesseract_eng_lstm_psm${input.psm}_${input.profile}_${render}`;
  return id.slice(0, 96);
}

/** Build the contract `Reader` record for one configured reading. */
export function buildReader(input: ReaderIdentityInput): Reader {
  const capabilities: Capability[] = [
    {
      name: 'ocr',
      support: 'supported',
      limits: [
        'raster input supplied by the named render reader',
        `psm ${input.psm} fixed for this configured reading`,
      ],
    },
  ];
  return {
    id: ocrReaderId(input),
    name: ENGINE_NAME,
    version: input.engineVersion,
    build: `tesseract.js-core ${input.coreBuild}`,
    adapter_version: ADAPTER_VERSION,
    method: 'ocr',
    environment: 'browser',
    settings: {
      normalization: 'scalar-whitespace-v1',
      language: input.model.lang,
      psm: Number(input.psm),
      render_reader_id: input.renderReaderId,
      raster_dpi: input.rasterDpi,
      annotation_mode: 'not_applicable',
    },
    capabilities,
    model_hashes: [input.model.sha256],
    limitations: [...(input.limitations ?? [])],
  };
}

/**
 * `describe()` — the adapter's ReaderManifest. `asset_hashes` binds the
 * staged worker/core/lang assets the reader was configured with.
 */
export function buildManifest(
  reader: Reader,
  assetHashes: readonly string[],
): ReaderManifest {
  return {
    kind: 'reader_manifest',
    schema_version: '1.0.0',
    reader,
    distribution_digest: null,
    asset_hashes: [...assetHashes],
    execution_policy: 'installed_allowlist_no_report_commands',
  };
}
