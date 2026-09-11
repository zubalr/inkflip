# Reader adapter contract

The canonical definitions are in [inkflip.schema.json](../contracts/inkflip.schema.json). Adapter version is 1.0.0. A reader instance is identified by engine name/version, binary build, adapter version, normalized configuration, model hashes and rendering dependency. The same engine with a different OCR crop/PSM or raster source is a distinct configured reading.

## Operations and boundaries

```text
describe() -> ReaderManifest
open(immutable bytes, document digest, generation) -> bounded document handle
pages(handle) -> count and supported geometry metadata
plan(handle, explicit page/region selection, budget) -> CheckPlan[]
extract(handle, check, emitChunk, cancellation) -> terminal CheckResult
close(handle) -> release native/worker resources
```

These are project interfaces to implement, not claimed third-party method names. The actual library calls are listed below. Emitted chunks are capped at 256 occurrences and two unacknowledged messages. The coordinator acknowledges only after validating shape, identity and capacity. Every job has exactly one terminal result. An empty successfully completed native text extraction is a completed check with zero occurrences, not an error or proof the visual page is blank.

## PDF.js adapter

Use the exact `pdfjs-dist` legacy main and paired worker from the selected package. Configure `GlobalWorkerOptions.workerSrc` with a bundled same-origin URL. Pass local `Uint8Array` data to `getDocument`; never a document-controlled URL. Set `isEvalSupported:false`, `enableXfa:false`; do not instantiate scripting, auto-print, attachment-launch or interactive form managers. Disable automatic annotation navigation. Render static annotation appearances with explicitly recorded mode; if unsupported, render base page and say annotations were not included.

`getTextContent({disableNormalization:true,includeMarkedContent:true})` returns TextItems plus marked-content records. Keep TextItems in emitted order, retain original strings and item ordinals, and store the actual geometry source. Marked-content markers are not text occurrences. The “raw” label is scoped to this API output; the parser may still decode character mappings. Do not expose `getOperatorList` as an occurrence-level visibility oracle. Unsupported structural check requests get `unsupported` with reason.

`getViewport`, `render`, `RenderTask.cancel`, `RenderTask.onContinue`, document cleanup/destroy and worker destroy provide the selected lifecycle. Check signatures in the frozen package tests. Closing after cancellation must not terminate an unrelated new generation's worker.

## Tesseract.js adapter

Initialize `createWorker('eng', OEM.LSTM_ONLY, options)` with explicit `workerPath`, `corePath`, `langPath`, `gzip:false` for the verified uncompressed English data, `workerBlobURL:false`, and a logger that emits only bounded stage/progress codes. Request `{text:true,blocks:true}` from `recognize`. Treat a missing blocks result as a capability failure, not fabricated boxes.

Full selected page uses PSM 6; a deliberately single-line user region uses PSM 7; user choice is recorded. No unconditional five-PSM vote. Context padding is 8 raster pixels or 10% of region height (larger), clipped to the render, and visible in the preview. Preserve original region and padded OCR crop separately. Decode a Blob/ImageData the application already owns; no external image URLs. On timeout/cancel terminate the OCR worker and rebuild only if the user retries. Reusing a model instance within the same generation is allowed; file replacement terminates the worker to drop previous document state.

## Native adapters

PDFium opens bytes in a separate child process. Calls are single-threaded in that process. Close text page, page, bitmap and document handles deterministically. Native rendering uses explicit UserUnit compensation proven by fixtures; no threads around global PDFium calls. Iterate character indices to preserve duplicate occurrences and retain loose/tight box semantics. Glyph-to-Unicode expansion may make a character mapping contain several Unicode scalars; preserve that relation rather than forcing one scalar per glyph.

pypdf 6.18.0 parses the declared page dictionaries and supplies an independent page-level text path. It never supplies exact per-word locations without a successful dedicated adapter test. Do not combine text from pypdf with PDFium boxes by matching strings alone.

Tesseract is invoked with fixed argv and `shell=False` on a bounded application-created raster in a private temporary directory. The parent enforces wall time and kills the whole child process group, not merely a Python signal handler. TSV output includes engine scores and boxes; raw text is preserved even where geometry is absent. The native process may not download missing language data during an inspection.

Native object checks use actual `FPDFTextObj_GetTextRenderMode`, page object traversal and documented color/geometry getters, with a finite nesting/object budget. A mode-3/7 observation is a property of the object, not a maliciousness finding. Unknown binding from object to a text occurrence yields a structural object-region observation without a false text link. Prior source ideas are credited even when reimplemented. [S15](../research/SOURCES.md#s15), [S17](../research/SOURCES.md#s17), [S27](../research/SOURCES.md#s27).

## Capability negotiation and errors

A plan asks for capability and reader IDs, not a presumed universal feature set. The manifest reports supported/approximate/experimental/unavailable. User opt-in is required for experimental checks, and they are excluded from headline findings until promoted. Distinguish `unsupported`, `missing_model`, `model_integrity`, `parser_error`, `render_error`, `timeout`, `cancelled`, `resource_limit`, `unreadable_pixels`, `geometry_unavailable` and `nondeterminism`. Public reason codes map to exact copy; raw exceptions are local diagnostic opt-in and stripped of filenames/paths by default.

Native adapter output includes the complete plan even after failure. The parent synthesizes a **failure record**, never an extracted value, for a dead child. Native returned paths are not trusted: assets must be inside the assigned scratch/output directory, regular files, size-bounded and rehashed. Imported reports cannot choose arbitrary adapter names or executable commands.

## Parity promise

The shared comparison package must return identical semantic findings for identical canonical input data in browser and Node. Different readers are not promised identical text or rasters. Identical reader versions across platforms must be measured; any permitted render variance is described in the build profile. Never reuse a prepared report under a new reader version without reprocessing and publishing the changed manifest.
