/**
 * @inkflip/readers-tesseract — browser selected-page/crop OCR reader
 * (T10) over the staged tesseract.js@7.0.0 build.
 *
 * Contract surface (`planning/architecture/READER_ADAPTER_CONTRACT.md`):
 * explicit same-origin worker/core/lang paths, `gzip:false`,
 * `workerBlobURL:false`, `{text:true, blocks:true}` output, PSM 6 for
 * full pages / PSM 7 for deliberate single-line regions, context
 * padding max(8px, 10% region height) clipped to the raster, and the
 * recorded crop/resize chain (`O = K·T·S·R·C`) from packages/geometry.
 *
 * One reusable initialized model per active profile; the named render
 * reader supplies rasters via `RasterSource`. Model bytes are fetched
 * by the adapter, SHA-256-verified against the frozen manifest and
 * committed to the worker-readable cache — no default CDN anywhere.
 *
 * Failure honesty: initialization/model failures are terminal `failed`
 * results distinct from `unreadable_pixels` (a completed recognition
 * with no usable text). Engine confidence is a diagnostic estimate on
 * every occurrence — never asserted as ground truth.
 */
export {
  ADAPTER_VERSION,
  buildManifest,
  buildReader,
  ENGINE_NAME,
  LINE_PSM,
  ocrReaderId,
  PAGE_PSM,
  type ReaderIdentityInput,
} from './identity.ts';

export {
  classifyError,
  OcrError,
  OCR_NO_RETRY_REASONS,
  OCR_REASON,
  OCR_TRANSIENT_REASONS,
  requireOcr,
  type OcrReason,
} from './errors.ts';

export {
  createEngineWorker,
  OCR_PSM,
  type EngineBBox,
  type EngineBlock,
  type EngineLine,
  type EngineParagraph,
  type EnginePaths,
  type EngineProgress,
  type EngineRecognizePage,
  type EngineWord,
  type OcrPsm,
  type TesseractEngineModule,
  type TesseractEngineWorker,
} from './engine.ts';

export {
  KeyvalStore,
  MODEL_STATES,
  ModelAssetManager,
  type ModelIdentity,
  type ModelManagerHooks,
  type ModelPreparation,
  type ModelProvenance,
  type ModelState,
  type PreparedModel,
} from './model-cache.ts';

export {
  canonicalToRaster,
  planCrop,
  type CropBounds,
  type CropPlan,
  type OcrRegionInput,
  type PageRasterInfo,
} from './crop.ts';

export {
  ENGINE_SCORE_MAX,
  ENGINE_SCORE_MEANING,
  ENGINE_SCORE_MIN,
  LOW_CONFIDENCE_BELOW,
  mapEngineBlocks,
  meanWordConfidence,
  type MappedBlocks,
  type MapBlocksInput,
} from './occurrences.ts';

export {
  cancellationOf,
  DEFAULT_OCR_BUDGET,
  MAX_CHUNK_OCCURRENCES,
  TesseractOcrReader,
  type EmitChunk,
  type OcrBudget,
  type OcrCancellation,
  type OcrCheckOutput,
  type OcrEngineIdentity,
  type OcrHandle,
  type OcrReaderConfig,
  type OcrReaderHooks,
  type OcrSelection,
  type PageRaster,
  type RasterSource,
} from './reader.ts';
