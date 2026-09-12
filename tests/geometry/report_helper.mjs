// Shared minimal-report builder for TEST-04: embeds real buildPage /
// makeTransform / makeGeometry output in a schema-complete report so the
// contract validator itself proves conformance (not a re-declared schema).
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import { normalize } from '../../packages/contracts/src/index.ts';
import {
  buildPage,
  displayTransformRecord,
  rasterTransformRecord,
  makeGeometry,
} from '../../packages/geometry/src/index.ts';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const GEOM0 = readFileSync(join(ROOT, 'fixtures', 'public', 'geometry-0.pdf'));
const GEOM0_SHA256 = createHash('sha256').update(GEOM0).digest('hex');

export function minimalReport(overrides = {}) {
  const built = buildPage({
    index: 0,
    mediaBox: [-20, -30, 520, 420],
    cropBox: [20, 40, 500, 390],
    userUnit: 2,
    rotation: 0,
    boxSource: 'fixture public/geometry-0.pdf page dict',
  });
  const display = displayTransformRecord(built.page);
  const raster = rasterTransformRecord(built.page, 2, 'geom0');
  const transforms = [built.canonical, display, raster];
  const estGeometry = makeGeometry({
    precision: 'estimated',
    polygon: [
      [40, 122],
      [200, 122],
      [200, 195],
      [40, 195],
    ],
    transformIds: [built.canonical.id],
    basis: 'Estimated text extent polygon in canonical points',
  });
  const pageOnly = makeGeometry({
    precision: 'page_only',
    polygon: null,
    transformIds: [built.canonical.id],
    basis: 'Reader reported page-level text only',
  });
  const mkOcc = (id, ordinal, geometry) => {
    const raw = 'SYNTHETIC EXAMPLE';
    const n = normalize(raw);
    return {
      id,
      reader_id: 'r_pdfium',
      page_index: 0,
      ordinal,
      raw_text: raw,
      normalized_text: n.text,
      normalization_map: n.map,
      geometry,
      engine_score: null,
      source_asset_id: null,
      raw_source_locator: `text line ordinal ${ordinal}`,
      limitations: [],
    };
  };
  const occurrences = [
    mkOcc('o_est', 0, estGeometry),
    mkOcc('o_pageonly', 1, pageOnly),
  ];
  const parsed = { sha256: GEOM0_SHA256 };
  return {
    kind: 'report',
    schema_version: '1.0.0',
    report_id: '0'.repeat(64),
    document: {
      sha256: parsed.sha256,
      byte_length: 1437,
      page_count: 1,
      display_name: null,
      source_asset_id: null,
    },
    readers: [
      {
        id: 'r_pdfium',
        name: 'PDFium via pypdfium2',
        version: '5.8.0',
        build: 'PDFium 149.0.7825.0',
        adapter_version: '1.0.0',
        method: 'native_text',
        environment: 'native',
        settings: {
          normalization: 'scalar-whitespace-v1',
          language: null,
          psm: null,
          render_reader_id: null,
          raster_dpi: null,
          annotation_mode: 'none',
        },
        capabilities: [
          { name: 'native_text', support: 'supported', limits: [] },
        ],
        model_hashes: [],
        limitations: [],
      },
    ],
    pages: [built.page],
    transforms,
    occurrences,
    findings: [],
    annotations: [],
    plan: {
      version: '1.0.0',
      selected_pages: [0],
      regions: [
        {
          id: 'region_est',
          page_index: 0,
          geometry: estGeometry,
          label: 'estimated extent',
        },
        {
          id: 'region_page',
          page_index: 0,
          geometry: pageOnly,
          label: 'page-level anchor',
        },
      ],
      checks: [
        {
          id: 'c_native',
          page_index: 0,
          reader_ids: ['r_pdfium'],
          capability: 'native_text',
          region_id: null,
        },
      ],
      normalization_version: 'scalar-whitespace-v1',
      alignment_version: 'region-match-v1',
      profile: 'native',
      budget: {
        max_raster_pixels: 4000000,
        max_run_ocr_pixels: 20000000,
        timeout_ms: 120000,
        max_retries: 0,
      },
    },
    checks: [
      {
        id: 'c_native',
        status: 'completed',
        reason: null,
        produced_occurrence_count: 2,
        retained_occurrence_ids: occurrences.map((o) => o.id),
      },
    ],
    execution: {
      execution_id: '11111111-2222-4333-8444-555555555555',
      run_key: '0'.repeat(64),
      status: 'complete',
      started_at: '2026-09-12T00:00:00+00:00',
      duration_ms: 1,
      environment: 'node test',
      result_origin: 'contract_example',
      errors: [],
    },
    export: {
      mode: 'evidence',
      scope: 'selection',
      included: ['document_hash', 'settings', 'coverage', 'selected_text'],
      omissions: [],
      replay: 'requires_original',
      origin_report_id: null,
    },
    assets: [],
    limitations: [
      'Synthetic TEST-04 report: geometry package output embedded for contract validation.',
    ],
    ...overrides,
  };
}

