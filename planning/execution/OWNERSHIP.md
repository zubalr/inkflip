# Worktrees, leases and integration ownership

## Roles and actual tool boundary

The owner supplies product decisions/approvals and judges the visible result. A coordinator reads the DAG and dispatches ready tasks. Product workers own modules; experiment workers own candidate namespaces and cannot see untouched evaluation labels; independent reviewers inspect implementation/evidence; the integrator merges and reruns affected checks. Roles can move between sessions, but an implementer cannot approve its own material change.

No custom orchestration product is required. The operator may launch independent authorized SWE-2/Devin sessions where the actual account supports them. The documented provider capabilities are not proof of this owner's entitlement or model availability. Verify available mode, concurrent-session limit, file/repository access and artifact export in the actual account before dispatch; record only observable values. An ordinary coding session per worktree with manual dispatch is the complete fallback. No invented `devin swarm` command or provider bypass is part of this plan. No managed coding workers were launched in this planning pass.

## Worktree isolation

From the new repository, after T01 and a real initial commit:

```sh
git worktree add ../inkflip-T09 -b task/T09 HEAD
git worktree add ../inkflip-T10 -b task/T10 HEAD
```

Each task uses its own dependency environment, temp root, test outputs and artifact namespace `artifacts/tasks/Txx/`. Reserve ports through an operator lease, not hardcoded simultaneous 3000. A worker asks the OS for a free ephemeral test port and reports it, or receives a coordinator-assigned unused port. Share only immutable package caches/model bytes; never writable result directories, SQLite state, native parser instances or mutable fixture manifests. PDFium calls use process isolation, not concurrent calls from different threads.

Compute-heavy runs are admitted according to measured RAM/CPU/model residency and actual provider concurrency. Queue runs when resources are saturated; do not cut test scope or assume infinite visitor hardware because coding sessions are generous. There is no fixed pool size.

## Serialized surfaces

| Surface | Exclusive change owner | Required review |
|---|---|---|
| Canonical schema, hash algorithm, normalization contract, generated types | T03 contract owner; later designated successor | Geometry/comparison/import consumers + integrator |
| Root package manifests, lockfiles, toolchain/base image/model/static asset manifests | T02 supply-chain owner; T47 final review | Affected runtime owner + security reviewer |
| Coordinate contract / adapter mapping | T04 geometry owner | Browser and native owners |
| Root routing, CSP/headers, service-worker allowlist and deployment config | T48 deployment owner, T25 cache owner through lease | Privacy reviewer + integrator |
| Shared generator and public fixture manifest | T05 fixture owner; T21 gallery owner through lease | Geometry reviewer and rights reviewer |
| Untouched evaluation fixtures/labels and result denominator | T36 custodian only | Independent evaluator; no optimization worker access |
| Goldens, baseline expectations, quality thresholds | Evaluation custodian + owner/integrator approval | Independent reviewer; explicit before/after rationale |
| Integration branch, state acceptance, gate receipts and release tag | Integrator / T54 owner | Final reviewer and owner authorization |

Allowed task scopes overlap only as sequential responsibilities or by an explicit lease. Example: T06 establishes styles; T38 later polishes them. T09/T10 independently implement readers and cannot change the shared schema while doing so. T41–T45 only write experiment namespaces. Promotion to production requires a separate reviewed integration change under the consumer's lease, followed by all consumer tests; document this as a subtask of the owning adapter task without changing task meaning.

## Contract change proposal

Write `docs/proposals/Txx-short-name.md`: observed contradiction, exact source/version/reproducer, current invariant, recommended minimal contract delta, alternative, affected consumers/tasks/fixtures/tests, migration and rollback. Do not implement incompatible local fields first. The owner of the shared surface and integrator accept/reject with reasons; if accepted, update canonical spec/schema/types together, merge that dependency before consumers rebase, and invalidate old acceptance receipts. Pause only affected work.

## Merge discipline

Workers commit meaningful coherent changes with actual timestamps/authorship and factual agent co-author disclosure where appropriate. No artificial microcommits or backdating. PR body names task IDs, contract versions, scope, actual tests/counts/skips, screenshots where relevant, provenance/license changes and known limits. Review the implementation diff and test diff, not only the worker summary.

Integrator rebases a task onto current accepted integration, reruns its exact acceptance plus dependency consumer checks, and merges one shared-contract change at a time. Resolve conflicts semantically, never “ours/theirs” blindly. Record merge commit and reviewed head. A branch passing before rebase is not accepted after an untested merge.

Rejected candidates keep compact reproducible result manifests and source references; large scratch rasters/temp models stay untracked. Delete dormant competing production code, not evidence of the failed experiment. Worktree removal follows verified commits/artifacts and owner approval for untracked work; do not use destructive cleanup on the original repository or private files.

## Common evidence-only write allowance

Every task may add its own `artifacts/tasks/Txx/` receipt files and its own `docs/proposals/Txx-*.md` proposal. These namespaces do not grant authority over another task, a shared contract, release approvals or `execution/state.json`. State updates are requested through handoff and applied only by the coordinator/integrator. A module-scoped task may create its own package manifest, but dependency/version edits require the T02 lock-owner lease before installation or merge. Root App composition is initially T01 then T13; later gallery, cache and documentation integrations use an explicit composition lease.
