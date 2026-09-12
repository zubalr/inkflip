# T28 independent review — bounded native structural observations

## ROUND 3 — candidate `28eb932` (impl `cf01857` + evidence `28eb932`), merged into this checkout as `080e76f`

- **Reviewer:** Devin Local SWE-2 (independent reviewer subagent), macOS arm64 checkout `review-devin-t28`. Replacement reviewer for the crashed round-2 subagent; work resumed from preserved checkout/branch.
- **Candidate reviewed:** `28eb9326bbb4ddff1db605ebeafb9a2e1ef9075b` on `work/zcode/t28`, fetched from origin and merged cleanly (merge `080e76f`); delta touches only `native/inkflip/checks/structure.py`, `native/tests/structure/test_structure.py` and `artifacts/tasks/T28/*` — inside allowed scope plus task artifacts.
- **Verdict: APPROVED** — all four round-2 findings verified resolved with live evidence. Two residual P3 documentation nits carried below (neither reaches the machine-consumed acceptance record).

### Round-3 reproduced counts (macOS arm64, merged head `080e76f`)

| Command | Worker claim (Linux) | Reproduced here |
|---|---|---|
| `uv run --project native python -m pytest native/tests/structure -q` | 20 + 14 subtests | **20 passed, 14 subtests** ✓ |
| `uv run --project native python -m pytest native/tests -q` | 131 + 160 subtests | **130 passed, 1 failed**, 160 subtests — same pre-existing T27 OCR macOS `/var`→`/private/var` failure (`test_ocr.py:847`), not introduced by this diff |
| `python3 scripts/task_acceptance.py task T28 --report artifacts/tasks/T28/run.json` | exit 0, 20/20 | exit 0, collected 20 / passed 20, `run.json` rebound to `evaluated_commit=080e76f` ✓ |
| `python3 scripts/acceptance_receipts.py verify-run T28` | — | **verified**; `{"verified": "T28", "tests": {collected 20, passed 20}}` ✓ |
| `acceptance_receipts.criterion_evidence(task, receipt.json)` | resolves | **RESOLVED** — returns all four criteria mapped to `artifacts/tasks/T28/`-namespaced paths only ✓ |

### Round-2 finding verification

**1. P1 evidence namespace — RESOLVED.** `acceptance_criteria_evidence` keeps byte-exact contract keys (verified through `criterion_evidence` normalization incl. curly-quote `“all checked”` and trailing-period keys) and every `evidence` list now cites only `artifacts/tasks/T28/criterion-evidence-current.md`, `commands.log`, `run.json`. Live import of `scripts/acceptance_receipts.py::criterion_evidence` returns the four-criterion map with no `ValueError`; `verify-run` passes. New `criterion-evidence-current.md` itemizes per-criterion proof points (test names + module behavior) — real, checkable citations.

**2. P2(b) /BM prose — RESOLVED in all operative locations.** Corrected claim verified in: module docstring ("`FPDFPageObj_HasTransparency` flags … alpha fills, soft masks AND non-Normal blend modes (empirically verified: /BM /Multiply and /Screen objects are flagged)"), manifest `limitations` ("per-occurrence compositing flags cover transparency and non-Normal blend modes (HasTransparency)"), receipt `limitations` (same, with /OC as the stated residual), and handoff `review_revision_round_2.bm_claim_correction`. My probes confirm the corrected claim is *true*: `/BM /Multiply` object flags per-occurrence, `/BM /Normal` and q/Q-scoped plain sibling do not. New pinning test `test_non_normal_blend_mode_is_flagged_per_occurrence` passes. **Residual nit:** the `detail` narrative of receipt criterion "unsupported compositing explicitly recorded." (receipt.json) still contains one copy of the retracted "…/BM not detectable per object (setter-only)" sentence — contradicted by the receipt's own limitation five lines up. Carried as P3: `record_acceptance` propagates only criterion *evidence paths* into `acceptance.json` (acceptance_receipts.py:212–225), so the stale sentence never reaches the consumed record. Historical `handoff.review_revision_round_1a00561` and round-1 `commands.log` entries legitimately keep the old claim as history.

**3. P2(c) /CA stroking alpha — RESOLVED.** `structure.py:440–443` now applies the symmetric check `stroke[3] < 255` (stroke RGBA fetched only for stroke-involving modes 1/2/5/6 — correct, since `/CA` only affects stroking). Independent probes on the merged build:

