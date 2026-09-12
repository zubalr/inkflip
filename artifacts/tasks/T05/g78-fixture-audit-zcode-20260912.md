# pdf-g78 fixture audit — ZCode (read-only), 2026-09-12

Grant: Devin note on `pdf-g78` (audit-only during the frozen G1 batch).
Scope honored: **no writes to `fixtures/`, `scripts/`, or any manifest**; no
Beads writes; this note is the deliverable, returned via the `hb/inkflip/g78`
handoff branch. Base inspected: main `aa6d039` (T28 accepted, g78-priority
merged at f83a2d4).

## 1. Inventory — catalog vs fixtures/manifest.json

`planning/quality/fixture-catalog.json` specifies **26 families**.
`fixtures/manifest.json` currently carries **15 families / 51 files**:

- Present: F01, F02, F03, F04, F05, F06, F07, F08, F10, F11, F17, F18, F19,
  F20, F21 (the original F01–F03/F07/F08 generator output plus the ten
  priority families landed from `integrate/g78-priority` 485147fa).
- **Missing (11): F09, F12, F13, F14, F15, F16, F22, F23, F24, F25, F26.**

The preserved codex record `911367c` (reachable locally) contains the
independent review/probe artifacts for the ten landed families
(`artifacts/tasks/T05/followup-g78/`), but the generator branch holding
recipes for the remaining 11 (`work/codex/pdf-g78` worktree on the Mac) is
**not on the Homebase relay** — only `origin/work/codex/*` refs exist there
and none is pdf-g78. Either publish that branch first (cheapest: its recipes
are already written and reviewed for generation correctness) or regenerate
from the plan below; do not do both blindly.

### Data-quality finding (catalog, T05-owner/coordinator lane)

