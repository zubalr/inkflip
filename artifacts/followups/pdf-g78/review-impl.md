# pdf-g78 follow-up — independent implementation review (round 2)

- **Checkout**: worktrees/review-devin-g78, branch `review/devin/pdf-g78`
- **Revision under review**: `ff92d99` (ZCode's revision of `f260778`, which received
  CHANGES-REQUIRED with 7 findings)
- **Reviewer**: independent; did not write this code
- **Date**: 2026-09-13

## Verdict: CHANGES REQUIRED

Five of the seven prior findings are genuinely resolved and one (F13) is
resolved-as-scoped identically to F14. Two blocking defects remain/are new:

- **B1 (residual of finding 2, F23):** the `rules` sub-document inside every
  `baseline-misuse-*.json` payload still fails the canonical shared schema, and the
  expectation metadata claims it is valid.
- **B2 (new regression):** the registered `test:fixtures` command now fails —
  `tests/fixtures/test_g78_semantic.py` hard-imports `jsonschema`/`pypdfium2`, which
  the registered bare-`python3` argv does not provide.

---

## Per-finding results (prior review findings 1–7)

### 1. F22 import-security — RESOLVED
All four JSON payloads derive from `canonical_report()` (make_fixtures.py:890),
which independently validates against `inkflip.schema.json $defs/Report` (0 errors,
verified with jsonschema 4.26.0 Draft202012). Each variant mutates exactly one
mechanism and reaches its declared stage:
- `control`: schema-valid, bound to `SOURCE_DIGEST = "a"*64` → full pass.
- `unknown-key`: rejected at the schema stage — verifier emits exactly one error:
  `Additional properties are not allowed ('unknown_top_level' was unexpected)`.
- `script-string`: schema-VALID; `<script>alert(1)</script>` sits in the allowed
  `limitations` array as inert field content — proves display/use is separated from
  schema checking (the prior defect: rejected before display).
- `digest-mismatch`: schema-valid but `document.sha256 = "b"*64` ≠ bound digest →
  fails the source-binding stage after schema.
- `png-oversized` (IHDR width 0x7fffffff → 2.1e9 px > 40M budget) and
  `png-truncated` (12 bytes, IHDR incomplete) hit the decode/budget stage; both
  explicitly share the JSON control (control pointer corrected for the extension
  mismatch).

### 2. F23 baseline-misuse — NOT RESOLVED (B1)
Progress: the payload is now `{baseline, rules, report}` built on the canonical
report. Independently validated: `report` → `$defs/Report` **0 errors**;
`baseline` → `$defs/Baseline` **0 errors**; variants mutate one mechanism at a time
(coverage-loss changes only `checks`; mismatched-doc only `document`; silent-refresh
only `checks`), and the test-side rule interpreter fires the declared stage for each.

**But** `rules` fails `$defs/AcceptanceRules` with 6 schema errors on every variant:
- `rules[].type = "occurrence_count"` is not in the enum (`required_coverage`,
  `expected_text`, `expected_occurrence_count`, `max_geometry_delta`,
  `stable_reading`) — should be `expected_occurrence_count`;
- `policy` lacks all three required keys (`fail_on_coverage_loss`, `fail_on_error`,
  `unruled_change`) and adds undeclared keys (`baseline_refresh`, `rationale`).

Every `baseline-misuse-*.expect.json` asserts
`"canonical_schema": "report/baseline/acceptance_rules all schema-valid"` — provably
false, and `test_g78_semantic.py` never validates `baseline` or `rules`, so the
suite cannot catch it. This is the same defect class as the original finding
(invented structure failing canonical schema while claiming validity), now confined
to the rules sub-document. Fix: emit schema-valid rules (type
`expected_occurrence_count`, canonical policy keys) and extend the test to validate
all three sub-documents.