| Context | Flag? |
|---|---|
| `/CA 0.5` + `1 Tr` stroke text | **YES** — "stroke alpha compositing not inspected; stroke alpha below 255", basis records `stroke=0,0,0,128` |
| `/CA 0.5` + `2 Tr` fill+stroke | YES — stroke flag fires |
| `/CA 0.5` + `0 Tr` fill-only | correctly NO — stroke is `None` for non-stroking modes; `/CA` is irrelevant to fills, no false positive |
| `/ca 0.5 + /CA 0.5` + `2 Tr` | all three flags (fill alpha + stroke alpha + HasTransparency) |
| `/BM /Multiply` | YES (HasTransparency non-Normal-blend limitation) |
| `/BM /Normal` | no (correct) |
| `/OC /OCG BDC` membership | no — now the sole explicitly documented residual (receipt limitation + docstring), per round-2 condition |

Pinning test `test_stroking_alpha_is_flagged_symmetrically` passes; `HasTransparency` indeed does not fire for `/CA` on this build, so the symmetric check is the actual mechanism — verified, not just test-trusted.

**4. P3 stale fields — RESOLVED.** `worker.implementation_commit` = `cf01857` (receipt + handoff); receipt `commands` table refreshed to 20/131(+160 subtests)/20 which matches both the worker's Linux claim and my macOS reproduction (130+1 pre-existing T27 env failure); handoff top-level `executed_commands` and `review_revision_round_2.executed_commands_linux` consistent at 20/131.

### Residual P3 nits (carried, non-blocking)

1. receipt.json criterion "unsupported compositing explicitly recorded." `detail` retains one stale copy of the retracted /BM-setter-only sentence (see finding 2) — narrative only; fix on next touch of the receipt.
2. `commands.log` round-2 summary line reads "counts 20/129" while the transcript lines below it correctly record 131 full-native — summary typo only.

### Resolution

All round-2 requests satisfied: task-namespaced criterion evidence resolves through the real pipeline function; the /BM claim is corrected and pinned by test + independent probe; the /CA gap is closed by a verified symmetric check; stale fields refreshed. **APPROVED.** Coordinator may proceed to `record`/`verify` (review path `artifacts/tasks/T28/review.md`, this commit).

---

## ROUND 2 — revision `faa365a` (impl `3863dde`), merged into this checkout as `8823e09`

- **Reviewer:** Devin Local SWE-2 (independent reviewer subagent), macOS arm64 checkout `review-devin-t28`
- **Candidate reviewed:** `faa365ac3fb7214dbae4c481b9b179991265941e` on `work/zcode/t28` (descendant of `6e0d17a`), fetched from origin and merged cleanly; revision delta touches only the two allowed code paths plus task-local artifacts.
- **Verdict: CHANGES-REQUIRED** — P1 is still blocking (record path fails on a different rule), P2 code fix is real and verified but its supporting prose is factually wrong and one same-class gap is undisclosed.

### Round-2 reproduced counts (macOS arm64, merged head `8823e09`)

| Command | Worker claim (Linux) | Reproduced here |
|---|---|---|
| `uv run --project native python -m pytest native/tests/structure -q` | 18 + 14 subtests | **18 passed, 14 subtests** ✓ |
| `uv run --project native python -m pytest native/tests -q` | 129 + 160 subtests | **128 passed, 1 failed**, 160 subtests — same pre-existing T27 OCR macOS `/var`→`/private/var` failure (`test_ocr.py:847`), not introduced by this diff |
| `python3 scripts/task_acceptance.py task T28 --report` | exit 0, 18/18 | exit 0, collected 18 / passed 18, `evaluated_commit=8823e09` ✓ |
| `python3 scripts/acceptance_receipts.py verify-run T28` | — | verified; `run.json` correctly **rebound to `3863dde`** (the revision impl) — the staleness concern does not apply; `3863dde..faa365a` is artifacts-only so freshness holds ✓ |
| `acceptance_receipts.criterion_evidence(task, receipt.json)` | resolves | **STILL FAILS**: `ValueError: T28: evidence must stay in its task namespace` |

