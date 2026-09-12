# Independent focused final review: pdf-ebz

Reviewer: Codex/Astra subagent Pauli (`01a093db-42d8-79d3-befb-0b7680c3e405`).

**Candidate: 185d51db4d5fb132bc1ef65edc82a31ce68a16ec. Verdict: APPROVE for the explicitly adjudicated pdf-ebz scope; no blocking finding remains.** This is independent source-review approval, not repository/task acceptance, merged verification or T10 acceptance.

Reviewed revision 68d31df -> cd4923d evidence ->185d51d on the authorized clean isolated checkout `/Users/zubair/Code/Projects/pdf project/worktrees/review-codex-ebz`, branch `review/codex/pdf-ebz`. Applied only the authorized fast-forward and frozen dependency upgrade. No production/test edits, commits, pushes, Beads or acceptance writes. Final HEAD exact185d51d; Git status clean. Current revision diff, scoped documentation/types, wrapper/tests, target validation, provenance and evidence inspected under the code-review skill and canonical repository instructions previously loaded.

## Findings disposition

1. **Registered package override — fixed.** `tests/build/test_tesseract_worker.py` copies os.environ, removes INKFLIP_TEST_TESSERACT_PACKAGE and supplies that environment to both Node subprocesses. The new sentinel test actually invokes both suites under `/nonexistent/inkflip-control-package`; it passed. This closes the installed-entry evidence-binding issue while preserving explicit standalone negative controls. It is not a mocked subprocess or a simulated successful test result.

2. **Upstream asynchronous input loading — explicitly scoped, not falsely claimed fixed.** Parent adjudicated pdf-ebz as cancellation of constructor readiness, raw transport and already-posted jobs. docs/proposals/T02.md, dependency-patches purpose, README and WorkerOptions.signal type comment now all say that upstream URL/Blob/FileReader/canvas input loaders remain uncancelled. The failing round-one URL/input-loader probes remain valid evidence for that excluded upstream API; they are not relabeled passing. T10 has an approved separate prepared-Uint8Array port, with Blob materialization inside its own absolute operation deadline and after-await guards. This review does not assert that unmerged T10 implementation is complete.

3. **Prepared byte boundary — verified.** Added fifth tiny real-browser case invokes recognize(Uint8Array), aborts before the image-load microtask resumes, and requires the original abort reason rather than success. It passed. Source inspection confirms Uint8Array uses no external URL/FileReader loading in the pinned browser loader; startJob's terminal guard prevents dispatch after abort. Existing constructor tests cover posted jobs, init stage cancellation/rejection, raw worker errors, late messages, idempotent teardown and the successful protocol path.

4. **Patch targets / .bun-tag — final candidate clean.** Git's actual patch inventory contains only src/createWorker.js and src/index.d.ts. No .bun-tag addition is in the committed patch. Target validation checks expected headers and duplicate count; the new extra-target test updates the patch digest and still gets patch.targets failure. This test passed. Provenance matches the newly generated patch and updated type comment.

## Independent execution on exact185d51d

Node PATH prefix: `/Users/zubair/.local/share/mise/installs/node/22.23.2/bin`; Bun1.4.0.

- Authorized `git merge --ff-only 185d51db4d5fb132bc1ef65edc82a31ce68a16ec`: successful, preserves review branch history.
- `bun install --frozen-lockfile` in the existing review clone: **exit0**, one package reinstalled in66ms. This exercises the cached patch-upgrade path from the existing68d31df install. No lock or source drift.
- `python3 scripts/check_dependencies.py --frozen`: **25 passed,0 failed**. Covers current patch digest, exactly recorded source/types, installed version/declarations, installed hashes and existing staged assets.
- `python3 -m unittest discover -s tests/build -v`: **48 passed,0 failed** in6.148s. Includes **11 constructor and5 real-browser cases**, plus actual sentinel reruns of both suites (32 nested JS executions,16 distinct JS cases; do not add these to the48 Python count). Provenance tests now comprise one positive control and seven tamper cases.
- Explicit independent installed-byte comparison: constructor SHA256 **11d687cf60deee6cdf428d16ee1f5e83a3f906aa6825b0c2da3781840cc96c9c**, identical to68d31df; types SHA256 **eebc61f3d9d7ac6402585165c237cc5d01b18e9a32ff2ed8f290f7652e056c6e**, matches185d51d, differing only by the scoped comment in the patch diff.
- `git apply --numstat patches/tesseract.js@7.0.0.patch`: constructor28 additions/18 deletions; types2 additions/0 deletions; no third file.
- Final Git HEAD exact185d51d, status empty.

Raw maintained-suite output: `/private/tmp/inkflip-ebz-probes/revision2-build.log`. All real-browser tests used tiny protocol workers and local tick traffic; no Tesseract core/WASM/model or actual OCR. Browser processes/servers completed and closed. Nothing remains running or queued. The 115 verify result is parent-run evidence inspected, not independently rerun in this focused revision.

## Target-parser probing and its practical limit

I investigated an apparent regex gap before deciding the verdict. TEMP checker probe appended a Git-valid third target with a space-containing filename and updated its digest. The checker ignored that header, while Git reported the extra file. However, I then tested the actual Bun1.4.0 frozen install in a separate TEMP manifest-only clone: the quoted variant failed `bad_diff_line`; a full-metadata unquoted variant failed `hunk_header_integrity_check_failed`. Both installations failed closed. No accepted installed-patch bypass was reproduced, and the actual candidate's two-file inventory is independently confirmed. This observation is not a blocking candidate finding. It would be inaccurate to claim the regex is a general Git-patch parser, or to report those failed Bun probes as successful extra-file installations.

## Evidence boundaries

The independent fresh Linux x86_64 proof remains correctly bound to **68d31df**, with Bun1.4.0/Node22.23.2,8 installed-patch checks,11 constructor cases and clean Git status. It was not rerun or relabeled185d51d. Constructor runtime bytes are independently identical, so the existing physical-worker behavior evidence remains relevant; current type-comment/test/checker changes are validated on Mac above. Parent's two fresh Mac68d31df clone proofs likewise retain their exact candidate provenance.

The dependency repair preserves the public Promise API, existing worker protocol, staged worker/core/model bytes and license notices. Source-entry bundling remains mandatory; unpatched prebuilt client dist is unsupported. T02 freshness continues covering patches/, config/dependency-patches.json and shared manifest/lock/scripts inputs. No gate or invariant was loosened. Parent still owns source handoff, merged verification and final acceptance; T10 still owns its separate input preparation/deadline implementation.
