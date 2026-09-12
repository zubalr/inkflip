# Independent pdf-ebz review

Candidate **68d31df54734e2d086f0915346b04a20e2e8d1e2**, parent **500abfc**, branch `review/codex/pdf-ebz`, isolated checkout `/Users/zubair/Code/Projects/pdf project/worktrees/review-codex-ebz`. Reviewer: Pauli (`01a093db-42d8-79d3-befb-0b7680c3e405`), independent Codex, not Astra implementation owner. Reviewed all 21 candidate files, including patch/types, manifest/lock/provenance, dependency checker, scope additions, tests and recorded evidence. Current canonical AGENTS/HOMEBASE and code-review skill applied. No source edits, commits, Beads, pushes or acceptance writes. End HEAD unchanged and tracked/untracked Git status clean.

## Verdict

**Changes requested: clear the negative-control package override in the registered TEST-02 wrapper, and resolve or explicitly scope the P2 input-loading cancellation gap.** The principal hidden-initializer defect IS fixed: readiness/pending dispatched jobs settle and the raw browser worker physically stops. No additional defect found in that constructor/transport path, patch installation, provenance or freshness wiring.

The gap concerns a supported recognize input-loading call which has not yet entered the pending-job registry. This is NOT evidence that initialization still leaks its worker, and NOT a request to implement T10's operation deadline in this patch. Existing upstream preprocessing already had this behavior; the new lifetime signal does not yet cancel it.

## Executed evidence (pinned runtime)

Every Node run used PATH prefix `/Users/zubair/.local/share/mise/installs/node/22.23.2/bin`; `node --version` = v22.23.2, Bun =1.4.0.

- `bun install --frozen-lockfile`: exit0, isolated review checkout, 86 packages installed; no tracked changes. Parent's two separate fresh-clone proofs were not duplicated or claimed.
- `node --test tests/build/tesseract-worker.test.mjs`: **11/11 pass**, zero skipped/cancelled.
- `node --test tests/build/tesseract-browser.test.mjs`: **4/4 pass**, zero skipped/cancelled; real Chromium workers stop independent loopback ticks at load, loadLanguage, initialize and after readiness. No OCR, core or model code loaded.
- `python3 -m unittest discover -s tests/build -p test_dependency_patch.py -v`: **7/7 pass**. Exact count is **one positive control and six tamper cases**, not seven negative tamper cases.
- `python3 scripts/check_dependencies.py --frozen`: **24 passed,0 failed**, including installed constructor/types hashes and 212 staged files.
- `python3 -m unittest discover -s tests/build -v`: **46/46 pass**, includes nested installed-constructor 11 and real-browser4. Counts are nested, not 61 Python tests.
- TEMP independent stalled-loader unit probe: **0/1 pass,1 reproduced failure**, zero skipped/cancelled.
- TEMP independent real-browser stalled image URL probe: **0/1 pass,1 reproduced failure**, zero skipped/cancelled. Details below.

`verify`115 and historical old-library negative controls are writer evidence inspected, not independently rerun here. All independent browser runs used ephemeral loopback ports, were sequential, and were closed. Nothing remains running or queued. No heavy OCR reservation used.

## P2 — lifetime abort leaves recognize() pending while loadImage is pending

