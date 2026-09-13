# Independent Peer Review — T05

**Task:** T05 — Create original fixture foundation and rights manifest  
**Beads Issue:** `pdf-t05`  
**Candidate Commit Reviewed:** `f30b8705f41aa1d575498867a54483a9ce657c91` (implementation commit `36bff8f407666b87f649a25d056cf9d4522f87cf` + worker evidence)  
**Base:** `3bef697a31120d4cb32e8fa044d419bc34e32cf5`  
**Branch Reviewed:** `work/zcode/t05` (reviewed in isolated worktree `review-t05` on `review/antigravity/t05`)  
**Reviewer:** `antigravity-peer-reviewer` (Session ID: `a8c5c577-d459-41aa-87e8-e8cf834e6b4d`)  
**Worker / Author:** `zcode-t05` (ZCode app)  
**Date:** 2026-09-12  
**Contract Version:** 1.0.0  
**Explicit Verdict:** **`approved`**

---

## Executive Summary

Antigravity conducted an independent, adversarial peer review of ZCode's T05 delivery candidate at commit `f30b870` in an isolated checkout (`worktrees/review-t05`).

The implementation establishes a clean, fully deterministic stdlib-only PDF fixture generator (`scripts/make_fixtures.py`), the fixture catalog splits (`fixtures/public/` and `fixtures/development/`), expectation metadata files (`.expect.json`), the root content-addressed manifest (`fixtures/manifest.json`), and the comprehensive `TEST-05` test suite (`tests/fixtures/test_fixtures.py`, 38 unit tests).

All five contract acceptance criteria are substantiated by direct verification:
1. **Determinism:** `scripts/make_fixtures.py --check` passes cleanly across all 33 files; two fresh regenerations produce byte-identical outputs; tampering with a single byte triggers failure as verified by unit tests. PDF RunLength encoding eliminates zlib implementation divergence.
2. **Mapping vs. Control:** `mapping-amount.pdf` and `mapping-control.pdf` possess byte-identical content streams and paint operators ($100), diverging solely in the ToUnicode `<31>` mapping ($1,000 vs $100). macOS QuickLook render captures confirm pixel-identical rendering of the marks.
3. **No Filename Conditioning:** Fixture bytes contain zero occurrences of their filenames or stems; manifest lookups are strictly SHA-256 content-addressed.
4. **Rights & Privacy:** Zero embedded font programs (/FontFile*), no FontDescriptors, only standard base-14 Helvetica. No private keys, passwords, challenge markers, or email addresses present. All entries carry the project MIT license grant.
5. **Legitimate Searchable Scan (F03):** An original 680x880 DeviceGray raster drawn from an owned 5x7 bitmap font with an invisible text layer (`3 Tr`) placed with absolute text matrices (`Tm`) at exact word anchors. Sibling `scan-raster-only.pdf` (no text layer) and `scan-shifted.pdf` (displaced layer) are provided. Renders are byte-identical with and without the invisible layer.

---

## Commands Executed During Independent Review

All checks were executed independently in `/Users/zubair/Code/Projects/pdf project/worktrees/review-t05`:

| Command | Exit Code | Observed Result |
|---|---|---|
| `python3 scripts/make_fixtures.py --check` | 0 | `check ok: 33 files in .../fixtures match deterministic regeneration` |
| `python3 -m unittest discover -s tests/fixtures -v` | 0 | `Ran 38 tests in 0.459s: OK` (38 passed, 0 failed, 0 skipped) |
| `python3 scripts/task_acceptance.py task T05` | 0 | 2 commands executed; 38 tests collected, 38 passed, 0 failed |
| `bun run verify` | 0 | 81 tests passing (49 bootstrap, 2 native-bootstrap, 30 coordination), self-check 16 commands |
| `shasum -a 256 scripts/make_fixtures.py` | 0 | `f64e98e88544705cbfcdfbc9333b08330ab689b12a840dfe96296f834aacfbce` (matches `manifest.json` `generator_sha256`) |

Observed test counts (38 collected, 38 passed) match `commands.log` and `receipt.json` exactly.

---

## Scope & Integrity Check

- **Allowed Deliverables:**
  - `fixtures/public/` (F01, F02, F07 PDFs and `.expect.json` files)
  - `fixtures/development/` (F08, F03 PDFs and `.expect.json` files)
  - `scripts/make_fixtures.py` (fixture generator)
  - `fixtures/manifest.json` (content-addressed manifest)
  - `tests/fixtures/test_fixtures.py` (TEST-05 suite)
  - `artifacts/tasks/T05/` (`receipt.json`, `handoff.json`, `commands.log`, `criteria-evidence.md`, `render-evidence/`)
- **Out-of-Scope Modifications:**
  - `config/acceptance-commands.json`: Activated `test:fixtures` with `["python3", "-m", "unittest", "discover", "-s", "tests/fixtures", "-v"]`. T05 is the designated `owner_task` for `test:fixtures`.
  - `tests/bootstrap/test_bootstrap.py`: Decoupled `test_declared_suite_with_no_implementation_fails` to use an isolated synthetic registry entry rather than pinning to `test:fixtures`.
  - `docs/proposals/T05.md`: Submitted formal change proposal documenting rationale, reproducer, and clean fallback.
