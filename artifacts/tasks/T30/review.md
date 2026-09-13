# T30 independent review — native inspect/report/replay CLI contracts

Reviewer: independent subagent (626af643) + coordinator verification.
Reviewed tip: 7875076 (implementation bc5f8fd + repairs through 7875076).

## Disposition: APPROVE

- cli/main.py: alias/overwrite guards (50-58), inspect dispatch
  (87-109), KeyboardInterrupt->130, declared exit codes (495-503).
- cli/pages.py: real 1-based page/range parsing with duplicate/overflow
  rejection; --region polygon intersects filtering (78-106).
- tests/cli/test_cli.py — 27 real assertions: symlink/hardlink/direct
  alias refusal, URL refusal, unknown reader, missing-profile
  fail-closed, untrusted profile path, region filtering, distinct
  multipage transform ids, replay hash-mismatch refusal, replay
  output-alias refusal under --replace-output, tampered reader-version
  replay refusal, {} model manifest not-ready, full HTML-path
  validation.
- All 16 prior withheld-batch findings verifiably repaired at source
  with dedicated regression tests (see handoff REVIEW.md mapping).
- Evidence honesty: receipts explicitly non-approving placeholders;
  run.json binds 2e36f9b — merged-state re-run required at
  integration (delta since is T35-scope + doc-only CLI.md note).
