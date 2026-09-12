# Independent q38 dependency-correctness review

**Verdict: approve within the bounded conventional review scope. No actionable findings.** The real-engine rerun is deferred until the parent explicitly grants the reserved slot; this verdict does not claim that rerun or constitute task acceptance.

Reviewer: **Codex**, independent review task `01a09467-215d-7a30-827e-e60905c3d73d` (obtained from this process's `CODEX_THREAD_ID`), separate from author Parent Astra. Date: 2026-09-12.

Candidate: `14f062e887d49812fbd8e9369547bd99f6cba201`.
Base: `a4f1069e763fb9769aac421331b91de1fed67837`.
New isolated checkout: `/Users/zubair/Code/Projects/pdf project/worktrees/review-codex-q38`, branch `review/codex/pdf-q38`.
Initial and final tracked/untracked status were clean; HEAD remained the exact candidate. The base is also the verified merge base.

## Assessment

Read current AGENTS.md, docs/NATIVE_PASSES.md, docs/HOMEBASE.md, the language-payload README, and effective T02 contract via `python3 scripts/coordination.py task T02`. The project brief and invariants had already been read in this session. Reviewed the full base/candidate source, provenance and test diff, the complete maintained Bun patch, the installed constructor/worker/types, and the dependency-checker implementation. No nested AGENTS.md/CLAUDE.md was found by repository file discovery.

The defect description is supported by both installed 7.0.0 source and the [pinned upstream worker](https://github.com/naptha/tesseract.js/blob/v7.0.0/src/worker-script/index.js): loading takes object `.code` for the filename and `.data` for the bytes, while initialization incorrectly converts object `.data` to a language-name string. The patch sends names through the worker's existing string initialization path. It preserves the original objects for loading and retains the existing OEM/config/job values. `cacheMethod: none` already avoids cache reads/writes in that worker; the change does not introduce a cache workaround.

Both initial creation and reinitialization call the same helper, so the fix covers both without changing their sequencing. Strings pass through unchanged, and mixed arrays preserve their order when converted to the existing plus-separated representation. Valid object payload bytes are not modified by this normalization. The [pinned client](https://github.com/naptha/tesseract.js/blob/v7.0.0/src/createWorker.js) and installed source confirm the call paths. Existing reinitialization bookkeeping and cancellation/error handling are unchanged.

A temporary source reconstruction reversed the candidate patch from installed source, verified both reconstructed upstream hashes, then applied the base patch. The resulting constructor diff contains only the initialization payload hunk. Public types are byte-identical, and the earlier AbortSignal patch remains intact. Patch inventory and installed hashes agree with the updated provenance record. Manifest, Bun/native locks, staged assets and resolved-assets manifest are unchanged from base. Frozen installation succeeded with the existing patch declaration.

The existing unit harness executes the installed constructor and substitutes its transport boundary. It checks object initialization, mixed languages, new objects on reinitialization, unchanged string inputs, original loading payloads, and lifecycle/cancellation behavior. All 14 passed independently. The scope is small and consistent with existing package conventions; no standards issue requiring a change was identified.

The two new real-engine tests were inspected, not executed here. They bundle the maintained client and use the staged worker/core/model; they cover unavailable IndexedDB and a corrupt cache slot. Their assertions compare the engine filesystem model hash after creation and reinitialization with the pinned digest, require one preparation fetch, and check unexpected local/remote requests. Registration includes the suite and clears the negative-control package override. These tests support the intended claim when run, but their committed author results are not independent execution evidence.

## Actual commands and results

Logs are under `/private/tmp/inkflip-q38-review/`. Commands ran in the new review checkout unless otherwise stated.

| Command | Actual result / log |
| --- | --- |
| `git worktree add -b review/codex/pdf-q38 '../worktrees/review-codex-q38' 14f062e887d49812fbd8e9369547bd99f6cba201` from `original` | Exit 0; created only the assigned new branch/checkout. |
| `git status --porcelain=v1`; `git rev-parse HEAD`; `git merge-base BASE HEAD` | Clean, exact candidate, exact base. Final results in `source-checks.log`. |
| `git diff --stat BASE HEAD`; `git diff BASE HEAD -- ':!artifacts'` | Inspected committed scope; BASE is the full hash above. |
| `node --version`; `bun --version` | v22.23.2 and 1.4.0. Node PATH prefixed with `/Users/zubair/.local/share/mise/installs/node/22.23.2/bin`. |
| `bun install --frozen-lockfile` | Initial sandbox attempt failed before installation with tempdir EPERM (`install.log`); retry with `TMPDIR=/private/tmp` had the same environment failure (`install-tmp.log`). |
| `bun install --frozen-lockfile` with authorized sandbox escalation | Exit 0; 86 packages installed in this checkout; `install-authorized.log`. No lock drift. |
| `node --test tests/build/tesseract-worker.test.mjs` | Exit 0; **14 tests, 14 passed, 0 failed/cancelled/skipped**; `unit.log`. No real worker/model initialization. |
| `PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_dependencies.py --frozen` | Exit 0; **25 checks passed, 0 failed**; `frozen.log`. Includes both patched-file hashes and **212 staged-file hashes**. Host Python was 3.14.7; this checker validates the committed 3.13.15 pin without proving execution on that interpreter. |
| `PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/inkflip-q38-review/check-patch.py` | Exit 0; temporary reconstruction/digest/type comparison and minimal source delta; `patch-source.log`. Script retained beside log. |
| `git diff --exit-code BASE HEAD -- package.json bun.lock native/uv.lock apps/web/public config/resolved-assets.json` | Exit 0; listed surfaces unchanged; `source-checks.log`. |
| `git diff --check BASE HEAD` | Exit 2 for whitespace in the captured red log and the blank-context marker of the patch file. No applied-source defect; patch application and digest checks passed. Details preserved in `source-checks.log`. |

Read-only cat/sed/rg/git inspection and primary-source web reads also completed. Initial lookups for nonexistent `scripts/check_frozen.py` and `.tool-versions` were resolved by inspecting the actual checker and pin configuration; they were not product-test failures.

Author evidence inspected: baseline 11/11 constructor tests; revised red run 11 passed/3 failed; green 14/14; browser 2/2; Python build 49/49; verify 49 + 2 + 64 = 115. Those are historical author counts. The parent's in-progress source-bound registered T02 run was not observed to completion and is not claimed here.

## Limits and completion

No real-engine browser test, OCR or model initialization ran in this review. No independent full 49-case Python build suite or 115-case verify run was performed. The requested lightweight checks and source review are complete; a future engine rerun requires the parent's explicit grant after the other reviewer releases the slot. No exploit development or external-target scanning occurred.

All install, unit, frozen and source-review commands have finished; no review process remains running. No production/test edits, commits, pushes, Beads writes, acceptance, GitHub or native-app actions occurred. Other workers' checkouts were untouched. Apart from the authorized worktree creation and its frozen installation, outputs are confined to temporary review storage.
