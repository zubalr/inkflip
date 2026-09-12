/**
 * PDF.js reader adapter (T09) — project interface of
 * READER_ADAPTER_CONTRACT.md over the pinned paired legacy build:
 *
 *   describe() -> ReaderManifest[]
 *   open(immutable bytes, document digest, generation) -> bounded handle
 *   pages(handle) -> count and contract geometry metadata
 *   plan(handle, page selection, budget) -> CheckPlan[]
 *   extract(handle, check, emitChunk, cancellation, job?) -> CheckResult
 *   close(handle) -> release document/worker
 *
 * What this adapter deliberately does NOT do: activate PDF actions,
 * links, attachments, forms, XFA or scripting; expose getOperatorList as
 * a visibility oracle; infer original MediaBox/CropBox; deduplicate equal
 * strings across positions; normalize raw_text; or claim glyph-paint /
 * per-character provenance. Unavailable structure checks terminate as
 * `unsupported` with a named reason — never a faked success.
 */
import { require } from '../../contracts/src/index.ts';
import type {
  CheckPlan,
  CheckResult,
  Occurrence,
  Page,
  Reader,
  ReaderManifest,
  Transform,
} from '../../contracts/src/index.ts';
import { REASON, deriveRunKey } from '../../runtime/src/index.ts';
import type { AdapterConfig, AdapterConfigInput } from './config.ts';
import { resolveConfig } from './config.ts';
import type { DocumentHandle } from './document.ts';
import {
  closeDocument,
  documentPages,
  handlePage,
  openDocument,
  requireOpen,
} from './document.ts';
import {
  CANCEL_REASON,
  ReaderError,
  TIMEOUT_REASON,
  classifyError,
  unsupportedReason,
} from './errors.ts';
import { ADAPTER_VERSION, buildManifest, buildReaders } from './manifest.ts';
import { renderPage, type RenderedRaster } from './render.ts';
import {
  extractText,
  type TextExtractionDetail,
} from './text.ts';
import type { PdfJsApi } from './types.ts';

/** Capabilities the text reader can execute. */
const TEXT_CAPABILITIES = new Set(['native_text', 'reading_order']);
/** Capabilities the render reader can execute. */
const RENDER_CAPABILITIES = new Set(['render']);
/** Every capability the adapter can answer (anything else is unsupported). */
const EXECUTABLE_CAPABILITIES = new Set([
  ...TEXT_CAPABILITIES,
  ...RENDER_CAPABILITIES,
]);

const CAPABILITY_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;

export interface PlanSelection {
  /** Zero-based page indices (contract internal numbering). */
  pages: number[];
  /** Requested capability ids; unsupported ones stay planned and are
   *  answered `unsupported` by extract (never dropped, never faked). */
  capabilities: string[];
  /** Optional region ids per check, keyed `${capability}:p${page}`. */
  regions?: Record<string, string>;
}

export interface ExtractJob {
  /** Coordinator run identity; defaults to a deterministic per-plan key. */
  runKey?: string;
  /** Render scale request in px/pt for render checks (default 1). */
  renderScalePxPerPt?: number;
  /** Per-render deadline override (defaults to renderTimeoutMs). */
  renderDeadlineMs?: number;
  /** Raster sequence number for raster id minting (default 0). */
  rasterIndex?: number;
}

export interface Cancellation {
  signal?: AbortSignal;
}

export interface ExtractOutcome {
  result: CheckResult;
  /** Occurrences emitted through emitChunk (== produced count). */
  emitted: number;
  /** Present for completed render checks. */
  raster?: RenderedRaster;
  detail?: Record<string, unknown>;
}

