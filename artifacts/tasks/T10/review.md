# T10 wave-4 independent review — changes required

Candidate: `66655e142f815fccf089248a73f575d34953ef57` (impl `c08849e`, tests `8e567e5`+`1a655a1`, evidence `c1cc743`+`66655e1`, on merged q38 `1f0d900`/`14f062e`). Review checkout: `/Users/zubair/Code/Projects/pdf project/worktrees/review-devin-t10-wave4`, branch `review/devin/t10-wave4`. No production/test source edits in the checkout; this file is the only added artifact.

Reviewer: independent Devin SWE-2 reviewer; direct local source review and executions against Pauli's wave-3 verdict `a4f0e725` (`wave3-full-review.md`, `/private/tmp/inkflip-t10-wave3-review.md`, `/private/tmp/inkflip-t10-wave3/probes.spec.ts`) and the wave-4 direction `/private/tmp/inkflip-t10-wave4.txt`. Review evidence only, not product acceptance.

Verdict: **changes required**. The full registered suite passes **41/41**, `task_acceptance` reports 41/41 at `66655e1`, `bun run verify` is green, and all five wave-3 findings are verifiably resolved — verified model bytes now cross the engine boundary as a snapshot with `cacheMethod:'none'`, cleanup is operation-scoped, close wakes pending work as `user_cancel`, model preparation owns its side effects through epoch+signal guards, and scope admission gates callbacks. However, two independent boundary attacks reproduce lifecycle defects that violate the wave-4 requirements:

- **F1 (P1)** — recognize `userJobId` is not unique across operations, so a superseded op's in-flight (zombie) recognize job on a legitimately reused worker collides with the newer op's job of the same id. Upstream's own `promises` map then delivers the dead job's result — and reader-side admission publishes its progress — to the *newer* operation. Demonstrated on the real engine: the second op, fed a blank raster, `completed` with the first op's full invoice text and 14 occurrences. This fails the explicit requirement "recognize-job ownership on reused worker."
- **F2 (P2)** — `OcrHandle.id` is `ocrh_${generation}_${floor(now)}`: two same-generation opens inside one millisecond mint identical ids, and every stale-handle guard compares only `.id`. Demonstrated with a fixed clock: `close(staleHandle)` was accepted and closed the live reader; the foreign-handle distinction is lost. Handle identity is the load-bearing key for `plan`/`extract`/`close` admission and the scope guard.

Both mints predate wave-4 (`7699f97:556`, `7699f97:1101`), so these are inherited latent defects rather than regressions — but the wave-4 rework specifically claims operation-scoped admission and recognize-job ownership on reused workers, and the new `jobScopes` layer cannot compensate for F1 because the collision happens inside tesseract.js's own response routing before reader-side gating runs.

**Heavy reservation released.** Registered suite, acceptance run, and all real-engine probes have exited; `lsof -nP -iTCP:5192 -sTCP:LISTEN` shows no listener. No further heavy work is queued from this review.

## F1 — zombie recognize job delivers its result and progress to a newer same-id job on the reused worker (P1)

Locations: `packages/readers-tesseract/src/reader.ts:1271` (`const jobId = `j_${check.id}_${attempt}`;`), `reader.ts:1272` (`this.jobScopes.set(jobId, scope)`), `reader.ts:787–791` (`forwardProgress` resolves `userJobId → jobScopes → scope`), `packages/readers-tesseract/src/engine.ts:221–226` (`userJobId` passthrough). Upstream: `apps/web/node_modules/tesseract.js/src/createWorker.js:75–76` (`promises[`${action}-${jobId}`] = {resolve,reject}` — a second post with the same key overwrites the first), `createWorker.js:223–235` (a response resolves/rejects whatever entry is currently registered; progress is stamped `userJobId: jobId`), `worker-script/index.js:500–528` (`dispatchHandlers` runs every packet concurrently — no job-id dedup or queue).

Mechanism: `check.id` is `ocr_${pageIndex}_${ordinal}` and `attempt` restarts at 0 for every extract, so two extracts of the same check on the same shared worker mint the *same* `userJobId`. When op1 is superseded mid-recognize, op1's job keeps running inside the worker (upstream has no per-job cancel; the adapter only drops the await). Op2 posts `recognize` with the same `action-jobId` key → upstream `promises` entry is overwritten with op2's resolver → op1's response arrives first (it started first) and **resolves op2's promise with op1's data**. Reader-side `jobScopes` cannot detect this: by delivery time the key legitimately maps to op2's live scope. Zombie progress is likewise stamped with the colliding id and published under op2.

