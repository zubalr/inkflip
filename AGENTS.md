# PDF inspector implementation

Read `docs/COORDINATION.md` before starting, resuming, reviewing, or integrating a task.
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

- Beads owns live task status, dependencies, claims, and handoff notes. T01 maps
  to `pdf-t01`, and so on. The planning task list describes the original spec;
  its `planned` fields are not current status. Do not create `execution/state.json`.
- Run `python3 scripts/coordination.py ready` for dispatch candidates. Run
  `python3 scripts/coordination.py start Txx --actor <unique-session-name>` before
  editing. This checks the branch, clean/fresh base, accepted dependencies, owned scopes, and
  the five-worker limit, then claims the Beads task under a shared admission lock.
  The coordinator admits read-only reviews through `start-review`, using both
  `execution:worker` and `execution:review` labels. Never claim workers or
  reviewers directly with `bd update --claim`; both use the shared admission lock.
- One task, one branch, one writer. Multiple sessions may use the same model.
  Every writer gets its own worktree. Keep `original` on the integration branch.
- Only the coordinator merges, closes product tasks, changes acceptance metadata,
  approves baselines, and resolves shared-file ownership. Workers hand off local
  commits and evidence; they do not approve their own work.
- Local implementation commits and coordinator integration are owner-authorized.
  Remote creation, pushes, PRs, publication, deployment, and messages to other
  people require separate explicit authorization.
- Preserve unrelated changes. Never reset, clean, force-push, or overwrite another
  worktree. Worktree isolation is not a permissions boundary for evaluation labels.

## Verification and handoff

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
