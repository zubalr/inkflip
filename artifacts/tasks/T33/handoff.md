# T33 handoff

- **Task:** T33 version-isolated reader profiles (`pdf-t33`)
- **Branch:** `work/cursor/native-completion`
- **Worktree:** `/Users/zubair/Code/Projects/pdf project/worktrees/cursor-native-completion`
- **Base:** `c696948a74bde02d19749ed4fc929179a2c94c16`
- **Implementation commit:** `6a28e59359269a68f6f7cdbe02a9e09bea54d797`
- **Evaluated HEAD:** `2e36f9bfd3b8056ea08902b453a961014119020e`
- **Scope:** `scripts/install_reader_profile.py`, `native/inkflip/profiles/`, `native/tests/profiles/`, `packages/readers-pdfjs/node/`
- **Tests:** `uv run --project native python -m pytest native/tests/profiles -q` → **8 passed**, exit 0
- **Review:** pending
- **Unresolved:** generated profile venvs live under `/profiles/` (gitignored, root-anchored). Root `bun` workspaces do not include `packages/readers-pdfjs/node`; that tree has its own `bun.lock`.
