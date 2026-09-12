# T27 wave-4 independent light review

**Verdict: source/light review approved on exact `e0e7d4c513832bd7fb23aac4f6f0822f2f1a6214` (source `2ea6233`). All three blocking wave-3 findings are resolved.** No new actionable source finding in this focused revision review. Final real-OCR verification and task acceptance remain pending; this is not approval of unexecuted checks.

Independent reviewer: Codex/Erdos (`01a093f7-2dea-78e3-80cc-c495153d946c`). Compared against `4eed963` / source `5ba110b`, previously reviewed in full on `1e7c8db`. Read current `pdf-t27` Beads grant and candidate guidance; repository coordination/contract documents and dependency locks are unchanged. Reviewed the complete revision diff in `native/inkflip/readers/tesseract.py` and `native/tests/ocr/test_ocr.py`, without repeating the unchanged-base full review.

The reviewer-owned Linux checkout `/home/wertyp/.local/share/homebase-factory/worktrees/inkflip/review-t27-wave3` was verified clean, fetched from the local relay, and safely fast-forwarded to exact `e0e7d4c`. It remains at that commit with no source changes. Existing pinned Linux environment: CPython 3.13.15, Pillow 12.3.0 and frozen native lock. No writer checkout, Beads writes, commits, pushes or service changes.

## Evidence resolving the findings

- **W3 TSV completeness/extents:** source lines **550–553, 578–581** now fail short rows and nonpositive word width/height with typed `parser_error`. Independently replayed five cases—short, zero width, zero height, negative width, negative height—each after **257 valid punctuated words**. Every case failed typed while retaining exactly 257 occurrences and ids. Registered regression tests also pass.
- **W3 typed boundaries:** lines **168–174** use bigint-safe bounded numeric comparison; **480–491** validate inverse shape/values before conversion; **675–680** narrowly map resize `MemoryError` to `resource_limit` and `OSError` to `unreadable_pixels`. Independent replay confirmed typed outcomes for inverse `42`, oversized matrix/resize/legacy-scale/inverse components (`10**309`), and both injected valid-resize faults. No raw TypeError/OverflowError/OSError escaped these cases; strict JSON serialization succeeded.
- **W3 F08 regression fidelity:** `test_f08_fiducial_all_four_rotations` now uses the actual F08 UserUnit-2 PDFium render, checks dimensions and fiducial ink, and compares all four emitted corners with independent closed-form expected coordinates at **0/90/180/270**. Its unchanged control passed. An in-memory mutant adding **10,000 pt to every emitted x/y** caused **four assertion failures in that test itself**, with zero errors. Preserved shear and odd-resize tests also killed the two-corner-bounding-box and requested-resize-factor mutants respectively. Mutations existed only in memory and were restored.

## Actual runs on this candidate

1. `PYTHONDONTWRITEBYTECODE=1 uv run --offline --frozen --project native python /tmp/inkflip-t27-wave4-logs/light.py "$PWD"`
   - Exact registered test selection recorded in `light.py` and `light.log`.
   - **58 discovered: 46 passed, 12 real-OCR tests deselected; 20 subtests passed; 0 failed/skipped; exit 0, 1.99 s.**
   - Runtime guard prohibited installed-engine OCR; the manifest's `--version` call was allowed. Stub executables were checked as scripts.
2. `PYTHONDONTWRITEBYTECODE=1 uv run --offline --frozen --project native python /tmp/inkflip-t27-wave4-logs/probes.py "$PWD"`
   - **13 independent failure-replay cases passed**, F08 control passed, and all three intended mutants were killed (F08 mutant failed all four rotation subtests). Exit 0. Real OCR was blocked in this runner too.

Raw logs/structured XML and exact hashes: `/private/tmp/inkflip-t27-wave4-logs/` (`light.log`, `light.xml`, `probes.log`, `setup.log`, `final-identity.log`). Reproducible runners: `/private/tmp/inkflip-t27-wave4-light.py` and `/private/tmp/inkflip-t27-wave4-probes.py`. Linux originals reside under `/tmp/inkflip-t27-wave4-logs/`.

**Historical versus current:** prior `1e7c8db` passed 52 real-suite OCR tests + 13 subtests, 105 native tests, registered T27 acceptance and 115 verify tests. Those results are historical, not fresh evidence for this revision. This light round did not execute real OCR, full-native, registered T27 acceptance, or rerun unchanged verify; the writer's current 115-verify result is not claimed as independently repeated here.

**Artifact correction only:** current `handoff.json:182–183` still describes source `5ba110b` and 52 collected tests; `:187` still describes scalar-authorized geometry. Update these to source `2ea6233`, 58 discovered / 46 light passed + 20 subtests / 12 real-OCR deselected, and matrix-only geometry. The top-level current limitation block correctly leaves heavy checks pending. These stale summaries are not source defects and do not reopen the resolved findings.

**Resource state:** no heavy reservation was acquired or used in this round; T10 SWE retains it. All light review commands have exited; this reviewer has no running or queued work. Proceed to final heavy verification only after the coordinator grants the reservation, then bind acceptance to the actual merged candidate and corrected evidence.
