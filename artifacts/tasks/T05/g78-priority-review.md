# Independent review — g78-priority integration candidate (consumer half)

Verdict: **approved** for the consumer-changes half of this candidate. The
ten fixture families themselves were already independently approved at
fixture level (`911367c`, candidate `fd822d9`); this review covers the
consumer assertions, generator additions, merge cleanliness and scope only.
It is not acceptance or closure of pdf-g78, T05, T09, T26 or any gate.

Reviewer: Devin Local SWE-2 independent reviewer (read-only), sole reviewer on
`review/devin-g78-priority`. No delegates, no source edits, no Beads writes.

Exact candidate reviewed: `485147fa1d6dfdd9bfe9ec227980450bb358b19b` (HEAD of
`review/devin/g78-priority`, worktree
`/Users/zubair/Code/Projects/pdf project/worktrees/review-devin-g78-priority`).
Branch-side delta measured from merge-base `8f6cc3c` (three-dot); claimed main
reference `546accd` confirmed as a main-side descendant of the same base.

## Reproduced checks (fresh, this checkout)

Environment: no `node_modules`/venv present at start; ran
`bun install --frozen-lockfile` (v1.4.0, 86 packages, lockfile resolved clean).
`uv run --frozen` created `native/.venv` itself (CPython 3.13.15, 13 packages).

| Command | Claimed | Reproduced |
| --- | --- | --- |
| `python3 scripts/task_acceptance.py run test:browser tests/readers/pdfjs.spec.ts` (= `bun x --no-install playwright test …`) | 10 passed (`artifacts/tasks/T09/fixture-integration/consumer-tests.log`) | **10 passed** in 3.5–4.3s, exit 0, @playwright/test 1.57.0, real Chromium |
| `uv run --frozen --project native python -m pytest native/tests/readers -q` | 22 passed + 13 subtests (`artifacts/tasks/T26/fixture-integration/consumer-tests-final.log`) | **22 passed, 13 subtests passed**, exit 0, 3.15s |
| `python3 -m unittest discover -s tests/fixtures -v` (registered `test:fixtures`) | 50 passed (registered-tests.log) | **50 tests, OK**, exit 0 (38 `test_fixtures` + 12 `test_catalog_followup`) |

The committed `consumer-tests-initial.json` also honestly records the
candidate's own intermediate failure (PdfPage misused as a context manager,
3 subfailures) and its repair via `contextlib.closing` — good provenance, not
concealed.

## Consumer assertions — faithful, not shallow

`tests/readers/pdfjs.spec.ts:837` (F10/F11 test) replaces the old
absence-check (which asserted `mapping-missing.pdf`/`duplicates.pdf` were
*missing* and only ran a synthetic `occurrenceId` unit check — the committed
`prior-coverage-gap.json` documents this gap). The new test:

- fetches all five committed F10/F11 bytes over the harness's `/fixtures/`
  route (real bytes, `development/` split served at `pdfjs.spec.ts:125-132`);
- drives the real adapter open→plan→extract→close per file;
- compares adapter `raw_text` sequence **verbatim** to an independent direct
  `pdfjs.getDocument().getTextContent({disableNormalization:true})` read of
  the same bytes (`spec.ts:856-857`, `:866`);
- asserts byte immutability (sha before == after, `:865` — I01), sequential
  ordinals (`:867` — I02), and `status === 'completed'` per file;
- F11: control yields exactly 1 `$100`; `duplicates-four` yields 4 with
  distinct ids, ordinals **and** polygons, all `precision === 'estimated'`
  (`:869-878` — I02/I04).

`native/tests/readers/test_readers.py` edits are strictly stronger:

- `test_missing_mapping_output_passes_through_unchanged` (`:263-277`): one
  inline-generated PDF → three committed variants
  (control/absent/malformed) under `subTest`, still asserting adapter joined
  raw text == independent `pypdfium2` `get_text_range` verbatim;
- `test_duplicate_occurrences_keep_distinct_boxes_and_ordinals`
  (`:279-289`): inline-generated PDF → committed `duplicates-four.pdf`;
  all original assertions kept (4 `$` occurrences, 4 distinct polygons,
  distinct ordinals, schema-validated occurrences).

No existing assertion was weakened anywhere in the delta. The only removed
assertions are the obsolete absence-checks that the fixtures now falsify by
existing — replaced with real-byte coverage of the same mechanisms.

## Generator additions — deterministic, rights-clean, manifest-consistent

