# T15 independent review — prove initial own-file no-egress behavior (TEST-15, gate G1)

- **Reviewer:** independent read-only reviewer (Devin Local subagent, coordinator-requested); not the writer (`devin-t15` / `4b09fb92`), never ran this code before this review.
- **Candidate:** `0bf638d589ba270ebd046357cab6ea1051274452` (impl `7804dc4`, tests `ed960fd`, evidence `0bf638d`; base `21be4c9`)
- **Review checkout:** `worktrees/pdf-t15` @ `work/devin/t15`, HEAD `0bf638d`, clean tree before and after review (evidence regenerated during reproduction was restored; only this file is added).
- **Round-1 verdict: changes-required.** All five acceptance criteria verify and the captured evidence is genuinely strong — real production build, real collaborators, independent server-side log, three honestly distinct modes, marker-free committed artifacts. Two defects in the *proof machinery* must be fixed before G1 rests on this receipt: the offline inspector passes on absent evidence (F1), and request headers — the one unconstrained carrier left on an allowlisted GET — are captured nowhere while the README claims they are (F2). Both fixes are small and well-specified; everything else is low/info.
- **Round-2 verdict (current): approved** — F1 and F2 resolved at `9cc6356`/`8bcbc12`, verified on candidate `d11db83`; every blocking probe now fails closed and the round-1 P3s are fixed or honestly bounded in the receipt's limitation list. See the Round-2 section below.

## Reproduced commands (this worktree, real counts)

| Command | Worker claim | Reproduced |
|---|---|---|
| `bun run test:privacy -- tests/privacy/local.spec.ts` | 4/4 pass | **4/4 pass, 0 fail/skip, exit 0 (~4.5s)** — real pinned Chromium, real two-pass Vite production build; ran twice (via `task T15` and `--report`) |
| `python3 scripts/task_acceptance.py task T15 --report /tmp/t15-run.json` | exit 0 | exit 0; `evaluated_commit=0bf638d…`, `collected 4 / passed 4`, `failures: []`, `evidence_errors: []` |
| `python3 scripts/inspect_network_receipt.py --capture .private/capture --canary .private/canary.json --dist tests/privacy/dist --receipt <out> --require-modes cold,warm,offline` | verdict=pass, 11/11, 47 req | **verdict=pass, checks=11 failed=0, requests=47, exit 0** (standalone, fresh captures) |
| `node_modules/.bin/oxlint tests/privacy/local.spec.ts tests/privacy/harness/mount.tsx` | 0/0 | 0 warnings, 0 errors (96 rules) |
| Fresh-run equivalence | — | Test 4 regenerated `network-receipt.json` + `capture/`: checks + capture records **byte-identical** to committed except ephemeral port and download sha256 (fresh random `report_id`/`run_key`); fresh digests verified against fresh canary manifest |
| Committed-artifact marker scan (independent) | marker-free | **0 hits** — all 11 markers × raw/url/b64/b64url/hex/hex-upper/b64-digest spellings + canary token + doc-sha slices across all 12 committed files in `artifacts/tasks/T15/` |

## Verification items

1. **Coverage honesty — PASS, verified against raw captures.**
   - *Cold* (4 captures): index boot (4 fixed-asset requests), open-mount journey (open→plan→malformed-error→replace→render→clear, 14 req), harness OCR+export (**real model path**: `GET /models/tessdata-fast-eng/7d4322bd/eng.traineddata` served 200 → `provenance:"network"`, `ready_memory` asserted in-test → IndexedDB `keyval-store/keyval/inkflip/models/eng.traineddata` slot with `value_sha256 = 7d4322bd…70b2` and `bytes=4113088` — I re-hashed the dist model and it matches the manifest, the IDB record, and `MODEL.sha256`), import reopen. Captures 00–01 show `idb:[]` before the fetch — a genuine cold→prepared transition, not cache.
   - *Warm* (1 capture): `ocrPrepare` asserts `provenance:"cache"`, `ready_cached`; `open()` reports `memory`. Zero `/models/` entries in requests **and** the server log shows only `GET /privacy.html` (no-cache) — zero refetch proven two independent ways.
   - *Offline* (3 captures): prepared page completes OCR→open→render→export with `setOffline(true)` — **server access log empty**, zero request failures, only `/assets/` cache-served request events. Cold context: model fetch fails `net::ERR_INTERNET_DISCONNECTED` → typed `unavailable_offline`/`missing_model` (real reasons, `readers-tesseract/src/errors.ts:39,53`), navigation blocked. Distinction is real.
