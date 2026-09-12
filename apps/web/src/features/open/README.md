# `features/open` — local file intake (T08)

Handles offering/dropping/replacing one PDF through the file lifecycle
`idle → validating_file → loading_metadata → selecting` with local checks
only — nothing is uploaded, hashed for transport or persisted (I01/I08).
The filename is a display label, never an identity and never placed in a
route or request.

## Layout

| File | Role |
|---|---|
| `types.ts` | `FileCandidate` (structural File subset), `OpenError` kinds, `OpenHost`/`OpenAdapter` contracts, `OpenedDocumentInfo`/`PageMeta` |
| `limits.ts` | Desktop/mobile safety profiles mirrored from `planning/config/settings.json` (20 MiB/1000 pages/20 native pages vs 10 MiB/5 pages) and the environment resolver |
| `copy.ts` | Canonical strings mirrored verbatim from `planning/product/copy.json` |
| `validate.ts` | Size gate (metadata only, **before any byte read**), declared-MIME hint and ≤1 KiB `%PDF-` header sniff |
| `controller.ts` | `OpenController` — offer → validate → `adapter.open` → `adapter.pages` → `metadataLoaded`, mapping reader failures to distinct local errors; generation-first replacement through `requestClear("replace")` |
| `FileDrop.tsx` | Drop zone + hidden file input + privacy statement (T07 primitives) |
| `OpenWorkspace.tsx` | Composition: drop/replace (T07 `ReplaceConfirmDialog`), document panel, `PagePicker`, `RegionEditor`, plan display |
| `mount.tsx` / `preview.html` | Dev/test harness wiring the **real** pinned pdf.js pair, T09 adapter and T11 coordinator; `?profile=mobile` pins the mobile profile; `window.__t08` exposes the collaborators + event log |

## Distinct local errors

| `OpenError.kind` | Trigger | Copy |
|---|---|---|
| `not_pdf` | declared non-PDF MIME, missing `%PDF-` magic, empty file | `input.notpdf` |
| `too_large` | declared size over profile cap (no bytes read) | `input.toobig` |
| `encrypted` | reader `PasswordException` (`encrypted:*` reason) | `input.encrypted` |
| `malformed` | parser failure (`parser_error:*`, unreadable bytes) | `input.malformed` |
| `too_many_pages` | page count over `max_document_pages` | `pages.toomany` |
| `open_timeout`/`open_failed` | load deadline / lifecycle violation | `input.malformed` + detail |

## Generation-first replacement (I07)

A new offer while a document is live calls `host.requestClear("replace")`;
the coordinator increments `generation` **before** owned teardown runs. The
controller registers the pdf.js handle via `host.own(...)` with a teardown
that emits `{type:"teardown", generation}` into the controller event log —
the recorded generation is always the new one, and stale messages are
rejected by the message authority, not merely hidden.

## Usage

```ts
const adapter = createPdfJsReader({ pdfjs, workerSrc, cMapUrl, … });
const coordinator = new RunCoordinator();
const controller = new OpenController({ host: coordinator, adapter, profile });
const outcome = await controller.offer(file); // File satisfies FileCandidate
```

The preview harness is served by Vite at
`/src/features/open/preview.html` (see `tests/browser/open.spec.ts`).

## Explicit boundaries

- Run *execution* (dispatching checks to workers, OCR, export) is owned by
  later tasks — `startRun` here freezes the plan and dispatches intents,
  which the preview lists; no workers are spawned.
- `apps/web/tsconfig.json` cannot resolve cross-package `.ts` specifiers
  (see `state/store.ts` note), so the feature types are structural and only
  `mount.tsx` imports the concrete packages.
