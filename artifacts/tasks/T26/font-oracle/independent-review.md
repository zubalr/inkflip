# Independent review: pdf-932

Verdict: **approved**. No actionable findings.

Reviewer: Codex independent reviewer, separate from implementation worker Volta. Reviewed 2026-09-12.
Candidate: `e3fc0b616786c7d9612ac852ee16bf3a78342c67`.
Base: `65e84da4ae25c6f292ef265ed5b0d69c7982a824`.
Checkout: `/Users/zubair/Code/Projects/pdf project/worktrees/pdf-932`.
Scope: exact `git diff 65e84da e3fc0b616786c7d9612ac852ee16bf3a78342c67`; checkout HEAD matches candidate and status was clean before and after verification.

Read canonical AGENTS.md, docs/HOMEBASE.md, docs/NATIVE_PASSES.md, project brief and glossary/invariants, and the code-review skill. Read the supplied root diagnosis and all candidate proof logs and mutation_probe.py; inspected the actual adapter, fixture generator, and installed pinned pypdfium2 get_charbox implementation.

The only existing file changed is native/tests/readers/test_readers.py. The other nine files are new font-oracle evidence artifacts. Product source, fixtures, contracts/schema, dependencies, and baselines are unchanged.

The oracle is independent of adapter geometry: raw_dollar_box opens the fixture directly with PdfDocument, locates the dollar via the engine text API, and obtains loose bounds through FPDFText_GetLooseCharBox. It does not call adapter metadata, extraction, transform, or polygon helpers. Expected coordinates use independently specified fixture constants: crop [20,40,500,390] with unit 2 for rotations, and [0,0,520,400] with the four declared units for scaling. The generator confirms those boxes, baseline 220, origin x=48 and unembedded Helvetica. The helper closes textpage, page and document.

Both coordinates of all four corners are asserted, with an explicit polygon length check. Rotation equality, fixed x anchors, and physical dimensions remain. Tolerances remain 1e-3 for rotation and 1e-2 times UserUnit for scaling. Replacing a substitute-font-dependent numeric y anchor with observed raw engine bounds is appropriate for this adapter conversion test; it does not broaden tolerances or remove coordinate coverage. The supplied causal font diagnosis is consistent with the inspected fixture and pinned API, the Linux failure deltas, and fresh Mac bounds.

Fresh reviewer verification on Mac, using the worktree's existing native/.venv and PYTHONDONTWRITEBYTECODE=1:

- `native/.venv/bin/python -m pytest native/tests/readers -q -p no:cacheprovider`: **22 passed, 10 subtests passed** (0.34 s).
- `native/.venv/bin/python artifacts/tasks/T26/font-oracle/mutation_probe.py`: baseline passes; double UserUnit, reversed y axis, omitted crop x translation, and last-corner-only shift each fail through assertions, with no errors. Counts reproduce 4, 5, 1 and 5 respectively.
- Additional process-local reviewer mutations shifted each of the eight corner coordinates independently by 1; every mutation caused 5 assertion failures and no errors. Replacing crop-top translation with 400 times UserUnit caused 1 assertion failure and no errors. These independently confirm coverage beyond the worker's single last-corner perturbation.
- Verified all eight entries in checksums.json against actual file bytes.
- `git diff --check 65e84da e3fc0b6`: passed.

The mutation probe rejects unexpected errors, requires both test methods to run, and requires a passing baseline and assertion failures for mutations. Its patches affect adapter functions only, leaving raw-box acquisition and fixture math independent.

Limits: Linux execution was not repeated; reviewed its checksum-bound original/fixed/mutation logs, which record the expected five original font-oracle failures and a passing fixed suite. The earlier causal Mac font intervention was reviewed rather than rerun. This review establishes adapter-coordinate test correctness, not universal font metrics or rendering determinism. No heavy OCR/full native suite was needed or run. No source, Beads, GitHub, or service changes were made; only this requested review file was written.
