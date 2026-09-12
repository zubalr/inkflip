# T10 wave-3 independent review — changes required

Candidate: `7699f9752d82f97251c86f53e15407b5b087668d` (source `d4caea5`, tests `c757be7` plus renderer-fixture correction `fa5934824361045520eeb32c2a76ff37b3ae9d13`). Review checkout: `/Users/zubair/Code/Projects/pdf project/worktrees/review-codex-t10-wave3`, branch `review/codex/t10-wave3`. Started at immutable `927a1aa460d6642c0bfc8c7df0a0412c823e0b4e`; fast-forward to `7699f97` was explicitly authorized. No production/test source edits in the checkout.

Reviewer: independent Codex GPT-6 reviewer, Pauli task `01a093db-42d8-79d3-befb-0b7680c3e405`; direct local source review and executions, no delegated/app reviews. This is review evidence, not product acceptance.

Verdict: **changes required**. The full registered suite passes **35/35**, but an independent real-worker probe demonstrates incorrect model provenance, and four stub probes expose incomplete lifecycle ownership. The prior geometry, renderer-id, UTF-8, public-knob and test-registration findings are resolved. The parent owns the separate q38 dependency correction; that correction is not installed in this exact candidate.

**Heavy reservation released at 2026-09-12 07:19:57 UTC.** Both the registered suite and real-engine probes exited; port 5192 had no listener. No further heavy work is queued. A subsequent same-generation clarification probe was stub-only and has also finished.

## P1 — verified cache read-back does not bind the bytes the engine loads

Locations: `packages/readers-tesseract/src/model-cache.ts:334–373`, especially the final read-back at lines 356–373; `reader.ts:694–702`; `engine.ts:210–219`.

`prepareForEngine()` verifies a shared IndexedDB slot and returns before the worker reads that slot through its own transaction. `createEngineWorker()` passes `{code:'eng',data:'eng'}` with `cacheMethod:'readOnly'`, so the verified bytes themselves never cross the engine boundary. A same-origin cache writer can replace the slot between those two reads. The absence of a second network request does not establish exact-byte provenance.

The independent real-engine experiment inserts a cache replacement through an injected wrapper immediately on entry to `createWorker`, after the production reader has completed `prepareForEngine()`. It then delegates to the unchanged installed Tesseract source, unchanged staged worker/core, and reads `/eng.traineddata` through the real worker's `FS('readFile', ...)` after initialization. It also runs actual F03 crop OCR. No production module, staged asset, dependency or worker protocol was edited.

| Observation | Unchanged-cache control | Cache replacement after verification |
|---|---|---|
| Adapter verified bytes | 4,113,088; SHA `7d4322bd…27170b2` | Same |
| Replacement | None | Verified model plus one zero byte: 4,113,089; SHA `ed260abd…89b6752` |
| Real engine filesystem bytes | Original length/hash | Replacement length/hash |
| Actual recognition | Completed; four occurrences | Completed; four occurrences |
| Reported model hash | Original hash | **Original hash despite replacement engine bytes** |
| Model requests | 1 | 1 |