Real-engine reproduction (`ZOMBIE_JOB_CROSSTALK`, `/private/tmp/inkflip-t10-wave4-review/probes.spec.ts:2071`): raster A = real pdf.js invoice render (47,962-byte PNG), raster B = blank repaint carrying the same `renderReaderId` (44,030 bytes). Extract1 starts a real recognize on A; extract2 supersedes it and recognizes B on the same worker.

```json
recogCalls: [{"jobId":"j_ocr_0_0_0","bytes":47962},
             {"jobId":"j_ocr_0_0_0","bytes":44030},
             {"jobId":"j_ocr_0_0_0","bytes":44030}]
r1: {"status":"cancelled","reason":"user_cancel"}
r2: {"status":"completed","rasterId":"synthetic_blank_0","occurrences":14,
     "text":"QUARTERLY' SUMMARY\nINVOICE 2a26-8417\nAMOUNT CUE $168. 6\nISSUED 2426-89-81\nPAGE 1 OF 1\n"}
r3: {"status":"completed","reason":"unreadable_pixels","text":"","attempt":0}
pageerrors: []
```

All three jobs share `j_ocr_0_0_0`. Op2's output claims raster `synthetic_blank_0` yet carries the dead job's full-page invoice text and 14 occurrences — a fabricated cross-op reading, the exact "stale asynchronous operation corrupts newer work" class the lifecycle model exists to prevent. The worker stays usable afterward (r3 completes). (Probe note: the `recogCalls.length===2` assertion trips at 3 because the aftermath call is also recorded; the contamination itself is proven by the captured r2 payload and by the downstream `r2.text`/`r2.occurrences` assertions.)

Stub corroboration (`ZOMBIE_PROGRESS`, probes.spec.ts:2162): after op1 dies and op2 re-registers the same id, injecting the zombie's late `logger({status:'zombie progress', progress:0.5, userJobId:'j_ocr_0_0_0'})` is **published** to `onProgress`; a control event tagged `j_unknown_9` is correctly dropped. `forwardProgress` admission is only as strong as the job-id uniqueness it keys on.

Fix direction: mint `userJobId` with a component unique per operation — e.g. `j_${scope.op}_${check.id}_${attempt}` or a monotonic `++this.jobSeq` — so upstream keys never collide across scopes; the zombie's response then resolves only its own orphaned entry and its progress maps to a deleted/dead scope and is dropped. A per-op component also keeps retries inside one op distinguishable from a later op's attempt 0.

## F2 — timestamp-based handle ids collide; stale-handle guards then admit the stale handle (P2)

Location: `packages/readers-tesseract/src/reader.ts:581` — `id: `ocrh_${input.generation}_${Math.floor(this.now())}``. Every foreign-handle check compares only `.id`: the scope guard `reader.ts:696` (`this.handle?.id !== scope.handle.id`), `plan()` admission `:963`, `extract()` admission `:1033`, `extractOnce` admission `:1185`, and `close(handle)` stale-handle return `:1413`.

Reproduction (`FOREIGN_HANDLE`, probes.spec.ts:2275): with `hooks.now = () => 1000`, two same-generation opens mint identical ids:

```json
ids: {"h1":"ocrh_1_1000","h2":"ocrh_1_1000","equal":true}
closeWithStaleOk: true
afterStaleClose: {"ok":false,"reason":"unsupported","message":"unsupported: extract() requires this reader's open handle"}
foreign: {"ok":false,"reason":"unsupported"}
```

`close(h1)` — meant to be refused as a stale handle — is accepted and tears down the live reader; subsequent extraction on `h2` fails `unsupported`. With naturally differing timestamps the same probe passes, so the defect is timing-dependent, not universal: any same-generation reopen that completes within the same `Math.floor(now)` tick collides. That is reachable in production whenever the model is already memory-resident — `modelManager.prepare()` on the `ready_memory` path performs no I/O, so a superseding `open()` can plausibly mint its handle in the same millisecond the previous open minted its. Once ids collide, every `.id`-keyed admission in the file treats the stale handle as current: stale `plan()`/`extract()` are admitted, stale `close(h1)` kills the live generation, and the scope guard cannot tell `scope.handle` from `this.handle`.

Fix direction: make handle ids unique independent of the clock — include a monotonic component (`ocrh_${generation}_${++this.handleSeq}` or the op sequence) or a random suffix — or compare handle object identity in the guards instead of the id string. The id must stay contract-valid (`[A-Za-z0-9._-]+`).

## Wave-3 findings: all five verifiably resolved

