# T34 handoff

- **Task:** T34 stored-run comparison, rules, immutable baselines (`pdf-t34`)
- **Branch:** `work/cursor/native-completion`
- **Worktree:** `/Users/zubair/Code/Projects/pdf project/worktrees/cursor-native-completion`
- **Base:** `c696948a74bde02d19749ed4fc929179a2c94c16`
- **Implementation commit:** `fcb0db85ca3b8112f1587cbad9d6488a4e3a81df`
- **Evaluated HEAD:** `2e36f9bfd3b8056ea08902b453a961014119020e`
- **Scope:** `packages/compare/regression/`, `native/inkflip/baselines/`, `native/tests/baselines/`, `tests/regression/`; `config/acceptance-commands.json` activation of `test:regression` (proposal `docs/proposals/T34.md`)
- **Tests:** `bun run test:regression` → **7 passed**; `uv run --project native python -m pytest native/tests/baselines -q` → **9 passed**; task totals **16 passed**
- **Review:** pending
- **Unresolved:** activating `test:regression` edits the root command registry (T01/T02 ownership). Proposal records that. `native/tests/baselines/` is implied by the effective command.
