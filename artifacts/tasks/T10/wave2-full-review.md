# Independent T10 final candidate review — changes required

Exact candidate: **87e2073fb53db17cea0af3ed55cbe249f4e29456** on `review/codex/t10-wave2`, checkout `/Users/zubair/Code/Projects/pdf project/worktrees/review-codex-t10-wave2`. Reviewed full T10 delta against merged canonical base `500abfc`, including original adapter and 831e0a1 implementation, 567b482 tests, 8fb1cee/87e2073 evidence. Reviewer: Pauli, independent Codex session `01a093db-42d8-79d3-befb-0b7680c3e405`, distinct from SWE writer 24843e3f. HEAD and clean tracked status verified at end. No production/test source edits, commits, Beads, receipt, acceptance or publication writes. Temporary experiments only; frozen dependency installation and ignored build/test outputs in the isolated review checkout. Artifact-only writer follow-up is outside this exact verdict.

Read code-review skill, current canonical AGENTS/HOMEBASE, applicable worktree guidance and effective T10 contract, coordinate/reader/lifecycle contracts and acceptance guidance. Scope is the full selected-page/crop adapter, model/engine boundary, identity, occurrence geometry, resize and maintained acceptance coverage. No general feature audit or coordinator changes.

## Verdict

**Do not accept this candidate.** The requested lower-edge arithmetic and actual-factor rendering are verified. All existing candidate tests pass, but independent probes reproduce invalid occurrence polygons, model integrity bypass, inconsistent planned/output reader identity, missing deadline coverage, and incorrect byte accounting. The public test-only smoothing knob is unnecessary and explicitly prohibited; pixel regressions are not included by T10's effective acceptance command.

## Executed checks and honest counts

- `bun run test:browser -- tests/readers/tesseract.spec.ts --workers=1`: **11/11 passed**, through registered structured-report harness, exact source candidate, real Chromium/Tesseract.js 7.0.0 staged worker/core and model. Observed PSM7 raw text `AMOUNT DUE $108, a`; engine version `5.1.0-288-g2a9c1`; reported PSM/OEM null are retained honestly, configured PSM/OEM supplied separately. This proves recognition, not perfect transcription.
- `node --test tests/readers/crop-math.mjs`: **13/13 passed**.
- `bun run test:browser -- tests/readers/crop-pixels.spec.ts --workers=1`: **4/4 passed**, real production PNG path, stub recognition only.
- `bun x --no-install tsc -b tsconfig.json`: **exit 0**.
- TEMP `default.spec.ts`: **4/4 passed** with smoothing option omitted from calls, assertions unchanged, candidate production source.
- TEMP `removed.spec.ts`: **4/4 passed** after removing the public option, cropToBlob parameter, assignment and call argument from a temporary source copy. Real default-smoothing PNG path, assertions unchanged.
- TEMP `mutation.spec.ts`: **2 expected mutation failures / 2 controls passed**, no skips: restoring integer destination dimensions makes both source branches fail at pixel (4,0), red `[255,0,0,255]` instead of black `[0,0,0,255]`. Harness correctly exits 1; this is mutation evidence, not a passing suite.
- TEMP `resource.spec.ts`: **1/1 diagnostic probe passed**, reproducing current incorrect UTF-8 cap and planned/output reader identity through real adapter PNG path.
- `bun /private/tmp/inkflip-t10-wave2/probes.mjs`: actual mapEngineBlocks + contracts.validateReport show zero-area polygon rejection; real reader extraction remains pending 123ms with checkTimeoutMs=20 and a stalled raster source, no recognition or automatic worker termination.
- TEMP real OCR `cache-integrity.spec.ts --grep 'real English crop OCR'`: **1 expected diagnostic failure** at the one-model-download assertion; recognition and all preceding model-identity assertions passed even though engine received different bytes. Details below.

All browser commands used `NODE_OPTIONS=--require=/private/tmp/inkflip-t10-port5192.cjs`, a temporary net.Server listen shim changing only test loopback port0 requests to **5192**, with one worker and no port fallback. Browser runs were sequential. No server intentionally left running; suites close their server. No old writer5191 used. No other heavy job started.

