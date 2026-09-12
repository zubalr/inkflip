# Independent Peer Review — T14 (changes-required)

**Reviewer:** devin-review-t14 (SWE-2 subagent, independent — did not write this code; antigravity wrote it, reviewer never ran it before this review)
**Candidate reviewed:** `e9b14b9` on `review/devin/t14` (implementation `2cf02941f12b4e208e7de7a5dc55cadaf3854d36`, base `546accd`)
**Date:** 2026-09-12 · **Verdict: changes-required**

## Reproduced results (independent, this checkout)

- `bun install --frozen-lockfile` → 86 packages, clean.
- `bun run test:browser -- tests/browser/findings.spec.ts` → **6 collected / 6 passed / 0 failed / 0 skipped (3.4s, exit 0)**, matching run.json and commands.log. Tests mount the REAL `FindingsList`/`CoveragePanel`/`FindingCard` components via a Vite server + React root (`mount.tsx`), not mock markup.
- `bun run build:web` → clean, 18 modules, exit 0.
- `bun x oxlint` on the three impl paths → 0 warnings / 0 errors.
- `python3 scripts/acceptance_receipts.py verify-run T14` → `{"verified": "T14", tests 6/6}`.
- Live module probes (`bun -e`) of `categorizeCheckStatus`, `isMaterialTokenDifference`, `explainCoverage`, `groupFindings` — results cited per finding below.
- `run.json` `evaluated_commit` = `2cf02941f12b4e208e7de7a5dc55cadaf3854d36` ✓ binds the impl commit.

## Per-criterion verdicts

1. **6/6 against real mounted features — REPRODUCED.** `preview.html` + `mount.tsx` render the shipped components with fixture data; `?scenario=` selects fixture sets at the harness level only — no behavioral knob inside the components themselves. Not a test-only production knob.
2. **Normal invisible scan — PASS.** `coverage.normal_scan` renders with `role="note"`, `.scanNotice` (teal info styling); grep confirms no warning/danger/error/alert copy or class reachable for invisibility. Same scenario still surfaces the named reading-difference card (test 4 runs on `scenario=normal-scan`). I11 satisfied.
3. **timed-out/model-missing/unsupported distinct — PASS with caveat.** `TerminalStatusCategory` enum (7 kinds) maps all six contract `CheckResult.status` values; model-missing is derived from `failed`+reason keywords since the contract has no such status — reasonable. Distinct stat cards (`#stat-timeout`/`#stat-model-missing`/`#stat-unsupported`), badge colors and copy verified in test 2 and by probe. Caveat: P2-1 below — `failed`/`cancelled`/`skipped` fall through to Unsupported styling.
4. **Zero findings cannot display clean/safe — PASS.** `FindingsList` renders `#findings-noalert` with the scoped `coverage.noalert` disclaimer; grep across `apps/web/src/features/` + `packages/explanations/` finds zero `clean`/`safe`/`all-clear`/`no issues` copy. Checked scope (pages summary, completed/incomplete counts, status rows) renders adjacent via `CoveragePanel`; agreement copy is scoped to "the checked region" and always carries the no-alert disclaimer. Probe: zero findings + 1 completed + 2 timeouts still shows "1 checks completed · 2 incomplete or unsupported" + status rows next to the agreement notice. I06 satisfied.
5. **Deterministic templates + recorded evidence — PASS with one P1.** `COPY` is verbatim from `planning/product/copy.json`; readings cite real evidence fields (reader name+version, occurrence ordinal+id, `raw_text`, geometry basis via disclosure); disclaimer `finding.limit` always present; ambiguous/unmatched correctly abstain from location/missing-text claims; hypothesis titled "not established by this check". P1-1 below: the material-token re-derivation fabricates a claim beyond recorded `priority`.

## Also verified

- **Grouping preserves counts:** probe with 6 findings → 2 groups × 3 = 6 items; header badge shows total `findings.length`; no dedupe of duplicate occurrences (`readings` maps all `occurrence_ids`, keys include occurrenceId+idx). I18 satisfied.
- **Kind coverage:** all 5 contract `Finding.kind` values get distinct title copy; material/ambiguous get badges.
- **Scope discipline:** `2cf0294` touches exactly the four allowed paths (12 files, all additions). `Disclosure`/`Button` imports are pre-existing T07 controls — untouched.
- **Receipt resolves:** `acceptance_criteria_evidence` keys match all four contract criteria after `rstrip(".")` normalization in `acceptance_receipts.criterion_evidence` (scripts/acceptance_receipts.py:172-182); every entry `status: executed` with nonempty existing evidence paths.

