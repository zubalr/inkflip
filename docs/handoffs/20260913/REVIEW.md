# Review of delivered AGY and Devin work — 2026-09-13

This is an immutable review/handoff snapshot, not a replacement task tracker.
User requested review, private integration of verified work, and two independent
next-pass prompts. Beads integration issue: pdf-d99. Product acceptance remains
with original Devin; delivery and passing unit tests do not establish acceptance.

## Inspected revisions and integration decision

- Canonical base: 25bb2b9d74acdba6bdd08cfdf52f2d7091ee6765. G1/T18 is recorded
  accepted in Beads, following Devin's fresh evidence work.
- AGY: work/antigravity/independent-ready-pass at 42ef42494060115ff846d867686c958f0584bea3,
  based on 879ff3b11189971419ae6858547d7225c183bedf. Preserve this branch.
- Merge AGY export 39edac3 and the attribution/OCR-path/scope parts of b61793b.
  Exclude b61793b's scanner and scanner-test changes: they regress loader detection.
- Merge Devin work/devin/t19 at 1df73e34b32ab18d02a89e7c29aa50bc33444fc8,
  plus the integration fix clearing stale mobile preview pixels on page change.
- Withhold AGY T30/T32/T33/T34/T35/T40/T44/T45 from main pending the findings below.
  Their source and evidence remain available on the original branch. Do not merge
  their self-authored acceptance/review claims as independently verified results.
- Preserve Devin's partial untracked T21 tests/gallery and T25 offline/sw.js work
  in original/worktrees/pdf-t21 and original/worktrees/pdf-t25. T20's worktree is
  at the base without source changes. These are unfinished, not lost or merged.
- The original Devin desktop displayed an overall message-rate-limit error while
  working on T19. A source commit and subsequent acceptance-run commit exist.
  This establishes saved progress, not a promise of automatic provider resumption.

## Independent reviewers

- Euclid, Codex Astra reviewer, session 01a09a58-3d2f-7493-b852-7b33e4d0c487:
  T30/T32/T33/T34/T35. Ran 59 existing native/regression tests and disposable
  reproductions below. Existing tests passed despite the failures. No source edits.
- Hypatia, Codex Astra reviewer, session 01a09a5b-0393-78b3-9a8c-e5b1023680b6:
  export/dependency/OCR slice; 23 dependency tests and 19 export tests passed.
  Reproduced scanner bypasses. Subsequently reviewed Devin T19 and the integration
  raster fix; no additional substantive findings. Parent executed the new browser test.
- Parent Codex reviewed experiment/containment source, reproduced the T19 stale
  preview in Playwright, repaired it, and ran the integration checks.

## Native batch: changes required (line numbers refer to AGY 42ef424)

1. **P1, CLI source preservation:** native/inkflip/cli/main.py:726 permits replay
   output to alias --source. Disposable replay with --out source.pdf --replace-output
   exited 0 and replaced the PDF with JSON. Reject resolved aliases, including links,
   regardless of overwrite flags; preserve source bytes on every command.
2. **P1, trusted profiles:** native/inkflip/profiles/registry.py:80 accepts external
   absolute descriptors and :130 accepts arbitrary existing wrappers. A descriptor
   executed a harmless custom wrapper without a digest. This requires explicit profile
   selection, not automatic report-import execution. Restrict installed names to a
   trusted registry and bundled adapters; verify environment/runtime identity.
3. **P1, silent reader fallback:** cli/main.py:311 catches profile errors and uses
   defaults. corpus/runner.py:69 resolves relative names from child scratch. Missing
   profiles and the named before profile both produced successful PDFium runs.
   Valid executable paths containing spaces are also rejected. Resolve profiles in
   the parent, pass fixed identity, fail closed, and test this repository's spaced path.
4. **P1, invalid resume:** corpus/runner.py:71 omits source SHA, manifest identity,
   profile contents and algorithm identity from job identity. Changing source bytes
   plus manifest SHA then resuming skipped the file and reused the old report.
   Bind these identities, refuse changed resumes, and validate reusable reports.
5. **P1, mutable/unverified baselines:** baselines/engine.py:41 allows overwrite;
   :197 guesses nearby report directories without checking baseline report_ids.
   Creation uses constant identity hashes when missing. Overwrite changed baseline
   bytes; matching tampering of backing/candidate reports produced unchanged/0.
   Require real identities, exclusive creation, and content-verified approved reports.
6. **P1, lost files disappear:** baselines/engine.py:269 intersects filenames and
   ignores failed index entries. Baseline a+b versus candidate a returned unchanged/0,
   coverage_lost=false. Compare intended key unions and retain missing/error outcomes.
7. **P1, malformed comparison inputs:** baselines/engine.py:148 checks only kind,
   skips unreadable files, and accepts unvalidated baseline reports. Two objects
   containing only kind=report compared unchanged/0. Use strict full validation;
   malformed inputs must produce exit 2, not silently disappear.
8. **P1, incomplete rule semantics:** baselines/engine.py:301 and
   packages/compare/regression/evaluator.ts:117 ignore document/reader/region/capability
   scope and geometry rules, count occurrences as coverage, and infer regression
   without declared rules. An unrelated-document expected_text rule caused exit 5;
   changing a terminal check status without text changes returned unchanged/0.
   Implement complete scopes, check-plan coverage, compatible geometry and exit policy.
