# Inkflip — project brief

**Product:** a local-first PDF reading inspector. **Opening:** “Your PDF can look right and read wrong.”

A visitor sees a document immediately, compares a named reading with its rendered page, follows a disagreement to a region, and exports evidence. An ingestion engineer can run a local corpus before and after changing a reader, then open the same portable reports in the browser. A reading disagreement is not a verdict about truth, safety, maliciousness or which reader is correct.

## Finished scope

The release includes a carefully composed no-account public experience, six curated examples, real local PDF selection and rendering, native-text and selected-page/region OCR comparison, synchronized evidence and raw readings, uncertainty and coverage, cancellation/retry, local HTML/JSON export and JSON import. It also includes a bounded native CLI, at least PDFium/pypdf/Tesseract reader paths, version-isolated run comparisons, corpus baselines, a practical local CI example, public adversarial fixtures, evaluation, documentation and deployment/rollback instructions.

The CLI is part of the release, not deferred. The browser must independently deliver preview, extracted text, useful OCR comparison and evidence export. Native structural inspection is additional capability, not a hidden server dependency.

## Product boundary

One active user PDF per browser workspace. Corpus work is local, not a cloud document library. No accounts, organizations, billing, upload endpoints, extraction API, database, cloud history, team collaboration, webhooks, enterprise permissions or CRM. No chat, generic agent orchestration product, PDF repair, destructive sanitization, fraud detection, redaction certificate or high-stakes adjudication. Original bytes are immutable. Fixed harmless synthetic fixtures explain reader behavior; there is no arbitrary payload generator.

**Quality ambition is not schedule-limited.** Milestones depend on demonstrated capability. Runtime budgets protect devices; they do not constrain development effort or number of coding sessions. Parallel work is elastic subject to actual memory, access, provider limits and shared-file ownership.

## Audience and presentation

Primary working user: an engineer investigating a concrete ingestion failure. Curious visitors must understand the first interaction without knowing OCR or provenance. The page and discrepancy lead; configuration, raw JSON and regression details are progressively disclosed. Branding is configurable “Inkflip”, provisional and not commercially cleared.

## Definition of finished

All mandatory requirements in `execution/requirements.json` have merged tasks, executed acceptance evidence and a passed release gate. The gallery proves its claims with real bytes and pinned manifests. Own-file processing passes no-egress, cancellation and partial-result tests. A second person can inspect an exported selected finding and replay an explicitly source-included case. The local corpus example detects a known output change and a declared rule failure without updating its baseline. Supported browser/device and native profiles meet the release targets; unsupported capability remains visible. Static deployment has no application-compute or upload path. Documentation, notices, source/model inventories, tagged artifacts and real development history agree.

A completed specification is **not** an implemented feature. `PACKAGE_AUDIT.md` covers this planning delivery; `execution/gates.json` governs the eventual product.
