# T40 handoff

- **Task:** T40 native containment (`pdf-t40`)
- **Branch:** `work/cursor/native-assurance`
- **Worktree:** `/Users/zubair/Code/Projects/pdf project/worktrees/cursor-native-assurance`
- **Base (repair checkpoint):** `78750769d1a29d58b7b79f91c1c8ffd749dc4eac`
- **Implementation commit:** `efa11d4b97ec94b732216524aea4f405b629821f`
- **Scope:** `build/native/`, `scripts/run_native_container.sh`, `native/tests/security/`, `tests/containment/`, `artifacts/containment/`, `docs/proposals/T40.md`
- **Tests:** `uv run --project native python -m pytest native/tests/security -q` → **9 passed**; `python3 tests/containment/run.py` → **6 passed**, container criterion **blocked**
- **Review:** pending
- **Unresolved:** Docker daemon/OrbStack not running; T47 hashed wheels absent. Native OS supervisor tests are not a substitute for the container no-network digest record.