### P1 — partially fixed, still blocking
`acceptance_criteria_evidence` now exists with **byte-exact keys** — verified set-equal to the contract criteria including curly quotes `“all checked”` and the trailing period. **But** every criterion cites `native/inkflip/checks/structure.py` and `native/tests/structure/test_structure.py`, which violate `evidence_path()`'s `artifacts/tasks/T28/` namespace rule (`scripts/acceptance_receipts.py:42–48`). `criterion_evidence` raises before `record` can build `acceptance.json`. The handoff claims "task-local evidence paths" — false. T05/T26/T27 cite only task-local files (commands.log, criteria-evidence.md, run.json, reviews). **Fix:** replace source-file citations with task-local evidence (e.g. a `criteria-evidence.md` narrative plus `commands.log`/`run.json`).

### P2 — code fix verified real; two evidence/prose defects remain
(a) **Verified**: `FPDFPageObj_HasTransparency` exists on this build and is called per text object (`structure.py:436`); new test `test_transparent_text_is_flagged_per_occurrence_opaque_is_not` proves a `q/Q`-scoped alpha object is flagged while the opaque object on the same page is not. My own probes on the merged build:

| Context | Per-occurrence flag? |
|---|---|
| `/ca 0.5` | YES (alpha + transparency limitations) |
| `/BM /Multiply`, `/BM /Screen` | **YES** — flagged |
| `/BM /Normal`, `/SMask /None` | no (correct — not transparency) |
| `/SMask /Luminosity` | YES |
| `/OC /OCG BDC` membership | no — explicitly disclosed in the new receipt limitation; acceptable per review condition |
| `/CA 0.5` (stroking alpha) | **NO — undisclosed gap** |

(b) **Prose is factually wrong**: receipt limitation + module docstring + handoff all claim "/BM … not detectable per object on the installed binding (setter-only API)". Empirically false — `HasTransparency` DOES flag non-Normal blend modes; those objects emit the transparency limitation, not "ordinary records". The claim under-reports actual coverage (safe direction) but misstates the mechanism and must be corrected for an accurate record.

(c) **`/CA` stroking alpha is a residual silent case**: a `1 Tr` object under `/CA 0.5` emits a generic-limitation-only record (`HasTransparency` does not fire for CA on this build; the code checks `fill[3] < 255` but never `stroke[3] < 255`). The stroke alpha IS still reported in basis (`stroke=0,0,0,128`), so the value isn't hidden — but no "unsupported compositing" limitation fires and no receipt limitation covers it. Same-class gap as /OC. **Fix options:** symmetric `stroke[3] < 255` check (data already fetched) or an explicit documented limitation line like the /OC one.