9. **P1, PDF.js stub:** packages/readers-pdfjs/node/bridge.mjs:139 never executes
   PDF.js. The four bytes %PDF returned ok:true, version 6.3.289 and empty occurrences.
   scripts/install_reader_profile.py:205 trusts the hardcoded version. Execute a real
   pinned reader in an isolated environment and verify its installed version/output.
10. **P1, incompatible/incomplete replay:** cli/main.py:751 ignores recorded reader
    versions/settings and does not reconstruct OCR pages/region. A report declaring
    pypdf 0.0.1 replayed successfully in the default environment. Require compatible
    installed identities and reconstruct the recorded plan; refuse substitution.
11. **P1, failures become empty success:** profiles/pypdf_worker.py:106 catches text
    extraction exceptions and reports completed empty checks. An injected extraction
    exception reproduced this. Keep errored terminal checks and successful other pages.
12. **P1, multipage failure:** cli/main.py:497 reuses a PDFium transform ID per page.
    A two-page PDF with --pages all exited 4 with Duplicate identifiers. Use distinct,
    correct page transforms and consistently bound occurrences.
13. **P2, ignored region:** cli/main.py:290 parses --region but does not execute or
    record it. A 1x1 region returned all 98 fixture occurrences with regions:[].
    Execute/record the requested region or explicitly refuse unsupported execution.
14. **P2, incomplete import validation:** cli/main.py:691 uses semantic-only validation
    for HTML/report and replay. A sealed report with an extra forbidden field was
    rejected by validate but accepted by report --format html. Use core.validate.
15. **P2, model preparation stub:** cli/main.py:849 merely parses JSON. {} reports
    model cache ready/0. Perform allowlisted preparation and digest verification;
    absent or invalid models must remain unavailable.
16. **P2, nonportable comparison output:** baselines/engine.py:386 emits an unknown
    comparison_summary with no canonical comparison links/HTML. Produce validated
    portable comparisons using the established bridge and human-readable artifacts.

Repair the native core before revalidating T35. Execute the documented run.sh
verbatim with named profiles; its tests currently substitute absolute paths and
miss the broken path. Verify actual pypdf 5.9.0 versus 6.18.0 in reports, an intentional
rule failure, browser reopening, and unchanged baseline bytes.

## T40: actual containment remains unverified

tests/containment/run.py audits strings and executes only --dry-run, yet emits a
passed containment receipt. Its digest is the Dockerfile text hash, not an image
digest. build/native/Dockerfile defaults to mutable python:3.13-slim and does not
demonstrate the frozen native runtime/model installation. The traversal test accepts
both exit 0 and 2, so it cannot establish rejection. Keep these as failed review
findings until a real digest-pinned container runs owned synthetic inputs and proves
no network, nonroot/read-only behavior, limits, output containment, source preservation
and descendant cleanup. Missing container tooling is blocked, not passed.

## T44/P13 and T45/P14: evidence does not support the disposition

P13's run_experiment ignores the manifest, checks two model filenames for existence,
does not execute RapidOCR/Tesseract, and writes rejected_experiment anyway. Existing
files are labeled verified without digest verification. No memory or accuracy run
supports the handoff's memory-exhaustion claim.

P14 ignores the manifest, computes a constant 1.5-degree matrix, hardcodes drift and
registration-loss booleans to true, and never rasterizes/resamples/measures controls.
Both scripts manufacture a 1/1 runner summary. Existing tests only inspect those
generated records. Replace unsupported claims with actual per-fixture measurements;
unavailable dependencies or labels mean blocked/unexecuted, not a measured rejection.
Do not silently substitute a different manifest when the requested one is missing.

## Scanner regression withheld from b61793b

scripts/check_dependencies.py:362 regex-based comment stripping hides executable
loaders in both `const quote = /"/; fetch("https://example.com/model.bin");` and
CSS `@import url(https://cdn.jsdelivr.net/npm/example/style.css);`.
Both pass the candidate checker but fail the baseline. Repair using reliable
language-aware handling, preserving URLs and regex/template/JSX contents, with
regression cases. Keep harmless notices supported without erasing executable code.

## Integration verification

- New mobile page-change test failed before repair: canvas retained width 557 instead
  of 0 after switching pages. After clearing raster/error before early returns:
  `bun run test:browser -- tests/browser/large-mobile.spec.ts tests/browser/open.spec.ts tests/browser/export.spec.ts tests/browser/viewer.spec.ts`: 37 passed.
- `bun run test:native`: 196 passed.
- `node --test tests/reports/export.test.mjs`: 19 passed.
- `python3 -m unittest discover -s tests/build -q`: 49 passed.
- `bun run verify`: bootstrap/native-bootstrap/coordination checks and registry passed.
- `bun run build`: passed; Vite reports the existing large bundle warning.

These checks cover only the included integration slice. They do not validate the
withheld native implementation or establish fresh G1–G5 release acceptance. Devin
must refresh affected acceptance records before closing dependent release gates.
