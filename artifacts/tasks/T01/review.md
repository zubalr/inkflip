# T01 independent review and integration

Disposition: approved for T01 bootstrap acceptance.

The implementation worker was `swe2-t01` (reported SWE-2 Max). Independent
reviewers were `codex-t01-standards` (Hume, agent
`01a09214-3fac-7fb3-8a29-d712a637c561`) and `codex-t01-spec` (Ampere, agent
`01a09214-3f56-7e12-bf15-6984c7cfdcd0`). Both reviewed the original T01 handoff,
requested changes, and approved the repaired candidate
`672731c1d67f90c027c3199869a2c83ae82e0e4f` without remaining actionable findings.

The coordinator integrated it with the existing OSS and coordination guidance
in `a92f9db1575542b3b919fde0ad8328a2dae1b81e`. Git merged the scope additions
without conflicts. The historical worker commits and source license remain
intact. The incomplete earlier file merge was preserved in a local recovery
stash before integration; it is not part of the accepted source.

## Findings resolved

- Required skipped tests previously passed. Structured unittest results and
  JUnit/custom reports now require every collected case to pass. Expected
  failures, empty suites and absent reports fail required tests.
- Empty task command lists previously succeeded. The task runner now rejects
  empty registration and requires nonempty passing test evidence.
- Gates previously accepted any committed receipt blob. They now validate the
  task, disposition, effective contract, evaluated commit, ordered command
  results, independent review, criterion coverage and evidence hashes.
- A follow-up found command labels could hide different executed commands and
  one suite's counts could conceal another suite's missing results. Executed
  argv must now match the effective command, and every required suite needs
  its own counts. Positive and negative T01/T17/G5 probes confirmed this.
- Source or evidence changes invalidate old receipts. Tests use actual
  temporary Git histories to prove acceptance, stale-code rejection,
  stale-evidence rejection and preservation across unrelated evidence commits.

## Acceptance evidence

The coordinator ran these checks on the merged candidate. Exact output is in
`coordinator-commands.log`, with structured records in `run.json` and
`integration-checks.json`.

| Check | Result |
| --- | --- |
| `bun run verify` | 66 passed, 0 failed, 0 skipped: 44 bootstrap, 2 native boundary, 20 coordination |
| `python3 scripts/task_acceptance.py task T01 --report artifacts/tasks/T01/run.json` | 44 passed, 0 failed, 0 skipped |
| Full diff whitespace check from `20543a3` | Passed |
| Current origin checkout | HEAD remained `94f35ce9f9beb1640ddebdc2c72aa379ecebb004`; the previously logged Dockerfile modification remains |

All four T01 criteria have evidence: the command registry is exposed through
Bun scripts; missing/empty/skipped required suites fail; the origin license is
byte-exact and the sibling repository was only read; no install, publication or
product achievement is implied by the scaffold. The planning checksum test
passes. The coordinator normalized trailing whitespace in the worker command
log; the original bytes remain in worker evidence commit `182a3a8`.

## Limits and next owner

This acceptance covers bootstrap and the command/evidence harness. No browser
PDF/OCR product flow or release gate passed. The worker's screenshot remains a
labelled static approximation. T02 owns dependency resolution, locks and the
first real build. Pytest and Playwright reporter interfaces were checked against
their official documentation; live adapter verification awaits those resolved
tools. The installed Node v26.7.0 adapter was exercised directly: one passing
test passed, and a passing test plus a skipped required test failed. That does
not certify the planned Node version. T02 must verify the selected runtime.

Acceptance structure and conservative freshness rules are documented in
`docs/ACCEPTANCE.md`. Manual evidence remains a reviewer responsibility.
