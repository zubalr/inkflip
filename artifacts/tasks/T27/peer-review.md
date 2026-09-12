# Independent Peer Review — T27

**Task:** T27 — Implement native rendered-region Tesseract reader
**Beads Issue:** `pdf-t27`
**Candidate Commit Reviewed:** `c884b59fee2c470233a6ee0f9f2207cc2d21c6cb` (implementation `394e65c07be89e2a867b0b316fe46940f927dbf9`, evidence `ffe7313`) on `work/zcode/t27`
**Base Commit:** `726d61c0c56bde92605e139edeb4e7c62df17a01`
**Reviewer:** `devin-cloud-review-t27` (Devin Cloud session `devin-f540d598210843a795e3d38bd97c3079`, https://app.devin.ai/sessions/f540d598210843a795e3d38bd97c3079)
**Review Branch:** `review/zcode/t27`
**Date:** 2026-09-12
**Contract Version:** 1.0.0
**Platform:** Linux amd64 (Ubuntu 22.04.5 LTS, x86_64) — **not** the worker's macOS arm64 host; this run is itself useful T46-relevant parity evidence, though it does not claim Linux support
**Verdict:** `incomplete — run stopped`

> **STOP NOTICE:** This review was halted mid-run by coordinator order (Cloud quota; project transfers back to Devin Local + ZCode). Every result below was actually executed on this machine; unexecuted checks are marked NOT RUN. No verdict is fabricated — the candidate is **not approved** by this review.

---

## Scope & Boundary Audit (completed)

`git diff 726d61c..c884b59 --stat`:

```
 artifacts/tasks/T27/commands.log    |  29 ++
 artifacts/tasks/T27/handoff.json    |  69 +++++
 artifacts/tasks/T27/receipt.json    | 112 ++++++++
 native/inkflip/readers/tesseract.py | 514 ++++++++++++++++++++++++++++++++
 native/tests/ocr/test_ocr.py        | 356 +++++++++++++++++++++++++
 5 files changed, 1080 insertions(+)
```

- All changes inside allowed scope (`native/inkflip/readers/tesseract.py`, `native/tests/ocr/`, `artifacts/tasks/T27/` evidence). `planning/` untouched; no lockfile/manifest/routing changes.

## Environment setup actually executed (Linux amd64)

- Node v22.23.2, Bun 1.4.0, uv 0.12.13, Python 3.13.15 — all pinned tarballs, checksums verified, versions confirmed.
- Tesseract 5.5.3 built from source per assignment (`tesseract --version` → 5.5.3, leptonica-1.82.0); `eng.traineddata` (tessdata_fast) placed at `~/toolchains/tesseract-install/share/tessdata/`.
- `bun install --frozen-lockfile` OK; `uv sync --frozen --project native` OK (pillow 12.3.0, pypdfium2 5.8.0, pytest 9.1.1, jsonschema).

## Reproduction — commands actually executed

| Command | Exit | Result |
|---|---|---|
| `uv run --frozen --project native python -m pytest native/tests/ocr -q` (no `TESSDATA_PREFIX`) | 1 | 10 passed / **10 failed** — see F1 |
| same, with `TESSDATA_PREFIX=~/toolchains/tesseract-install/share/tessdata` | **0** | **20 passed** in 2.38s — matches worker's claim |
| `uv run --frozen --project native python -m pytest native/tests -q` (with `TESSDATA_PREFIX`) | 1 | **72 passed, 5 failed, 122 subtests passed** — all 5 failures are in `native/tests/readers/test_readers.py` (T26 scope, PDFium geometry); all 20 T27 OCR tests passed within this run |
| `bun run test:native` | NOT RUN | run stopped before execution |
| `python3 scripts/task_acceptance.py task T27` | NOT RUN | run stopped before execution |
| `bun run verify` | NOT RUN | run stopped before execution |

### F1 — tessdata resolution requires `TESSDATA_PREFIX` under a PATH-symlinked binary (observed, low)

`shutil.which("tesseract")` returns the unresolved PATH entry (`~/.local/bin/tesseract`, a symlink into the install prefix). `_tessdata_dir` then probes `~/.local/share/tessdata` and `~/.local/bin/tessdata` — both absent — so `model_digest` reports the model missing and every extraction run fails typed as `missing_model`. Setting `TESSDATA_PREFIX` (the documented escape hatch) yields 20/20. On the worker's Homebrew install the layout resolves without it. Design is per contract ("located on disk next to the binary (or via TESSDATA_PREFIX)"), but a `Path.resolve()` on the binary would have made the symlinked-PATH layout work out of the box; failure mode is at least honest (typed `missing_model`, never silently wrong).

### F2 — T26 reader suite fails on this Linux host (out of T27 scope, material for T46)

`test_rotations_store_identical_canonical_anchors` and `test_userunit_scales_exactly_once` (subtests userunit 0.5/1/2/10) in `native/tests/readers/test_readers.py` fail with canonical-anchor drift (e.g. `249.280029 != 253.12`, `1346.400146 != 1365.6`). These are T26 (PDFium text reader) assertions, unchanged by this candidate — recorded here only as platform-parity evidence for the Linux-support task (T46), not as a T27 defect.

## Code inspection (complete read of `tesseract.py`, `test_ocr.py`, contract + invariants)

Verified by inspection before the stop (not yet independently re-executed beyond the suite above):

- **Fixed argv, no shell:** `subprocess.run([binary, <mkdtemp>/input.png, "stdout", "--psm", str(psm), "tsv"], shell=False)`; caller never names a file; temp dir is adapter-generated and removed in `finally`. A spied-argv test asserts the exact 6-element argv.
- **Option injection:** language validated against `^[a-z0-9_-]{1,32}$` inside `model_digest`; `psm` restricted to `VALID_PSM` ints in `plan_crop`; every variable field stays a single argv element — injection is structurally impossible. NOTE (unverified edge): `extract()` accepts a caller-built `CropPlan` whose `psm` is not re-validated; a hostile non-int `psm` would still be a single `--psm` value argument (cannot create argv elements), so the impact is a bad PSM value, not option injection.
- **Distinct failures:** missing binary → `unsupported`; missing traineddata → `failed`/`missing_model`; undecodable bytes → `unreadable_pixels` at open; wall-time overrun → `timeout` (subprocess timeout kills the child); blank raster → `completed` with zero occurrences. All exercised by tests and reproduced.
- **Crop inverses:** padding = max(8px, ceil(10% region height)) clipped to raster; `crop_to_raster` = `x/kx + padded_origin`, `raster_to_canonical` = `/raster_scale`; tested including resize (2,2) halving and edge clipping.
- **Raw retention:** TSV level-5 rows emitted verbatim (`normalized_text` = raw, identity map), engine confidence as diagnostic `EngineScore`; F03 scan-correct vs scan-raster-only produce identical word sequences (pixel-only independence); PSM recorded per occurrence via `raw_source_locator` `psm{n}` tag.
- **No network:** imports are stdlib+PIL only (hashlib/subprocess/tempfile/…); model hashed from disk, never fetched.
- **Contract division of labor:** parent-side process-group kill and partial-result atomicity are correctly left to T29; in-adapter `subprocess.run(timeout=)` kills the direct child only — consistent with the contract's "the parent enforces wall time" wording and recorded in worker limitations.
- **Worker's PSM-6-drops-'$100' justification:** plausible and consistently recorded in code comment, receipt and commands.log, but I did NOT independently re-run the PSM sweep before the stop — flagged as the top remaining verification.

## Not completed / next steps to finish this review

1. Re-run the three remaining commands and record real exits/counts: `bun run test:native`, `python3 scripts/task_acceptance.py task T27`, `bun run verify`.
2. Independently verify the measured decision: render `fixtures/public/mapping-amount.pdf` at scale 3 and run `tesseract out.png stdout --psm 6 tsv` vs `--psm 3 tsv`; confirm `$100` present under 3 and absent under 6.
3. Decide severity/disposition on F1 (symlinked-binary tessdata resolution) and the unchecked `CropPlan.psm` passthrough — both currently look like observations, not blockers.
4. Route F2 (T26 Linux geometry failures) to the coordinator/T46 as parity evidence; confirm it reproduces on the integration host.
5. Only then replace this verdict with `approved`/`changes_requested`.

## Verdict

**`incomplete — run stopped`**

Partial evidence above is real and points positive (contract suite 20/20 green on Linux amd64 with `TESSDATA_PREFIX`; scope clean; no injection/network paths found by inspection), but three required commands and the PSM-sweep spot-check were not run. The coordinator should treat T27 as **still in review**.
