# Local performance evidence

Receipts in this directory are **local, untracked evidence**. They are not the
implementation identity.

- Schema 2.2.0 binds `implementation.cli_sha256` / `browser_sha256` /
  `docker_sha256` (product inputs) plus fixture/settings hashes and built
  artifact bytes.
- `git_head` is informational. A notes-only commit must not force a 30-sample
  rerun. Changing native/web/runtime/config/fixture inputs must.
- Dirty product files are recorded; accept still requires the content hashes
  to match the current tree.
- Copy durable receipts into `handoffs/` rather than committing them here.
