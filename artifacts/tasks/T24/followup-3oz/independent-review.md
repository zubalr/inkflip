# Independent conventional correctness review

Verdict: **Approve within the requested review scope; no actionable findings identified.** This is a code-review verdict, not task acceptance or a comprehensive security assurance.

- Reviewer: Helmholtz, independent Codex session `01a09467-215d-7a30-827e-e60905c3d73d`, separate from patch author Astra.
- Date: 2026-09-12.
- Checkout: `/Users/zubair/Code/Projects/pdf project/worktrees/review-codex-3oz`.
- Exact candidate: `9f60ea01e0c61e00c2e185bed729a307d4bd096f`.
- Exact comparison base: `ccfc11f91278d9bca0c14617a0c420eccc138d60`.
- Initial and final `git status --porcelain=v1` returned no entries; `git rev-parse HEAD` returned the exact candidate both times.

## Scope and assessment

Read AGENTS.md, docs/NATIVE_PASSES.md, docs/HOMEBASE.md, planning/PROJECT_BRIEF.md, planning/architecture/GLOSSARY_AND_INVARIANTS.md, the effective T24 contract (`python3 scripts/coordination.py task T24`), planning/architecture/REPORT_EXPORT_IMPORT.md, planning/security/THREAT_MODEL.md, planning/DECISIONS.md, planning/config/settings.json, and packages/reports/validation/README.md. Reviewed the base-to-candidate production/test diff and surrounding validation/parser code. No nested AGENTS.md or CLAUDE.md was found by repository file discovery.

The package root and validation subpath now target the maintained entry rather than a nonexistent src entry. The configuration includes validation modules, retains inherited strictness, and follows the contracts package's declaration-only configuration. The contracts reference matches the actual imports; inspection found no current consumer depending on the former dangling entry. The existing package self-reference regression passed.

The serialized HTML changes fit the documented application-owned-template boundary: parsed quoted attributes, duplicate rejection, exact restricted CSP lists, early policy placement, stylesheet hashes, conservative CSS inspection, and strict PNG data URL decoding. Imported strings still depend on exporter escaping; the guard is expressly not a general HTML sanitizer. The test double requires sanitized image bytes. Existing valid-report rendering tests and the browser-bundled guard test passed. Browser verification exercised the test double, not a completed T16 product exporter.

PNG singleton and IDAT ordering checks run before image-data collection/inflation. Their treatment of optional palette/transparency and consecutive IDAT is consistent with the checked ordering requirements in the [PNG specification, section 5.6](https://www.w3.org/TR/png-3/#5ChunkOrdering). Existing first-IHDR/last-IEND and checksum checks remain. Valid color/depth, filtering, Adam7 and re-encoding regressions passed.

The empty distance-table change permits literal-only dynamic blocks while symbol decoding still fails when a length requires an unavailable distance. This matches [RFC 1951 section 3.2.7](https://www.rfc-editor.org/rfc/rfc1951#section-3.2.7). The existing new test independently decodes the valid stream with Node zlib before checking the owned implementation.

String accounting now traverses keys and array strings, counts Unicode code points, and confines the larger payload allowance to objects in the root assets array. Full schema/asset checks follow. String inputs reach the strict parser without lossy TextEncoder substitution. Import hash verification cannot be disabled; validate is called with its default verification enabled, independently of the legacy argument. Existing regression assertions cover the intended changes and their ContractError codes.

Checked [CSP policy parsing](https://www.w3.org/TR/CSP/#parse-serialized-policy) and [CSS escape processing](https://www.w3.org/TR/css-syntax-3/#consume-an-escaped-code-point) as primary references. Conservative rejection is appropriate to this owned-template contract; this review does not infer general parser equivalence from those checks.

## Actual commands and results

Commands ran in the review checkout unless stated otherwise. Runtime setup was `export PATH=/Users/zubair/.local/share/mise/installs/node/22.23.2/bin:$PATH`; `node --version` returned v22.23.2 and `bun --version` returned 1.4.0.

| Command | Actual result |
| --- | --- |
| `git status --porcelain=v1`; `git rev-parse HEAD` | Clean and exact candidate, before and after review. |
| `git diff --stat BASE CANDIDATE`; `git diff BASE CANDIDATE -- packages/reports tests/security/import` | Inspected explicit two-commit scope. BASE/CANDIDATE are the full hashes above. |
| `python3 scripts/coordination.py task T24` | Exit 0; effective contract read only. |
| `node --test tests/security/import/*.test.mjs` | Exit 1: 104 collected, 103 passed, one environment failure: Chromium test could not bind 127.0.0.1 (`listen EPERM`) under sandbox. No skips. Log: `/private/tmp/inkflip-3oz-review-tests.log`. |
| `node --test tests/security/import/html-browser.test.mjs` | Authorized sandbox escalation for the loopback test; exit 0, 1/1 passed, no skips. Log: `/private/tmp/inkflip-3oz-review-browser.log`. All 104 tests therefore passed across the initial run and targeted rerun, not a single all-green invocation. |
| `node node_modules/typescript/bin/tsc -p packages/reports/tsconfig.json --noEmit --tsBuildInfoFile /private/tmp/inkflip-3oz-review.tsbuildinfo` | Exit 0, no diagnostics. Strict project check with no repository output; empty log `/private/tmp/inkflip-3oz-review-typecheck.log`. |
| `git diff --quiet CANDIDATE 3190f6cb65b3f29ff652e5e145f41b5a8e99b6f0 -- packages/reports tests/security/import` | Exit 0; scoped source/tests identical to evidence commit. |
| `git show 3190f6cb65b3f29ff652e5e145f41b5a8e99b6f0:artifacts/tasks/T24/followup-3oz/registered-run.json` | Read source-bound receipt: exact candidate, 104 passed, fixed-seed 1000 cases with no unexpected results/crashes/egress. This is author evidence, not an independent fuzz rerun. |
| `git diff --check BASE HEAD` | Reported trailing whitespace in historical captured attempt/red logs only. No production/test whitespace issue reported; historical logs preserved. |

Source inspection used cat, sed, rg and git diff/show; a few guessed nonexistent paths were subsequently resolved through rg and read at their actual locations. Those lookup misses were not test failures.

## Coverage limits

The tests cover each intended repair, but do not enumerate every new PNG order branch: dedicated new cases do not individually cover tRNS-before-PLTE, tRNS-after-IDAT, and grayscale PLTE rejection. Those branches were inspected against the format rules. The package self-reference test covers the root entry; the validation subpath has the identical target but no separate runtime assertion. These are nonblocking coverage limitations, not demonstrated defects.

No new tests, format cases, payloads, attack chains, external scans, OCR, models or corpus runs were developed or executed. No frozen install, full declaration-emitting build, 1000-case fuzz rerun, or 115-test verify rerun was performed independently. Existing source-bound evidence does not replace those independent checks. No browser/device matrix, arbitrary-HTML sanitizer guarantee, exhaustive PNG/deflate conformance, or resource-exhaustion proof is established here.

No production/test files, commits, pushes, Beads records, acceptance state, or other workers were changed. Only the requested report and review outputs under temporary storage were written. All review test/typecheck commands have finished; the Chromium test completed its browser/server cleanup.
