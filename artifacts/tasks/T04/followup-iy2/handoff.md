# pdf-iy2 repair evidence

Source commit: `9ac2dc3d4d88693bfb5cf1c99d46afd05b3cac6e`.
Base: `37ae85e6e4a19ddebe41e1ff838f324cc52e7342`.
Branch: `work/codex/pdf-iy2`. Writer: this Codex task. Ready for parent review.

Zero-area clipped polygons now return outside/null while preserving source coordinates. The shared inverse-pair error function requires a nonempty array of finite two-number probes, covering checkedInverse and makeTransform without changing valid extents or omitted defaults. The existing conservative polygon construction threshold is unchanged; clipping checks exactly zero area. Tests directly pin mapPoint composition and pointInPolygon winding/shape/tolerance behavior. The deterministic sweep now asserts its completed population and bounded finite maximum instead of a vacuous nonnegative assertion.

Changed source/test paths:
- packages/geometry/src/affine.ts
- packages/geometry/src/geometry.ts
- packages/geometry/src/polygon.ts
- tests/geometry/followup-iy2.test.mjs
- tests/geometry/geometry.test.mjs

All commands below ran from this assigned worktree. Node commands and the task harness used `PATH=/Users/zubair/.local/share/mise/installs/node/22.23.2/bin:$PATH`; node-version.log confirms v22.23.2.

| Command | Result | Evidence |
| --- | --- | --- |
| `bun install --frozen-lockfile` | Initial sandbox failure: tempdir EPERM | install.log |
| `TMPDIR=/private/tmp bun install --frozen-lockfile` | Same sandbox failure | install-retry.log |
| `bun install --frozen-lockfile` (approved escalation) | Bun 1.4.0, 86 packages installed in isolated worktree; frozen lock unchanged | install-escalated.log |
| `node --test tests/geometry/followup-iy2.test.mjs` before fix | 15 collected, 4 passed, 11 failed: five contacts plus empty/malformed extent cases across three APIs | red.log |
| Same command after fix | 15 passed, 0 failed/skipped | green.log |
| `node --test tests/geometry/*.test.mjs` | 47 passed, 0 failed/skipped; includes 10,000 deterministic point samples | suite.log |
| `bun run --cwd packages/geometry typecheck` | Exit 0; registered `tsc -b` | typecheck.log |
| `python3 scripts/task_acceptance.py task T04 --report artifacts/tasks/T04/followup-iy2/run.json` before source commit | Correctly blocked pending source commit | task.log |
| Same task command after source commit | One registered command; 47 passed, 0 failed/skipped | run.json, task-committed.log |
| `python3 -m unittest discover -s tests/geometry -p 'test_*.py' -v` | Zero collected: not valid verification; suite uses pytest functions | python.log |
| `python3 -m pytest tests/geometry -q` | Unavailable: local Python has no pytest | pytest.log |
| `python3 tests/geometry/derive_expectations.py --check` | Exit 0; committed independent expectations fresh | derivation.log |
| `git diff --check` | Exit 0 | Executed during final source diff review |

Limitations: supplementary Python pytest suite was not executed because pytest is unavailable; no shared dependency changes were made. No OCR, browser/device overlays, independent review, merged-branch validation or acceptance receipt was performed or claimed. T04 is not marked accepted. Parent owns review and integration. No Beads writes, pushes, shared schema/planning/gate changes or other worktree edits.
