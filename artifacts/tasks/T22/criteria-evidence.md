# T22 criterion → evidence map

Registered command: `bun run test:browser -- tests/reports/import.spec.ts`
— 11/11 pass, exit 0 at evaluated commit `d802819` (see `run.json`,
`commands.log`).

The spec file is `tests/reports/import.spec.ts` (cited here by name —
evidence arrays carry task-local artifact paths only).

## Real selected export reopens without upload

Test: *"a real selected export reopens locally — no upload,
scope/omissions shown"*. A real T16 `projectReport` selection export is
serialized canonically in-page (`serializeReportJson`, trailing LF
asserted) and offered through the real `import-file-input`. The reopened
view shows report id prefix, document sha256 suffix, verbatim
`export.mode`/`scope`/`included`/`omissions` ("Original PDF excluded.",
"Filename excluded."), exact coverage counts (3 checks / 2 completed /
1 unsupported / 119 produced / 2 retained / 1 of 1 pages), recorded
readers, the finding with both cited raw texts (`$1,000` vs `$100`), the
crop as a `data:image/png` sanitized re-encode, and limitations. Every
network request is asserted same-origin GET/HEAD/OPTIONS; the report id,
document sha and occurrence text never appear in any URL or payload;
local/session storage and cookies are empty; the URL is unchanged.

## source omission and unavailable reader explicit

Tests: *"evidence export: missing source, chooser and unavailable
readers are explicit"* and *"replayable export shows embedded source and
the environment requirement"*. The evidence export shows the verbatim
`import.source.missing` copy, the `source-file-input` chooser, the
`import.nofetch` line and `export.replay.absent` replay state; both
recorded native readers are named `unavailable` and listed under
`replay-missing-readers`; `replay-ready` is absent. The delivered
replayable example (`native-replay.inkflip.json`) shows
`source-embedded` plus the `export.replay.present` environment-required
copy — missing readers still named, readiness still false.

## malicious report cannot fetch/execute/select profile

Test: *"hostile corpus: every input rejected, zero egress, nothing
executed"*. Thirty+ hostile inputs cross the real gate: every
archive/container magic (ZIP×3, gzip, 7z, RAR, xz, bzip2, zstd, CAB,
OLE/CFB, tar), a bare PDF, UTF-16 BOMs, HTML/SVG/XML, malformed JSON,
30-level depth, duplicate keys, nonfinite and unsafe numbers, a valid
comparison artifact and a schema-valid worker_message (wrong kinds).
Report-shaped attacks — `__proto__`/`constructor`/`prototype` JSON
members, `executable`/`command`/`profile`/`$ref`/`source_url`/
`binary_path`/`fetch`/remote-asset fields — all fail closed
(PROTOTYPE→not_a_report, SCHEMA→invalid). A contract-valid report whose
display_name/finding/occurrence/annotation strings carry `</bdi>`,
`<img onerror>`, `<script>`, `javascript:` and `https://evil.invalid`
payloads reopens successfully but renders every payload as literal text:
zero `img[src^="http"]`, no new script elements, `__pwned`/`__pwned2`
never set. Egress tripwires (fetch/XHR/sendBeacon/WebSocket/
EventSource/window.open) record nothing beyond the same-origin Vite HMR
socket; every `request` event is same-origin.

## hash mismatch blocks replay

Tests: *"hash mismatch blocks replay: tampered report and asset are
rejected"* and *"source attach requires exact bytes; mismatch is never
attached"*. The delivered `tampered-report-hash.json` is rejected HASH
through the real file input with the verbatim `import.invalid` copy and
never opens (`fileState` returns to `idle`). A retained occurrence
mutated without resealing fails `HASH` at the engine; a crop asset whose
`data_base64` no longer matches its declared sha256 fails `ASSET`. On
the source side, a different real PDF is rejected
`source:length-mismatch`/`sha256-mismatch`, shows the verbatim
`import.source.mismatch` copy, and is never attached — only the exact
`mapping-amount.pdf` bytes (sha256-bound to `document`) attach.

## comparison asks for exact locally selected source reports

Test: *"comparison requires two exact local selections — no ids, no
urls"*. The compare panel carries two real file inputs; a verdict
appears only after BOTH sides are explicitly chosen. Two distinct
exports of the same document produce `compare-status-ready` with both
report ids displayed; the same file twice yields `same_report`; a
different-document report yields `incomparable` with the verbatim
`compare.incomparable` copy plus the reason; an invalid side shows
`compare-right-error` and no verdict. No id, URL or remote pointer is
ever accepted as input, and egress stays empty.

## Additional coverage (beyond the five criteria)

- *"a new report clears the previous generation before reopening"* —
  I07: `clear` event records the retired generation; every teardown
  observes generation+1; a `MessageFactory` message stamped with the old
  generation is rejected `stale_generation` by the coordinator
  authority; the replace path stands behind an explicit confirm dialog.
- *"declared-size gate rejects before any byte is read"* — a
  32 MiB+1 candidate is `too_large` with zero `arrayBuffer()` calls.
- *"installed readers plus attached source make replay readiness
  explicit"* — a reader-substituted variant (recorded readers replaced
  by the installed pdf.js identities, references remapped, resealed,
  re-exported through the real engine) marks both readers `installed`,
  and attaching the original makes `replay-ready` visible — the honest
  positive side of the availability check.