| Wave-3 finding (Pauli `a4f0e725`) | Wave-4 disposition |
|---|---|
| P1 — verified cache read-back does not bind engine bytes | **Resolved.** `engine.ts:210` sends `[{code:'eng', data: input.modelBytes.slice()}]` — a snapshot of the adapter-verified bytes — with `cacheMethod:'none'` (`engine.ts:219`); `prepareForEngine` and the mandatory IDB engine path are gone. Real-engine probes (`REAL_MODEL_PROVENANCE` ×2): engine `FS` `/eng.traineddata` sha256 equals the reported `7d4322bd…27170b2` in both the unchanged control and the cache-replacement attack (replacement `ed260abd…89b6752`, 4,113,089 bytes written to the shared idb-keyval slot on `createWorker` entry — engine bytes unaffected). Exactly 1 model request in each run. The formerly-mandatory IDB failures are now truthful `ready_memory` + `model_cache_unavailable` successes (registered tests pass). |
| P1 — stale open cleanup destroys newer operation | **Resolved.** Registered test `superseded open cannot clear the newer handle and worker` passes; my `CLOSE_WITH_JOINERS` and join-adoption probes confirm the settle hook is the sole installer, a superseded open's late init product is orphan-terminated (`terminated:[true]` on close of a joined open), and a stale open retires nothing of the newer generation (`terminated:[false]` in the registered probe). |
| P2 — close does not interrupt pending awaits (timeout not cancel) | **Resolved.** `close()` fires each live scope's terminal `AbortController` (`reader.ts` close path); `withDeadline` rejects on `scope.ctl.signal` as `user_cancel` while the deadline timer still produces `timeout`. Reproducers: stalled-raster close settles `user_cancel` ~20 ms (not the 800 ms budget); `close during a real open aborts the raw worker init` is now deterministic — the in-page `__initPending`/`__initSettled` gate proves close lands mid-init, asserts `user_cancel`, `workerInitCount===0`, and `page.workers()` returns to baseline. |
| P1 — losing model preparation mutates state/cache after close/remove | **Resolved.** `model-cache.ts` snapshots `epoch` (`:226`) and re-checks `epoch !== epoch \|\| signal?.aborted` after every internal await and before state/memory/cache commits (`:347–357`); `remove()` bumps `epoch` (`:390`) invalidating in-flight preparation. Reproducers pass: held fetch + `close()` + `removeModelData()` + late release → no new states, `cacheExists:false`; `REMOVE_PREPARE` → r1 `user_cancel: model preparation invalidated by removeModelData`, r2 `ready_memory`/network, `fetches:2`, states `downloading,not_prepared,downloading,verifying,ready_memory`. |
| P2 — terminal init retains callback admission | **Resolved in shape, incomplete in scope.** `forwardProgress`/`forwardError` gate on `scopeAdmits` (`reader.ts:787–803`); the registered `late init progress and error callbacks are dropped after timeout` probe passes (empty progress/errors, `signal.aborted===true`). But the same admission layer is what F1 defeats: a dead job's events re-enter through a colliding `userJobId`. The gate exists; the key it consults is not unique. |

## Additional boundary probes (all passed)

- `a newer open joins the superseded open's in-flight init and keeps the produced worker` — lease adoption works: op1 superseded, op2 joins `lease.init`, produced worker installs for op2, survives until `close()` (`terminated` false before close, true after).
- `close rejects a joined open and orphan-terminates the late-produced worker` — `r1`/`r2` both `user_cancel`; the late worker product is terminated (`terminated:[true]`).
- `removeModelData mid-prepare invalidates it; a later prepare re-downloads honestly` — see table above.
- Foreign-handle extract with *distinct* ids fails `unsupported` without disturbing the live op — the guard logic is correct; only the minted id (F2) undermines it.

## Prior fixes re-verified (unchanged, still green)

- Polygon perimeter `TL,TR,BR,BL` (`occurrences.ts:87–92`); registered polygon + assembled-report tests pass.
- Renderer identity bound and matched; foreign rasters `render_error`; malformed ids rejected at construction.
- UTF-8 raw-text budget: `TextEncoder` (`reader.ts:288`), cap `8_388_608` (`:114`); registered UTF-8 test passes.
- `imageSmoothingEnabled`: zero matches in `packages/readers-tesseract/src/` and `tests/readers/` — fully removed.
- Budgets unchanged: `maxRasterPixels 4_000_000`, `maxRunOcrPixels 20_000_000`, `maxRasterEdge 8192`, `maxOccurrencesPerRun 100_000`, `check/openTimeoutMs 30_000` (`reader.ts:109–116`). No complexity-limit or assertion weakening found in the diff `546accd...HEAD`.
- No new test-only public knobs: `now`/`fetchImpl`/`idbFactory`/`online` hooks all predate wave-4 (`7699f97:240–243`).
- Receipt hygiene: `receipt.json` is refreshed to wave-4 (`candidate_commit`/`evaluated_commit` `1a655a1`, "41/41" note); no stale `567b482` attribution or "exact bytes by construction" claims in the receipt (the `handoff.json` mentions are correctly-framed history).
- q38 patch merged and installed: `package.json:40–41` + `bun.lock:67` `patchedDependencies`; patch file sha256 `74f0808c…db451`; installed `createWorker.js` sha256 `c0b1cd26…ae8a`, `index.d.ts` `eebc61f3…6c6e` — the signal/lang-payload repair is what the direct `{code,data}` boundary relies on.
- No stray edits: `git diff 546accd...HEAD` touches only owned implementation/test/artifact paths; `git status` clean before this artifact.