Full original SHA: `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.
Full replacement/engine SHA: `ed260abd301d3b849ccd94cd794b6250c0eaaffd7ba0836506a79ee2389b6752`.
Both returned raw OCR text `AMOUNT DUE $108, a\n`. The mutated case fails only the final exact engine-file/report hash assertion; the unmodified control passes. This directly disproves the source/evidence assertion that the engine consumes exact verified bytes or initialization fails. Evidence: `real-cache.log`, `real-cache-tests.txt`, and the appended tests in `probes.spec.ts`.

Correction direction: use an immutable verified byte payload at the engine boundary with upstream cache access disabled, once the separately owned q38 normalization repair is reviewed/integrated. The prior recommendation to do that against the unmodified v7 client was **wrong**: installed `worker-script/index.js:236–238` maps object `.data` to the initialization language name. That verified dependency limitation explains the workaround but does not make the shared cache atomic. This review neither changes nor approves q38. The current mandatory-IDB failure paths avoid the old unverified refetch, but they do not solve this race.

## Reproduced lifecycle findings

1. **P1 — stale `open()` cleanup destroys the newer operation.** `packages/readers-tesseract/src/reader.ts:576–580` unconditionally clears the current handle and calls global `destroyWorker()` after the old operation's guard rejects it as superseded. Reproducer: hold the first open's model fetch, let a second open finish, then resolve the first. Second open returns successfully, but its worker is terminated and `plan(secondHandle, ...)` now fails `unsupported: plan() requires this reader’s open handle`. The failure was reconfirmed with both opens using the **same document and generation**, so it does not rely on replacing a file without closing its reader. Similar unscoped cleanup exists in `extract()` at lines 981–997. Cleanup must be tied to the failing operation and concrete worker lifetime; it cannot clear a newer handle or worker. Evidence: `STALE_OPEN_CLEANUP` in `independent-stub.log` and `stale-open-same-generation.log`.

2. **P2 — `close()` does not interrupt pending raster/model awaits and reports timeout instead of cancellation.** `reader.ts:642–647` polls only the caller's cancellation predicate; `close()` changes `closed` and `opSeq`, neither of which wakes the pending race. Reproducer: a raster source never resolves, check budget 800 ms, close after 20 ms. Operation is still pending 100 ms after close and returns `timeout` at 802.6 ms instead of `user_cancel`. Default deadline would retain this pending operation for up to 30 seconds. The absolute scope needs a close/supersession terminal signal that rejects its awaits immediately. Evidence: `CLOSE_STALLED_RASTER`.

3. **P1 — losing model preparation still mutates state/cache after close and explicit data removal.** `reader.ts:436–447,550–553` races `modelManager.prepare()` without cancellation ownership; `model-cache.ts:262–265,288–309` continues after the fetch/arrayBuffer awaits, emits states, assigns the memory cache and writes IndexedDB. Reproducer: hold model fetch, call `close()` and await `removeModelData()`, then release a valid response. New states `verifying,ready_memory` appear after `not_prepared`, modelState becomes `ready_memory`, and the deleted cache entry exists again. Guarding the reader only after `prepare()` returns is too late. Propagate cancellation/invalidation into the model operation, abort the fetch, and guard internal state/cache commits after awaits. Evidence: `LATE_MODEL`.

4. **P2 — terminal initialization retains callback admission (stub seam evidence).** `reader.ts:662–673` compares only creating operation id/closed state; initialization timeout does not invalidate `opSeq`, and the error callback at line 701 has no scope check. After an 80-ms open timeout with its signal already aborted, invoking captured engine logger/error callbacks still publishes `late init progress` and `late init error`. The actual patched dependency drops raw-worker callbacks after stop; this probe establishes the adapter boundary does not satisfy the explicitly required terminal callback guards. Record terminal scope state and bind both callbacks to it. Evidence: `LATE_CALLBACKS`. This is narrower than a demonstrated late callback from the patched real worker.

All four probes use the actual unchanged reader/model source bundled for Chromium, real canvas/IndexedDB, and injected stub engines. Assertions express the required behavior and fail; logs include actual outcomes. Temporary harness: `/private/tmp/inkflip-t10-wave3/probes.spec.ts` and `/private/tmp/inkflip-t10-wave3/independent-tests.txt`.

## Prior seven findings: disposition

| Wave-2 finding | Wave-3 disposition |
|---|---|
| Bow-tie word polygon fails geometry validation | Resolved: TL,TR,BR,BL, nonzero area, and semantic assembled-report validation pass. |
| Engine model bytes not bound to verified hash | Still blocked: the refetch path is removed, but real shared-cache replacement proves different engine bytes with the original reported hash. |
| `pending` renderer id differs from immutable plan | Resolved: configured renderer id binds describe/plan/output/occurrences; foreign rasters fail `render_error`; synthetic test producers now have matching reader configuration. |
| Deadline covers recognize only | Partially resolved: raster, encode/materialization, eager/retry init and recognize share a deadline. Close, stale cleanup, late model commits and callback admission still fail the new lifecycle requirements. |
| UTF-16 length instead of UTF-8 byte budget | Resolved: multibyte rejection/exact-boundary controls pass. |
| Public `imageSmoothingEnabled` test knob | Resolved: removed; both production canvas paths pass under default smoothing. |
| Pixel tests outside registered T10 surface | Resolved: all four are collected/executed in `tesseract.spec.ts`; the extracted helper has no global test hooks. |

The assembled report test uses `validateReport(report, false)`: the second argument disables canonical hash checks, not semantic geometry or plan/reader-reference validation. It is valid evidence for the two reviewed semantic fixes, not a complete export-hash proof.

## Independent verification

- Pinned Node v22.23.2 in PATH; Bun 1.4.0 frozen install passed at `927a1aa`. Dependency files unchanged by fast-forward to `7699f97`.
- `node --test tests/readers/crop-math.mjs`: **13 passed**, 0 failed/skipped.
- `bun run --cwd packages/readers-tesseract typecheck`: passed.
- `bun x --no-install oxlint packages/readers-tesseract/src/ tests/readers/tesseract.spec.ts tests/readers/t10-pixel-harness.ts`: exit 0.
- Registered `bun run test:browser -- tests/readers/tesseract.spec.ts --workers=1 --grep 'light:' --grep-invert 'a stale or corrupt cache slot|the engine consumes the verified slot|close during a real open'`: **21 passed**, 0 failed, 5.4 seconds. Those three exclusions instantiate the real engine despite their `light:` describe name; no heavy work was started during the hold.
- Full registered `bun run test:browser -- tests/readers/tesseract.spec.ts --workers=1`: **35 collected, 35 passed, 0 failed, 0 skipped**, 10.5 seconds, exact `7699f97`; log `registered35.log`.
- Independent lifecycle probes: **4 distinct tests, 4 failed**, all observable product/adapter-boundary failures described above. Same-document/generation clarification rerun: **1 failed** (same stale-cleanup defect, not an additional distinct finding).
- Independent real-worker provenance probes: **2 tests, 1 passed control, 1 failed replacement**, 2.0 seconds; both actual OCR jobs completed, but the replacement violated the hash contract.
- `git diff --check` passed and review checkout remained clean after these checks.
- Browser commands used pinned Node v22.23.2, Bun 1.4.0, Playwright 1.57.0 and temporary `NODE_OPTIONS=--require=/private/tmp/inkflip-t10-port5192.cjs`. The preload changes only this harness's `listen(0,'127.0.0.1')` to strict port 5192, with no fallback. No source edit was needed for port allocation.
- Installed `createWorker.js` SHA-256 remains `11d687cf60deee6cdf428d16ee1f5e83a3f906aa6825b0c2da3781840cc96c9c`; installed types SHA `eebc61f3d9d7ac6402585165c237cc5d01b18e9a32ff2ed8f290f7652e056c6e`. The q38 repair was not silently consumed from a live checkout.
- Scope: canonical instructions, current read-only pdf-t10 notes, effective T10 contract, T10 source/test diff from `3fea9a8` plus the authorized `927a1aa..7699f97` revision inspected. Previously reviewed ebz constructor behavior was not re-reviewed as a new T10 implementation. No Linux/device matrix or independent full 115-check/bootstrap/build rerun is claimed here.

Evidence correction for the writer: `receipt.json` still says “35/35 … at 567b482” in its first criterion detail. That is an older wave-2 test commit; current top-level candidate/run fields correctly name `fa59348`. Correct the stale sentence and the “exact bytes by construction” statements when implementing the review revisions. Do not rewrite historical failure evidence.

Logs and probes are under `/private/tmp/inkflip-t10-wave3/`. No Beads writes, acceptance receipts, source fixes, commits or pushes were made by this review.
