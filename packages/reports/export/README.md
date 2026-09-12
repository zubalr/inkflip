# @inkflip/reports — export (T16)

Portable evidence export foundation: selected-evidence JSON plus
script-free HTML built on an inclusion allowlist and a pre-export preview.
No ZIP format, no HTML import — those surfaces do not exist.

## Pipeline

```ts
import {
  buildExportPreview,
  projectReport,
  renderReportHtml,
  serializeReportJson,
} from "@inkflip/reports/export";

const { report, notices } = projectReport(runReport, {
  scope: "selection", // or 'run'
  findings: "all", // or explicit finding ids
  occurrences: "cited", // 'all' | 'cited' | 'none' | ids
  crops: "all", // default evidence includes selected crops
  pageRenders: "none", // opt-in
  annotations: false, // opt-in
  filename: false, // opt-in
  sourcePdf: null, // opt-in: Uint8Array or 'carry'
});
const preview = buildExportPreview(report, { notices });
const json = serializeReportJson(report); // canonical, byte-stable
const html = renderReportHtml(report); // passes assertScriptFreeHtml
```

## Contract points

- **Allowlist defaults**: `selected_text`, `crops`, `document_hash`,
  `settings`, `coverage` on; `source_pdf`, `filename`, `annotations`,
  `page_renders` off until explicitly requested. `export.included` is
  derived from the projected object, so the disclosure always matches the
  actual bytes (I09).
- **Selection projection** keeps check scope and
  `produced_occurrence_count`, prunes `retained_occurrence_ids`, and
  auto-retains context a kept finding cites (a finding never exports while
  silently dropping the reading it asserts). Unsupported findings are
  omitted and named in `export.omissions`.
- **Source opt-in** requires the actual original bytes (or `'carry'` for an
  already-embedded source asset); they are re-hashed against
  `document.sha256`/`byte_length` before inclusion. Absent or mismatched
  bytes never produce `replayable` — missing bytes mark the export
  evidence-only.
- **Determinism**: `serializeReportJson` re-emits members in schema order
  with 2-space indent + LF, so identical report values give byte-identical
  files. `report_id`, `execution_id`, `started_at`, `duration_ms` are
  excluded from the canonical digest — timing fields are the only
  permitted difference between exports of otherwise identical runs.
- **HTML**: fixed stylesheet pinned by `style-src 'sha256-…'` meta CSP,
  `default-src 'none'`, `img-src data:`; every report string escaped;
  embedded images are the sanitized PNG re-encode; source PDF is never
  embedded. Output is verified with `assertScriptFreeHtml` before return.

## Executable check

```sh
node --test tests/reports/export.test.mjs
```