### 3. F14 unicode — RESOLVED AS SCOPED (honest gap)
The fixture no longer fabricates unembedded CJK/emoji CIDs. The Identity-H Type0 +
ToUnicode mechanism is demonstrated with Latin single-scalar codes (`<0001>`–`<0004>`
→ `$`,`1`,`0`,`0`); verified extraction is exactly `"$100"` via pypdfium2 — the
previous `$10` truncation is gone. `native-unicode-native.expect.json` declares the
exact boundary in `mechanism_scope`: native-script rendering/extraction requires a
rights-pinned embedded font, which the fixture font-program gate forbids, and states
the asset/gate change was reported to the coordinator (also in commands.log).
No font assets were acquired (diff contains only .pdf/.json/.png/.py/.log); no
coverage is overclaimed — the catalog mechanism "Arabic/CJK/emoji native strings"
remains genuinely uncovered pending the shared-owner font decision. The stale claim
`observed_extraction` still documents the non-embedded complex-script behavior as
reader-dependent rather than asserting it — accurate.

### 4. F13 ligature — RESOLVED AS SCOPED (same gate as F14)
The painted glyph is now honestly constant: both siblings paint code `A1`
(WinAnsi `¡`); `painted_glyph_constant: true` is declared. Verified via pypdfium2:
`ligatures-expansion` (ToUnicode `A1→0066 0069`) extracts `"fi"`;
`ligatures-control` (no ToUnicode) extracts `"¡"`. The extraction distinction is
preserved verbatim and the "literal fi" claim that mismatched the painted `¡` is
gone — the control is now the same painted glyph under identity mapping, which is
the honest comparison available without a font program. The generator docstring
records that a real font-backed ligature/combining glyph needs the same
rights-pinned embedded font (the reported F14 gate change); the combining-sequence
sibling remains absent under that gate — noted in commands.log. Renaming
`ligature` → `expansion` keeps the variant name truthful.

### 5. F26 asset-cache — RESOLVED
Each variant ships an executable tree: `manifest.required` digests + `files` with
real hex content and per-file sha256. Independently recomputed: control/offline-warm
verify clean; corrupt-model carries bytes whose digest ≠ declared good-model digest;
stale-worker/stale-core declare digests of `older-*-v0` while shipping good bytes
(mismatch realized); offline-cold ships `files: null`. The semantic test
materializes to a temp dir, recomputes sha256 and asserts each declared fault — real
consumer coverage, no prose-only scenarios.
Nit (P3): field is named `content_base64` but holds hex; the test correctly uses
`bytes.fromhex`. Rename to `content_hex` or actually base64-encode.

### 6. F15 ocr-material — RESOLVED
Independent RunLength decode of all three rasters (340×440):
- control: 3192 black px, **0 speckle px** (values only 0/255) — clean baseline;
- sign-ambiguity: 3144 black + 2766 speckle px;
- digit-ambiguity: 3144 black + 2767 speckle px.
Speckle is a fixed arithmetic function applied only to degraded variants;
`speckle: false` is recorded on the control expectation.

### 7. F24 overlap-ink — RESOLVED
The stroked border `[70,90,180,150]` has its left edge at x=70, which passes through
the text occurrence box `[50,110,97,128]` (verified in the raw content streams:
`70 90 180 150 re S` + `3 Tr`/`0 Tr`). pypdfium2 render at 4× confirms non-white
border ink inside the text bounds in BOTH siblings while
`FPDFTextObj_GetTextRenderMode` returns 3 (invisible) vs 0 (fill) — a real
crossing-border invisible-ink fixture proving ink-in-box ≠ visibility.

## New defect introduced by this revision

