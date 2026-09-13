# T34 independent review — stored-run comparison, rules, immutable baselines

Reviewer: independent subagent (626af643) + coordinator ratification.
Reviewed tip: 7875076 (implementation fcb0db8).

## Disposition: APPROVE (with coordinator ratification of the registry
## activation — done at integration)

- baselines/engine.py — exclusive create, no overwrite/auto-refresh
  (89-93), mandatory approved_by/rationale (94-103), refuses runs
  lacking corpus_manifest_sha256/profile_sha256 identity (127-133),
  backing reports hash-bound via report_ids with tamper detection
  (166-183).
- Comparison semantics: missing-key errored/exit3 or regressed/5 under
  policy (516-556); different documents incomparable/6 (557-585);
  reader-upgrade tolerates expected identity difference (586-588);
  coverage loss never improvement, regressed under fail_on_coverage_loss
  (592-618); rule violations regressed/5 (610-612); precedence
  2>4>5>6>3>0 (727-734, 769-772); canonical comparison.json/html +
  index.html (781-805).
- packages/compare/regression/evaluator.ts shared via Node bridge;
  7 node tests + 9 baseline tests.
- Registry: worker activated test:regression in
  config/acceptance-commands.json — disclosed in docs/proposals/T34.md,
  correct (T34 owns the command); ratified by integrator.
- regression.test.mjs needs Node >=23.6 (or 22.6+flag) for TS
  type-stripping — document minimum; fails loudly on older (honest).
- Evidence: run.json binds 2e36f9b — merged-state re-run at integration.