2. **Canary coverage — PASS on captured channels.** 11 markers cover the contract's bytes/text/name/hash/crop/report set: filename, visible text, hidden `/Info` string, user note + hostile-payload-free token, document sha256, pdf b64 head, raster pixel sha256, report_id, run_key, export filename. Inspector checks raw/percent/base64/base64url/hex/hex-upper + digest-b64 spellings (superset of the in-test 4) against requests, request_failures, websockets+frames, egress records, console, page_errors, server_log path+query, all storage strings, download filenames. `allowed_channels:["downloads"]` is used only for report-derived markers — the local file the user explicitly requested. Residual escapes are on log channels only — F6.
3. **Allowlist rigor — PASS.** Allowlist is derived from the actual `dist` listing (230 paths) + `/`, `/index.html`, `/favicon.ico`; every request must be http(s) on the single pinned loopback netloc, read-only method, no query; server_log paths get the same checks. Worker-internal traffic is genuinely captured — the tesseract worker's internal `wasm.js` fetch (`resource_type:"other"`) appears in `requests`, so traffic from inside Workers cannot bypass the network layer even though the JS tripwire wraps only the page realm. Redirects and `sendBeacon` surface as request events (POST would trip the method check; beacon construction trips the egress check). `form-action 'none'` + navigation requests are captured. Enumerated-but-unrecorded egress kinds and WebRTC are the residual — F4/F7.
4. **Redaction honesty — PASS, independently verified.** Raw `.private/` captures vs committed `capture/` diff to exactly one line: `downloads[0].filename` → `<marker:export_filename>` — the only channel legitimately carrying a marker. `document_sha256_16` in the receipt is `sha256(doc_sha256_hex)[:16]` (hash-of-hash); I recomputed every `sha256_16` in the committed receipt from the live private `canary.json` — **all 12 match**. My own multi-encoding grep found zero marker material, zero doc-sha slices, zero home paths in committed artifacts. The receipt test itself re-asserts marker-freedom of receipt + every redacted capture, and the stale redacted dir is wiped before regeneration.
5. **Inspector self-trust — PARTIAL; fails closed on content, fails open on absence (F1).** Probe-verified exit≠0 for: empty capture dir (exit 2), no markers, markerless ids, origin disagreement, non-http schemes, foreign origin, unlisted path, POST, query strings, marker in any encoding incl. base64-in-console, websockets, beacon/EventSource/window.open/SW-register records, foreign worker/fetch/xhr targets, unexpected IDB/localStorage/cookies/CacheStorage, wrong IDB sha, `leg.ok:false`, offline server hits, missing required mode, missing cold-boot capture, telemetry literals, literal-host-seen-at-runtime. Probe-verified **pass** for: captures stripped of `legs`+`storage` keys, a fully emptied capture, marker in `legs[].detail`, unrecognized egress kinds, foreign host appearing only in `request_failures`, split/wrapped-encoded markers on console.
6. **Scope — PASS.** `git diff 21be4c9..0bf638d` = `scripts/inspect_network_receipt.py`, `tests/privacy/{README.md,local.spec.ts,harness/mount.tsx,harness/privacy.html}`, `artifacts/tasks/T15/` only. `planning/` byte-identical (empty diff). No source changes, no assertion weakening, no lockfile/schema/routing/golden touches. `test:privacy` is the registered T15 command (`config/acceptance-commands.json:141`), `bun run test:privacy` maps to `task_acceptance.py run test:privacy`.
7. **Deployment headers — PASS.** The spec's `SECURITY_HEADERS` + `cacheControl` reproduce `planning/deployment/_headers` verbatim (CSP, Referrer-Policy, nosniff, Permissions-Policy, CORP; `/`+`/index.html`+`/release.json` no-cache; `/assets/*`+`/models/*` immutable), defaulting other paths to no-cache — a safe superset. The proof does not rely on the CSP: every channel is captured and asserted.
8. **Harness authenticity — PASS.** `mount.tsx` binds the real modules — `packages/readers-pdfjs` (pinned `pdfjs-dist` 6.3.289 legacy + same-origin worker asset), `readers-tesseract` `TesseractOcrReader` (real `tesseract.js@7.0.0` against staged same-origin worker/core/traineddata), `contracts.seal`, `packages/reports/export` engine, and the shipped `apps/web` `ExportPanel`. The T08 open and T22 import mounts are the app's own built pages; every `data-testid` the spec drives exists in the production components (`FileDrop.tsx`, `OpenWorkspace.tsx`, `ImportWorkspace.tsx`). Nothing at the contract surface is stubbed; only wiring is test-owned — consistent with the preview-mount role while T13 is unlanded.