Affected candidate hunk: `patches/tesseract.js@7.0.0.patch:29–47` (stop's settlement loop); installed patched `src/createWorker.js:50–61` and existing `:188–204` (recognize/detect await loadImage before calling startJob). Coverage gap: `tests/build/tesseract-worker.test.mjs:122–134` releases image loading at line131 before awaiting rejection, so it establishes no late dispatch but not abort settlement of the API call.

Reproducer 1, `/private/tmp/inkflip-ebz-probes/input-pending.test.mjs`: run the actual installed constructor with the same transport-only seam as its unit suite; loadImage returns a never-settling promise. Initialize normally, call recognize(), abort its WorkerOptions.signal. After50ms: **outcome='still pending',terminated=1,recognizeMessages=0**. The added assertion expects rejection with the original abort reason and fails.

Reproducer 2, `/private/tmp/inkflip-ebz-probes/browser-input.test.mjs`: bundle installed package source; initialize its normal client against the existing tiny protocol worker; call real `worker.recognize('/hang')`, where local server accepts but does not answer. Abort after40ms; after another100ms its promise is still pending. Test fails pending!=rejected. No fake loader in this browser probe, no OCR/core/model. Page/browser/server closed after observation. This is an ordinary supported URL input accepted by upstream, not a fabricated transport message.

Cause: stop rejects readiness and entries in `promises`, but recognize/detect await browser loadImage before adding an entry. The main-realm fetch/FileReader/image conversion isn't part of worker termination. A forever-pending input therefore retains an API continuation despite the new lifetime signal. It also allows image loading to begin after termination, since the first terminal check is startJob after loading.

Minimum coherent direction: enroll each async image-input API call in the owned cancellation lifecycle before starting loadImage, reject it immediately on stop, and prevent later dispatch/results. Thread cancellation into fetch/FileReader where those operations expose cancellation; keep rejection handling for nonabortable conversion completion, and avoid merely racing-and-forgetting the loader. Preserve the existing Tesseract protocol and Promise API; no global Worker patch or second protocol. Add a test that asserts settlement WITHOUT releasing the image first, then separately release it and prove no late dispatch. Cover terminate() as well as signal and the analogous detect path if kept supported. Any newly patched loader file needs its provenance/file allowlist updated, not bypassed.

If the parent deliberately limits pdf-ebz to raw-worker construction plus already-dispatched jobs, this can instead be explicitly classified as a remaining upstream input-preparation limitation; then narrow the feature claim accordingly and retain T10's independent operation deadline and ownership guard. It must not be represented as cancellation of every outstanding recognize() promise. This review does not decide an unrequested scope expansion into T10.

## What was checked and found sound

- `signal` is destructured out of worker options before protocol payloads, avoiding noncloneable AbortSignal transmission. Pre-aborted signals reject before spawn. One idempotent stop path nulls the transport, removes the abort listener, rejects readiness and registered jobs, terminates synchronously, and ignores late messages. Init chain failures now reach stop instead of an empty catch. Ready-worker errors/termination settle dispatched jobs. Success control preserves original action sequencing and language-byte payloads.
- Error-handler callback remains called for reject messages; init promise rejection occurs before that callback and is chained to cleanup. Generic worker errors stop the transport. No callback/protocol change requiring a separate finding was established. The existing removal of the unconditional throw for a handled worker rejection lets callers consume Promise rejection rather than also getting an uncaught event throw.
- Frozen Bun declarations match in package.json and bun.lock. Clean installed constructor and types match the exact patched hashes and recorded patch hash. I copied only those two installed files into TEMP and reverse-applied the committed patch: both resulting SHA256 values equal recorded upstream_sha256 values. No shared package cache edit or unrecorded node_modules repair was used.
- Origin/license and the unsupported unpatched prebuilt client dist entry are documented. Bundled source is necessary: the patch intentionally does not rewrite worker/core/model assets or prebuilt dist clients. Actual browser tests exercise that source entry. T10 must switch its separate unmerged harness to it as already directed; this does not make current T10 dist consumption patched.
- `execution/overrides.json` adds `patches/` and config/dependency-patches.json to effective T02 ownership. acceptance_receipts.validation_scopes uses effective scopes transitively; COMMON_INPUTS already includes scripts/config/package/lock/overrides. Thus source patch/provenance/checker changes invalidate appropriate acceptance inputs. No freshness narrowing found.
- Python TEST-02 discovery includes the new seven provenance tests and both JS wrappers. Wrappers reject nonzero exits, zero counts, failures, skipped and cancelled cases. Four tiny browser cases observe independent server ticks rather than trusting a main-thread logger. The current test assertions pass on this machine; independent image-loading failure is a separate case, not a failure of those four cases.

No production changes made. This is an exact-candidate review, not acceptance or merged verification. Report can be routed to the sole writer for the scoped disposition/revision.


## Follow-up: fresh Linux proof and registered-entry override

Parent reported two fresh Mac clones of exact68d31df passing frozen install, hashes,11 constructor cases and clean Git status; that is parent-owned evidence at `artifacts/tasks/T02/cancellation-patch/fresh-installs.log`, not an independent rerun claimed here.

I independently created the authorized fresh Linux clone at `/home/wertyp/.local/share/homebase-factory/worktrees/inkflip/review-ebz`, starting from the existing project Git objects and fetching a scoped Git bundle containing exact68d31df. It had no node_modules before installation. Activated only the existing canonical project `.tools/env.sh`; no global setup/service changes.

Executed Linux x86_64, Node **v22.23.2**, Bun **1.4.0**:
- `bun install --frozen-lockfile`: exit0,91 packages installed (platform count differs from Mac).
- `check_dependencies.check_dependency_patch()`: **8/8 installed patch/provenance checks pass**, including both installed source/types hashes.
- `node --test tests/build/tesseract-worker.test.mjs`: **11/11 pass**, no failures/skips/cancellations.
- Exact HEAD=68d31df54734e2d086f0915346b04a20e2e8d1e2, `git diff --exit-code` passes, `git status --porcelain` empty.

Raw evidence: `/private/tmp/inkflip-ebz-probes/linux-proof.log`; exact script `/private/tmp/inkflip-ebz-probes/linux-proof.sh`. No browser, OCR/core/model execution on Linux. Remote proof command completed exit0; no jobs left running/queued. Review clone retained for traceability. Candidate source on Mac also remains clean.

### P2 — Registered TEST-02 can execute a different package via inherited negative-control override

`tests/build/test_tesseract_worker.py:17–20` calls subprocess.run without an explicit environment. Both JS tests resolve `process.env.INKFLIP_TEST_TESSERACT_PACKAGE` first (`tesseract-worker.test.mjs:11`, `tesseract-browser.test.mjs:12`). Repository search confirms this override exists only in tests, not production; however, the maintained Python wrapper inherits it from its caller.

Fresh repro under pinned Node:
`INKFLIP_TEST_TESSERACT_PACKAGE=/private/tmp/inkflip-ebz-probes/missing-package python3 -m unittest discover -s tests/build -p test_tesseract_worker.py -k installed -v`
Result **1 failed** with ENOENT resolving that TEMP package, despite the actual installed constructor having just passed its hashes and11 tests. This directly proves package redirection reaches the registered wrapper. A valid alternative package could supply the lifecycle evidence while the separate frozen verifier checks this checkout's bytes; those would no longer prove the same installed entry. I did not alter installed source or spoof a green suite to demonstrate this.

Minimum revision: copy os.environ in the Python wrapper, remove `INKFLIP_TEST_TESSERACT_PACKAGE`, pass that env to BOTH node subprocesses. Keep the JS override for explicit standalone historical negative controls. Add wrapper-level coverage proving an inherited sentinel override is removed and both maintained cases still run the real installed package. Do not disable negative controls globally or change production imports. This is a small test-evidence binding fix, independent of the supported-input cancellation scope decision above.
