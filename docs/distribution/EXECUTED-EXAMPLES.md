# Executed CLI example matrix (release verification)

Recorded: 2026-09-13, on this Mac (macOS arm64), against the merged main-line
CLI in this snapshot. Every row below was executed with the documented
invocation; exit codes are the real ones. The corpus/baseline/compare and
exit-5 semantics are continuously exercised by
`tests/examples/test_reader_upgrade.py` (10/10 on this branch), which executes
the documented example commands.

| Documented command | Executed result |
| --- | --- |
| `inkflip readers list --json` | exit 0 — named reader manifest (PDFium 5.8.0 / PDFium 149.0.7825.0) |
| `inkflip inspect FILE --out REPORT` | exit 0 on `fixtures/public/mapping-amount.pdf` |
| `inkflip validate REPORT` | exit 0 — `VALID`, deterministic report_id, 98 occurrences |
| `inkflip report --format html` | exit 0 — script-free HTML written |
| `inkflip replay --source … --profile …` | exit 0 with source included |
| `inkflip inspect` remote URL source | exit 2 — "Remote URL sources are not permitted; local file paths only" |
| `inkflip inspect` malformed (non-PDF) input | exit 4 (runtime/read failure, per contract) |
| `inkflip validate` unknown/invalid report | exit 2 |
| `inkflip compare-readers FILE --readers pdfium,pypdf --out DIR` | exit 0 — comparison JSON + HTML + both reports |
| `inkflip models prepare` with a non-model manifest | refused with explicit kind error |
| `inkflip corpus run` with one corrupt entry | exit 3 (partial) — corrupt job failed after its bounded retry (attempts 2), good job completed; failure retained in `index.json` |
| `inkflip corpus run --resume` over that run | exit 3, good entries resumed (`resumed: prior complete run`), corrupt entry not silently retried into success |
| `inkflip baseline create` / `compare` / exit 5 / baseline immutability | executed by `tests/examples/test_reader_upgrade.py` (10/10) on the documented example commands |
| same-origin constraint | remote fetch refusal holds inside the Docker container too (see [distribution README](README.md)) |

## Implementation defects found while executing (for the integrator)

1. `inkflip baseline create` with a schema-invalid rules file exits **4**
   (contract: 2 for invalid arguments/configuration) and prints an internal
   dump prefixed `Unexpected error: SCHEMA: {…}` instead of a clean
   diagnostic. Reproduced 2026-09-13; the rules schema itself is the native
   lane's contract.
2. `inspect --embed-source` exists in the CLI but is not yet mentioned in
   [docs/CLI.md](../CLI.md) (minor docs gap; flag works).
