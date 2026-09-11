# Local execution agreement

The owner approved local repository setup, Beads initialization, isolated Git
worktrees, local implementation commits, and coordinator integration. Workers
are launched manually by pasting task prompts into the selected local harness.
Do not infer that a prompt file means a session is running. Herdr owns terminal
execution when used from its actual managed session; this Codex session has no
Herdr caller context and does not control the user's focused panes.

## Specification and current state

`planning/` is the immutable 303-file source package. Its product requirements,
invariants, and task acceptance remain in force except for the explicit owner
decisions in `AGENTS.md` and `execution/overrides.json`. The supplied bootstrap
helper writes a second task-state file, so do not run it in this prepared repo.

The agreed stack is Bun (isolated), React/Vite/TypeScript, CSS Modules with
central design tokens, oxlint/oxfmt, Python/uv, and the package's Node comparison
bridge. Effect and a framework migration are excluded. T02 resolves and audits
real dependencies; the package pins and the local planning interpreter are
inputs, not claims that production versions have been verified.

The canonical JSON Schema remains the single TS/Python report contract. Readers,
geometry, comparison, and report packages keep the package's public interfaces.
No application feature or report format change is implied by orchestration.

Beads is authoritative for work state. Product tasks are `pdf-t01` through
`pdf-t55`; the setup chore is `pdf-setup`. Runtime task state is not exported to
a JSON/Markdown tracker. Immutable receipts are evidence linked from Beads.
The coordination CLI queries Beads in the canonical Git checkout even when
called from a linked worktree. Do not initialize another database in a worker.

## Task admission

The canonical checkout is `original`; worker checkouts are siblings under
`worktrees/<beads-id>`, on `work/<beads-id>` branches. Folder names identify work,
not providers. At most five product workers, including reviewers, may run at
once. Completed/blocked sessions must yield. The coordinator creates review tasks
with both `execution:worker` and `execution:review` labels, then admits them from
`original` with `python3 scripts/coordination.py start-review <beads-id> --actor <session>`.
Workers and reviewers must use these admission commands; direct `bd update --claim`
would bypass the shared lock and is not an approved dispatch path. The CLI counts
in-progress issues carrying `execution:worker` and serializes all admission with
a local file lock; that lock contains no task database.

For a newly assigned task, enter its checkout, inspect Git status, and run:

```sh
python3 scripts/coordination.py start T01 --actor swe2-t01
```

Replace both values for the assigned task/session. The command requires a clean
task branch equal to current `main`, an unclaimed ready Beads issue, accepted
predecessor evidence, disjoint active writer scopes, and capacity. Even a clean
branch with additional commits requires a coordinator-reviewed resume. It changes only the task claim, never Git
branches. Repeated starts fail; for an interrupted in-progress task, ask the
coordinator to verify the existing claim and assign the resume explicitly.

When a future seed branch needs refreshing, the coordinator first confirms it
has no changes or task commits, then fast-forwards it to `main`. Branches with
implementation commits require deliberate rebase/integration and new checks.
Workers may not refresh another task's checkout or silently reset a stale branch.

Admission compares directory/file scope prefixes, conservatively reserving the
literal prefix of wildcard scopes. Overlapping writers wait for the current
owner to finish and integrate. For example, T09's reader package and T33's nested
Node adapter cannot be written concurrently even though the original DAG does
not directly order them. A changed ownership agreement needs a coordinator
contract update and a Beads handoff before dispatch; an informal lease does not
bypass this guard. Read-only reviewers reserve a worker slot without a write scope.

Use the development port `5180 + task number`; the canonical viewer uses 5173.
Enable strict-port behavior so a collision fails visibly. Test servers request
separate OS-assigned ports. Each checkout owns its `node_modules`, Python venvs,
test output, scratch, generated assets, and mutable fixtures. Share immutable
download caches only. Admit one heavy OCR/corpus/performance run at a time until
resource measurements justify more. Never weaken workload limits to make a test pass.

## Batches and shared surfaces

