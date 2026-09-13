# PDF inspector implementation

Read `docs/NATIVE_PASSES.md` and `docs/HOMEBASE.md` before starting, resuming,
reviewing, integrating, or transferring a task.
Read `planning/PROJECT_BRIEF.md` and `planning/architecture/GLOSSARY_AND_INVARIANTS.md`
once per session, then only the assigned task's inputs.

## Owner decisions

- Build the complete browser inspector and local native/corpus/regression tool.
- Use Bun workspaces with `linker = "isolated"`, React, Vite, TypeScript,
  CSS Modules, central semantic design tokens, oxlint, and oxfmt. Do not add Effect.
- Preserve the package's design direction, shared JSON Schema, coordinate and
  report contracts. Python/uv and the explicit Node comparison runtime remain.
- `execution/overrides.json` adapts the frozen package's paths and commands.
  `python3 scripts/coordination.py task Txx` prints the effective task contract.
- Keep `planning/` byte-identical to the delivered snapshot. Put accepted changes
  in owned implementation files and recorded decisions outside it.

## Work ownership

- Beads owns live status, dependencies, claims, notes and acceptance. Product task
  T01 maps to pdf-t01. Static planning and passes.json are not live task state.
- Devin Local SWE-2 on the Mac is the sole integration lead, hard-work owner
  and Beads writer. Mac Antigravity and Homebase ZCode consume assignments.
  Codex has yielded coordination and its continuation heartbeat stays paused.
  Only the canonical integration checkout on main dispatches with `native_pass.py dispatch`.
  Owner-authorized setup issue pdf-enc may install/reconcile this workflow; product
  acceptance remains Devin-owned. Read docs/plans/independent-workbenches/README.md.
  Do not use the historical local-only `coordination.py start`/`start-review`.
- Native apps own execution. Use their own delegation and resume facilities.
  Admit useful independent work with disjoint ownership and review capacity;
  stay within five active execution slots total, including descendants. Allocate by independent
  scope, memory/load, review throughput and actual running descendants, not
  historical cards. Configured finite budgets still bound their app (codex
  stays zero); honor lower harness limits. Record allocations in Beads;
  writers yield before review. Do not spawn idle recursive supervisors.
- One branch, one writer, one isolated checkout. Preserve existing work. Never
  reset, clean, force-push or overwrite another checkout. Mac worktrees share
  the canonical Beads database. Homebase pulls a native read replica through
  the project SSH relay; only the Mac coordinator publishes authoritative state.
- The owner explicitly approved private GitHub access, source sharing with the
  selected harnesses, commits, pushes, review and integration. The current
  execution uses Mac Devin Local SWE-2, Mac Antigravity and Homebase ZCode.
  Cloud is stopped. Only the Devin coordinator
  accepts/closes product tasks after independent review and real merged checks.
  T54 public publication/deployment and messages to people require approval.
- Continue ready granted work across independent workbenches; do not stop at each ticket.
  Admission uses fresh accepted dependencies, not a global pass barrier.
  Pass completion still requires its checkpoint and required gates.
  Beads pass checkpoints require listed tasks and actual gate evidence.
- Worktrees are not an access boundary for held-out evaluation labels.

## Implemented commands (T01)

- `bun run verify` — registered bootstrap, native-bootstrap and coordination
  suites plus registry checks. It tests existing behavior only.
- `bun run <name>` for `test:browser`, `test:privacy`, `test:a11y`,
  `test:visual`, `test:fixtures`, `test:regression`, `test:native`, `build`,
  `check:static-dist` — declared commands that fail explicitly until their
  `requires` prerequisites land (see `config/acceptance-commands.json`).
- `python3 scripts/task_acceptance.py list|run <name>|task Txx|self-check`
  — the command harness; an empty or missing test registration always fails.
- `python3 scripts/gate.py G1..G5|pre-release` — nonrecursive gate runner; verifies Beads
  acceptance receipts, executes adapted scenario commands, writes a fresh
  receipt only on success.
- `python3 -m unittest discover -s native/tests/bootstrap -v` — native boundary
  checks; stdlib only until T02 resolves native dependencies.

## Verification and handoff

See `docs/ACCEPTANCE.md` for structured test outcomes, committed acceptance
receipts, manual evidence and freshness requirements.

- Inspect the effective acceptance commands before editing. Execute real checks;
  missing tools, empty test collections, skipped required cases, and absent manual
  evidence cannot pass. Application commands do not exist until their tasks add them.
- A worker records implementation commits, exact commands/results, relevant
  screenshots, limitations, and dependency requests in its own task artifacts.
- Contract, dependency, fixture, or token changes require the named shared owner.
  Use a minimal reproducer for mismatches; preserve geometry, raw text, duplicate
  occurrences, incomplete coverage, original bytes, and immutable baselines.
- Follow the local engineering gates. Do not raise complexity limits, weaken token
  rules, suppress type errors, or refresh goldens to conceal a failure.
- Homebase must never be rebooted, shut down, suspended, or power-cycled.
