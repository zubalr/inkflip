# T17 Independent Review — Devin reviewer (review/devin/t17)

- **Verdict: APPROVED**
- **Reviewed candidate:** implementation `d39e607` + evidence `993fa5c` (branch `work/antigravity/t17`, worker `antigravity-t17`, base `b2b5db3`)
- **Reviewer:** Devin independent review subagent, isolated checkout `/Users/zubair/Code/Projects/pdf project/worktrees/review-devin-t17`
- **Reviewed at:** 2026-09-12 (fresh `bun install` in this worktree; no node_modules were present)

## Commands actually executed by this reviewer (real counts)

| Command | Result |
|---|---|
| `bun run test:browser -- tests/browser/amount.spec.ts` | **7/7 passed** (4.9s), exit 0 |
| `bun run test:fixtures` | **50/50 passed** (0.742s), exit 0 |
| Contract total | **57/57, 0 failed, 0 skipped** — matches worker claim |
| `python3 scripts/prepare_examples.py --check` | `OK: apps/web/public/examples/amount/ matches generation`, exit 0 |
| `python3 scripts/task_acceptance.py task T17 --report …` | re-executed in this checkout, exit 0, 57/57 |
| `python3 scripts/acceptance_receipts.py verify-run T17` | `{"verified":"T17","tests":{"collected":57,"passed":57}}` |
| `bun run build:web` | clean, 535ms; `dist/examples/amount/` contains all 9 files |
| `bun run oxlint` | 0 errors (3133 pre-existing warnings, mostly minified-file notices) |
| `bun run verify` | **116/116** (49 bootstrap + 2 native-boundary + 65 coordination/homebase/native-pass), exit 0 |

## Scope check

`git diff b2b5db3..993fa5c --name-only` — all changes inside `apps/web/public/examples/amount/`, `scripts/prepare_examples.py`, `tests/browser/amount.spec.ts`, `artifacts/tasks/T17/`. No out-of-scope edits. No `.skip`/`.only`/weakened assertions in the spec; no `fetch`/XHR/localStorage/sendBeacon in `amount.js` (no undeclared network or persistence).

## Receipt check

`artifacts/tasks/T17/receipt.json` `acceptance_criteria_evidence` is keyed by the six exact criterion strings, including the trailing period on `"clean counterpart renders equal under same renderer."`. All `evidence` paths resolve inside `artifacts/tasks/T17/` (commands.log, run.json, criteria-evidence.md exist on disk). run.json `evaluated_commit` = `d39e607` = implementation commit.

## Per-criterion adversarial verification

1. **Renamed identical bytes → same reading — VERIFIED.** The client hashes bytes (`crypto.subtle.digest` SHA-256), never the filename; hash match only selects the notice text — extraction is always executed live via pinned pdfjs `getTextContent`. My probe uploaded the fixture as `zzz-renamed.pdf`: live extraction returned `$1,000`, `provenance: "live"`, `replayedPrepared: false`. Stronger than required: identical bytes are re-executed, not replayed.
2. **Modified bytes cannot replay — VERIFIED.** There is no replay code path for uploads at all: mismatched hash → `#replay-notice.tamper-warning` ("Prepared report replay rejected") + live extraction (`replayedPrepared: false`). Probe: `covered-amount.pdf` (valid PDF absent from the allowlist) → warning + live extraction of its own true text (`$1,000 $100`), not a canned value.
3. **Provenance labeled — VERIFIED.** Initial state: badge `prepared`, `data-provenance="prepared"`, class `badge-prepared`. After upload: `live`/`badge-live`/`data-provenance="live"`. Manifest `provenance: "prepared"`; report `result_origin: "prepared_actual_run"`.
4. **Real source downloadable — VERIFIED.** Anchors point at real static files; probe `GET /examples/amount/mapping-amount.pdf` → HTTP 200, `application/pdf`, 1,437 B, sha256 `04898afc…` = fixture bytes. All four shipped PDFs are byte-identical to `fixtures/public/` and match manifest digests (verified with `shasum -a 256`).
5. **Actual timing — VERIFIED.** `performance.now()` deltas only; no `setInterval`/`setTimeout`/`requestAnimationFrame`/`@keyframes` anywhere (only a hover opacity transition). Live probes measured real elapsed values (130 ms, 138 ms — distinct per run). The static "142 ms" is the generator-baked prepared-run record, consistent with `report.json execution.duration_ms=142` and plausible against observed live timings.
6. **Clean counterpart equal rendering — VERIFIED.** Source and control render through the identical `renderPdfToCanvas` path (same pdfjs 6.3.289, worker, cMaps, scale 2.0); `getImageData` pixel loop asserts `diffCount === 0` over all pixels; text diverges (`$1,000` vs `$100`) under the same reader.
7. Negative/error path (review brief requirement): garbage non-PDF bytes → `data-state="error"`, "Invalid PDF structure.", badge stays `live`, `replayedPrepared: false`. Honest failure labeling.

