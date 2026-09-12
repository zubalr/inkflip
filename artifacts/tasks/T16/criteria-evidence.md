# T16 criterion → evidence map

Registered command: `node --test tests/reports/export.test.mjs` — 15/15 pass,
exit 0 at evaluated commit 35f524b (see run.json, commands.log).

## Preview equals decoded contents
Test: *"preview is measured on the projected object and equals decoded
contents"*. `buildExportPreview` is called on the final sealed projection;
the test decodes the exported `.inkflip.json` back through the T24 import
gate and asserts every preview count/byte figure against the decoded
object — not against the request or UI state. Byte totals are recomputed
from decoded asset payloads, not declared metadata.

## raw text/geometry/coverage survive
Tests: *"raw text, geometry and coverage denominators survive the export"*
and *"selection projection prunes retained ids and keeps produced counts
honest"*. Retained occurrences keep `raw_text` byte-exact plus
`normalized_text`/`normalization_map`; geometry keeps precision, polygon,
basis and transform_ids with the referenced transforms carried over;
checks keep original `produced_occurrence_count` while
`retained_occurrence_ids` prunes to the kept set; `plan.selected_pages`,
`document.page_count`, readers/settings/model_hashes and budgets persist
through re-validation of the sealed projection.

## no source PDF without explicit opt-in
Tests: *"source PDF stays out by default and enters only on explicit
verified opt-in"* and *"filename and notes stay off by default and honor
opt-in"*. Default projection carries no `source_pdf` asset and nulls
`document.source_asset_id`; opt-in bytes are verified against
`document.sha256`/`byte_length` before inclusion (mismatch → ContractError
SOURCE); `'carry'` reuses only an already-embedded verified asset. HTML
never embeds source bytes (image embeds are `image/png` only).

## script-like strings escaped
Tests: *"script-like report strings are inert in JSON and escaped in
HTML"*, *"exported HTML of every delivered example passes the script-free
guard"* and *"embedded crops are sanitized re-encodes, never the stored
bytes"*. Hostile strings rotated through title/explanation/raw_text/
reader names appear escaped (`&lt;script&gt;` etc.) or not at all;
`renderReportHtml` runs `assertScriptFreeHtml` on the final bytes before
return; embedded crops are the bounded `sanitizePng` re-encode, verified
byte-unequal to a stored payload carrying a hostile ancillary chunk.

## missing bytes marked evidence-only
Test: *"missing or unverifiable asset bytes mark the export
evidence-only"*. Payloads failing base64/length/sha256 audit are dropped,
recorded in `notices.missingAssetIds` and `export.omissions`, and the
export can never become `replayable`; an explicit source request whose
bytes are absent sets `requestedSourceMissing` and stays evidence-only
instead of throwing away the rest of the evidence.

## export is deterministic aside from excluded run timing fields.
Tests: *"identical inputs give byte-identical JSON and HTML; timing
fields are the only permitted delta"* and *"canonical serialization is
byte-stable under member reordering"*. Two runs differing only in
`execution.execution_id`/`started_at`/`duration_ms`/`report_id` produce
different sealed ids but share `reportDigest`; identical projections
serialize byte-identically; object member insertion order cannot affect
output because every schema member is re-emitted in declared order.
`exportFileName` derives from `report_id` + mode only.
