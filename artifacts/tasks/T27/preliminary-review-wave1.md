# Independent Source Review — T27 (wave 1, preliminary)

**Task:** T27 — Implement native rendered-region Tesseract reader
**Beads Issue:** `pdf-t27`
**Candidate reviewed:** `c884b59fee2c470233a6ee0f9f2207cc2d21c6cb` (implementation `394e65c07be89e2a867b0b316fe46940f927dbf9`, evidence `ffe7313`), base `726d61c0c56bde92605e139edeb4e7c62df17a01`
**Reviewer:** `devin-swe-t27-wave1` — Devin Local SWE-2 subagent under coordinator Astra (independent source reviewer; not the worker `zcode-t27`)
**Review branch:** `review/devin/t27-wave1`
**Date:** 2026-09-12
**Contract version:** 1.0.0
**Platform:** Mac arm64 (macOS). **SOURCE REVIEW ONLY** — ZCode/Homebase holds the global heavy-OCR reservation; no tesseract/OCR/model-load or heavy raster work was run. Checks executed: full-file reads, contract/schema/invariant cross-reads, and small pure-python probes (module import, hashing, canned-TSV parse, a *stub* executable emitting canned TSV — no OCR engine involved).
**Verdict:** `changes-needed` — core design sound, all five contract criteria evidenced, but bounded correctness/identity fixes are required before final acceptance.

> File named `preliminary-review-wave1.md` because `artifacts/tasks/T27/peer-review.md` already exists in this task's evidence chain (Cloud partial review, commit `a3fff16` on `review/zcode/t27`, a direct child of this candidate). This file does not replace it; reconciliation is below.

---

## 1. Scope audit — PASS

`git diff --name-only 726d61c..c884b59`:

```
artifacts/tasks/T27/commands.log
artifacts/tasks/T27/handoff.json
artifacts/tasks/T27/receipt.json
native/inkflip/readers/tesseract.py
native/tests/ocr/test_ocr.py
```

All inside allowed scope (`native/inkflip/readers/tesseract.py`, `native/tests/ocr/`) plus task-local artifacts. `planning/`, `scripts/coordination.py`, `execution/overrides.json`, `prompts/` untouched; no lockfile/manifest/routing/golden changes. Matches the Cloud review's scope finding.

## 2. What I executed myself (no-OCR probes only)

| Probe | Result |
|---|---|
| `bun run verify` (stdlib registry: self-check, bootstrap, native-bootstrap, coordination — no OCR) | **exit 0** on this candidate (30+ coordination/bootstrap tests OK) |
| `uv run --frozen --project native` venv sync | CPython 3.13.15, Pillow 12.3.0, jsonschema 4.26.0 — lockfile honors `requires-python ==3.13.15` |
| `open_raster`/`plan_crop`/inverse math on a 200×100 PIL PNG | padding/clip/inverse math verified (§4) |
| `extract()` against a **stub** `bin/tesseract` (python script printing canned TSV, recording argv) | full emit path exercised: schema-valid Occurrences, page_index binding, typed terminals, tempdir cleanup — see findings |
| `model_digest`/`describe()` on a fake `share/tessdata` tree | exact-file SHA-256 returned; manifest schema-valid |
| Malformed-input matrix (region arities, hostile `CropPlan`) | raw crashes confirmed — findings F3/F4 |

No real tesseract invocation, no fixture renders, no model loads — per the heavy-OCR reservation.

## 3. Criteria assessment (contract `acceptance_criteria`)

