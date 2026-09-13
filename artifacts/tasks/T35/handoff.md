# T35 handoff

- **Task:** T35 local reader-upgrade example (`pdf-t35`)
- **Branch:** `work/cursor/native-completion`
- **Worktree:** `/Users/zubair/Code/Projects/pdf project/worktrees/cursor-native-completion`
- **Base:** `c696948a74bde02d19749ed4fc929179a2c94c16`
- **Implementation commits:** `3d50053c204df23d08a0b7b5871ee40558e63617` (example) + `2e36f9bfd3b8056ea08902b453a961014119020e` (frozen-interpreter re-exec)
- **Evaluated HEAD:** `2e36f9bfd3b8056ea08902b453a961014119020e`
- **Scope:** `examples/reader-upgrade/`, `docs/READER_UPGRADE.md`, `tests/examples/`; proposal `docs/proposals/T35.md` for `upgrade-rules.json` vs planning `quality/upgrade-rules.json`
- **Tests:** `python -m unittest discover -s tests/examples -v` (harness maps `python` → `python3`) → **5 passed**, exit 0
- **Browser reopen:** executed at `http://127.0.0.1:5195/mapping-control.html` in Cursor IDE browser view `f7c6ed`. Screenshot `artifacts/tasks/T35/mapping-control-browser.png`. See `browser-reopen.md`.
- **Review:** pending
- **Unresolved:** This host has no `python` launcher; tests re-enter `native/.venv`. Independent review is not done.
