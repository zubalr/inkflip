/**
 * @inkflip/contracts — canonical contract surface.
 *
 * Structural types and the precompiled structural validator are generated
 * from the single authoritative `planning/contracts/inkflip.schema.json` by
 * `scripts/generate_contracts.py`. Semantic validation, strict parsing,
 * canonical identity and normalization are implemented in `./core.ts` in
 * exact parity with `native/inkflip/contracts/core.py`.
 */

export type {
  AcceptanceRules,
  Annotation,
  Asset,
  Baseline,
  Box,
  Capability,
  Change,
  CheckPlan,
  CheckResult,
  Comparison,
  CorpusEntry,
  CorpusManifest,
  Document,
  EngineScore,
  Execution,
  Export,
  Finding,
  Geometry,
  InkflipArtifact,
  Matrix,
  Occurrence,
  Page,
  Plan,
  Point,
  RawMap,
  Reader,
  ReaderManifest,
  Region,
  Report,
  Rule,
  Transform,
  WorkerMessage,
} from './generated/types.ts';

export { checkSchema } from './generated/schema-check.ts';
export type { SchemaIssue } from './generated/schema-check.ts';

export {
  CANONICALIZATION,
  ContractError,
  MAX_ASSET_BYTES,
  MAX_ASSET_TOTAL,
  MAX_DEPTH,
  MAX_JSON_BYTES,
  MAX_PNG_PIXELS,
  MAX_STRING_LENGTH,
  SAFE_INTEGER,
  SCHEMA_ID,
  SCHEMA_VERSION,
  WS,
  apply,
  bounded,
  canonical,
  digest,
  inverse,
  loadsStrict,
  normalize,
  occurrenceId,
  reportDigest,
  require,
  runKey,
  seal,
  sha256,
  unique,
  validate,
  validateJson,
  validateReport,
} from './core.ts';
