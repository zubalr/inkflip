# Browser/native capability matrix

This is the **selected support contract**, not a table of already passed product tests. “Supported” means required implementation and release tests. Actual executed scope is in `probes/results/`. Approximate results must carry that label and limitation in exported data.

| Capability | Browser PDF.js | Browser OCR | Native PDFium / pypdf | Behavior when absent |
|---|---|---|---|---|
| Visible page raster | Supported, bounded canvas | Consumes render only | Supported PDFium | Show render failure; text may remain available |
| Native searchable text | Supported | Unavailable | Supported PDFium; pypdf independent page text | “This reader returned no text” only after completed read |
| Occurrence geometry | Estimated TextItem quad / line extent | Estimated word boxes from pixels | PDFium reported char boxes; exact as API geometry, not exact visible ink | Page-only reading, no invented highlight |
| Original MediaBox/CropBox | Unavailable through selected high-level API; effective `page.view` available | Unavailable | Supported pypdf dictionary adapter | Store null original boxes, explain effective view |
| Rotation / effective view / UserUnit | Supported via viewport contract | Inherited from raster transform | Supported with explicit UserUnit correction | Block precise anchors on failed transform validation |
| Text object's rendering mode | Unavailable as occurrence property | Unavailable | Supported narrow PDFium object observation | Unsupported check, never “visible” default |
| Foreground/background/overlap | Unavailable as comprehensive check | Pixels only, no causal structure | Approximate bounded opaque-rectangle experiment | No automatic hidden/safe label |
| Arbitrary clipping/blends/OCG/historical revisions | Unavailable for full inspection | Unavailable | Unavailable for comprehensive claim | Explicit limits, no clean certificate |
| OCR over chosen page or region | Via raster adapter | Supported printed English | Supported Tesseract | Missing model / timeout distinct from unreadable pixels |
| Second OCR family | Experimental only | Not in default bundle | RapidOCR experiment | Keep one named OCR path; no silent fallback |
| Second browser PDF renderer | Experimental only | Not applicable | PDFium provides native alternate | Browser remains useful without this experiment |
| Reading-order comparison | Supported raw sequence; derived geometric sequence labeled | Supported OCR sequence | Supported, page-level for pypdf | Not screen-reader compliance proof |
| English amount/punctuation findings | Supported alignment | Supported subject to precision targets | Supported | Abstain when box/punctuation ambiguous |
| Unicode native text incl Arabic/CJK | Display/preserve supported; logical/visual order explicitly recorded | English only | Preserve supported; complex-script alignment conservative | Page-level text; OCR “language not supported” |
| Password-protected PDFs | Unsupported initial release | Not applicable | Unsupported default CLI (no stored passwords) | “Open an unencrypted copy you are permitted to inspect” |
| Forms/annotations | Static appearances only, no form actions; XFA unsupported | Reads recorded static raster | Same declared mode, renderer differences possible | Result labels annotation mode and limitations |
| Export/import | Supported JSON and escaped static HTML | Same | Same | HTML is human-readable only, not imported as code |
| Corpus/version regression | Import and view results, no hosted corpus runner | Not applicable | Required local CLI | Ask for local reports; never fetch them by URL |

## Device support chosen for release

Desktop supported matrix: current and previous stable Chromium-family (Chrome/Edge), Firefox stable and ESR, Safari current and previous major on a supported OS at release. Freeze exact versions in the release manifest; do not turn rolling language into an untested claim. Reference performance profile: 4 logical CPU cores, 8 GiB RAM, SSD, desktop viewport 1366×768, DPR 1 and 2. Functional testing adds 1440×1000 and 200% zoom.

Narrow-screen support: 360–767 CSS pixels, including 390×844. Gallery, own-file preview/native text, evidence inspection and export are required. Mobile OCR is opt-in, one selected page/region under the mobile pixel limit, enabled only after capability detection and tested on a representative 4 GiB-or-better device. A small screen alone is not a RAM detector. `navigator.deviceMemory` is an advisory when present, not a reliable universal limit; permit a conservative manual “lighter processing” profile. On unqualified mobile browsers OCR is visibly unavailable, not a misleading dead button. The core desktop browser path must still pass full G1.

Hardware acceleration, SIMD and OffscreenCanvas are detected. Single-threaded scalar WASM is the required fallback for OCR. Browser workers are not evidence that arbitrary heavy files are safe. Native reference tests run Linux x86_64 with explicit image digest and 4 vCPU/8 GiB host allocation; native processing default remains one child at a time.

Sources: [PDF.js](../research/SOURCES.md#s22), [Tesseract.js](../research/SOURCES.md#s24), [PDFium](../research/SOURCES.md#s26), [object API](../research/SOURCES.md#s27). All supported rows have tasks and tests; incomplete experimental rows never gate a useless browser demo into production.