export interface PdfJsReaderAdapter {
  describe(): { readers: Reader[]; manifests: ReaderManifest[] };
  open(input: {
    bytes: Uint8Array;
    sha256: string;
    generation: number;
  }): Promise<DocumentHandle>;
  pages(
    handle: DocumentHandle,
  ): Promise<{ count: number; pages: Page[]; transforms: Transform[] }>;
  plan(handle: DocumentHandle, selection: PlanSelection): CheckPlan[];
  extract(
    handle: DocumentHandle,
    check: CheckPlan,
    emitChunk: (chunk: Occurrence[]) => unknown,
    cancellation?: Cancellation,
    job?: ExtractJob,
  ): Promise<ExtractOutcome>;
  close(handle: DocumentHandle): Promise<void>;
  readonly readers: { text: Reader; render: Reader };
  readonly config: AdapterConfig;
}

export function createPdfJsReader(
  input: AdapterConfigInput,
): PdfJsReaderAdapter {
  const config = resolveConfig(input);
  const readers = buildReaders({
    engine: input.engineName ?? 'pdf.js',
    version: input.pdfjs.version,
    build: input.buildLabel ?? 'pdfjs-dist-legacy',
  });
  const manifests = [
    buildManifest(readers.text, {
      packageName: 'pdfjs-dist',
      packageVersion: input.pdfjs.version,
    }),
    buildManifest(readers.render, {
      packageName: 'pdfjs-dist',
      packageVersion: input.pdfjs.version,
    }),
  ];

  function checkResult(
    check: CheckPlan,
    status: CheckResult['status'],
    reason: string | null,
    produced: number,
    retained: string[],
  ): CheckResult {
    return {
      id: check.id,
      status,
      reason,
      produced_occurrence_count: produced,
      retained_occurrence_ids: retained,
    };
  }

  function failOutcome(
    check: CheckPlan,
    status: CheckResult['status'],
    reason: string,
    produced = 0,
    retained: string[] = [],
  ): ExtractOutcome {
    return { result: checkResult(check, status, reason, produced, retained), emitted: produced };
  }

  /**
   * AdapterFailure -> schema terminal status. `resource_limit` is a
   * reason code, not a schema status: the check ends `failed` with the
   * limit named (taxonomy in RUNTIME_LIFECYCLE / READER_ADAPTER_CONTRACT).
   */
  function statusFor(error: ReaderError): CheckResult['status'] {
    return error.failure === 'resource_limit' ? 'failed' : error.failure;
  }

  async function extract(
    handle: DocumentHandle,
    check: CheckPlan,
    emitChunk: (chunk: Occurrence[]) => unknown,
    cancellation: Cancellation = {},
    job: ExtractJob = {},
  ): Promise<ExtractOutcome> {
    requireOpen(handle);
    require(
      Number.isInteger(check.page_index) &&
        check.page_index >= 0 &&
        check.page_index < handle.doc.numPages,
      'PAGE',
      `check ${check.id} targets a page outside the document`,
    );
    const capability = check.capability;
    if (!EXECUTABLE_CAPABILITIES.has(capability)) {
      // An unavailable structure/OCR/etc. request is `unsupported` with a
      // named reason — never executed against a substitute API and never
      // reported as success (I05, CAPABILITIES.md behavior-when-absent).
      return failOutcome(
        check,
        'unsupported',
        unsupportedReason(
          `capability ${capability} is unavailable on the pinned pdf.js API boundary`,
        ),
      );
    }
    const boundText = check.reader_ids.includes(readers.text.id);
    const boundRender = check.reader_ids.includes(readers.render.id);
    // A check bound only to a foreign reader cannot run on this adapter;
    // report it rather than silently substituting our own reading.
    const bound = (TEXT_CAPABILITIES.has(capability) && boundText) ||
      (RENDER_CAPABILITIES.has(capability) && boundRender);
    if (!bound) {
      return failOutcome(
        check,
        'unsupported',
        unsupportedReason(
          `capability ${capability} is not bound to this adapter's readers`,
        ),
      );
    }
    if (cancellation.signal?.aborted) {
      return failOutcome(check, 'cancelled', CANCEL_REASON);
    }
    const runKey =
      job.runKey ??
      deriveRunKey(handle.digest, [readers.text, readers.render], {
        checks: [check.id],
      });
    let page;
    try {
      page = await handlePage(config, handle, check.page_index);
    } catch (error) {
      const classified = classifyError(error);
      return failOutcome(check, statusFor(classified), classified.reason);
    }
    if (RENDER_CAPABILITIES.has(capability)) {
      try {
        const raster = await renderPage(
          config,
          handle,
          page,
          job.renderScalePxPerPt ?? 1,
          job.rasterIndex ?? 0,
          cancellation.signal,
          job.renderDeadlineMs,
        );
        return {
          result: checkResult(
            check,
            'completed',
            raster.viewportVerified
              ? null
              : 'geometry_unverified:viewport transform diverged; raster kept, precise overlay disabled',
            0,
            [],
          ),
          emitted: 0,
          raster,
          detail: {
            rasterId: raster.rasterId,
            widthPx: raster.widthPx,
            heightPx: raster.heightPx,
            scalePxPerPt: raster.scalePxPerPt,
            annotation_mode: 'static_appearance',
            limitations: raster.limitations,
          },
        };
      } catch (error) {
        const classified = classifyError(error, true);
        return failOutcome(check, statusFor(classified), classified.reason);
      }
    }
    // native_text / reading_order extraction.
    try {
      const outcome = await extractText(
        config,
        handle,
        page,
        check.id,
        readers.text.id,
        {
          runKey,
          locatorTag: capability === 'reading_order' ? 'order' : 'text',
        },
        emitChunk,
        cancellation.signal,
      );
      const detail: TextExtractionDetail = outcome.detail;
      return {
        result: checkResult(
          check,
          outcome.cancelled ? 'cancelled' : 'completed',
          outcome.cancelled ? CANCEL_REASON : null,
          outcome.occurrences,
          outcome.retainedIds,
        ),
        emitted: outcome.occurrences,
        detail: {
          textItems: detail.textItems,
          markedContent: detail.markedContent,
          lang: detail.lang,
          degenerateExtents: detail.degenerateExtents,
          emittedOrderIsRawSequence: capability === 'reading_order',
        },
      };
    } catch (error) {
      const classified = classifyError(error);
      return failOutcome(check, statusFor(classified), classified.reason);
    }
  }

  return {
    readers,
    config,
    describe(): { readers: Reader[]; manifests: ReaderManifest[] } {
      return { readers: [readers.text, readers.render], manifests };
    },
    open(input) {
      return openDocument(config, input);
    },
    pages(handle) {
      return documentPages(config, handle);
    },
    plan(handle: DocumentHandle, selection: PlanSelection): CheckPlan[] {
      requireOpen(handle);
      const checks: CheckPlan[] = [];
      const seen = new Set<string>();
      const capabilities = [
        ...new Set(
          selection.capabilities.map((capability) => {
            require(
              CAPABILITY_PATTERN.test(capability),
              'PLAN',
              `unknown capability spelling ${JSON.stringify(capability)}`,
            );
            return capability;
          }),
        ),
      ];
      for (const pageIndex of selection.pages) {
        require(
          Number.isInteger(pageIndex) &&
            pageIndex >= 0 &&
            pageIndex < handle.doc.numPages,
          'PAGE',
          `selected page ${pageIndex} outside the document`,
        );
        for (const capability of capabilities) {
          const id = `chk_p${pageIndex}_${capability}`;
          require(!seen.has(id), 'PLAN', `duplicate planned check ${id}`);
          seen.add(id);
          const readerIds = TEXT_CAPABILITIES.has(capability)
            ? [readers.text.id]
            : RENDER_CAPABILITIES.has(capability)
              ? [readers.render.id]
              : [readers.text.id];
          checks.push({
            id,
            page_index: pageIndex,
            reader_ids: readerIds,
            capability: capability as CheckPlan['capability'],
            region_id: selection.regions?.[`${capability}:p${pageIndex}`] ?? null,
          });
        }
      }
      return checks;
    },
    extract,
    close(handle) {
      return closeDocument(handle);
    },
  };
}

export { ADAPTER_VERSION, REASON };
export type { PdfJsApi };