## Prepare-manifest integrity (bypass attempts)

- Byte-flip in shipped `mapping-amount.pdf` → `--check` exit 1 (`content mismatch`).
- `duration_ms` edit in `manifest.json` → `--check` exit 1.
- Byte-flip in `fixtures/public/mapping-amount.pdf` → `--check` exit 1 (`hash mismatch` — EXPECTED_HASHES SHA-256 gate runs before output comparison).
- Binding is SHA-256 of fixture bytes → embedded into manifest/report → shipped PDFs are the fixture bytes themselves, byte-compared on `--check`. No non-cryptographic bypass found. Tree restored clean after each probe.

## Findings (all non-blocking)

1. **[Low] Tamper gate is a hardcoded constant pair, not a manifest read.** `amount.js` compares against `MAPPING_AMOUNT_HASH`/`MAPPING_CONTROL_HASH` literals while the notice says "does not match prepared manifest"; the client never fetches `manifest.json`. Values are equal today (both baked by `prepare_examples.py`), but a future `EXPECTED_HASHES` edit without touching the `build_js()` literal would drift silently while `--check` still passes. Suggest deriving the JS constants from `EXPECTED_HASHES` or fetching the manifest at runtime — follow-up hardening, not a contract violation.
2. **[Info] "142 ms" is a recorded-run claim**, not independently re-verifiable — acceptable because it is labeled `prepared` provenance and matches the sealed report's `execution.duration_ms`.
3. **[Low/UX] Single header badge flips to `live` while prepared panes remain visible**; live results live in their own labeled section, so provenance remains distinguishable, but a page-level badge could be misread as covering the static panes.
4. **[Cosmetic] Spec's `elapsed >= 0` assertion** would admit 0; the code genuinely measures. Playwright also reports test callsites ~14 lines above physical file lines (61 vs 75 etc.) — identical between the worker's recorded log and this reviewer's fresh run, so the recorded evidence corresponds to the committed spec; it is a loader callsite quirk, not stale evidence.

Inspection-only areas: Beads live state, dependency-acceptance freshness for T05/T09/T10/T12/T14/T16, and coordinator merge acceptance are outside this checkout review and remain the coordinator's gate.

---

## Worker's original implementation summary (retained below)

- **Task:** T17 (pdf-t17)
- **Status:** Implemented, pending independent review
- **Candidate Implementation Commit:** `d39e607feda6f8d6c3443c678ac013435c5533b1`
- **Branch:** `work/antigravity/t17`
- **Base:** `b2b5db3ad497c27ca7988dffcfdec618e697b89a`
- **Worker:** `antigravity-t17`

## Implemented Deliverables

1. `apps/web/public/examples/amount/`:
   - `index.html`: Interactive demo card matching design tokens and accessibility standards.
   - `amount.css`: Pure token consumption (zero raw hex or rgba literals).
   - `amount.js`: Pinned PDF.js 6.3.289 browser reader integration, pixel comparison engine, and live file intake.
   - `manifest.json`: Example metadata cataloging F01 and F02 fixture files, hashes, and durations.
   - `report.json`: Canonical sealed report artifact validated by `@inkflip/contracts`.
   - 4 fixture files: `mapping-amount.pdf`, `mapping-control.pdf`, `covered-amount.pdf`, `covered-control.pdf`.
2. `scripts/prepare_examples.py`:
   - Standalone generation script with `--check` support.
   - Validates byte identity of generated files against disk.
3. `tests/browser/amount.spec.ts`:
   - Comprehensive Playwright test suite covering all 6 acceptance criteria and WCAG AA accessibility.

## Verification Summary

- `bun run test:browser -- tests/browser/amount.spec.ts && bun run test:fixtures`: 57 passed (7 browser + 50 fixtures), exit 0.
- `python3 scripts/task_acceptance.py task T17 --report artifacts/tasks/T17/run.json`: exit 0.
- `python3 scripts/acceptance_receipts.py verify-run T17`: verified, 57 passed, exit 0.
- `python3 scripts/prepare_examples.py --check`: OK, exit 0.
- `bun run build:web`: built in 560ms, exit 0.
- `bun run oxlint`: 0 errors.
- `bun run oxfmt --check tests/browser/amount.spec.ts`: 0 format issues.
- `bun run verify`: 116/116 tests passed, exit 0.
