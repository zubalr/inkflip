# Architecture

This describes the system as implemented in this snapshot, with pointers to
the frozen planning documents that specify it. Planning references are
included for traceability — the source of truth for intent is
`planning/`, for code it is the code, and for what currently works it is
[limitations.md](limitations.md).

## System shape

```
┌──────────────────────────────────────────────────────────────────┐
│ Browser (static client, no server compute)                       │
│                                                                  │
│  Home / Workspace UI (apps/web, React + CSS Modules)             │
│    │                                                             │
│    ├─ readers-pdfjs   → PDF.js 6.3.289 render + text extraction   │
│    ├─ readers-tesseract → Tesseract.js 7.0.0 OCR of rendered px   │
│    ├─ runtime         → bounded run lifecycle, cancel/replace    │
│    ├─ geometry        → canonical page space + transforms        │
│    ├─ compare         → normalization + conservative alignment   │
│    ├─ findings/explanations → findings, coverage, plain language  │
│    └─ reports         → portable JSON / script-free HTML export  │
│    └─ contracts       → one schema, deterministic report identity│
│                                                                  │
│  Same-origin static assets: WASM engines, eng.traineddata,       │
│  cmaps, standard fonts, ICC profiles (no CDN at runtime)         │
└──────────────────────────────────────────────────────────────────┘
          ▲ JSON reports (import/export, strictly validated)
┌─────────┴────────────────────────────────────────────────────────┐
│ Local Python side (native/, uv-pinned 3.13.15)                   │
│  readers: pdfium (pypdfium2 5.8.0), pypdf 6.18.0,                │
│           rendered-region tesseract                              │
│  checks/structure: bounded structural observations               │
│  runtime: supervised workers, atomic partial artifacts           │
│  (planned, not built: the `inkflip` CLI over these modules)      │
└──────────────────────────────────────────────────────────────────┘
          ▲ shared report/schema identity
┌─────────┴────────────────────────────────────────────────────────┐
│ Node comparison bridge (packages/compare)                        │
│  lets browser and Python sides run the same comparison code so   │
│  their outputs can be checked against each other                 │
└──────────────────────────────────────────────────────────────────┘
```

## The investigation pipeline

1. **Open.** The user's file is read through the File API and validated
   locally (T08). Original bytes are treated as immutable; the app keeps a
   digest for identity but never writes back to the source.
2. **Render.** The PDF.js adapter (T09) rasterizes the selected page to
   canvas and extracts the document's own text layer with per-item geometry.
   Rendering and reading are deliberately separated: the picture and the text
   layer are independent witnesses.
3. **OCR on request.** For a selected page/region, the Tesseract.js adapter
   (T10) recognizes the rendered pixels. Model/engine assets are staged
   same-origin ([config/resolved-assets.json](../config/resolved-assets.json));
   initialization is cancellable (the pinned patch exists for this).
4. **Run lifecycle.** The runtime package (T11) bounds concurrent work,
   propagates cancellation, and makes replace-in-flight the only way a view
   can be stale-proof: a superseded job's results are discarded before they
   can reach the UI.
5. **Normalize and align.** Raw reader output is normalized into the
   canonical coordinate space (unrotated physical page points, ADR-004) and
   aligned geometry-first (T12, ADR-006). Alignment is conservative: when the
   correspondence is ambiguous, the comparator abstains and records
   uncertainty instead of forcing a match.
6. **Findings.** Differences that survive alignment become findings (T14)
   with kind, occurrences, per-reader readings and plain-language
   explanations. Coverage (what was actually read) is tracked alongside.
   Finding kinds and copy are constrained by invariant I06: a difference is
   never translated into a verdict about truth, fraud or safety.
7. **Export.** Reports (T16) are portable JSON or script-free HTML with all
   evidence images inlined as strict data URLs, no external fetches, and no
   local filesystem paths. Identity is deterministic: the same inputs seal to
   the same report identity (ADR-005). Import (T22) validates strictly and is
   fuzz/hardening tested (T24).

The native side mirrors steps 2–5 with independent readers (T26–T28) so a
disagreement can be established between genuinely different implementations
(browser JS vs Python/C), under a supervisor that yields atomic partial
results even when a child crashes (T29). The Node comparison bridge (T31)
runs the same comparison code on both sides to check parity of the
comparison itself.

## Contracts and identity

`planning/contracts/inkflip.schema.json` is the single JSON Schema for
evidence reports; TypeScript types are generated from it
(`packages/contracts`). Report identity is canonical (hash of normalized
content, not of serialization accidents), which is what makes stored runs
comparable later — the foundation the corpus/baseline tooling will build on.

## Why static and local (the security posture)

- **No server compute.** The app is a static bundle (ADR-001); there is no
  extraction API to attack or to trust, and the deployment target has no
  application compute path (the preflight check for that is a pending task).
- **No egress by construction.** The browser path has no upload code. The
  claim is continuously verified by the privacy canary suite
  ([tests/privacy/README.md](../tests/privacy/README.md)), which inspects
  requests, workers, WebRTC, storage and downloads against a marked document.
- **Same-origin assets.** WASM engines and model data ship with the app. This
  removes the CDN from the trust base and makes offline behavior coherent.
- **Bounded local processes.** Native work runs under a supervisor with
  resource budgets, atomic partial results, and explicit cleanup (ADR-008,
  T29); native containment/failure-recovery hardening (T40) is still pending.
- **Strict import.** The only externally supplied data the app parses beyond
  the opened PDF is an exported report; its parser is schema-validated,
  size-bounded and adversarially tested.

## Invariants this code answers to

From `planning/architecture/GLOSSARY_AND_INVARIANTS.md`, the four bound to
the documentation and reporting surface:

- **I06** — disagreement/consensus do not establish truth, fraud or safety.
- **I13** — source/model/adapter identity accompanies every run.
- **I16** — licenses and material influences are retained; authorship and
  executed work are never invented.
- **I18** — claims derive from exact shipped artifacts and stated test
  populations ([planning/launch/CLAIMS_LEDGER.md](../planning/launch/CLAIMS_LEDGER.md)).

## Native runtime details

- `native/inkflip/readers/` adapters isolate each engine behind the shared
  report contract; PDFium's UserUnit handling and pypdf's page-only geometry
  are explicit adapter behaviors with their own tests.
- `native/inkflip/runtime/supervisor.py` bounds child processes, retries only
  where policy allows, and writes per-file artifacts atomically (temporary
  sibling + rename) so a killed run never leaves a half-written report.
- The Python environment is pinned exactly (`requires-python == 3.13.15`,
  `uv.lock`); `uv run --frozen` is the only supported invocation.

## Deliberate non-goals

No accounts, upload endpoints, extraction APIs, cloud storage, collaboration,
fraud scoring, document repair or sanitization, redaction certificates, or
agent orchestration as a product feature. The product boundary in
[planning/PROJECT_BRIEF.md](../planning/PROJECT_BRIEF.md) is the contract;
this snapshot implements a subset of it ([limitations.md](limitations.md)).
