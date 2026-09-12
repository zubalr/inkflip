# T28 independent review — bounded native structural observations

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