| Criterion | Source evidence | Status |
|---|---|---|
| No URL or runtime model fetch | `tesseract.py` imports stdlib+PIL only; `model_digest` (:151-161) hashes on-disk traineddata; no network primitives | **met** |
| missing model/binary/unreadable page differ | missing binary → `unsupported` (:126-130); missing traineddata → `failed`/`missing_model` (:380-386, probe-confirmed); undecodable → `unreadable_pixels` at open (:241-245); timeout → `timeout` (:421-422) | **met** |
| malicious filename cannot become an option | argv fixed at :404-411, `shell=False`, neutral `input.png` in private `mkdtemp`; language regex :61/:153-154; probe argv exactly 6 elements | **met** |
| crop padding/resize inverses correct | :282-289 pad `max(8, ceil(10% h))` clipped; `crop_to_raster`/`raster_to_canonical` :110-119 are the documented inverse of `O = Scale(k)·Translate(-r)·P` (COORDINATES.md:30); probe: TSV (10,10,40,12) → canonical (26,21)-(46,27) at scale 2, correct | **met** |
| native OCR retains raw punctuation and all occurrences | level-5 rows verbatim (:329-331), `normalized_text`=raw + identity map (:467-476); probe retained `'$100'`, `'SYNTHETIC.'`, `'trans-'` | **met** |

The five criteria are substantiated by source + the worker suite (which the Cloud review reproduced 20/20 on Linux with `TESSDATA_PREFIX`).

## 4. Findings

### F1 — MEDIUM: `language` is validated and hashed but never reaches the engine

`tesseract.py:404-411` builds `argv = [binary, input_png, "stdout", "--psm", str(psm), "tsv"]` — **no `-l` element anywhere**. `extract(language="deu")` on a host with `deu.traineddata` present passes `model_digest` (probe: returned `sha256("deu-model-bytes")` for deu) and then runs tesseract's *implicit default language* (eng). Result: successful OCR in the wrong language while the recorded run context implies the deu model — an I13 identity mismatch, silent. Even for `eng`, the manifest declares `settings.language="eng"` while the engine selection is implicit default rather than pinned argv.
*Fix:* add `"--psm", str(psm), "-l", language, "tsv"` (language already regex-validated → single argv element, no injection), or reject `language != "eng"` explicitly until non-English is claimed. The first is preferred: it also pins eng against tesseract config/env drift.

### F2 — MEDIUM: `region_id` never inspected; a region-scoped CheckPlan silently runs full-page OCR

`extract()` reads `plan.get("region")` (:368) — a key the schema `CheckPlan` cannot carry (`additionalProperties: false`; the only schema region channel is `region_id`) — and never reads `region_id`. Probe: plan `{region_id: "some-region"}` with no `crop=` kwarg → `completed` with full-page occurrences, labeled as the region check's result. Sibling adapter `pdfium.py:336-341` explicitly refuses `region_id` plans it cannot serve. Coverage semantics (glossary: "coverage is the check results in the context of selected pages"; a region is "selected explicitly") are silently widened.
*Fix:* when `crop is None` and `plan.get("region_id")` is not None (and no resolvable region channel), return a typed terminal (e.g. `geometry_unavailable`/`unsupported`) instead of full-page OCR; or document/enforce that the parent always supplies `crop=` for region plans and drop the dead non-schema `plan["region"]` path.

### F3 — LOW-MEDIUM: malformed `plan["region"]` → raw `ValueError` crash, not a typed terminal

`extract()` wraps `plan_crop` in `except AdapterError` only (:370-373). Arity/type failures escape: probe — `region=[1,2,3]` → **raw `ValueError: not enough values to unpack`**; `(1,2,3,4,5)` → raw `ValueError`; `{"a":1}` → raw `ValueError`; `"ab"` → raw `ValueError`. (`[1.5,2,3,4]` is correctly typed `geometry_unavailable`.) I05 requires every planned check to reach a terminal result; an uncaught exception produces none.
*Fix:* validate region shape (`isinstance` of 4-sequence of ints) before unpacking, or catch `(TypeError, ValueError)` → `AdapterError("geometry_unavailable", ...)`.

### F4 — LOW: caller-built `CropPlan` bypasses all validation