T01 alone bootstraps the monorepo and honest command harness. After acceptance,
T02/T03/T05/T06 can run concurrently: three SWE2 sessions and one short Gemini
assignment. T04 starts after T03; T07 after T03 and T06. Start ready work as it
unblocks instead of waiting for every task in a pass.

Then parallelize disjoint reader, runtime, comparison, input, and report tasks
under the five-worker ceiling. T22/T24 are prerequisites of the first browser
gate despite their later numbers. Native adapters may begin before G1 once
their own prerequisites are accepted. Protect the complete browser and native
release, not just the demonstration.

| Shared surface | Change owner |
| --- | --- |
| Root manifests, Bun/uv locks, toolchain/model manifests | T01 initially, then T02; later explicit successor |
| Canonical schema, generated types, identity semantics | T03 |
| Coordinate transforms | T04 |
| Fixture generator and public manifest | T05; T21 after explicit handover |
| Initial tokens/primitives | T01 establishes the styles location; T06 takes styles after T01 acceptance, then T07/primitives and an explicit UI-owner handover |
| Root application composition | T01 initially, then T13 |
| Routing, cache rules, CSP/deployment | T25/T48 under explicit, non-overlapping leases |
| Held-out labels, baselines, acceptance, integration | Coordinator and independent evaluator |

Module owners request new dependencies from the lock owner instead of editing
shared manifests or running an unfrozen install. A task's own package manifest
may be edited inside its owned module, but versions/install changes require the
lock owner's coordination. The common fixture setup needed by a test remains
the fixture owner's work, not parallel edits from every reader session.

Scope additions in the override file enable T01's required bootstrap tests,
monorepo manifests, and initial styles location, T02's build tests, and T03's
native contract tests. They do not authorize changes to the coordination CLI,
its tests, the frozen planning snapshot, or acceptance policy. Propose any such
change to the coordinator with a reproducer and impact.

## Review and acceptance

Workers stop at a coherent task implementation and hand off local commits,
actual checks/counts/skips, screenshots when relevant, limitations, and any
dependency requests. They use their own `artifacts/tasks/Txx/` namespace and
must not create a reviewer approval themselves. Record model/session identity
only when observable. Material changes get a distinct reviewer; the coordinator
inspects both implementation and test changes and reruns acceptance after integration.

Only after that review and the merged-branch checks does the coordinator:

1. Commit a task acceptance receipt under `artifacts/tasks/Txx/`.
2. Store `disposition: accepted`, `accepted_commit` (the full commit containing that receipt) and
   `accepted_receipt` (its repository-relative path) in the Beads issue metadata.
3. Close the issue with the review/evidence rationale.

The coordination guard checks closed status, ancestry, and that the named receipt
exists at the accepted commit. It is a prerequisite guard, not the implementation
of product acceptance. T01's task/gate harness must validate actual commands,
test counts, semantic receipts, manual evidence, and nonrecursive gate scenarios.
Use the effective task commands and translate gate/test-record commands through
the same override function; do not execute stale pnpm examples verbatim.

Only T41–T45 may close with a measured rejection of their optional technique;
their metadata must record `disposition: rejected_experiment`. Required product
work closes with `disposition: accepted`. Missing evidence blocks consumers.
Material contract/dependency changes reopen affected tasks and invalidate their
acceptance metadata. An unrelated old green receipt cannot certify changed code.

## Release and evidence boundaries

G1 requires real browser own-file PDF/OCR, controls, geometry, cancellation,
export/reopen, and no-egress. G2 completes the public experience. G3 completes
native/corpus/version regression. G4 completes quality/security/accessibility,
evaluation, rights, and experimental decisions. T55 reviews the final candidate;
T54/G5 requires separate publication permission and actual deployment/rollback.

The current host is macOS arm64. Linux x86_64 native support requires actual
reference-environment evidence. Held-out labels require a separately restricted
environment; a different folder or ordinary Git worktree under the same user is
not access control. Manual accessibility receipts and real device results must
come from those checks. No fixture/probe success certifies the unfinished app.
