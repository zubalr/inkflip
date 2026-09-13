# T18 independent review — G1 own-file evidence gate

- **Reviewer:** devin-review-t18 (Devin Local SWE-2, independent reviewer persona — not the worker `devin-t18`/`5bf96ad6`)
- **Candidate:** `b74aee40690f0229dc0ebfb15c54210b6b184091` on `review/devin-t18` (base `f25d3ee`)
- **Review checkout:** `worktrees/review-devin-t18`
- **Verdict:** **APPROVED**

## What was verified (all independently re-executed, not trusted from artifacts)

| Check | Method | Result |
|---|---|---|
| Spec free of skips/mocks | grep `test.(skip\|fixme\|only)`, `page.route`, `context.route`, `mock` over `tests/gates/g1.spec.ts` | Zero hits — only the word "mocked" in a header comment |
| Real harness APIs (not invented) | Every `__t08`/`__t15`/`__t22` call in the spec cross-checked against `apps/web/src/features/open/mount.tsx`, `tests/privacy/harness/mount.tsx`, `apps/web/src/features/import/mount.tsx` and the underlying signatures in `packages/readers-pdfjs/src/adapter.ts` (PlanSelection/ExtractJob/Cancellation), `packages/runtime/src/messages.ts` (MessageFactory), `packages/runtime/src/coordinator.ts` (startRun/requestCancel/receive/snapshot/drainOutbox/prepareNewRun), `packages/runtime/src/view.ts` (SessionView), `packages/readers-tesseract/src/reader.ts` (OcrSelection/OcrCheckOutput), `packages/reports/import/{open,view,source}.ts` (openReport/replayView/verifySourceCandidate) | All signatures real; worker's claim that the salvaged draft (`eb56c74`) used invented `__t15` signatures confirmed (`ocrOpen(reader)` 1-arg, `ocrPlan(doc,...)` doc-first, `ocrExtract(doc, plan, check, opts)` — none exist) plus nonexistent fixture `scan-rendered-text.pdf` |
| Assertions contract-truthful | Cross-checked asserted values against contract/generator truth: `chk_p0_*` id convention (adapter.ts:350), `user_cancel` (limits.ts:91), `unsupported` never-retry vs `worker_crash` transient (limits.ts:110-126), OCR gated on same-page render → exactly 2 immediate dispatches (checks.ts:73-83 `deriveDependencies`), `stale_generation` rejection (I07), `estimated` precision (pdf.js TextItem extents are never `exact`), F21 canonical 320×240 (make_fixtures.py `fixed_page` box), F07 CropBox×UserUnit → 960×700 + rotate 90, F01 text `$1,000`/painted `$100` (expect.json `extraction_intent`/`painted`), model sha256 `7d4322bd…` (resolved-assets pin) | All assertions bind real contract values, not whatever the app emits |
| Independent re-run | `bun install` then `bun x --no-install playwright test tests/gates/g1.spec.ts --reporter=line` in this review checkout | **3 passed (5.5s), exit 0** — real Vite build + real pdf.js + real Tesseract over loopback |
| Captures regenerate identically | Diffed my run's output vs committed captures | Identical record counts (46/45/47/15/1), identical violation profile (20 hits, all `channel=downloads` whitelisted: canary text/doc sha256/report_id/run_key — the export files legitimately carry them), identical `canary-manifest.json` byte-for-byte (deterministic seal → stable report_id/run_key; deterministic raster sha). Diffs only in ephemeral port, `Date` headers, `execution_id` UUID, `started_at`, parallel-fetch ordering |
| No-egress scan real | Read `scanInto`/`endCapture`/`assertCaptureClean`: every carrier (request URLs + post data, response headers, failures, WS frames both directions, console, page errors, dialogs, downloads ≤400k, localStorage/cookies/IndexedDB/CacheAPI dump, server access log) scanned for every marker spelling (raw/percent/base64/hex→b64); scan runs on full records before the 4000-char file truncation; cross-origin filter `origin !== baseURL` | Sound; `allowed_channels` used only for `downloads`; offline leg asserts server-log empty + zero failures + fixed-asset-only requests — the honest bound |
| Registered `verify` unaffected | `bun run verify` | 65 tests OK, exit 0 |
| Gate-prereq claim | `python3 scripts/gate.py G1 --check-prereqs` here → `prerequisite unmet: Git evidence lookup failed` ×18; then per-task `merge-base --is-ancestor` + full `acceptance_receipts.validate(tid, issue, ref='origin/main')` | Claim **confirmed exactly**: all 19 Beads accepted_commits are ancestors of `origin/main`; only T17 (`f25d3ee`, the branch base) is an ancestor of this HEAD. All 19 receipts fully validate against `origin/main` (freshness, commands, evidence, review dispositions). Failure on-branch is purely accepted-commit ancestry vs HEAD — the designed gate-on-merged-branch flow |
| Scope | `git diff --stat f25d3ee..HEAD` | 15 files, +4618/−0 — only `tests/gates/g1.spec.ts`, `artifacts/tasks/T18/`, `artifacts/gates/G1/captures/`. Nothing else touched. No reserved paths |
| Main-delta claim | `git diff --name-only f25d3ee origin/main -- . ':(exclude)artifacts' ':(exclude).beads'` | Only `native/inkflip/checks/structure.py` + its test (T28) — nothing the spec touches; merged run expected green |
| Fixture/marker truth | `F24` absent from `scripts/make_fixtures.py` + `fixtures/` (exists only in planning docs) — flagged-not-fabricated claim holds; canary marker strings verified as real bytes inside `network-canary-channels.pdf`; manifest digests recompute correctly | Confirmed |
| Artifact consistency | `run.md`/`handoff.md`/`handoff.json`/`receipt.json`/`commands.log` vs observed behavior | Consistent; `commands.log` transparently records 3 real failing iterations with contract-truthful fixes (not weakened assertions) |

