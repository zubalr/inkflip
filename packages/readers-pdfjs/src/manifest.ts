/**
 * `describe()` — honest reader identity and capability matrix (I13).
 *
 * The pinned pdf.js build backs two configured readings on one engine:
 * a `native_text` reader (getTextContent occurrences) and a `render`
 * reader (bounded static page rasters). Capability levels mirror
 * CAPABILITIES.md exactly: original MediaBox/CropBox, object render modes,
 * paint overlap, OCR and alignment are all `unavailable` on this boundary.
 * The adapter makes NO full glyph-paint provenance claim — TextItem
 * geometry is always emitted as `estimated` extent.
 */
import { digest } from '../../contracts/src/index.ts';
import type {
  Capability,
  Reader,
  ReaderManifest,
} from '../../contracts/src/index.ts';

export const ADAPTER_VERSION = '1.0.0' as const;

const TEXT_LIMITATIONS = [
  'raw_text is the unmodified getTextContent API string; the parser may still decode character mappings',
  'occurrence extent is estimated from TextItem transform, width/height and font ascent/descent — not a glyph-paint or per-character provenance',
  'a multi-character TextItem carries no per-character advance boxes; highlight is the whole measured item',
  'marked-content records are preserved as counts only; they are never emitted as text occurrences',
  'emitted ordinal order is the raw API sequence, not a verified screen-reader or logical order',
];

const RENDER_LIMITATIONS = [
  'static annotation appearance streams only (AnnotationMode.ENABLE); no actions, links, forms, XFA or attachments are activated',
  'canvas is bounded by the configured pixel/edge caps and released after pixels are extracted',
];

const SHARED_LIMITATIONS = [
  'original MediaBox/CropBox are unavailable through the selected API: page.view is the effective view and original boxes are stored as null',
  'no getOperatorList exposure: there is no occurrence-level visibility, render-mode or paint-overlap oracle on this boundary',
];

function capabilities(
  overrides: Partial<Record<Capability['name'], Capability['support']>>,
  limits: Record<string, string[]>,
): Capability[] {
  const names: Capability['name'][] = [
    'render',
    'native_text',
    'ocr',
    'object_render_mode',
    'crop_metadata',
    'paint_overlap',
    'reading_order',
    'alignment',
  ];
  return names.map((name) => ({
    name,
    support: overrides[name] ?? 'unavailable',
    limits: limits[name] ?? [],
  }));
}

export interface ReaderIdentity {
  /** Engine name, e.g. "pdf.js". */
  engine: string;
  /** Actual injected library version, e.g. "6.3.289". */
  version: string;
  /** Distribution label, e.g. "pdfjs-dist-legacy". */
  build: string;
}

function slug(identity: ReaderIdentity, suffix: string): string {
  const v = identity.version.replace(/[^a-z0-9_-]+/gi, '_').toLowerCase();
  return `pdfjs-${v}-${suffix}`.slice(0, 96);
}

/**
 * Build the two contract Reader records for this adapter.
 * `text` answers native_text/reading_order checks; `render` answers
 * render checks. Their ids are deterministic for a given version.
 */
export function buildReaders(identity: ReaderIdentity): {
  text: Reader;
  render: Reader;
} {
  const text: Reader = {
    id: slug(identity, 'text'),
    name: `${identity.engine} text`,
    version: identity.version,
    build: identity.build,
    adapter_version: ADAPTER_VERSION,
    method: 'native_text',
    environment: 'browser',
    settings: {
      normalization: 'scalar-whitespace-v1',
      language: null,
      psm: null,
      render_reader_id: null,
      raster_dpi: null,
      annotation_mode: 'not_applicable',
    },
    capabilities: capabilities(
      { native_text: 'supported', reading_order: 'approximate' },
      {
        native_text: TEXT_LIMITATIONS,
        reading_order: [
          'raw emitted getTextContent order only; derived geometric/logical ordering belongs to the alignment layer',
        ],
      },
    ),
    model_hashes: [],
    limitations: [...TEXT_LIMITATIONS, ...SHARED_LIMITATIONS],
  };
  const render: Reader = {
    id: slug(identity, 'render'),
    name: `${identity.engine} render`,
    version: identity.version,
    build: identity.build,
    adapter_version: ADAPTER_VERSION,
    method: 'render',
    environment: 'browser',
    settings: {
      normalization: 'scalar-whitespace-v1',
      language: null,
      psm: null,
      render_reader_id: null,
      raster_dpi: null,
      annotation_mode: 'static_appearance',
    },
    capabilities: capabilities(
      { render: 'supported' },
      { render: RENDER_LIMITATIONS },
    ),
    model_hashes: [],
    limitations: [...RENDER_LIMITATIONS, ...SHARED_LIMITATIONS],
  };
  return { text, render };
}

/**
 * One contract ReaderManifest per Reader record. `assetHashes` binds the
 * caller-verified hashes of the pinned main/worker pair (and staged data
 * files when provided); `distributionDigest` covers the provenance record.
 */
export function buildManifest(
  reader: Reader,
  provenance: {
    packageName: string;
    packageVersion: string;
    mainSha256?: string;
    workerSha256?: string;
    extraAssetSha256?: string[];
  },
): ReaderManifest {
  const assetHashes = [
    ...(provenance.mainSha256 ? [provenance.mainSha256] : []),
    ...(provenance.workerSha256 ? [provenance.workerSha256] : []),
    ...(provenance.extraAssetSha256 ?? []),
  ];
  return {
    kind: 'reader_manifest',
    schema_version: '1.0.0',
    reader,
    distribution_digest: digest({
      package: provenance.packageName,
      version: provenance.packageVersion,
      build: reader.build,
      asset_hashes: assetHashes,
    }),
    asset_hashes: assetHashes,
    execution_policy: 'installed_allowlist_no_report_commands',
  };
}
