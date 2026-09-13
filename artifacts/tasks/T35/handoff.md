# T35 handoff

- **Task:** T35 local reader-upgrade example (`pdf-t35`)
- **Branch:** `work/cursor/native-completion`
- **Worktree:** `/Users/zubair/Code/Projects/pdf project/worktrees/cursor-native-completion`
- **Base:** `c696948a74bde02d19749ed4fc929179a2c94c16`
- **Source repair commit:** `5c8f52ae74d1a4ee5e10ed961ef0d964c711a9df`
- **Prior implementation:** `3d50053` example + `2e36f9b` test re-exec
- **Scope:** `examples/reader-upgrade/`, `docs/READER_UPGRADE.md`, `tests/examples/`; docs/CLI.md frozen-PATH note; proposal `docs/proposals/T35.md`
- **Tests:** `python -m unittest discover -s tests/examples -v` → **10 passed**, including ordinary-shell `run.sh`, README exports, path-with-spaces sandbox, missing-`python` / missing-venv failure paths, and offline corpus after install
- **Browser reopen:** named-profile after HTML and comparison HTML served at `http://127.0.0.1:5196/...` and opened in Chromium (`agent-browser`). Cursor IDE browser tab creation failed this session. Historical PDFium inspect is under `historical-pdfium-inspect/`.
- **Review:** pending
- **Unresolved:** Independent review is not done. `quality/upgrade-rules.json` still needs the shared-owner decision (`docs/proposals/T35.md`).