## Independent verification (this checkout, this session)

- `bun install --frozen-lockfile` — clean.
- `bun run tsc -b` — exit 0.
- `node --test tests/readers/crop-math.mjs` — **13 pass, 0 fail**.
- `node artifacts/tasks/T10/repro-planCrop.mjs` — **6/6** (`ALL OK`).
- `bun run test:browser -- tests/readers/tesseract.spec.ts` — **41 collected, 41 passed, 0 failed, 0 skipped** (10.4 s): 11 real-OCR incl. `AMOUNT DUE $108, a\n` PSM7 + full-page PSM6, the deterministic close-during-real-open gate, 4 ported lifecycle probes, 2 real cache-provenance tests.
- `python3 scripts/task_acceptance.py task T10 --report /private/tmp/inkflip-t10-wave4-review/run-review.json` — exit 0, `evaluated_commit=66655e1`, `commands_run=1`, `failures=[]`, `evidence_errors=[]`, tests 41/41.
- `bun run verify` — exit 0: bootstrap 49 + native-bootstrap 2 + coordination 64 = **115 checks**, self-check 16 commands.
- Probe harness `/private/tmp/inkflip-t10-wave4-review/probes.spec.ts` (47 tests, port 5192): **40 passed, 7 failed** —
  - 3 real product failures = F1/F2 evidence above (`ZOMBIE_JOB_CROSSTALK`, `ZOMBIE_PROGRESS`, `FOREIGN_HANDLE`);
  - 4 failures are stale wave-3 assertions in my probe copy (`worker init payload … readOnly`, `unavailable/failed IDB … missing_model`, `close during a real open … worker_crash`) — the wave-4 revision deliberately changed those semantics and the corresponding wave-4 versions pass inside the registered 41/41.
- Port `5192`: `lsof` shows no listener after the runs — **heavy reservation explicitly released**.

## Replayed wave-3 reproducers — outcomes

| Pauli reproducer | Wave-4 result |
|---|---|
| Close during stalled raster | **Pass** — settles `user_cancel` promptly, not `timeout` at deadline. |
| Late model preparation after close+remove | **Pass** — no post-close states; deleted cache not recreated. |
| Stale open cleanup vs newer open (same doc+generation) | **Pass** — newer open/handle/worker intact (`terminated:[false]`). |
| Late init progress/error after timeout | **Pass** — `progress:[]`, `errors:[]`, signal aborted. |
| Cache replacement after verification (real engine) | **Pass** — engine FS sha `7d4322bd…` despite `ed260abd…` replacement; 1 model request; control arm also passes. |

New boundary attacks: zombie-result misdelivery (**fail**, F1), zombie-progress admission (**fail**, F1 arm), handle-id collision (**fail**, F2), lease join/adoption (pass), close-with-joiners (pass), remove/reprepare race (pass).

## Not verified / scope notes

- No Beads writes, no pushes, no source edits; only this artifact is added on `review/devin/t10-wave4`.
- Upstream fallout of the trailing zombie response (second response hitting a deleted `promises` entry → `TypeError` risk at `createWorker.js:226`) was *not* observed — `pageerrors:[]` and r3 recovered; likely the late response resolved r3's re-registered entry with identical (blank) output. F1 stands on the demonstrated misdelivery alone.
- The 4 stale-assertion probe failures are harness drift, not product defects; they are listed for honesty and were not counted against the candidate beyond F1/F2.
- No Linux/device matrix; Playwright Chromium only, consistent with the registered suite.
- Observation only (not a finding): `prepareModel()` is itself a scope-owning operation, so calling it during a live extract supersedes (cancels) that extract — consistent with the one-operation-at-a-time model but worth confirming as intended API semantics.
- Observation only: `forwardError` admits only the lease-owner scope, which is dead once `open()` returns, so engine `errorHandler` events during recognize are never forwarded; recognize failures still surface through the job promise. Conservative, arguably intended; noted for completeness.

## Bottom line for the writer

F1: give `userJobId` a per-operation-unique component (`reader.ts:1271`). F2: give `OcrHandle.id` a clock-independent uniqueness component or compare handle identity directly (`reader.ts:581` plus the `.id` comparisons at `:696,:963,:1033,:1185,:1413`). Both are small, ownership-local fixes; everything else in the wave-4 revision verified clean.