Setup failures were environmental: initially missing Playwright dependency; sandbox tempdir/network failures during frozen install; sandbox EPERM binding5192. Frozen install and browser runs succeeded with approved escalation. A first TEMP copy missed errors.ts's runtime import and failed to bundle; corrected only that temp path and reran. None of these are counted as passing product tests. No full verify/build:web rerun claimed; their writer evidence remains distinct. Parent is handling separate coordination guard/count correction and criterion receipt.

## Findings (exact source line numbers)

### P1 — Every normal OCR box is emitted as a zero-area bow-tie

`packages/readers-tesseract/src/occurrences.ts:85–89` orders corners TL,TR,BL,BR. With bbox `{x0:1,y0:2,x1:11,y1:12}`, actual mapEngineBlocks emits `[[1,2],[11,2],[1,12],[11,12]]`, twice signed area **0**. A known-valid repeated-occurrences report passes `validateReport(report,false)`; replacing only its first polygon with this real mapped polygon fails **GEOMETRY: Degenerate source polygon**. Validator is contracts/core.ts:985–997. This affects ordinary recognized word boxes, not only pathological input. Current centroid and bounding checks are insensitive to crossing edges.

Minimum revision: perimeter order TL,TR,BR,BL; add a real mapped occurrence polygon test and a report-level semantic-validation test to the registered T10 surface. Retain actual supplied boxes and estimated precision; never loosen the validator.

### P1 — Engine can consume different model bytes from the reported verified hash

`engine.ts:145–152` initializes by language string and readOnly cache, never passes prepared.bytes; `model-cache.ts:291–309` treats unavailable/failed cache writes as nonfatal ready_memory. Exact pinned upstream implementation at `apps/web/node_modules/tesseract.js/src/worker-script/index.js:98–155` shows readOnly means read cache or fetch langPath; it does NOT mean integrity-verified-only.

Reproducer `/private/tmp/inkflip-t10-wave2/cache-integrity.spec.ts`: same real first English OCR case, only TEMP harness changes: adapter `idbFactory:null` (its documented unavailable-cache path) and model-serving instrumentation. First request serves original **4,113,088** bytes and passes SHA verification. Worker cache miss makes a second request; serve same model plus one appended zero byte (**4,113,089** bytes). Real worker initializes, completes OCR with `AMOUNT DUE $108, a`, and output still claims the original model SHA and network provenance. Existing assertions through recognition/model identity pass; final request-count assertion fails `2 !== 1`. Thus this is independently reproduced identity/integrity failure, not a hypothetical cache race.

Minimum revision: ensure engine receives the exact prepared payload or fail honestly when that cannot be guaranteed. The pinned worker supports language objects `{code,data}` on cache miss, but also checks cache first: any direct-byte design must deliberately bypass stale cache reads and verify the exact v7 createWorker surface before implementation. Do not merely point two fetches at the same URL or relax the hash expectation. Add unavailable-cache/failed-cache-write integrity regressions, and ensure model/engine cache namespaces cannot disagree silently.

### P1 — Immutable plan's reader ID differs from output/occurrence reader ID

`reader.ts:440–447` builds planned IDs with renderReaderId='pending'; output readerFor and occurrence generation (`reader.ts:815–819`) use actual raster renderer. Probe through real PNG path: planned `rdr_tesseract_eng_lstm_psm6_desktop_pending`; output `rdr_tesseract_eng_lstm_psm6_desktop_synthetic-fixture`. Node probe with renderer `render` shows the same mismatch. contracts/core.ts:1012–1014 requires planned readers exist; :1079–1081 requires every retained occurrence reader to be in its check's reader_ids. Returning OCR output cannot satisfy that immutable plan without caller rewriting it or inventing another reader record, neither part of the adapter contract.

Minimum revision: establish stable configured renderer identity before finalizing CheckPlan, or otherwise have a coherent stable reader identity used by describe/plan/output/occurrences without changing the immutable plan after execution. Preserve actual renderer/settings provenance. Add assembled plan/output report validation to registered T10 checks; it should catch both identity and polygon defects.

### P1 — Check deadline/cancellation does not bound raster acquisition or worker initialization

