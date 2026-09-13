# T35 independent review — runnable reader-upgrade CI example

Reviewer: independent subagent (626af643) + coordinator verification of
the two known repair gaps.

## Disposition: APPROVE

- run.sh:7-34 — hard exit 127 + setup guidance when
  native/.venv/bin/python missing; sets PYTHONPATH/INKFLIP_PROFILES_DIR;
  installs before/after profiles; runs both corpus jobs; creates
  approved baseline; preserves compare exit 5 as declared-rule result;
  emits after-HTML. Verified by coordinator at source level.
- Named-profile evidence (named-profile-run/): ordinary-shell run with
  python absent from PATH, real pypdf 5.9.0 vs 6.18.0 isolated
  interpreters, profile_name=after, chk_pypdf_text_p0, served HTML
  SHA-256-verified, baseline byte-identical after failed compare.
  Coordinator inspected the browser screenshot: named-profile report
  content confirmed.
- historical-pdfium-inspect/ correctly preserved and labelled
  historical, not silently reused.
- Cursor IDE browser reopen failure disclosed as blocked
  (browser-reopen.md) — no fabricated success.
- tests/examples/test_reader_upgrade.py re-enters the frozen
  interpreter; 10 tests.
- docs/proposals/T35.md: owned examples/reader-upgrade/upgrade-rules.json
  substitutes the out-of-scope quality/upgrade-rules.json — ratified;
  quality/ copy deferred to shared-owner.
- Evidence: run.json binds 5c8f52a; 7875076 adds evidence only —
  merged-state re-run still performed at integration for freshness.
