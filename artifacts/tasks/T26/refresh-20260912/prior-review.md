Archival review text; trailing whitespace normalized for this copy. Original bytes remain in Git at bbcddac7704733dc3491678878f1a6a31b1a0ed9:artifacts/tasks/T26/review.md.

# Independent Peer Review — T26

**Task:** T26 — Implement native PDFium and pypdf reader adapters
**Beads Issue:** `pdf-t26`
**Candidate Commit Reviewed:** `9f43bb0` (implementation `d9c18b0`) on `work/zcode/t26`
**Base Commit:** `ef5ffff076ea6833fe86db44e087768803646896`
**Reviewer:** `antigravity` (isolated review worktree `review-t26`)
**Review Branch:** `review/antigravity/t26`
**Date:** 2026-09-12
**Contract Version:** 1.0.0
**Verdict:** `approved`

---

## Executive Summary

Candidate `9f43bb0` delivers the native PDFium and pypdf text reader adapters and the TEST-26 test suite strictly within the T26 contract and allowed scope. The implementation faithfully honors the architectural invariants:
- **I02 (Occurrence Identity):** Every emitted occurrence binds reader ID, page index, ordinal, raw text, and canonical page geometry. Consecutive Unicode scalars originating from a single ToUnicode glyph expansion (F01 mechanism) are coalesced into a single occurrence sharing the reported glyph box; no widths are guessed or interpolated.
- **I03 (Raw Text Fidelity):** Preserves verbatim engine outputs (`$1,00000` for PDFium and `$1,000$100` for pypdf on F02). Normalization is an explicit identity map, reserving downstream transformation for T12.
- **I13 (Build & Engine Identification):** Both adapters expose complete `describe()` manifests that validate against the T03 Draft 2020-12 JSON Schema (`$defs/ReaderManifest`), including dynamic SHA-256 binary digests of the loaded `libpdfium` engine.
- **I17 (Failure Isolation):** Password-protected encrypted files, malformed bytes, and digest mismatches raise typed `AdapterError("parser_error")`; invalid plans and closed handles return terminal `CheckResult` records without leaking unhandled exceptions or partial state.

All acceptance criteria are substantiated by real automated tests and direct code inspection.

---

## Scope & Boundary Audit

- **Allowed Scope:**
  - `native/inkflip/readers/pdfium.py`
  - `native/inkflip/readers/pypdf.py`
  - `native/tests/readers/`
  - `artifacts/tasks/T26/`
- **Diff Stat:**
  ```
  artifacts/tasks/T26/commands.log     |  28 +++
  artifacts/tasks/T26/handoff.json     |  52 ++++
  artifacts/tasks/T26/receipt.json     | 121 +++++++++
  native/inkflip/readers/pdfium.py     | 460 +++++++++++++++++++++++++++++++++++
  native/inkflip/readers/pypdf.py      | 275 +++++++++++++++++++++
  native/tests/readers/test_readers.py | 444 +++++++++++++++++++++++++++++++++
  6 files changed, 1380 insertions(+)
  ```
- **Boundary Checks:**
  - No changes outside allowed scope.
  - `planning/` is untouched.
  - No lockfiles or root manifests modified.
  - No cross-module bleed into frontend, geometry core, or root coordination.

---

## Criterion-by-Criterion Evaluation

| Acceptance Criterion | Result | Evidence & Analysis |
|---|---|---|
| **Mapping/control/covered actual outputs preserved** | **PASS** | On F01 (`mapping-amount.pdf`), PDFium expands glyph 0x31 into `1,0` without splitting into bare commas or normalizing away; on `mapping-control.pdf`, identity `$100` is retained. On F02 (`covered-amount.pdf`), PDFium's raw merged string `$1,00000` and pypdf's `$1,000$100` are emitted verbatim. |
| **Shared glyph boxes not split with guessed widths** | **PASS** | In `native/inkflip/readers/pdfium.py:439-446`, characters sharing an identical reported `get_charbox(loose=True)` box coalesce into a single occurrence. Tested in `test_mapping_expands_glyph_without_splitting_shared_box`: dollar sign keeps distinct box; `1,0` quad is identical to the glyph box; basis explicitly records coalescing. |
| **pypdf text stays page-only** | **PASS** | In `native/inkflip/readers/pypdf.py:261-267`, extraction emits exactly one occurrence per page with `precision: "page_only"`, `polygon: None`, and empty transform IDs. No visitor matrices or per-word geometry heuristics are attempted. |
| **All rotations/origins map correctly; UserUnit once** | **PASS** | In `native/inkflip/readers/pdfium.py:216-226`, canonical transform $C = [u, 0, 0, -u, -u \cdot cx_0, u \cdot cy_1]$ accounts for crop box origin and `/UserUnit`. Rotation is confirmed display-only: rotations 0°, 90°, 180°, 270° yield identical canonical polygon coordinates for the dollar glyph (`test_rotations_store_identical_canonical_anchors`). Physical page dimensions and glyph anchors scale by $u$ exactly once across UserUnit 0.5, 1, 2, and 10. |
| **Malformed/encrypted failures isolated** | **PASS** | Tested in `TestPdfiumFailureIsolation` and `TestPypdfReader`: corrupt bytes, digest mismatch, and password-protected files raise typed `AdapterError("parser_error")`; closed handles and out-of-bounds page requests return terminal `failed`/`unsupported` `CheckResult` records. Resource cleanup is verified in `finally` blocks (`textpage.close()`, `page.close()`). Cancellation is handled cleanly. |
| **Build/version manifest complete** | **PASS** | Tested in `ReaderManifestTests`: both `pdfium_reader.describe()` and `pypdf_reader.describe()` validate against the T03 schema. `model_hashes` and `asset_hashes` contain the valid 64-character hex SHA-256 of the loaded `libpdfium.dylib` engine binary. Unsupported render capability is declared `unavailable` rather than overstated. |

---

## Verification Commands & Reproduction

The suite was executed in an isolated worktree (`worktrees/review-t26`) against the candidate commit `9f43bb0`:

| Command | Exit Code | Time | Outcome |
|---|---|---|---|
| `uv run --project native python -m pytest native/tests/readers -q` | 0 | 0.19s | 22 passed, 10 subtests passed |
| `bun run test:native` | 0 | 0.41s | 53 passed (bootstrap + contracts + readers) |
| `python3 scripts/task_acceptance.py task T26` | 0 | 0.20s | 22 collected, 22 passed, 0 failed, 0 skipped |
| `python3 scripts/task_acceptance.py self-check` | 0 | 0.05s | 16 registered commands checked; valid |
| `bun run verify` | 0 | 6.24s | 81 tests passing (49 bootstrap, 2 native-bootstrap, 30 coordination) |

---

## Review Findings & Observations

- **Positive:**
  - Strict adherence to the `COORDINATES.md` specification and compensation for PDFium's known `UserUnit`-blind `get_size()` behavior.
  - Pure in-process adapter implementation with zero thread spawning, safe for downstream multiprocess supervision (T29).
  - Explicit documentation of trade-offs, limitations, and measured decisions in `receipt.json` and `handoff.json`.
- **Note / Dependency Request:**
  - F10 (missing ToUnicode CMap passthrough) and F11 (duplicate occurrences across positions) are appropriately synthesized in `test_readers.py` using the T05 fixture generator script. We endorse ZCode's dependency request to the fixture owner lane to commit canonical standalone PDF files for F10 and F11 in a future pass.

---

## Verdict

**`approved`**

Candidate `9f43bb0` (implementation `d9c18b0`) satisfies all acceptance criteria, maintains strict boundary discipline, passes all automated checks green, and is recommended for integration.
