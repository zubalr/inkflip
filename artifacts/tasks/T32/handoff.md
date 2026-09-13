# T32 handoff

- **Task:** T32 corpus run, journal, validated resume (`pdf-t32`)
- **Branch:** `work/cursor/native-completion`
- **Worktree:** `/Users/zubair/Code/Projects/pdf project/worktrees/cursor-native-completion`
- **Base:** `c696948a74bde02d19749ed4fc929179a2c94c16`
- **Implementation commit:** `2f7a2b09a26e17710aac66432cfc73ffc8227b80`
- **Evaluated HEAD:** `2e36f9bfd3b8056ea08902b453a961014119020e`
- **Scope:** `native/inkflip/corpus/`, `native/tests/corpus/`, `docs/CORPUS.md`
- **Tests:** `uv run --project native python -m pytest native/tests/corpus -q` → **9 passed**, exit 0
- **Review:** pending
- **Unresolved:** none in owned corpus scope. Resume identity is bound in `JobSpec.env` (`INKFLIP_SOURCE_SHA256`, manifest/profile/settings hashes, `INKFLIP_ALGORITHM_ID=inkflip-inspect-v1`).