## My novel probes (scratch copies of the real captures under `/tmp/t15-probe*`, deleted after run)

| Probe (mutated capture) | Inspector result |
|---|---|
| empty capture dir | exit 2 (`no capture files`) ✓ |
| marker appended as `?doc=` on a request URL | exit 1 — query + marker violations ✓ |
| foreign `GET https://evil.example.com/x` in requests | exit 1 — 3 checks ✓ |
| `beacon` egress record | exit 1 ✓ |
| **all `legs` + `storage` keys removed from every capture** | **exit 0 — pass (F1)** |
| **one capture fully emptied (no requests/legs/egress/server_log)** | **exit 0 — pass (F1)** |
| all `*warm*` captures deleted | exit 1 — required mode missing ✓ |
| base64 marker in console | exit 1 ✓ |
| `leg.ok:false` | exit 1 ✓ |
| POST same-origin | exit 1 — method ✓ |
| unexpected IDB entry / marker in localStorage | exit 1 / exit 1 ✓ |
| same-origin websocket record | exit 1 ✓ |
| **`legs[].detail` containing a marker** | **exit 0 — pass (F3)** |
| **`form.submit` egress record to a clean foreign host** | **exit 0 — pass (F4)** |
| **foreign host only in `request_failures`** | **exit 0 — pass (F5)** |
| marker split across two console lines | exit 0 — pass (F6) |
| base64-of-JSON-wrapped marker in console | exit 0 — pass (F6) |
| single/double percent-encoded marker in console | exit 1 ✓ |

## Findings