## Findings

**None blocking.** Minor/cosmetic only:

1. `tests/gates/g1.spec.ts` is not byte-exact `oxfmt 0.67.0` output despite commit `b74aee4`'s "oxfmt" message — the pinned formatter reflows two `setInputFiles` call sites (lines ~1364, ~1419). Verified idempotent, so it is not a formatter-version race; likely a hand touch-up after formatting. No registered command enforces `oxfmt --check` (dev-only tool); zero semantic impact. Coordinator may re-format at merge if desired.
2. `run.md` says the spec is "≈1,270 lines" and `commands.log`'s `--list` cites pre-format line numbers (643/986/1218 vs current 632/957/1163) — documentation drift from the post-format commit; claims themselves verified true.
3. Spec header says the adapted scenario is `--reporter=junit`; `commands.log` records `line`/`list` reporters. The gate adapts only `pnpm exec → bun x --no-install`; reporter is the runner's choice. Cosmetic.

## Honest limitations (worker-disclosed, independently confirmed accurate)

- T13 composition gap is real: no shipped page composes open→inspect→export for own files; the gate drives the real built T08/T22 mounts, the test-owned T15 harness page (same production packages/pipeline as the accepted T15 suite) and the real app shell. Disclosed in spec header, run.md, receipt.json and the committed canary manifest.
- In-page egress capture cannot see OS/browser-level channels; release profile needs proxy/firewall capture per planning.
- Offline = warm-page `context.setOffline(true)` (real browser-level network cut, not route mocking); no service worker shipped, cold offline nav correctly out of scope.
- F24 fixture absent — flagged, not exercised.

## Reproduction

```sh
bun install
bun x --no-install playwright test tests/gates/g1.spec.ts   # 3 passed
python3 scripts/gate.py G1 --check-prereqs                  # fails on-branch (ancestry); all 19 validate vs origin/main
```

Post-merge on main, `python3 scripts/gate.py G1` re-runs this identical Playwright command and writes the gate receipt. The branch is ready for that flow.


---

## Delta review — 2026-09-13, evaluated `412fb9b2`

- **Reviewer:** devin-coordinator (acceptance refresh; not the implementing worker for this delta's shared changes)
- **Scope delta:** This task IS the composition work. `tests/gates/g1.spec.ts` rewritten to
drive the real public app (no private mounts): own-file open → real coordinator
run (PDF.js text + raster, Tesseract OCR) → sealed report → cancel/replace →
geometry/scan → JSON+HTML export → local reopen → source attach → offline OCR.
3/3 legs green on the merged state. Two rounds of independent review on the
composition commits (findings F1–F7 and round-2 stale-writer fix) are recorded
in the pdf-3g8 session and this task's gate receipt.
- **Fresh run:** Run evidence: the G1 gate receipt (`artifacts/gates/G1/receipt.json`) records the 3-leg journey result.
- **Verdict:** prior review stands; delta introduces no acceptance-relevant regression.


### Composition independent review (pdf-3g8) — two rounds

The implementation under test is the pdf-3g8 composition (`48fed92` + fix
commits, merged at `e9b8c4a`). An independent read-only review subagent
(`devin-review-3g8`, did not write the code) reviewed the full diff twice.

**Round 1 findings — all fixed before merge:**

- F1: coordinator outbox intents from internal transitions (deadlines,
  dependency cascades, clear) were not drained → drain added on
  `onCoordinatorChange` and post-message.
- F2: `cancelPending` could leak across replacement/stale generations → reset
  at run start, close/clear/import; applied only to the still-current
  generation.
- F3: stale-generation jobs could write rasters/transforms/readers into a new
  run → all writes moved behind generation checks; raster cache entries tagged
  with generation and rejected on mismatch.
- F4: imported reports exposed no OCR reader descriptors → deterministic
  descriptors for both supported configs returned via `installedReaders`.
- F5: verified attached source bytes were not retained for source-inclusion
  export → retained in session state, passed to `ExportPanel`.
- F6/F7: `window.__inspect` gated to test/dev (`VITE_INSPECT_HANDLE`); session
  closes on Workspace unmount.

**Round 2:** verified all fixes; found one residual stale-writer in the
OCR-prep failure path (notice could flash on a new document) — stale-guarded —
plus a dead-variable cleanup. Re-verified.

**Verdict:** approved; the gate run above is the acceptance evidence.
