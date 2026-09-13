# Review notes — T47 preparation (distribution rights, SBOM, vulnerability gate)

## What this batch is

Five milestone commits on `work/zcode/distribution-completion` (base 580ef63):

1. docs repairs + dated checker facts (aed9549)
2. deterministic inventory + CycloneDX SBOM (b3b74a9, refined before evidence)
3. distribution manifest + enforceable checker + 16 tests (7d0274a)
4. license evidence + NOTICE + advisory scans (6315207)
5. integration guide + evidence records (this commit)

Milestone commits are separated so the docs corrections (T49) and the T47
tooling can be integrated independently.

## What an independent reviewer should check

- **Checker strength**: tests/release/distribution proves each failure mode
  with disposable fixtures (hash tamper, undeclared assets, license gaps,
  notice inconsistency, path escape, symlink, private content). Consider
  whether additional properties belong in the gate (e.g. nested-archive
  scanning — out of scope here).
- **Manifest honesty**: every shipped byte under apps/web/public is declared
  (unknown bucket 0; undeclared-asset check enforces it going forward). The
  digests resolve from digest-verified sources rather than duplicating them.
- **No invented rights**: license texts are copied from the installed
  distributions with per-copy provenance; the project LICENSE/copyright line
  is recorded as pending (artifacts/tasks/T47/licensing-status.md); the Git
  author identity was not used to infer a copyright holder.
- **Advisory evidence**: raw outputs committed with timestamps; scoped by
  exact frozen versions; shipped vs development distinguished. This is
  evidence of a moment, not a standing clean bill.
- **Scope isolation**: no Cursor/Devin/AGY-owned paths touched (no product
  source, root manifests, locks, schemas, fixtures, workflows, registry).
  scripts/check_dependencies.py was not modified or copied.

## Review status

- Independent review: **PENDING** — no separate qualified reviewer has
  reviewed this batch yet (this note is author self-review). Per the batch
  contract, an independent review requires an identifiable reviewer;
  anything else must be recorded as pending, which this file does.
- Acceptance: with the coordinator only, after dependent features land.
