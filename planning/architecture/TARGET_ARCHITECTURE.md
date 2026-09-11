# Target architecture

## Selected composition

```text
Cloudflare Workers Static Assets (no Worker script)
  index / versioned JS, CSS, WASM, models / owned samples / docs
                    | static GETs only
                    v
  React document-first workspace ── export/import ── local JSON / static HTML
       | File/ArrayBuffer (memory only)          ^
       |                                        | same contract
       + PDF.js parser worker                   |
       + bounded canvas renderer                |
       + Tesseract.js OCR worker                |
       + alignment worker                       |
                                                |
  Local Python CLI supervisor ── isolated reader child processes
       | PDFium native + structural observations
       | pypdf native text + raw page metadata
       | Tesseract subprocess on bounded render
       | optional separately installed Node PDF.js profile
       + per-file reports / corpus index / baseline / stored-run comparison
```

The public app has no API, database, public file upload, SSR, third-party analytics or paid OCR fallback. A network diagram must not be mistaken for a server requirement: all arrows carrying user data stay on the visitor's device. Ordinary static HTTP requests still disclose normal connection information to the host.

The frontend is Vite + React + TypeScript. Static Next.js is technically viable, but this one-workspace browser application gains little from its server/client routing conventions. Vite's explicit worker/asset build and static output fit the boundary. There is no Cloudflare full-stack Vite plugin or application Worker entrypoint. [S29](../research/SOURCES.md#s29), [S30](../research/SOURCES.md#s30), [S33](../research/SOURCES.md#s33).

## Module boundaries

`packages/contracts` owns the canonical schema, generated TypeScript and precompiled browser validator. Python validates the same schema; it does not maintain an independent Pydantic truth model. `packages/geometry` owns affine transforms, page boxes, polygons and inverse tests. `packages/compare` owns normalization, alignment, grouping and rule evaluation; no reader calls are permitted there. `packages/reports` owns projections, asset inclusion, hashing and static HTML. `packages/readers-pdfjs` and `packages/readers-tesseract` wrap PDF.js and Tesseract.js; it cannot import UI components. `apps/web` owns presentation and lifecycle coordination, not hidden extraction heuristics.

`native/inkflip` owns CLI argument parsing, manifests, parent process supervision and Python adapters. The native comparison path invokes the shared Node comparison package as an installed, fixed executable protocol, rather than reimplementing alignment in Python. This makes browser/native finding semantics genuinely shared. Python-only metadata readers still emit the same report. Native installation therefore requires Node for comparisons; basic `inspect --reader pdfium` and report validation remain Python-capable. The release installer checks Node explicitly and fails with an actionable message for commands that require it.

Native version profiles execute the fixed adapter entrypoint inside an explicitly owner-created venv/container/Node workspace. Profiles record identities, not arbitrary shell strings. A report is never allowed to install or execute a plugin. The command supervisor selects from an installed allowlist by profile ID.

## Data flow

1. Validate byte length and PDF signature, then parse in a bounded worker. Hash original bytes locally. PDF header is only a plausibility check, not a safety certificate.
2. Read page count and effective page geometry. Ask for pages before rendering a large document. Do not eagerly rasterize every page.
3. Create an immutable check plan with versioned settings and budgets. Results are keyed to this plan, current generation, document digest and job identity.
4. Stream native-text occurrences in bounded chunks. Retain raw API strings and full occurrence identities. Send acknowledged chunks to alignment; do not accumulate unbounded worker messages.
5. Render the selected page or region. Record actual viewport matrix, annotation mode, pixel dimensions, clipping and downsampling. OCR receives only this bounded raster and its inverse transform.
6. Align two named readings. Ambiguity stays ambiguous. Explanations are deterministic templates tied to facts, not LLM-generated conclusions.
7. Project the selected evidence into an export. Preview exact inclusions before writing local JSON or script-free HTML. Reopen using the same validator and renderer-independent viewer.
8. CLI corpus runs write each completed file atomically. Stored-run comparison retains per-file evidence and distinguishes configuration changes, errors and coverage changes.

## Browser rendering decision

PDF.js parsing uses its documented worker. Rendering uses a bounded canvas on the main thread with `RenderTask.onContinue` yielding and a cancellable task. We do **not** claim PDF.js renders arbitrary files entirely in a Web Worker or that OffscreenCanvas is universal. One render is active; one previous raster may remain for comparison. Offscreen rendering is an isolated performance experiment, not a prerequisite. If yielding is inadequate for selected reference files, reduce the render tile/pixel budget and optimize the supported renderer path; do not hide a server fallback. [S22](../research/SOURCES.md#s22).

Tesseract.js consumes raster images, not PDF files. It uses one dedicated OCR worker and an explicitly requested structured block output. The language and core assets are same-origin, versioned and integrity checked. A missing model disables OCR with a visible reason; native text remains usable. [S24](../research/SOURCES.md#s24).

## Structural depth

Browser `getTextContent` is not a glyph visibility oracle. Native PDFium object render modes and geometry plus pypdf page dictionaries add narrow observed properties. Basic object-mode inspection is required; complete blend/clipping/OCG/historical-object reconstruction is not. Rectangular paint overlap is a separately labeled approximation with an acceptance experiment. PyMuPDF is not in the primary distribution; its convenient trace API does not justify an accidental license change. [S26](../research/SOURCES.md#s26), [S27](../research/SOURCES.md#s27), [S39](../research/SOURCES.md#s39).

## Failure boundaries

Worker termination protects responsiveness but is not a guarantee against browser vulnerabilities or tab OOM. Native subprocesses and containers bound hangs/privileges but are not infallible sandboxes. Failed checks produce terminal error records. Successful occurrences from other completed checks remain inspectable; no partial file silently replaces a complete baseline.

No runtime component contacts an LLM. Coding agents are development resources only. Their provider, mode and concurrency can change without changing this architecture.
