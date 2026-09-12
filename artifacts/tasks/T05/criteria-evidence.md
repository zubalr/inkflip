# T05 criteria evidence map

Worker: zcode (zcode-t05) · branch `work/zcode/t05` · pass 1 · contract 1.0.0.
Every check below actually ran on this branch; see `commands.log` for the full
transcript (exact commands, exit codes, counts, host) and `receipt.json` for
the criterion → evidence binding.

## Criterion 1 — Repeated generation is byte-identical or declared pinned asset-dependent

Executed, via `scripts/make_fixtures.py` + `tests/fixtures/test_fixtures.py`:

- `test_two_regenerations_are_byte_identical` — two fresh generations into
  separate temp directories produce byte-identical trees (all 33 files).
- `test_check_mode_passes_on_committed_tree` — `make_fixtures.py --check`
  regenerates and byte-compares the committed `fixtures/` tree.
- `test_check_mode_detects_tampering` — a flipped byte in a committed PDF
  makes `--check` exit 1 (the check itself is real).
- `test_manifest_declares_determinism_without_seed_or_timestamp`.

Design note (measured decision): all streams avoid compression-codec
dependence. The F03 raster uses PDF RunLength filtering encoded by the
generator itself, so byte identity does not depend on the zlib/deflate build
of the host (zlib-ng vs zlib outputs differ; RLE removes that variable). All
entries are `byte-identical`; none needed the "pinned asset-dependent" escape.

## Criterion 2 — mapping/control render equal under same environment and actual extraction differs

Executed at fixture level:

- `test_paint_operators_are_identical` — mapping-amount and mapping-control
  content streams are byte-identical, so any correct renderer in the same
  environment paints equal marks.
- `test_tounicode_differs_exactly_at_amount_glyph` — the only difference
  between the two files is the ToUnicode CMap entry `<31>`:
  `<0031002C0030>` (mapping) vs `<0031>` (control). Extraction of the same
  painted `$100` therefore differs (`$1,000` vs `$100`) for any reader that
  honors ToUnicode; `extraction_intent` is recorded in both expectation
  files.
- Supplemental macOS-local render observation (QuickLook/PDFKit 400 px
  thumbnails, repeatable, archived under `render-evidence/`):
  mapping-amount.png == mapping-control.png byte-identical, and all four
  public `$100` pages render identical marks; ink-decode confirms non-blank.

Limitations (honest boundary): no PDF renderer or extractor is installed in
this checkout yet (dependency locks belong to T02; native readers are
T26/T27), so pixel rendering inside `tests/fixtures` and measured raw
extraction strings are not executed here. The macOS thumbnail observation is
environment-labeled and is not Linux or device evidence. Reader-side
confirmation lands with T26/T27 evidence and the G1 browser scenario, which
consume these fixtures and expectations.

## Criterion 3 — no filename-conditioned app output

Executed:

- `test_filename_appears_nowhere_in_fixture_bytes` — no fixture's name or
  stem occurs anywhere in its bytes, so the app cannot discover its own
  filename-conditional behavior from content.
- `test_renamed_copy_is_byte_identical_and_content_addressed` — a copy under
  an unrelated name is byte-identical, and manifest identity is content
  (SHA-256) addressed, so renamed documents resolve to the same fixture entry.

## Criterion 4 — no embedded unlicensed font or private/challenge answer data

Executed:

- `test_no_embedded_font_programs_anywhere` — across all 17 PDFs: no
  `/FontFile`, `/FontFile2`, `/FontFile3`, no `/FontDescriptor`; the only
  `/BaseFont` is Helvetica (base-14, no program embedded). The F03 raster is
  drawn by the generator's own 5×7 bitmap table; no font resource at all.
- `test_no_private_or_challenge_answer_data` — decoded stream content of
  every PDF contains none of: private key armor, password/secret markers,
  challenge-flag patterns, or any `@` address-like marker.
- `test_manifest_rights_cover_every_entry` — every manifest entry carries the
  rights statement (project MIT terms, no embedded font program, no
  third-party material).

## Criterion 5 — F03 legitimate searchable-scan minimum control present before G1

Executed (fixture side):

- `development/scan-correct.pdf`: owned 680×880 DeviceGray raster of an
  original printed page (generated 5×7 bitmap print; see
  `commands.log`/`receipt.json` for the legibility preview decision) plus a
  correctly positioned invisible layer (`3 Tr`), each word placed with an
  absolute `Tm` at the raster word anchors recorded in
  `development/scan-correct.expect.json`.
- Clean sibling `scan-raster-only.pdf` (no text operators at all) and
  displaced sibling `scan-shifted.pdf` (same words displaced +90,+72 pt),
  all in the same `development` split:
  `test_raster_only_sibling_has_no_text_operators`,
  `test_correct_layer_is_invisible_and_matches_expectation`,
  `test_layer_words_are_exactly_the_raster_words_in_order`,
  `test_decoded_raster_equals_generator_drawing`,
  `test_word_anchor_boxes_contain_matching_raster_ink`,
  `test_shifted_layer_is_displaced_by_declared_offset`,
  `test_scan_siblings_share_one_split`.
- `test_correct_scan_records_no_alarm_intent` — the manifest/expectation
  record the intended invariant "no alarm solely because its OCR text is
  invisible".
- macOS-local render check: scan-correct and scan-raster-only thumbnails are
  byte-identical — the invisible layer adds no visible marks.

Limitations (honest boundary): the "read without an alarm" outcome is realized
when the native/browser readers (T26/T27) and the G1 scenario process these
fixtures; fixtures and expectations are the control those readers consume.
This task executes no OCR and fabricates no reading.

## Registry and out-of-scope edits (for reviewer attention)

- `config/acceptance-commands.json`: `test:fixtures` activated with the
  harness-unittest argv, per that file's own delegation to the fixture owner;
  pinned by `test_test_fixtures_command_is_registered_and_active`.
- `tests/bootstrap/test_bootstrap.py` (T01-owned): one test decoupled from
  the `test:fixtures` lifecycle using the file's existing synthetic-registry
  pattern. Rationale and reproducer: `docs/proposals/T05.md`.