`psm = crop.psm` (:374) trusts the dataclass; `plan_crop`'s `VALID_PSM` check (:269) only guards the built path. Probe: `CropPlan(psm="--tessdata-dir /etc")` → string lands as a **single** argv element (confirms Cloud's note — no option injection possible, but a bad value reaches the engine). `CropPlan(resize=(0.0,0.0))` → **raw `ZeroDivisionError`** inside the occurrence loop (`crop_to_raster` :113) — after partial emits. `padded` coordinates are also trusted (out-of-raster rects would just crop oddly).
*Fix:* re-validate `crop.psm ∈ VALID_PSM`, `resize` positive-finite, `padded ⊆ raster` at extract entry, or funnel construction through `plan_crop`.

### F5 — LOW: occurrence id omits `page_index`

`_occurrence_id` (:302-304) = `tesseract-native-<raster-digest12>-ocr-<ordinal>`; sibling `pdfium.py:300-302` includes `-p{page_index}-`. Two pages of one document rendering to byte-identical rasters (duplicated form/scan pages) yield identical occurrence ids across distinct CheckResults — I02 page binding survives via the `page_index` field, but id uniqueness does not.
*Fix:* include `plan["page_index"]` in the id, matching the sibling convention.

### F6 — LOW: raster pixel cap enforced after decode, not before allocation

`open_raster` (:241-247) calls `image.load()` **then** checks `width*height > MAX_RASTER_PIXELS` (40M). A 40–89Mpx PNG allocates full decode memory before `resource_limit`; PIL's own bomb guard (`MAX_IMAGE_PIXELS=89,478,485`, probe-confirmed) bounds the worst case above that. Input bytes are already held, so amplification is bounded — but the stated budget is post-allocation.
*Fix:* check `image.size` before `image.load()`.

### F7 — OBSERVATION: occurrence budget off-by-one

`if ordinal > MAX_WORD_OCCURRENCES` (:501) trips on the 5001st word — 5001 emitted under a "5000" cap. Trivial.

### F8 — OBSERVATION: unbounded `capture_output`

RUNTIME_LIFECYCLE.md:49 "Limit subprocess stdout/stderr"; the whole TSV is buffered in memory (:415). Practically bounded by raster size + the word cap only applies post-parse. Low risk; note for T29 supervision.

### F9 — OBSERVATION: cancellation cannot interrupt the blocking subprocess

`cancellation()` is polled pre-flight (:360) and per-occurrence (:436); during `subprocess.run` a cancel waits until child exit/`timeout_s` (default 120 s). Consistent with the contract's "parent enforces wall time / kills the process group" (T29) and the worker's recorded limitation. The in-adapter `timeout` kills only the direct child — no process-group kill — acceptable per contract division, restated here for the record.

### F10 — OBSERVATION: raster transform model is scale-only

`render_meta` carries `raster_scale_px_per_pt`; COORDINATES.md `P = Scale(s)·R·C` can include rotation `R`. A rotated named render cannot be represented — `transform_ids` record only `ocr-crop-inverse`/`raster-scale-inverse`. Fine if the named-render contract guarantees canonical-unrotated rasters; undocumented in-adapter. The recorded chain is otherwise reversible and honest (`estimated` precision, null polygon without scale — I04 preserved).

### F11 — LOW: `TESSDATA_PREFIX` precedence quirk (related to Cloud F1)

`_tessdata_dir` (:134-148) returns the first *existing* dir without checking the language file inside: a `TESSDATA_PREFIX` dir lacking `<lang>.traineddata` shadows a binary-relative dir that has it → `missing_model` despite a usable model. Same class as Cloud F1 (unresolved symlink parent). Both fixed by resolving `binary` and probing per-language, or by trying each candidate dir per language rather than first-dir-wins.

### F12 — LOW: tempdir/save I/O faults escape raw

`tempfile.mkdtemp` (:399) and `cropped.save` (:403) can raise `OSError` uncaught (disk full, perms) — finally still cleans, but the check gets a raw exception instead of a typed terminal. Wrap in the typed-error discipline.

## 5. What verified clean

