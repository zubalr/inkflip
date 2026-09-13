# T33 independent review — explicit version-isolated reader profiles

Reviewer: independent subagent (626af643).
Reviewed tip: 7875076 (implementation 6a28e59).

## Disposition: APPROVE

- profiles/registry.py:91-158 — name regex, reserved built-ins,
  path-like/.json/symlink descriptor rejection, reader allowlist
  (pypdf/pdfjs-node), executable existence check, wrapper resolves to
  bundled wrapper with digest verification.
- profiles/adapter.py:52-89 — shell=False, proxy/env filtering,
  worker-reported version must equal profile version.
- pypdf_worker.py fails closed; install_reader_profile.py installs
  pinned versions into isolated interpreters.
- readers-pdfjs/node pins pdfjs-dist@6.3.289; bun.lock carries sha512.
- 8 profile tests. TestProfileInstall does real pip installs — cold
  offline re-runs may skip; noted for CI planning, not a defect.
- Evidence: run.json binds 2e36f9b — merged-state re-run at integration.
