# @inkflip/readers-pdfjs

PDF.js rendering/text reader adapter (task T09). Translates the pinned
pdf.js API surface into the canonical reader contract without deciding
truth, activating document behavior, or inventing geometry.

## Boundary (what it uses, what it never does)

- **Pinned pair only.** The caller injects the legacy build module and the
  same-origin URL of its paired worker (`pdfjs-dist@6.3.289`,
  `legacy/build/pdf.mjs` + `legacy/build/pdf.worker.mjs`, staged by T02;
  see `config/resolved-assets.json`). The adapter imports no `pdfjs-dist`
  code itself and never downloads or resolves a different version.
- **Documented API only.** `getDocument`, `page.getTextContent`,
  `page.getViewport`, `page.render`, `RenderTask.cancel`,
  `RenderTask.onContinue`, loading-task `destroy`. `getOperatorList` is
  never used as an occurrence-level visibility oracle.
- **Bytes in, never a URL.** `getDocument` receives an adapter-owned copy
  of the caller's immutable `Uint8Array` (the library takes ownership of
  the buffer it is given; the original is untouched). No `url`,
  `httpHeaders`, `withCredentials`, `range` or password paths exist here.
- **No activation.** `enableXfa:false`; no scripting/sandbox, annotation
  storage, form, link or attachment machinery is instantiated, so PDF
  actions cannot run through this adapter. Rendering uses
  `AnnotationMode.ENABLE` — static appearance streams only — and the
  recorded `annotation_mode` is `static_appearance`. (`isEvalSupported`
  was removed upstream before 6.x; the structural guarantee above is the
  real control, and the flag is still passed for compatibility.)

## Contract mapping

| Contract call | Implementation |
|---|---|
| `describe()` | Two `Reader` records + `ReaderManifest`s: `pdfjs-<v>-text` (method `native_text`) and `pdfjs-<v>-render` (method `render`, `annotation_mode: static_appearance`). Capabilities mirror CAPABILITIES.md: `render`/`native_text` supported, `reading_order` approximate (raw emitted sequence only), everything else `unavailable`. |
| `open(bytes, digest, generation)` | Verifies the supplied SHA-256 against the bytes, copies them, loads via `getDocument` under `parseTimeoutMs`. `PasswordException` → `unsupported:encrypted`. Oversized inputs are rejected. |
| `pages(handle)` | `Page` records from `@inkflip/geometry.buildPage`: `effective_view_box = page.view`, `media_box`/`crop_box` `null` (unavailable via this API — never invented), `user_unit`, `rotation`. pdf.js' own `getViewport({scale:1}).transform` is validated against `R·C`; a mismatch disables precise overlays and is recorded, not repaired. |
| `plan(handle, selection, budget)` | Deterministic `chk_p<idx>_<capability>` CheckPlans bound to the right reader id; unavailable capabilities stay planned and are answered `unsupported`. |
| `extract(handle, check, emitChunk, cancellation, job?)` | `native_text`/`reading_order` stream `Occurrence`s in awaited ≤256 chunks (the two-unacknowledged window belongs to the runtime ChunkSender). `render` returns a `RenderedRaster` (RGBA `ImageData`, actual scale, display+raster transform records, viewport verification flag). All other capabilities → `unsupported:<capability> ...`. |
| `close(handle)` | `loadingTask.destroy()` — this handle's document and worker only; a new generation's worker is a separate instance and unaffected. |

## Occurrence fidelity (I02)

- `raw_text` is the exact `getTextContent` item string with
  `disableNormalization:true` — never injected, reordered or normalized by
  the adapter. `normalized_text`/`normalization_map` are the shared
  scalar-whitespace-v1 view required by the schema validator.
- `ordinal` is the 0-based index among TextItems in emitted order;
  marked-content records are counted, never emitted as occurrences.
- Occurrence ids are hash identities over
  (run_key, reader, page, ordinal, raw_source_locator) — identical
  strings at distinct positions stay distinct occurrences.
- Geometry is always `estimated` (TextItem transform + width/height +
  font ascent/descent, mapped through the page's canonical `C`). A
  degenerate extent is `page_only`/`null`, never an invented polygon
  (I04). **No full glyph-paint or per-character provenance is claimed.**

## Rendering, bounds and cancellation (I17)

- Scale is clamped by `max_raster_pixels`/`max_raster_edge`; clamping is
  recorded as a limitation with the actual scale.
- `onContinue` is scheduled on a macrotask so rendering yields between
  operator-list chunks; text extraction yields every 512 items.
- `RenderTask.cancel` + the awaited `RenderingCancelledException` release
  the task; the adapter-owned canvas is zeroed in every outcome — done,
  cancelled, timeout, error. Successful rasters hand out `ImageData`
  pixels, not a live canvas.
- Cancellation/`timeout`/failure return terminal `CheckResult`s; an
  empty successful extraction is `completed` with zero occurrences.

## Known limits (stated honestly)

- Original MediaBox/CropBox are unavailable through the selected API;
  `page.view` is the effective view only.
- Object render modes, paint overlap, arbitrary clipping/blends/OCG,
  original annotations' metadata and OCR are all `unavailable` here.
- `reading_order` is the raw emitted sequence, not verified logical or
  screen-reader order.
- Rotation must be a quarter turn; other `/Rotate` values fail as
  unsupported page geometry rather than being guessed.

## Running the tests

```sh
bun run test:browser -- tests/readers/pdfjs.spec.ts
```

The Playwright suite builds this package for the browser with
`bun build --target browser`, serves the pinned worker, the staged
cmaps/standard-fonts/wasm/iccs and the T05 fixture bytes over a local
loopback server, and drives the adapter inside real Chromium. All
geometry expectations come from `@inkflip/geometry` plus independent
analytic anchors (the COORDINATES.md numeric example and known raster
fiducials).