- **Fixed argv / `shell=False`**: probe-recorded argv `['<stub>', '/…/inkflip-ocr-XXX/input.png', 'stdout', '--psm', '3', 'tsv']` — exactly 6 elements, private `mkdtemp` dir, neutral filename; dir removed in `finally` (no `inkflip-ocr-*` leftovers after probes).
- **Distinct terminals**: missing binary → `unsupported`; absent traineddata → `failed`/`missing_model`; stderr "Error opening data file" → `missing_model`; generic nonzero → `failed`/`parser_error`; undecodable → `unreadable_pixels`; closed handle → `failed`; non-ocr capability → `unsupported`; blank raster → `completed`/0 (suite); timeout → `timeout` (:421).
- **Geometry chain**: pad `max(8, ceil(10% region_h))` clipped at raster edges; `crop_to_raster` = `x/k + padded_origin`; `raster_to_canonical` = `/raster_scale`; probe numbers match the COORDINATES inverse chain; null polygon + `unknown` when no scale (I04); `-0.0` normalized via `+0.0` and 6-dp rounding (:444-447).
- **Raw retention (I03)**: verbatim TSV text incl. `'trans-'`/`'SYNTHETIC.'`/`'$100'`; `normalized_text`=raw with identity RawMap — honest (same convention as pdfium).
- **I02 binding**: `reader_id`, `page_index` (probe: plan page 3 → occurrences page 3), `ordinal`, precision on every occurrence; schema-valid objects.
- **I13**: manifest carries engine version line, adapter version, settings (language/psm/render_reader_id), `model_hashes` = actual local traineddata SHA-256; per-occurrence `raw_source_locator` records `psm{n}`. Except F1's non-eng edge.
- **I09/no network**: stdlib+PIL imports only; no URL/telemetry paths.
- **Chunking**: emits at 256 (:496-500), trailing partial chunk flushed (:508-511); retained ids tracked.
- **PSM discipline**: `VALID_PSM` allowlist; single-line regions → PSM 7 (probe argv `--psm 7`); per-invocation PSM recorded in locator; PSM-3-vs-6 deviation is documented as a measured decision (contract's PSM 6 prescription is in the Tesseract.js browser section — the native section prescribes only fixed argv, so this is a recorded divergence, not a contract violation).

## 6. Cloud partial review (`a3fff16`) reconciliation

| Cloud finding / step | Disposition | Evidence |
|---|---|---|
| Scope clean | **confirmed** | identical diff set (§1) |
| F1 — symlinked-PATH binary → tessdata probes wrong prefix; needs `TESSDATA_PREFIX` | **confirmed still open** (low) | `_tessdata_dir` :134-148 probes `binary.parent` without `.resolve()`; unchanged. See also my F11 precedence quirk. |
| F2 — T26 reader suite Linux failures (canonical-anchor drift) | **out of T27 scope — confirmed** | `native/tests/readers/test_readers.py` not in this diff; route to T46 parity; not re-run here (no renders). |
| Fixed argv, `shell=False`, private tempdir | **confirmed** | :399-420 + stub-recorded argv |
| Option injection structurally impossible; unchecked `CropPlan.psm` edge | **confirmed; still open** as input-validation gap (my F4) — single-element only, no injection | probe |
| Distinct failure terminals | **confirmed** | probe matrix (§5) |
| Crop padding/resize inverses | **confirmed** | probe math vs COORDINATES.md:30 |
| Raw retention, engine-score-as-diagnostic | **confirmed** | :329-331, :484-489, probe texts |
| No network | **confirmed** | imports audit |
| Process-group kill / atomic partial = T29 scope | **confirmed consistent**; adapter kills direct child only | :413-424; worker limitation recorded honestly |
| Worker's "PSM 6 drops `$100`, PSM 3/11 find it" measured decision | **still unverified** — requires real OCR; on Linux list below. (Suite asserts PSM-3 *finds* `$100` — that half is covered by the green suite; the PSM-6 absence claim has no test.) | — |
| Pending: `bun run test:native` | deferred — runs the OCR suite (heavy reservation) | Linux list |
| Pending: `task_acceptance.py task T27` | deferred — executes the OCR suite | Linux list |
| Pending: `bun run verify` | **executed by me: exit 0** | this review |

## 7. Evidence honesty assessment

- `receipt.json` criteria→evidence map to real files; details match source behavior (verified above). `commands.log` transcript plausible: 20/20 in 1.42 s consistent with Cloud's 2.38 s Linux reproduction.
- **Minor inaccuracy:** `commands.log` header records `python: Python 3.14.7` — the *host* interpreter; the suite actually ran under the pinned CPython 3.13.15 (`requires-python ==3.13.15`, confirmed by my `uv run --frozen` sync). `receipt.json`'s environment block is the accurate one.
- Handoff `recorded_at: "2026-09-13 (overnight handoff)"` vs commit timestamps 2026-09-12 (+0300) — trivial clock drift.
- Contract `evidence_artifacts` names `artifacts/tasks/T27/review.md`; convention + acceptance example use `peer-review.md` — naming drift only; neither exists on this candidate (Cloud's lives on `review/zcode/t27`).
- Worker's fixed-defect claim ("language param overwritten by hardcoded default") — **confirmed fixed**: `language` flows to `model_digest` (`:376`); but see F1 — it still never reaches argv.
- No fabricated claims detected; worker limitations (child-only kill, no Linux claim, eng-only) are honest and match source.

## 8. Verdict

**`changes-needed`** — preliminary source verdict on `c884b59`. The architecture is right (fixed argv, typed terminals, verbatim raw, recorded inverse chain, honest manifest) and all five contract criteria are evidenced — but F1 (`-l` never passed; non-eng model-hash/identity mismatch), F2 (`region_id` silently widened to full-page), F3/F4 (raw crashes on malformed region/caller CropPlan) are bounded fixes that belong in the worker's next candidate. F5–F8, F11, F12 are recommended in the same pass. None require re-architecture; all are testable without new contract surface.

## 9. Required final verification on the NEW candidate — Linux amd64, heavy-OCR slot

The source-level verdict above must be paired with this executed checklist (holder of the heavy reservation, or ZCode on its updated candidate):

1. `uv run --frozen --project native python -m pytest native/tests/ocr -q` — full TEST-27 on Linux amd64 with real tesseract 5.5.3; record counts.
2. **PSM sweep reproducer** (basis of the measured decision): render `fixtures/public/mapping-amount.pdf` at scale 3; run `tesseract in.png stdout --psm 6 tsv` vs `--psm 3` vs `--psm 11`; confirm `$100` absent under 6 and present under 3/11.
3. `uv run --frozen --project native python -m pytest native/tests -q` — whole native suite; confirm the Cloud-observed T26 geometry failures reproduce (or not) and route to T46.
4. `bun run test:native` and `python3 scripts/task_acceptance.py task T27` — real exits/counts.
5. `bun run verify`.
6. Failure-mode matrix on Linux: missing binary, missing traineddata, undecodable bytes, tiny `timeout_s`, blank raster — confirm the five distinct terminals.
7. F1/Cloud-F1 check: PATH-symlinked tesseract without `TESSDATA_PREFIX` → typed `missing_model` (or resolved if worker lands `.resolve()`/per-language probing).
8. Post-fix re-verification if the worker addresses F1–F4: argv carries `-l eng` (or non-eng rejected); `region_id` plan without `crop=` fails typed; malformed region → typed `geometry_unavailable`; caller `CropPlan` validated; occurrence id includes page index.
9. Process hygiene under timeout/cancel on Linux: no stray tesseract children; `inkflip-ocr-*` dirs removed.
10. Record the actual `eng.traineddata` SHA-256 used on the Linux host and compare with `planning/config/model-assets.json` pinned `7d4322bd…` (document which model serves, per parity manifest rules — the adapter already records whatever it hashes, which is I13-honest).
