# `@inkflip/reports/import` — strict local report import (T22)

Domain layer for reopening a saved `.inkflip.json` machine report on the
same machine it was exported from — with no upload, no fetch, no
execution, and no schema negotiation.

## Trust boundary

All untrusted-input validation lives in the T24 gate
(`../validation/import_gate.ts` → `importReport`). This package calls it
first and never re-parses, re-validates, or bypasses it:

- Only bounded canonical UTF-8 JSON reports are accepted — ZIP/archive,
  HTML/XML/SVG, bare PDF, UTF-16, duplicate keys, depth > 24, unsafe
  numbers, `__proto__`/`constructor`/`prototype` keys, unknown schema
  fields (executable/plugin/command/URL), wrong artifact kinds
  (comparison/worker_message/corpus_manifest), and unsupported
  `schema_version` values all fail inside the gate.
- Report hashes (`report_id`, `execution.run_key`), every asset
  `sha256`/`byte_length`, semantic references, and PNG signatures are
  re-verified; imported PNGs are decoded and re-encoded before display.
- Reports can never fetch, execute, select a reader executable/profile,
  or mount markup. Report-controlled strings are display-only data.

## Surface

| Export                                         | Purpose                                                                                                                                                                                                        |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `openReport(data)`                             | Gate + derived `SourceState` and verbatim export scope/omissions disclosure. Returns `ImportOutcome` (`ok` + `ImportedReport` or classified `ImportFailure`).                                                  |
| `classifyImportFailure`                        | Maps gate `ContractError` codes to `not_a_report` / `unsupported_version` (with declared version) / `too_large` / `invalid`.                                                                                   |
| `verifySourceCandidate(report, bytes)`         | Binds an explicitly chosen local PDF only when its byte length and SHA-256 equal `document.byte_length`/`document.sha256`. A hash is never sufficient — real bytes are required; a mismatch is never attached. |
| `readerAvailability(report, installed)`        | Matches recorded `Reader.id`s against the host-installed allowlist by exact equality; missing readers are named, never substituted.                                                                            |
| `prepareComparison(left, right)`               | Readiness for two explicitly, locally selected reports: `same_report` / `incomparable` (different document bytes) / `ready` (same document, distinct reports). Report ids or URLs alone are never input.       |
| `reportViewModel(imported, availability)`      | Inert display projection: identity, scope/omissions, coverage counts, readers (+installed), findings with cited occurrences, annotations, sanitized-PNG data URLs, limitations.                                |
| `replayView(imported, availability, attached)` | Replay readiness: `embedded`/`attached`/`missing`/`not_applicable` source standing + named missing/installed readers + `ready` (source present and zero missing readers).                                      |
| `IMPORT_JSON_LIMIT`                            | The gate's max JSON byte bound, for callers pre-checking declared file size.                                                                                                                                   |

## Executable examples

```sh
# Typecheck the package (composite project build)
bun x --no-install tsc -b packages/reports

# Lint + format this module
bun x --no-install oxlint packages/reports/import
bun x --no-install oxfmt --check packages/reports/import

# Browser acceptance (import/reopen flow, real exports, no-upload proof)
bun run test:browser -- tests/reports/import.spec.ts
```

Programmatic use (the app binds the same functions structurally):

```ts
import {
  openReport,
  readerAvailability,
  reportViewModel,
  replayView,
  verifySourceCandidate,
} from "@inkflip/reports/import";

const outcome = openReport(bytes); // Uint8Array or string
if (!outcome.ok) {
  // outcome.failure: not_a_report | unsupported_version | too_large | invalid
} else {
  const availability = readerAvailability(outcome.imported.report, installed);
  const view = reportViewModel(outcome.imported, availability);
  const replay = replayView(outcome.imported, availability, false);
  // evidence-mode export: replay.source === 'missing' until the user
  // explicitly chooses the original locally:
  const check = verifySourceCandidate(outcome.imported.report, pdfBytes);
  // check.ok === true only on exact byte_length + sha256 match.
}
```

## Honesty guarantees

- Evidence-mode reports are inspectable without the source but are
  explicitly _not_ replayable until the matching original is attached;
  nothing fabricates the missing bytes.
- `ready` in `replayView` means prerequisites are met — it does not
  claim a run happened or that a different reader could substitute.
- A report whose recorded readers are unavailable displays them by
  name as missing; the UI never silently selects another profile.
- The imported report object is preserved as immutable evidence; import
  never mutates it into a new result.
