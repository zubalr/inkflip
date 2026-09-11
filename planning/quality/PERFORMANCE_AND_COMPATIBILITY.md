# Performance, resource protection and compatibility

Canonical budgets are in `config/settings.json`; numbers are targets/limits chosen for reference profiles, not achieved performance. Reference desktop: 4 logical CPU cores, 8 GiB RAM, SSD, 1366×768 or 1440×1000, DPR1/2. Mobile reference: 390×844 and a tested 4 GiB-or-better device, smaller pixel/page profile. Freeze actual browser/OS/hardware versions with each receipt; unknown hardware is not replaced by a guess from viewport width.

## Separate measurements

Measure entry download versus lazy reader/model download; file read/hash versus metadata parse; first preview versus extraction; rasterization versus OCR; alignment versus report serialization. Cold model/network, warm model, offline-complete cache and offline-missing cache are different cases. Record p50/p95/max and failures over at least 30 samples for a claimed latency distribution. Report source bytes, selected pages, raster pixels and OCR settings. Do not turn a one-off synthetic proof into a p95 benchmark.

Peak memory includes JavaScript heap, canvases, transferred buffers, WASM heaps and reader allocations. Application accounting can bound owned buffers but not every parser/browser allocation. Use real browser process measurement in the release environment and explicit garbage-collection limitations. After ten file replace/clear cycles, retained application references and tracked buffers return to baseline; allow documented browser allocator retention but investigate monotonically growing process use. Test low-memory failure injection and subsequent next-file health.

Raster request validation must check positive finite dimensions, total pixel budget and maximum edge (8192 browser / 16384 native), not only PDF file size. Browser limits are at most 4 MP per selected raster, 20 MP per OCR run, two live buffers and one active OCR worker. Mobile uses 2 MP and one selected OCR page. Downsampling is recorded and visible; a result at lower resolution is not silently equivalent to a higher-resolution baseline.

## Compatibility evidence

Run current/previous stable Chromium-family, Firefox stable/ESR and Safari current/previous major at release. Pin exact test versions. Test legacy PDF.js distribution with the same worker version, module worker creation, FontFace/CSP interaction, Blob downloads, structured OCR blocks, canvas rendering and dataURL PNG export. Missing essential module workers produces a specific unsupported-browser state; there is no unbounded fake-worker main-thread processing fallback. Missing optional OCR/SIMD leaves native text and selected supported actions intact.

Native Linux x86_64 is the initial executed reference; arm64/macOS/Windows need their own installation, subprocess termination, path, image/model and parity receipts before they appear as supported binaries. Python/Node source compatibility alone does not establish all platform behavior. Two reader versions are isolated; lock/model/build identities participate in comparison.

## Optimization policy

Prioritize first preview, bounded region OCR, chunked normalization/alignment and avoiding duplicate RGBA copies. Do not add a second model merely because an isolated accuracy measure improved. Test the full interaction's download, memory, cancellation and review burden. Any optimization that loses geometry, drops duplicate occurrences, hides incomplete checks or changes raw strings is rejected irrespective of speed.

The default source model remains one browser OCR path. A browser PDFium/WASM or second OCR family must earn an optional/adopted role through its dedicated experiment; no GPU requirement or paid endpoint is an accepted performance fallback. Large documents receive explicit page selection and partial analysis instead of silent omission.