### B2 — registered `test:fixtures` command fails under its own argv (P1)
`config/acceptance-commands.json` registers `test:fixtures` as
`python3 -m unittest discover -s tests/fixtures -v` (harness-unittest), and
`scripts/task_acceptance.py` executes that argv literally (no interpreter remap —
`python3` resolves on PATH). The pre-existing suite is deliberately stdlib-only
("stdlib only, no PDF library" — test_fixtures.py docstring).
`test_g78_semantic.py:24` does `import jsonschema` at module top (and uses
pypdfium2 in test methods); neither exists for system python3 on this machine.
Measured: `python3 scripts/task_acceptance.py run test:fixtures` → exit 1,
"test evidence invalid: required tests failed=1" (51 tests ran, 1 collection
error). The worker's green runs used `uv run --project native python -m pytest`
— a different invocation than the registered command. Options: make the module
env-tolerant (guarded imports + explicit skip is weak — repo rules count skipped
required cases against a pass), move the semantic suite under a command that runs
inside the native uv project, or register a corrected argv — note
`config/acceptance-commands.json` is outside this task's write scope, so the
in-scope fix is on the test file placement/imports plus a coordinator-side
registration decision.

## Process checks

- **Determinism**: `python3 scripts/make_fixtures.py --check` → "check ok: 161
  files"; two independent `--out` regenerations + in-place tree are byte-identical
  (`diff -r` clean). No timestamps/random IDs.
- **Existing fixture preservation**: `git diff aa6d039..ff92d99` under `fixtures/`
  modifies only `manifest.json` and adds new files; all 45 pre-existing manifest
  entries are field-identical (sha256, bytes, expectations hash, control, recipe,
  rights, observation). The 15 pre-existing families' PDF/expect bytes unchanged.
- **Scope**: changes confined to `scripts/make_fixtures.py`, `fixtures/`,
  `tests/fixtures/`, `artifacts/followups/pdf-g78/` (the `artifacts/tasks/T05/`
  audit file came from 92cd11f and predates the scope rules). No `planning/`
  writes.
- **Font/rights**: no embedded font programs anywhere (`test_no_embedded_font_
  programs_anywhere` passes); no acquired font assets; no private/eval data.

## Test evidence

- `uv run --project native python -m unittest discover -s tests/fixtures -v`
  → **69 tests, all OK** (50 pre-existing + 19 semantic) in 3.8s.
- `python3 scripts/make_fixtures.py --check` → ok, 161 files.
- `python3 scripts/task_acceptance.py run test:fixtures` (registered argv, bare
  python3) → **exit 1** (collection error on test_g78_semantic; see B2).
- Independent verification performed: jsonschema validation of all F22/F23
  sub-documents; hand-rolled RunLength decode of all three F15 rasters; sha256
  recompute of all six F26 file sets; raw-stream + render inspection of F24;
  pypdfium2 extraction for F13/F14.

## Remaining nits (non-blocking)

- **P3 dead code**: `ligature_entries` (lines 714–723) and `unicode_entries`
  (lines 755–758) are defined twice — the first def in each pair is dead code left
  by a partial replacement, and its stale docstrings actively misdescribe the
  current behavior ("against a literal 'fi' control"; "Arabic/CJK/emoji logical
  strings"). Delete the dead first definitions. (`followup_entries` duplication
  pre-dates this revision.)
- **P3 F16 annotation**: `adjacent-crop-clipped` intent says "$100 cut by the crop
  edge at x=100" — the cutting edge is the LEFT edge x=50 (text spans ~40–93pt;
  x=100 is the right crop edge). Cosmetic but the edge label is wrong.
- **P3 F23 referential integrity**: `retained_occurrence_ids` ("x", "a", "b") name
  no occurrence in the report; schema can't check this, harmless for the rule
  exercise.

## Required to approve

1. B1: make the F23 `rules` document validate against `$defs/AcceptanceRules`
   (rule `type` → `expected_occurrence_count`; canonical `policy` keys) and extend
   `test_g78_semantic.py` to validate `baseline` and `rules` sub-documents, so the
   "all schema-valid" expectation claim is actually exercised.
2. B2: make the registered `test:fixtures` command pass as registered — either
   keep `tests/fixtures/` stdlib-only (move schema/render-dependent checks to a
   native-env suite and its registration) or change the registration through the
   shared owner. As committed, the acceptance command exits 1.