`F22.status` is `"22 invalid examples generated"` and `F23.status` is
`"contract examples generated"` — both look like corrupted concatenations
(the grant's own phrasing "marked 'examples generated'" reflects this). The
status vocabularies elsewhere are `specified` / `generated; native
executed` / similar. Recommend the catalog owner correct these two status
values in the planning lane before or alongside generation, so
manifest/catalog status audits do not keep flagging phantom mismatches
(both families are absent from the manifest despite "generated" statuses).

## 2. Family → unblocked accepted-task limitations

| Family | Mechanism (catalog) | Unblocks |
| --- | --- | --- |
| F09 | skew/rotated text matrices, crosshair controls | T04/T09 rotated-text quad coverage (COORDINATES "text skew requires transformed quads; bounding an unrotated rectangle first is wrong"); no accepted-task receipt names F09 — it hardens the T09/T26 geometry claims |
| F10, F11 | mapping-missing, duplicates | **T09 accepted w/ limitation** (absence-asserting tests + docs/proposals/T09.md) — families already landed; T09 receipt revalidation can now flip those tests to real coverage |
| F12 | two columns, reordered stream | T12 TEST-12 synthetic-construction limitation (receipt: "Occurrence inputs in TEST-12 are synthetic constructions per F11–F15 dimension descriptions"); reading-order comparison (T13 family) |
| F13 | ligatures, combining sequences | T12 limitation (as above); exercises T26's glyph-to-Unicode multi-scalar coalescing against real font-backed text |
| F14 | Arabic/CJK/emoji native strings | T12 limitation; T26 unicode-preservation row; T27's printed-English-only OCR boundary keeps F14 with native text readers |
| F15 | digit/punctuation/sign/negation ambiguity, seeded raster noise | **T27 accepted limitation** ("F15 … remain catalog 'specified'"); T12 limitation |
| F16 | adjacent amounts, clipped glyph, wrong-neighbor rejection | T27/OCR region-selection wrong-neighbor criterion (receipt: F16 not named, but the check consumes crops generically); strengthens crop/padding suites |
| F17–F21 | unreadable/bad-pdf/huge-page/worker-fault/canary | **landed** — unblocks T08 (F17/F18/F19/F21) and T29 (F17–F21) supervisor/fault suites; F20 also closes T27's recorded "F20 worker faults … specified" half |
| F22 | import-security hostile variants | T22 receipt limitation: "F24/F25/F26 are specified-not-generated … exercised through constructed variants" (T21/T22 import path) |
| F23 | baseline-misuse mutated reports | T22 limitation (same line); T22/T23 regression-baseline rule coverage |
| F24 | invisible span intersecting visible border | T22 limitation line (F24/F25/F26); **T16 needs F24** per grant; direct evidence for T28's I06 "ink-in-box does not prove glyph visibility" boundary |
| F25 | static annotation appearance vs actions/XFA | T22 limitation line (F25); **T16 needs F25** per grant; annotation_mode records |
| F26 | corrupt model, stale worker/core, offline cache | T22 limitation line (F26); T02/native asset-pipeline fault injection |

Net effect: after the ten-family landing, the still-open
accepted-task limitation set is exactly **T12 (F12–F15 synthetic
constructions), T22 (F24/F25/F26 constructed variants), T16 (F24/F25 per
grant), T27 (F15 half; F20 half already closed)** — plus the
proposals-based T09 pattern, whose F10/F11 blockers are already gone.

## 3. Concrete generation plan for `scripts/make_fixtures.py`

The generator already provides the right idioms: `pdf()` object assembly,
`fixed_page()`/`fixed_text()` content helpers, `catalog_entry()`,
`recipes()` registry, `expectation_for()` expectation emission, and the
determinism rule (no timestamps/random IDs; F15's raster noise must use a
fixed seed and document it). Recommended addition order follows consumer
need (T12 → T22 → T16 → T27 → hardening):

1. **F09 text-transform** (`skew_pdf()`): two pages — control with
   `1 0 0 1 48 120 Tm` and skewed `0.9 0.25 0 1 48 120 Tm` (plus a 90°
   matrix variant) drawing `(S1,234)` and registration crosshair lines.
   Expectations: per-object matrices and crosshair anchors, so quad
   consumers must apply the full transform (kills axis-only bbox logic).
2. **F12 reading-order** (`columns_pdf(order)`): one function, two calls —
   control emits left-column then right-column text; variant emits
   right-then-left with identical visual coordinates. Expectation: stream
   order vs visual order recorded separately; explicit "no accessibility
   verdict" note.
3. **F13 ligatures** (`ligature_pdf()`): use a font program with an fi/fl
   ligature if rights allow, else synthesize a ToUnicode CMap mapping one
   code to `fi` (multi-scalar) next to a literal `fi` control. Expectation:
   raw values and normalization maps preserved verbatim.
4. **F14 native-unicode** (`unicode_pdf()`): requires a rights-cleared font
   with Arabic/CJK coverage (catalog rights line). Emit RTL Arabic, CJK
   sentence and emoji runs plus a Latin control; expectation records logical
   values and conservative (unknown-precision) geometry.
5. **F15 ocr-material** (`ocr_material_raster(seed)`): render fixed strings
   with seeded noise/blur operators into the 5x7-style bitmap rasterer used
   by F03 (deterministic PRNG with pinned seed in the generator);
   siblings: clean raster, digit-ambiguous, sign/negation-ambiguous.
   Expectation: OCR may misread; tests assert non-normalization.
6. **F16 adjacent-crop** (`adjacent_pdf()`): two amounts 8 px apart plus a
   half-clipped glyph row; control with correctly scoped crop rectangle.
   Expectation: recorded crop rects and glyph extents so wrong-neighbor
   selection is rejectable.
7. **F22 import-security** (`import_security_payloads()`): JSON variants —
   unknown top-level key, wrong digest, `<script>` in a string field,
   oversized PNG header bytes — plus a valid report control. These are
   `.json` payloads like F20's (generator already emits JSON entries).
   Expectation: each names the rejection reason the importer must produce.
8. **F23 baseline-misuse** (`baseline_misuse_variants()`): take a canonical
   stored report and produce three mutations — dropped check (coverage
   loss), swapped document digest, silently refreshed baseline values —
   plus the identical-run control. Expectation: each must NOT improve.
9. **F24 overlap-ink** (`overlap_pdf()`): invisible-mode text (`3 Tr`)
   whose box crosses a stroked border rectangle; control with visible-mode
   text at the same position. Expectation: mode + geometry facts only
   (mirrors T28's no-verdict discipline).
10. **F25 annotation-mode** (`annotation_pdf()`): page with a static
    appearance-stream annotation and an inert widget referencing an
    unsupported form type; plain-page control. Expectation: annotation_mode
    records and unsupported-form labeling.
11. **F26 asset-cache** (`asset_cache_faults()`): manifest/cache fault
    fixtures — corrupt model file, stale worker/core digests, offline
    cold/warm cache states — as JSON entries like F20/F22, plus the
    verified-complete cache control. Expectation: no silent fallback/CDN.

Sequencing proposal: land F12+F13+F14+F15 (T12/T26/T27 unblocking) and
F22+F23+F26 (T22) in one generator batch with their expectation files;
F09+F16+F24+F25 in a second batch (geometry/annotation). Every batch ends
with `fixtures/manifest.json` regenerated by the generator itself, then
absence-asserting tests in T09/T12/T22/T28 suites flip to real coverage in
the owning tasks' lanes.

## 4. Verification boundaries honored

This audit read `planning/quality/fixture-catalog.json`,
`fixtures/manifest.json`, `scripts/make_fixtures.py` (family surface),
task receipts (T04/T05/T08/T09/T12/T16-era grant notes/T22/T26/T27/T28/T29)
and the locally reachable g78 record commits. Nothing was written to
`fixtures/`, `scripts/`, manifests, or Beads.

— zcode-t28 worker, Homebase (via existing Goal, Devin coordination)