- **F1 — P2 — `scripts/inspect_network_receipt.py` fails open on absent evidence.** The validator that produces the committed G1 receipt requires *no* evidence presence: `journey_legs_completed` iterates `cap.get("legs", [])` so a capture with zero legs passes vacuously; `storage_document_free` does `if storage is None: continue`; non-offline captures needn't contain a single request; no required leg names are enforced (the detail string names open/error/render/OCR/export/reopen/clear but nothing checks them). Probe: stripping `legs`+`storage` from all 8 captures, or zeroing one capture entirely → `verdict=pass`. Today's evidence is dense and the in-test `assertCaptureClean` requires `requests>0` for non-offline captures, so this did not produce a false receipt — but the offline re-validator cannot be the independent check it claims to be while absence passes. Fix (small): require `legs` nonempty with named legs per mode/surface, require `storage` present, require ≥1 request (or an explicit `offline` flag) per capture, and treat missing keys as violations rather than skips.
- **F2 — P2 — request headers are an unmonitored egress channel; README claims them captured.** The `Capture.requests` interface records `url/method/resource_type/is_navigation/post_body` (`local.spec.ts:363-369`) — no headers — and the server access log records only `method/path/query/status`. `README.md:53` states "Requests (URL/method/headers/post body), responses, …" — **neither headers nor responses are captured**. This is the cleanest remaining exfil path: every other carrier on an allowed request is closed (path allowlisted, query banned, method read-only, body scanned), but a same-origin `GET /privacy.html` with `X-Doc: <marker>` reaches the server invisible to **both** capture layers and passes all 11 checks. Referer is doubly mitigated (`no-referrer` policy + only allowlisted query-free URLs exist to be leaked), so the residual is deliberately-set custom headers — narrow but real, and it is the *only* blind spot that reaches the wire. Fix: record `req.allHeaders()` in request entries + request headers in the server access log, and scan them; or correct the README and bound the claim explicitly.
- **F3 — P3 — `legs[].detail` is never marker-scanned** in either layer (`observation_texts` and `assertCaptureClean` both omit it). Probe: marker inside a leg detail → pass. Leg details are a log channel; a typed error echoing the filename would go unflagged (redaction still strips it from public copies).
- **F4 — P3 — unrecognized egress `kind`s pass unchecked.** The inspector validates `{beacon,eventsource,window.open,serviceworker.register}` and `{fetch,xhr,worker,websocket}` and ignores anything else (`form.submit` to a foreign host → pass). The tripwire only emits wrapped kinds, so current records are covered; the check should flag kinds outside the closed set rather than skip them.
- **F5 — P3 — `request_failures` skip origin/allowlist/method/query checks.** Normally shadowed — a failed request also appears in `requests` (verified: both offline failures in capture 07 do) — but a failures-only record would pass. Cheap to include in check 1.
- **F6 — P3 — encoded/fragmented markers escape on log channels.** Substring matching misses markers split across two console lines, base64-of-a-wrapping-JSON, and content beyond the 500-char console / 300-char detail / 300-char ws-frame truncations (truncation happens *before* capture — the tail is never recorded). Network carriers are closed by method/query/allowlist so exposure is confined to console/egress-detail/leg-detail logs; planning requires "none of the markers appear in default logs", so partial-log scanning is a bounded gap worth recording.
- **F7 — P3 — WebRTC / WebTransport are unmonitored and unlisted.** `RTCPeerConnection`/`WebTransport` data channels emit no `request` events and aren't wrapped. Verified zero `RTCPeerConnection|WebTransport|sendBeacon|EventSource` literals in the built bundles (only `navigator.connection`), so nothing today uses them — but the limitation belongs in the receipt's list alongside OS-level capture. Also `page.on('dialog')` is unregistered: a fired `alert()` from the hostile annotation would auto-dismiss unrecorded (the annotation is React-escaped text today; the import render asserts content but not literal-text safety).
- **F8 — P3 — capture `06-offline-cold-nav` is labeled `mode:"offline"` while recording an online navigation** (pre-`setOffline` leg of ctxB; correctly carries no `offline:true` flag so no offline checks apply). Receipt counts it among offline captures — cosmetic, but the label overstates; rename or annotate.
- **F9 — P3 — provenance claims are in-test-only.** Cold `network` provenance, warm `cache` provenance and zero-refetch are asserted by the spec, not re-derived by the inspector. The committed captures independently substantiate them (`/models/` present in 02's requests+server log, absent in 04), so the evidence is there — a dedicated inspector check would harden it.
- **F10 — info — `allowed_channels` is self-attested.** The redaction/allowlist choices live in the private `canary.json`, which is git-ignored; committed evidence shows the effect (download filename → `<marker:export_filename>`) but not the rule. Currently narrow and legitimate; worth a receipt field if the mechanism is reused.
- **F11 — info — commit message says "8 greppable markers"; the manifest carries 11** (8 static + raster_sha256/report_id/run_key/export_filename pushed at runtime). Receipt/handoff say 11 — cosmetic.

## Assessment of the recorded limitations (are they honestly bounded?)

- *T13 unlanded → no composed shell:* honest and correctly bounded. The shell does not exist, so there is nothing to fake; the suite drives the real shipped mounts plus a test-owned page binding the real collaborators — the strongest available target. The receipt names it plainly. It does **not** undermine G1's "initial own-file no-egress" claim for the code that exists, provided the claim is re-proven on the composed shell when T13 lands (freshness rules already force revalidation when `apps/web` composition changes).
- *No OS-level capture:* honest; planning itself defers proxy/firewall proof to the release profile. Correctly recorded.
- *No service worker:* honest; none ships, so cold-offline navigation cannot load a shell — the suite proves the honest failure rather than claiming readiness, exactly as planning's "cache failure is explicit" requires.
- *Missing from the list:* WebRTC/WebTransport channel (F7) and the header channel (F2) — the two unmonitored wire paths — are not recorded; F2's fix or a recorded bound is part of the required change.

## What would change the verdict

Fix F1 (inspector requires evidence presence) and F2 (capture+scan request headers or correct+bound the README claim); F3–F5 are one-line hardenings worth taking in the same pass. The remaining items are documentation-level. The underlying captured evidence, mode design, canary model, allowlist enforcement, redaction and scope discipline are sound and reproduced.

---

# Round 2 — re-review of `d11db83` (worker `9cc6356` inspector + `8bcbc12` spec/README + `d11db83` evidence)

Reviewed in this worktree on `work/devin/t15` @ `d11db83`, clean tree; all findings below re-verified by rerunning the suite and re-running **my own** mutated-capture probes (the worker's probe table was not trusted).

## Reproduced commands (round 2)

| Command | Worker claim | Reproduced |
|---|---|---|
| `bun run test:privacy -- tests/privacy/local.spec.ts` | 4/4 | **4/4 pass, 0 fail/skip, exit 0** via `task_acceptance.py task T15 --report /tmp/t15-r2-run.json` — `evaluated_commit=d11db83`, `collected 4/passed 4`, no failures/evidence errors |
| `python3 scripts/inspect_network_receipt.py` (standalone on fresh captures) | verdict=pass, 13/13, 47 req | **verdict=pass, checks=13 failed=0, requests=47, exit 0** — two new checks `capture_evidence_present` + `model_fetch_provenance` present and passing |
| Fresh-run digest equivalence | digests only | all 12 committed-receipt `sha256_16` values recomputed from the live canary — **all match** (the report-id/run-key/export-name digests are deterministic across runs; only download bytes vary) |
| Committed-artifact marker scan (independent) | marker-free | **0 hits** across all markers × 7 encodings in all committed `artifacts/tasks/T15/` files at `d11db83` |
| `node_modules/.bin/oxlint` | 0/0 | 0 warnings, 0 errors |

## Round-2 probe results (my mutations of the fresh raw captures, `expect !=0`)

| Probe (class) | Round-1 result | Round-2 result |
|---|---|---|
| Strip `legs`+`storage` from all captures / empty one capture / `legs` key absent / `legs:[]` (F1) | **pass (defect)** | **exit 1 — fail closed** ✓ |
| Remove a required journey leg (clear / error / reopen removed entirely) | n/a | **exit 1** — union enforced ✓ |
| Marker in `requests[].headers` on an allowlisted GET; marker in `server_log[].headers`; `headers` key removed or `null` (F2) | channel absent | **exit 1**; headers now recorded from `allHeaders()` on every request/failure **and** in the server access log — verified real browser + wire headers in committed captures (incl. on the two offline-blocked requests) |
| Marker in `legs[].detail` (F3) | pass | **exit 1** ✓ |
| `form.submit` + novel `bluetooth.request` egress kinds (F4) | pass | **exit 1** — closed `EGRESS_FORBIDDEN`/`EGRESS_SAME_ORIGIN` sets, unknown kinds violate ✓ |
| Foreign host only in `request_failures`; foreign host in `responses` (F5) | pass | **exit 1** — wire checks extended ✓ |
| Marker split across console lines; whitespace-smeared marker; halves adjacent across channels (F6) | pass | **exit 1** — joined + whitespace-collapsed sweep ✓ |
| base64-wrapped marker in console; base64 marker inside a request header (F6) | pass | **exit 1** — `B64_TOKEN_RE` decode+rescan ✓ |
| `webrtc` egress record; recorded `dialogs` entry (F7) | unmonitored | **exit 1** — constructor tripwire + dialog=violation ✓ |
| Warm-mode model request (even cache-satisfied, zero server hits); all model evidence removed; offline served model path (F9) | in-test only | **exit 1** — `model_fetch_provenance` re-derives from wire evidence ✓ |
| `dialogs`/`storage`/any required key absent; request missing `url`; leg missing `ok` | — | **exit 1** ✓ |
| Marker in `downloads[].filename` (a marker *not* declared `allowed_channels`) | — | **exit 1** — the downloads allowance stays scoped to the three report-derived markers ✓ |
| Benign `#fragment` URL (no marker) | — | exit 0 — correct: fragments never reach the wire |

## Round-2 findings

- **R2-F1 — P3 — `storage:{}` still passes vacuously.** `capture_evidence_present` requires the `storage` key but not its sub-fields; a `{}` satisfies both it and `storage_document_free`. Narrower residue of F1 — the producer (`storageDump`) always emits the full sub-structure (verified in committed captures), so this needs a hand-edited/broken capture. One-line tightening: require the storage sub-keys. Not blocking.
- **R2-F2 — P3 — bounded residual escapes, now honestly recorded.** Marker halves with non-whitespace junk between them, and base64-of-UTF-16 marker, still evade (probes exit 0); markers beyond the raised truncation bounds (console 2000, details/ws 1000) likewise. The receipt now carries an explicit "log-text bound" limitation and the joined/collapsed/b64-decode sweeps shrink the window to exactly this class — acceptable as bounded.
- **R2-F3 — info — `model_fetch_provenance` detail says "exactly once"** while the check accepts ≥1 cold model request. Semantics are right (the wire path must be exercised and warm/offline must be clean); wording nuance only.
- **Weakening check — PASS.** The diff is strictly additive: all 11 original checks retained + 2 new; forbidden-egress set grew (webrtc/webtransport/form.submit), unknown kinds flip from ignored to violations; truncations *raised* (more content scanned, not less); in-test assertions added (headers non-null, dialogs empty, failure wire checks, legs/detail/dialog/response haystacks, split sweep); `mode:"online"` is a new honest label, not a relaxed requirement — `cold,warm,offline` are still required and the offline flag semantics are unchanged. No assertion was loosened to pass.
- **F7/F8/F10/F11 confirmed closed:** `webrtc`/`webtransport`/`form.submit`/`requestSubmit` constructors are tripwired in `armEgress`; capture `06` is now `mode:"online"`; `allowed_channels` is echoed per marker id in the committed receipt (`["downloads"]` for the three report-derived markers, `[]` elsewhere); docs say 11 markers; the two new limitations (constructor-level WebRTC/WebTransport guarantee, log-text truncation bound) are recorded verbatim in the canary manifest and receipt.
- **F2 depth note:** `allHeaders()` is resolved in `endCapture` for every request/failure entry, `null` fails closed in-test (`assertCaptureClean`) *and* in the inspector (`capture_evidence_present`); the static server independently logs `req.headers` — the two layers genuinely see the wire now. Committed captures carry real header sets (sec-fetch-*, sec-ch-ua, origin, host, empty `referer` consistent with `no-referrer`).

## Round-2 verdict: **approved**

F1 (fail-open validator) and F2 (unmonitored header channel + README overclaim) are resolved and probe-verified fail-closed; F3–F5 are fixed; F6/F7 are fixed to the bounded level now recorded as receipt limitations; F8–F11 are closed. The committed evidence reproduces deterministically (4/4 tests, 13/13 checks, 47 requests, marker-free artifacts), scope stayed inside `tests/privacy/` + `scripts/inspect_network_receipt.py` + task artifacts, `planning/` untouched, and nothing was weakened to pass. The G1 own-file no-egress claim now rests on a validator that fails closed on absent, hollowed, or smuggled evidence.
