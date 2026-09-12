# Independent Peer Review — T02

**Reviewer:** devin-review-t02 (SWE-2 subagent, independent)
**Candidate:** `work/devin/t02` @ `f216a5dbef0e0cd1db1d63ed9357ffcb37edf36e` (base `3bef697`), reviewed in detached worktree `worktrees/review-t02`
**Worker:** devin-subagent-t02 · **Date:** 2026-09-12

## Verdict: approved

All six acceptance criteria independently substantiated; contract command reproduces exactly (16 checks + 37 tests); evidence credible and honest incl. disclosed limitations. Approval conditioned on two integration-time coordinator actions (a: record `apps/web/public/` staging-root scope amendment; b: apply verified actions/checkout SHA pin per proposal P1). Findings 3–4 are recommended follow-ups, not gating.

## Checks run on the candidate (real results)

| Command | Claimed | Reproduced |
|---|---|---|
| `python3 scripts/check_dependencies.py --frozen` | 16/16 | exit 0, 16 passed / 0 failed |
| `python3 -m unittest discover -s tests/build -v` | 37 | exit 0, 37/37 passed, 0 skipped |
| `python3 scripts/task_acceptance.py task T02` | — | exit 0, both segments pass |
| `bun install --frozen-lockfile` | 84 pkgs | exit 0, 84 pkgs |
| `uv sync --frozen --project native` | 13 pkgs | exit 0, 13 pkgs |
| `uv run --frozen --project native python -m pytest --version` | pytest 9.1.1 | exit 0 — T03's contract leg resolves |
| `bun audit` | clean 168 pkgs | reproduced verbatim |

## Adversarial verification

- Scope: all non-asset paths inside allowed scope + artifacts/proposals/ATTRIBUTION; `planning/` untouched; reserved paths clean. Exception: 212 files under `apps/web/public/{assets,models}/` outside effective allowed_scope — Finding 1.
- Fail-closed (live): renamed a staged cmap → `FAIL assets … missing staged file` exit 1; appended 8 bytes to `eng.traineddata` → `FAIL assets … checksum/size mismatch`. Restored via `git checkout`; `prepare_assets.py verify` → 212 OK.
- Asset hashes: independently re-hashed 6 staged files incl. 4,113,088-byte model — all match `config/resolved-assets.json`. All 8 asset groups carry source/license/serve_prefix; every file sha256+bytes; upstream pinned-commit source_url; no `://` in staged paths/serve prefixes.
- bun.lock: lockfileVersion 2; workspaces map == disk; 169 sha512 integrity hashes (workspace entries exempt, correct). bunfig.toml: `linker = "isolated"`, `exact = true`, `minimumReleaseAge = 604800` with documented excludes.
- native/uv.lock: `requires-python ==3.13.15` matches `.python-version`/pyproject; every registry package carries sdist+wheel sha256 (15 locked).
- OCI digests verified live: `docker buildx imagetools inspect python:3.13.15-slim-trixie` → index `9d2e5553…e00285`, arm64 `c89921a0…44b0b4` — exact match to `build/base-image.lock.json`.
- Action SHA verified live: `git ls-remote https://github.com/actions/checkout refs/tags/v4 refs/tags/v4.4.0` → `11d5960a326750d5838078e36cf38b85af677262` = recorded.
- Linux proof log: credible `set -x` container transcript (aarch64, Python 3.13.15, publisher checksums verified, 2× clean installs from `git archive`, acceptance inside, `PROOF-OK`). Not staged; arm64-only execution disclosed.
- Browser probe: honest harness — serves only production paths, logs every server-side request; 7/7 pass; missing-model recorded as `TIMEOUT` (disclosed). Feasibility-only labeling consistent.
- P1/P2/P3 reproduced: ci.yml:10 uses `actions/checkout@v4`; `test_declared_suite_with_missing_runner_fails` fails as described; repo-root pytest collects `planning/tools/test_validators.py` → yaml ImportError.
- Evidence commit `f216a5d` contains only `artifacts/tasks/T02/*` — clean separation.

## Findings

1. **[major] Undocumented scope extension — staging root.** `apps/web/public/{assets,models}/` (212 files) outside effective `allowed_scope`. No other task owns these subpaths so no real conflict, and `plan_mismatch` was correctly used for P1–P3 but not this surface. Required: coordinator records scope amendment (`apps/web/public/`) in overrides/Beads at merge. Integration-time action, not worker rework.
2. **[minor] Mutable action tag in-file.** `.github/workflows/ci.yml:10` still `actions/checkout@v4`. Immutable SHA recorded + enforced by check_dependencies (unrecorded/short-SHA `uses:` now fails). P1's recommended pin (`actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0`) verified — apply at merge (T01-owned file; coordinator resolution).
3. **[minor] `no-cdn.sources` scan blind spot.** `check_dependencies.py:370-371` scans `apps/web/src`, `index.html`, `vite.config.ts` — not `apps/web/public/`. Staged `worker.min.js` contains live `cdn.jsdelivr.net` fallback strings; `REMOTE_LOADER_RE` misses dynamic `import("https://…")`. Mitigated by explicit-path adapter contract + probe proof. Suggest extending scan to staged text assets (follow-up).
4. **[minor] QuickJS attribution gap.** Staged `wasm/quickjs-eval.{js,wasm}` (MIT QuickJS/Emscripten) carry source+hash but no staged notice; group license Apache-2.0 inaccurate for that binary. One line in ATTRIBUTION/rights closes it (follow-up).
5. **[note]** commands.log `git diff --check` claim inaccurate — trailing whitespace exists only inside hash-pinned verbatim upstream LICENSE files (must not be "fixed"). Evidence inaccuracy only.
6. **[note]** `evidence_artifacts` lists `artifacts/tasks/T02/review.md` — this review is the deliverable (convention `peer-review.md`); coordinator reconciles at record.
7. **[note]** Probe scenario-A same-origin verdict rests on server request log (no browser-side capture in scenario A); theoretical residual only.
8. **[note]** Linux proof on linux/arm64 only; amd64 digest recorded, unexecuted — disclosed.

## Per-criterion assessment

- Frozen install ×2 clean checkout: SUBSTANTIATED — 2× in pinned OCI from git-archive + macOS clean copy + reviewer's own frozen installs.
- Bundled binary source/hash/license: SUBSTANTIATED — 212/212 verified incl. independent re-hash. Caveat: finding 4.
- Substituted model fails checksum: SUBSTANTIATED — unit test + live tamper → FAIL.
- Missing asset fails closed: SUBSTANTIATED — unit test + live rename → exit 1; probe scenario B.
- No runtime CDN/download: SUBSTANTIATED — all serve prefixes same-origin; all 8 scenario-A resources origin-served; downloads prepare-time only. Caveat: finding 3.
- Action/OCI revisions immutable + recorded: SUBSTANTIATED — digests + SHA verified live; in-file workflow pin pending P1 (finding 2).

## Required integration-time actions (coordinator)

(a) Record `apps/web/public/` staging-root scope amendment in overrides/Beads at merge (Finding 1).
(b) Apply verified `actions/checkout` SHA pin in ci.yml per P1 (Finding 2).
Recommended follow-ups (scheduled, non-gating): extend no-cdn scan to staged text assets; QuickJS rights line.