- **Forbidden Boundaries:** No changes made to `planning/`, lockfiles, or other task source files. No unlicensed fonts or external proprietary data imported.
- **Scope Verdict:** **PASS** (proposal documented and justified).

---

## Criterion-by-Criterion Evaluation

### 1. Repeated generation is byte-identical or declared pinned asset-dependent
- **Status:** **SUBSTANTIATED**.
- **Audit Findings:**
  - `scripts/make_fixtures.py` is completely deterministic: fixed object ordering, zero creation timestamps, zero random document IDs, and custom PDF RunLength encoding instead of host-dependent zlib deflate.
  - Unit tests `test_two_regenerations_are_byte_identical`, `test_check_mode_passes_on_committed_tree`, and `test_check_mode_detects_tampering` confirm byte-identical reproducibility and active tamper detection.

### 2. mapping/control render equal under same environment and actual extraction differs
- **Status:** **SUBSTANTIATED**.
- **Audit Findings:**
  - `mapping-amount.pdf` and `mapping-control.pdf` share identical content streams (`test_paint_operators_are_identical`). Both render $100.
  - The ToUnicode CMap differs specifically at `<31>`: mapping-amount maps to `<0031002C0030>` ($1,000), whereas mapping-control maps to `<0031>` ($100).
  - Unit tests verify extraction intent metadata and structural stream equality.
  - Supplemental render evidence (`mapping-amount.pdf.png`, `mapping-control.pdf.png`) confirms byte-identical macOS QuickLook rendering. Real reader extraction is honestly bounded to T26/T27/G1 when readers land.

### 3. no filename-conditioned app output
- **Status:** **SUBSTANTIATED**.
- **Audit Findings:**
  - Unit test `test_filename_appears_nowhere_in_fixture_bytes` scans all 17 PDFs and confirms no filename or stem appears in the file bytes.
  - `test_renamed_copy_is_byte_identical_and_content_addressed` confirms renamed copies resolve identically via SHA-256 manifest lookups.

### 4. no embedded unlicensed font or private/challenge answer data
- **Status:** **SUBSTANTIATED**.
- **Audit Findings:**
  - Unit test `test_no_embedded_font_programs_anywhere` asserts no `/FontFile`, `/FontFile2`, `/FontFile3`, or `/FontDescriptor` dictionaries exist in any generated PDF. The only font referenced is standard BaseFont `/Helvetica`.
  - The scan raster is drawn directly using a self-contained 5x7 bitmap glyph table.
  - Unit test `test_no_private_or_challenge_answer_data` verifies decoded streams are free from private key armor, passwords, flags, or email indicators.
  - Unit test `test_manifest_rights_cover_every_entry` confirms MIT rights grant on all items.

### 5. F03 legitimate searchable scan minimum control present before G1
- **Status:** **SUBSTANTIATED**.
- **Audit Findings:**
  - `scan-correct.pdf` contains a 680x880 DeviceGray raster with an invisible (`3 Tr`) text layer placed with absolute text matrices (`Tm`) exactly matching raster word positions.
  - Accompanied by clean sibling `scan-raster-only.pdf` and displaced sibling `scan-shifted.pdf`.
  - Renders of `scan-correct` and `scan-raster-only` are byte-identical.
  - The requirement to read without an alarm is correctly deferred to integration with the readers in T26/T27/G1.

---

## Findings

1. **[INFO] Harmless traceback in commands.log snippet:**
   In `commands.log`, an inline regex parse of `/tmp/t05_task2.log` encountered `AttributeError: 'NoneType' object has no attribute 'group'` because `task_acceptance.py` outputs JSON. The actual command `python3 scripts/task_acceptance.py task T05` succeeded with exit 0, and our independent run confirmed clean execution and matching counts (38/38).
2. **[INFO] Cross-Task Registry Update:**
   The activation of `test:fixtures` in `config/acceptance-commands.json` and decoupling in `test_bootstrap.py` are clearly documented in `docs/proposals/T05.md`. The fallback (reverting `test:fixtures` to `argv: null`) is viable if the coordinator prefers root-manifest ownership, but the change is beneficial and preserves full `verify` suite health.

---

## Final Disposition

**Verdict: `approved`**

The delivery at `f30b870` satisfies all task requirements, respects non-negotiable invariants, adheres to honest evidence standards, and provides a dependable fixture foundation for Inkflip Pass 1.


---

## Delta review — 2026-09-13, evaluated `412fb9b2`

- **Reviewer:** devin-coordinator (acceptance refresh; not the implementing worker for this delta's shared changes)
- **Scope delta:** Owned scope delta: `scripts/make_fixtures.py` and the fixture suite changed
via merged `pdf-g78` (semantic catalog correction, `test_g78_semantic.py`), plus
`execution/overrides.json` now runs `tests/fixtures` under the pinned uv env
(the g78 suite needs `jsonschema`/`pypdfium2` absent from bare python). Verified:
deterministic `--check` regenerates 161 files byte-identically; 70/70 green.
- **Fresh run:** Re-ran all registered commands at `412fb9b2`: **70/70 green**, zero failures.
- **Verdict:** prior review stands; delta introduces no acceptance-relevant regression.