`reader.ts:739` awaits rasterSource without the deadline; :787 awaits ensureWorker without deadline; only recognize is wrapped at :788–796 with a fresh full timeout each attempt. RUNTIME_LIFECYCLE requires finite checks, cancellation and retries only within remaining run budget. Real reader probe configured timeout20ms, returning a never-resolving rasterSource; at **123ms** extraction is still pending, recognition calls=0, auto terminations=0. A user cancellation during that wait has no poll until raster resolves. A stuck initialization has the same unwrapped await by direct source inspection.

Minimum revision: apply one absolute deadline/cancellation scope to the complete asynchronous extraction attempt/retry chain, pass remaining budget, and prevent late upstream completions from creating workers/emitting stale results. Preserve already completed unrelated checks. Add stalled-raster, stalled-init, cancellation-before-recognize and retry-budget tests; do not merely increase test timeouts. The probe manually closes the reader after observing the failure; it does not leave an OCR worker running.

### P2 — Raw-text byte cap counts UTF-16 length

`reader.ts:824–829` uses rawText.length for maxRawTextBytesPerRun. TEMP browser probe returns raw text `é` (2 UTF-8 bytes), budget1, real crop/PNG path: check still completes. Minimum revision: measure intended encoded bytes (`TextEncoder().encode(rawText).byteLength` for UTF-8 contract), preserve raw text, add multibyte boundary coverage. No cap increase.

### P2 — Remove public smoothing test option; same regressions work in production settings

Actual type is **OcrReaderConfig**, not OcrAdapterOptions. `reader.ts:255–261`, :270, :300 and :783 add/route the test-only imageSmoothingEnabled option. Explicit parent instruction forbids a public product escape knob for testing. Its own comment says it exists for tests, and changing it also changes pixels without adding configured reading identity.

Minimum revision: delete option/comment, parameter, ctx assignment and call argument; remove smoothing inputs from pixel harness. Leave default canvas smoothing true. Independently verified **4/4** tests pass with complete removal, and old integer-draw mutation fails both downscale tests without changing any expected pixel bytes. No alternative public knob, mock drawImage, threshold relaxation or test-only canvas instrumentation is needed on the tested Chromium.

### P2 — New pixel regressions are outside the maintained T10 acceptance command

Effective `python3 scripts/coordination.py task T10` command is only `bun run test:browser -- tests/readers/tesseract.spec.ts`; it collects 11 OCR tests. The 4 crop-pixels tests run only when explicitly selected (or an unfiltered broader run). Their passing manual evidence is useful but does not make T10/G1's task command protect the rendering fix.

Coherent minimal test revision with option removal: extract reusable pixel fixture/runner helpers into a test-only module with no global hooks; register its four cases inside a scoped describe in **tests/readers/tesseract.spec.ts**. Ensure the OCR and pixel harness hooks are scoped so moving/importing tests does not make both top-level harnesses bind/run for every test. Keep production PNG capture at stub recognition boundary. Effective T10 command should then collect **at least 15 cases**, before added contract/lifecycle regressions. Do not alter frozen planning, gate definitions, assertions or goldens. The 13 arithmetic cases likewise remain a separate manually executed command unless incorporated by an approved maintained test surface.

## Accepted part of revision and remaining handoff

Lower-edge three-factor computation is constant work, retains six-decimal factor, positive floor dimensions and caps; actual draw destinations use cropWidth*k and cropHeight*k in both source branches; nonzero fractional clipping is recorded in output units. The 49×80 test independently proves real PNG geometry at production default settings, and the mutation establishes discrimination. No further arithmetic redesign is requested by this review.

Minimum next source/test revision should fix the above actual adapter defects, remove the public knob, and put robust pixel/contract regressions through the registered T10 surface. Worker criterion receipt is separately being prepared by the parent-assigned same writer; it cannot substitute for independent approval or repair a failing contract. Do not fabricate coverage or rewrite this exact-candidate result as acceptance.

Repro artifacts: `/private/tmp/inkflip-t10-wave2/` contains default.spec.ts, removed.spec.ts, mutation.spec.ts, resource.spec.ts, cache-integrity.spec.ts, probes.mjs, temporary modified source directories and playwright.config.mjs. `/private/tmp/inkflip-t10-wave2-variants.py` builds the initial variants (its generated errors.ts requires the recorded absolute runtime import correction before rerunning removed/mutation). No shared writer files modified.