`scripts/make_fixtures.py` (+213): additive only. `pdf()` gains an optional
`trailer` parameter (backward compatible); new `fixed_page`/`fixed_text`/
`rc4`/`encrypted_page`/`raster_page`/`catalog_entry` plus per-family entry
builders and `followup_entries()` wiring. Determinism verified, not assumed:
`test_two_regenerations_are_byte_identical` and
`test_check_mode_passes_on_committed_tree` (full byte-exact regeneration of
all 91 files) pass in the rerun above. No timestamps, random IDs or seeds —
`rc4`/`encrypted_page` use fixed md5/sha256 inputs; the F17 noise pattern is
a closed-form generator.

Manifest consistency verified independently: 45 entries (29 new `g78.1`
recipes, 16 frozen originals); `generator_sha256` and new `catalog_sha256`
both match live file hashes; the only manifest deletion is the stale
generator hash line. All original 32 payload/expectation files remain
byte-identical (re-verified by `test_original_pdfs_and_expectations_are_unchanged`
against `baseline-hashes.json`, itself Git-verified by the prior fixture
review). Control graph, splits, rights strings and expectation binding are
suite-enforced and pass.

Rights: all new bytes are original synthetic material; F18 implements Adobe
PDF Reference 1.7 §3.1–3.5 R2 as an original implementation (no copied code)
documented in `docs/FIXTURE_RIGHTS-g78.md:9-14`; unembedded base-14
Helvetica only; no fonts/private data (suite-enforced). No scope creep in
the generator — every new function serves a cataloged family.

`tests/fixtures/fault_double.py` is a bounded F20 child: no reader imports,
no models, self-terminates ≤2s even unparented; `test_catalog_followup.py`
actually launches it per variant with shorter deadlines and reaps children
(`TestFaultDoubles`), plus byte-level generator-intent assertions for all
ten families. `test_fixtures.py` changes derive splits/families from the
frozen catalog — an expansion of coverage (5 → 14 ids), not a weakening.

## Merge cleanliness vs `546accd`

`git merge-tree --write-tree 546accd HEAD` exits 0, zero conflicts. Zero
overlapping files between the two sides (`comm` on name-only diffs): the
branch touches only fixtures/tests/generator/docs/artifacts, while main-side
commits touch prompts/, coordination tests, Beads records and pass docs.
`git diff --check` clean; no `.beads` paths in the branch delta.

## Scope

Branch delta outside `fixtures/`, `tests/`, `native/tests/`,
`scripts/make_fixtures.py` and `artifacts/`: exactly two documentation files
— `docs/FIXTURE_RIGHTS-g78.md` (provenance) and `docs/proposals/T05-g78.md`
(checkpoint proposal). No production source (`native/inkflip/`, `packages/`,
`apps/`), no shared contracts/schema, no `planning/` mutations
(fixture-catalog.json is only *read*), no acceptance-command or registry
edits.

## Findings

- **F1 (low, cosmetic)** — `native/tests/readers/test_readers.py:41-47`:
  `load_generator()` is now dead code; both former callers switched to
  committed fixtures. Harmless leftover helper; remove opportunistically.
- **F2 (low, consistency)** — `docs/ATTRIBUTION.md` has no T05/g78 entry.
  The F18 encryption recipe's named influence (Adobe PDF Reference 1.7) is
  retained in `docs/FIXTURE_RIGHTS-g78.md:9-14`, which satisfies I16's
  "name material influences" requirement, and no third-party code/text was
  copied — so an ATTRIBUTION line is not strictly required. A short entry
  would match the T12 precedent (which logged "original implementation,
  standard techniques" explicitly). Non-blocking.
- **F3 (info, environment)** — my Playwright runs report different source
  line numbers than the committed `consumer-tests.log` (e.g. test 1 at
  `:166` vs logged `:184`; F10/F11 at `:929` vs `:837`), while test names,
  order, count (10) and pass result match exactly, and the committed log's
  numbers match the actual source lines precisely. Attributed to local
  transform/source-map environment differences under `bun x`; the committed
  evidence remains self-consistent and genuine. No action needed.

## Not verified (explicit)

- The ten fixture families' internal correctness, rendered evidence and
  reader observations — independently reviewed already (`911367c`/
  `independent-review.md`); I relied on that verdict plus suite reruns.
- OCR/Tesseract paths, native corpus/regression, full `test:browser` suite
  beyond this spec, other spec files, Poppler (historical timeout only),
  Linux-arm64/amd64 behavior, held-out labels, G1+ gates, and the consumer
  halves for F04–F09/F12–F26 families (out of this checkpoint's scope —
  only F10/F11 consumers were claimed, and verified).
- Consumer coverage for F20 in a production supervisor: the double and its
  scenario JSONs are verified; the consuming supervisor is a separate task,
  as the proposal itself states.