### New P3 accuracy nits introduced by the revision
- `receipt.json` `worker.implementation_commit` still `1050c33` (pre-revision); should be `3863dde`. Its `commands` table still claims 17/128 and "run.json binds evaluated_commit 1050c33" — stale vs the actual 18/129 run and `3863dde` binding. Handoff top-level `executed_commands` similarly stale (its `review_revision_round_1a00561.executed_commands_linux` correctly shows 18).
- Carried over from round 1 (worker's choice, acknowledged): `checks/__init__.py` kept — fine, coordinator already has it on record; form-only `completed/0` under non-mode capabilities — worker's rationale accepted.

### Resolution requested (round 3)
1. P1: repoint `acceptance_criteria_evidence[].evidence` to `artifacts/tasks/T28/`-namespaced files only; then `criterion_evidence` must run clean.
2. P2(b): correct the /BM claim in `receipt.json` limitations, `structure.py` docstring and handoff — BM IS flagged via `HasTransparency`; the true undetectable-per-object gap is /OC membership.
3. P2(c): close or document the `/CA` stroking-alpha gap (recommend the symmetric `stroke[3] < 255` limitation since stroke RGBA is already recorded).
4. P3: refresh `worker.implementation_commit` and the `commands` counts/detail in `receipt.json` to the revision run (18/129, `3863dde`).

---

## ROUND 1 — candidate `6e0d17a` (below preserved verbatim)

- **Reviewer:** Devin Local SWE-2 (independent reviewer subagent), macOS arm64 checkout `review-devin-t28`
- **Candidate:** `6e0d17a` (impl `1050c33` + evidence commit), branch `review/devin/t28`, base `546accd`
- **Writer:** ZCode on Homebase (`zcode-t28`, `work/zcode/t28`, Linux amd64). I did not write or previously run this code.
- **Verdict: CHANGES-REQUIRED** — one P1 acceptance-pipeline blocker, one P2 criterion gap, plus P3 notes.

## Reproduced counts (this machine, macOS arm64)

| Command | Claimed | Reproduced |
|---|---|---|
| `uv run --project native python -m pytest native/tests/structure -q` | 17 + 14 subtests | **17 passed, 14 subtests** ✓ |
| `uv run --project native python -m pytest native/tests -q` | 128 + 160 subtests | **127 passed, 1 failed**, 160 subtests ✗ (see P3 #2) |
| `python3 scripts/task_acceptance.py task T28 --report` | exit 0, 17/17 | exit 0, collected 17 / passed 17 / failed 0 / skipped 0, `evaluated_commit=6e0d17a` ✓ |
| `python3 scripts/acceptance_receipts.py verify-run T28` | — | verified; worker `run.json` (evaluated `1050c33`) still fresh — only artifacts changed since ✓ |
| `acceptance_receipts.criterion_evidence(task, receipt.json)` | resolves | **FAILS** — `ValueError: worker evidence needs executed criterion and explicit evidence paths` (P1) |

## Scope check (`git diff 546accd..6e0d17a`)

`native/inkflip/checks/structure.py` (607 lines) + `native/tests/structure/test_structure.py` (447 lines) + `artifacts/tasks/T28/{commands.log,handoff.json,receipt.json,run.json}` — all inside the two allowed paths plus required task-local evidence. **One extra file:** `native/inkflip/checks/__init__.py` (0 bytes) is outside the literal `allowed_scope` (P3 #1). No label or label-adjacent data in artifacts — only design rationale and criterion→evidence mapping.

## Criteria verification (executed live, not just test-trust)

**1. No universal hidden/visible verdict — PASS.** I built a page mixing `0 Tr` normal + `3 Tr` invisible + `0 Tr` normal text: result = 3 per-object occurrences (`tr0:fill`, `tr3:invisible`, `tr0:fill`), each carrying "not a hidden or visible verdict". Result objects contain only `status`/`reason`/counts — no aggregation path exists. JSON of result+occurrences across all three capabilities contains no `"verdict"`/`"hidden"`/`"visible"`/`"suspicious"`/`"safe"` strings. Invisible-over-border (F03: 13 `tr3` objects) and synthesized white-on-dark vs white-on-light controls produce byte-identical structural records — a universal verdict is impossible by construction. **PASS.**

**2. No false "all checked" — PASS.** Absent properties surface as `fill=unavailable`, `font=unavailable`, `no bounds`, `geometry.precision="unknown"` + null polygon + empty `transform_ids`; out-of-range Tr → `unknown` name with raw int kept. Unsupported capability/`region_id`/out-of-range page → `unsupported`; budget overrun → `failed`/`resource_limit` retaining prior evidence (verified 4 occurrences retained); cancellation → `cancelled`. Uninspected items surface in per-occurrence `limitations[]`, manifest `limitations`, per-capability `limits`, and `support:"approximate"`. Caveat: see P2 for compositing contexts that surface only at manifest level.

**3. Off-crop raw geometry + crop page display — PASS (verified in one result).** Crop `[20 300 160 380]` on `[0 0 520 400]`: same `crop_metadata` result contains (a) off-crop object with polygon `[[400.67,329.79],[461.47,329.79],…]` outside the `[0,140]×[0,80]` canonical extent and `raw user box (420.67, 39.85, 481.47, 50.21)` in basis, limitation "page display remains the crop"; (b) `pdfium:page[props]` with polygon `[[0,0],[140,0],[140,80],[0,80]]` — the crop. Both facts hold simultaneously.

**4. Unsupported compositing explicitly recorded — PARTIAL (P2).** Alpha fills (`ca/CA 0.5` → alpha <255) record "alpha compositing not inspected"; nested Form XObjects record "compositing unsupported" and nested text is not emitted. Verified live. **However** `/BM /Multiply`, `/SMask /Luminosity`+transparency group, and `/OC /OCG BDC` objects each emit `tr0:fill` / `fill=0,0,0,255` with only the generic limitation — silently normal records; the declaration exists only in the manifest.

## Findings

### P1 — `receipt.json` cannot be consumed by the acceptance pipeline
`artifacts/tasks/T28/receipt.json` lacks the `acceptance_criteria_evidence` dict that `acceptance_receipts.criterion_evidence()` (scripts/acceptance_receipts.py:172–182) requires; calling it raises `ValueError` on the first criterion, so coordinator `record`/`verify` will fail on this receipt. T05/T26/T27 receipts all carry the dict keyed by exact criterion strings → `{status:"executed", evidence:[…]}`. Compounding: the `criteria` list itself has fidelity errors vs the contract — criterion 2 was rewritten with straight quotes (`'all checked'` vs contract `“all checked”`, breaks key resolution if copied) and criterion 4 dropped its trailing period (tolerated by `rstrip(".")` but sloppy). **Fix:** add `acceptance_criteria_evidence` keyed by the exact contract strings and correct the `criteria` text.

### P2 — Blend/SMask/OCG/transparency-group objects silently emit default records
Per the criterion's strict reading ("an affected object records `unsupported`/`unavailable` rather than silently reporting default values"), verified live: `/BM /Multiply` → `tr0:fill fill=0,0,0,255`; `/SMask` luminosity → same; `/OC … BDC` text → same — each with only the generic limitation. Only alpha fills and nested forms record per-occurrence. The manifest declares these uninspected globally, so no false claim of inspection is made, but a per-occurrence consumer cannot distinguish a blended/OCG/masked object from a normal one. **Fix options:** detect non-default graphics-state/OC context (e.g., pypdf resource scan or content-stream `BDC`/`gs` tracking within the finite budget) and stamp the limitation, or state explicitly in receipt `limitations` that these contexts emit unmarked records — coordinator decision on which satisfies the criterion.

### P3 — minor
1. `native/inkflip/checks/__init__.py` (0 bytes) is outside literal `allowed_scope`. Harmless marker — and arguably unneeded (`native/inkflip/readers/` imports fine without one via namespace packages). Acknowledge or drop.
2. "128 native tests" is platform-conditional: `native/tests/ocr/test_ocr.py::TestModelSelection::test_fallback_dir_is_probed_per_language` fails on macOS (`/var`→`/private/var` symlink, `path.parent` comparison). Pre-existing T27 scope, untouched by this diff — reproduced 127+1 here vs worker's 128 on Linux. Flag to the T27/OCR owner for a `resolve()` fix; not a T28 blocker.
3. `test_off_crop_object_keeps_unclipped_native_geometry` asserts coords outside `x∈[20,160]` though the canonical extent is `[0,140]` — threshold uses crop-box numbers, not canonical extent; still proves off-crop but is a sloppy bound. No test exercises the `geometry_supported=False` path (malformed boxes → `precision:"unknown"`), and form-skip records emit only under `object_render_mode` — a form-only page returns `completed` with 0 occurrences and no emitted limitation under `paint_overlap`/`crop_metadata` (manifest-level only).
4. Robustness nits: `page_index=True` passes `isinstance(int)` (bool subclass); an `emit_chunk` exception escapes untyped (I05 edge); `_object_text` absent → `raw_text:""` rather than an unavailable marker.

## What was verified good
- Tr-semantics anchor handled correctly: raw int + PDF `Tr` names recorded together; `3 Tr`→`invisible` verified on this build (sweep test pins all 8 modes; pypdfium2 enum-name divergence documented).
- Typed terminals only; partial evidence survives budget overrun; cancellation is a terminal.
- Occurrences validate against the real `Occurrence` schema in tests; manifest validates against `ReaderManifest`.
- `run.json` is genuine (argv, junit path, checkout, counts match) and `verify-run` passes; freshness holds since only artifacts changed post-evaluation.
- Honest limitation disclosure: F04/F05/F06 are catalog `specified`/not generated (verified against `planning/quality/fixture-catalog.json` and `fixtures/`); controls covered by synthesized in-memory PDFs + committed F02/F03/F07, with a fixture-lane dependency request recorded.

## Resolution requested from writer
1. Add `acceptance_criteria_evidence` to `receipt.json` keyed by exact contract criterion strings (fix the curly-quote criterion too).
2. Address P2 — either per-occurrence flagging of blend/SMask/OCG/group contexts or an explicit receipt limitation that such objects emit unmarked records (coordinator ruling on criterion sufficiency).
3. P3 items are advisory; #1 (scope nit) needs coordinator acknowledgement or file removal.
