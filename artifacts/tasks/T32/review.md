# T32 independent review — corpus run, journal and validated resume

Reviewer: independent subagent (626af643).
Reviewed tip: 7875076 (implementation 2f7a2b0).

## Disposition: APPROVE

- corpus/manifest.py:79-107 rejects absolute/../symlink/digest-mismatch
  entries.
- corpus/runner.py:52-85 binds source+manifest+profile+algorithm+
  settings hashes into job env — incomplete resume cannot swap identity.
- runtime/supervisor.py:1036-1062 verifies config and report hashes
  before skipped-reuse.
- 9 corpus tests assert the above, not stubs.
- Evidence honesty: receipts non-approving; run.json binds 2e36f9b —
  merged-state re-run at integration.
