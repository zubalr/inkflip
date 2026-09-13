# pdf-g78 fix round — review e8ab38a findings resolved

- **Branch**: work/devin/pdf-g78
- **Base under fix**: ff92d99 + merge 7fd8245 (integrate/pass1 = main 205e617
  + 2010fc3 test:fixtures native-env argv)
- **Review addressed**: artifacts/followups/pdf-g78/review-impl.md @ e8ab38a
  (review/devin/pdf-g78) — CHANGES REQUIRED with blockers B1/B2 + 4 nits.
- **Date**: 2026-09-13

## B1 — F23 baseline-misuse rules schema-invalid (FIXED)

`scripts/make_fixtures.py baseline_entries()`:

- Rule `type` `"occurrence_count"` → `"expected_occurrence_count"` (the real
  `$defs/Rule.type` enum member).
- `policy` → canonical keys only:
  `{"fail_on_coverage_loss": true, "fail_on_error": true,
    "unruled_change": "changed"}` — the undeclared `baseline_refresh` /
  `rationale` keys removed (`policy.additionalProperties: false`).
- Verified independently under the pinned native env: every
  `baseline-misuse-*.json` sub-document validates against
  `native/inkflip/contracts/schema/inkflip.schema.json` — `report` →
  `$defs/Report` 0 errors, `baseline` → `$defs/Baseline` 0 errors,
  `rules` → `$defs/AcceptanceRules` 0 errors (jsonschema 4.26.0
  Draft202012, all four variants).
- `canonical_schema` intent on the three fault variants strengthened to
  "report/baseline/acceptance_rules all schema-valid; the <stage> fires" —
  now genuinely true and exercised.

`tests/fixtures/test_g78_semantic.py`:

- New `subdoc_validator(def_name)` helper; `TestF23BaselineRules.errors_for`
  now validates `report`, `baseline` AND `rules` before running the rule
  interpreter, and new test
  `test_every_subdocument_is_canonical_schema_valid` iterates all four
  variants x three `$defs` asserting zero errors — the "all schema-valid"
  expectation claim can no longer silently regress.

## B2 — registered test:fixtures argv (FIXED BY MERGE)

Merged `integrate/pass1` (7fd8245): `config/acceptance-commands.json` now
registers `test:fixtures` as
`uv run --frozen --project native python -m unittest discover -s tests/fixtures -v`
(commit 2010fc3 on top of main 205e617). The pinned `native/uv.lock` env
provides jsonschema 4.26.0 + pypdfium2 5.8.0, so the semantic suite's
imports resolve. `python3 scripts/task_acceptance.py run test:fixtures`
→ exit 0, 70 tests, OK.

## Nits fixed

- **Dead defs**: removed the stale first `ligature_entries` (~714-723) and
  `unicode_entries` (~755-758) definitions whose docstrings misdescribed
  the shipped behavior; exactly one live def of each remains.
- **F26 field name**: `content_base64` → `content_hex` in the generated
  `asset-cache-*.json` payloads and the consumer test (the value is hex,
  consumed via `bytes.fromhex`).
- **F16 clipped intent**: `adjacent-crop-clipped` now says "$100 cut by the
  left crop edge at x=50 (text spans ~40-93pt; x=100 is the right edge)" —
  the cutting edge is the crop's LEFT edge.
- **F23 referential integrity**: `retained_occurrence_ids` now name real
  occurrences (`pdfium-native-aa00-p0-text-0`;
  `tesseract-native-aa00-p0-text-0/1`). The F23 report gained the matching
  `tesseract-native` reader, `check-ocr` plan entry and two OCR occurrences
  so the ids resolve (schema-valid, verified above).

## Commands and results

```
$ git merge --no-ff integrate/pass1            -> merge commit 7fd8245 (clean)
$ python3 scripts/make_fixtures.py             -> generated 161 files under fixtures/
$ python3 scripts/make_fixtures.py --check     -> check ok: 161 files match
$ python3 scripts/make_fixtures.py --out /tmp/g78f1 && --out /tmp/g78f2
$ diff -r /tmp/g78f1 /tmp/g78f2                -> DETERMINISM OK (byte-identical)
$ diff -r fixtures /tmp/g78f1                  -> IN-PLACE OK (byte-identical)
$ python3 scripts/task_acceptance.py run test:fixtures
  -> exit 0; Ran 70 tests — OK (50 pre-existing + 20 semantic;
     +1 vs prior: test_every_subdocument_is_canonical_schema_valid)
$ jsonschema re-validation (native env): all 4 F23 variants x
  Report/Baseline/AcceptanceRules -> 0 errors each (12/12 clean)
```

## Preservation checks

- All 45 pre-existing manifest entries (merge-base aa6d039) are
  field-identical — sha256, bytes, expectations hash, control, recipe,
  rights, observation; every pre-existing fixture file's bytes unchanged
  (scripted compare vs aa6d039).
- Determinism preserved: no timestamps, no random IDs; generator hash in
  manifest regenerated from source.
- Scope: `scripts/make_fixtures.py`, `fixtures/`, `tests/fixtures/`,
  `artifacts/followups/pdf-g78/` only (plus the merge-inherited main
  changes). No planning/ writes, no Beads writes, no font assets acquired;
  F14 remains scoped as before.
- Changed fixture bytes are confined to g78 families:
  `baseline-misuse-*` (4 json + 4 expect via manifest digests — expect
  intents also updated), `asset-cache-*.json` (5 files; offline-cold has
  `files: null`, unchanged), `adjacent-crop-clipped.expect.json`,
  `manifest.json`.