## Findings

### P1-1 — Material-token substring heuristic manufactures claims not in evidence

`packages/explanations/src/index.ts:175-179,216`. `MATERIAL_TOKEN_RE = /[$€£¥₹\d+-]/` tests whether **any reading contains** a digit/currency/sign — not whether the *difference* is in a material token. Probe: readings `"Page 2 layout"` vs `"Page 2 layoutt"` (priority `ordinary`) → `isMaterialTokenDifference` returns `true` → card is titled "This amount reads differently" and badged "Material difference", contradicting the recorded `priority` field. On the honesty-critical surface this is a generated truth claim: a word-level difference is presented to the user as an amount/material difference. Planning doc scopes materiality to *material-token changes*, not digit-bearing strings. Fix: trust `finding.priority === "material_token"` (the recorded classification), or intersect the *differing* tokens with the material charset.

### P2-1 — failed/cancelled/skipped collapse into Unsupported badge styling; no stat cards

`apps/web/src/features/coverage/CoveragePanel.tsx:105-112` — badge ternary: `timeout→badgeTimeout`, `model_missing→badgeModelMissing`, **everything else→badgeUnsupported**. A `failed` (non-model) or `cancelled`/`skipped` check is visually categorized as "unsupported" — a different terminal category (I05-adjacent conflation). Separately, stats grid (lines 50-70) only renders cards for timeout/model_missing/unsupported, so `failed`/`cancelled`/`skipped` count toward "incomplete" in the summary but are invisible in the card breakdown. Probe confirms `categorizeCheckStatus` emits all three residual categories with correct labels — only the visual layer flattens them.

### P2-2 — Recorded check identity and reason dropped; same-category rows collapse identically

`CoveragePanel.tsx:95-117` + `index.ts:88-115`. For `timeout`, `unsupported`, `cancelled` the recorded `reason` is discarded in favor of generic copy, and the check `id`/capability/reader is never rendered. Probe: two distinct timeouts (`"timed out page 0"`, `"timed out page 0 alt reader"`) produce two **byte-identical rows** — distinct unaligned work items are indistinguishable next to the no-difference result. Only `failed`/`skipped` surface reason text. Fix: render check id (or check→capability/reader label) plus recorded reason alongside the generic description.

### P2-3 — "notes" category from task purpose absent

Contract purpose: "Render actual named readings, structural observations, OCR interpretation, hypotheses, **notes** and incomplete checks distinctly." Contract `Annotation` (`origin: "human_entered"`) and copy keys `finding.note`/`finding.note.label`/`finding.note.disclosure` exist; nothing in `findings/` or `coverage/` accepts or renders annotations, and no add-note affordance exists. If note rendering is owned by a later task, the handoff does not disclose the deferral (handoff.json lists no such limitation).

### P3-1 — skipped reason built inline instead of frozen template

`index.ts:122`: `` `Not run: ${reason}` `` hardcoded; copy deck has `coverage.skipped: "Not run: {reason}"`. Identical output today; drifts if copy is revised. `coverage.empty`/`coverage.unchecked` keys also unused.

### P3-2 — Group header leaks raw region id

`FindingsList.tsx:60`: `"Region region-total"` — machine identifier shown to users as a label.

### INFO (no action required)

- `readingAlt` (rust) styling on the second comparative reading could subtly imply "the wrong one"; `finding.limit` disclaimer mitigates.
- `CoverageExplanation.isFullyComplete` computed but never consumed.
- `tsc -b` reports pre-existing repo-wide ambient-type gaps (missing `@types/react` incl. pre-existing `main.tsx`; contracts `.ts`-extension imports) — same class as `mount.tsx:454`; not introduced by T14 and outside its gates (oxlint/oxfmt/vite build all pass).
- Writer's self-assessment previously occupied this `review.md`; superseded by this independent review per T12 convention (original preserved in git history and `handoff.md`).

## Evidence of this review

- Commands rerun in `review-devin-t14` at `e9b14b9`: frozen install → test:browser 6/6 → build:web → oxlint → verify-run → module probes (quoted above).
- Writer evidence relied on: `run.json`, `commands.log`, `receipt.json`, `handoff.json/md`, five screenshots — all present, nonempty, consistent with reproduced output.
