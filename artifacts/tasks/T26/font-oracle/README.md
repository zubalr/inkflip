# pdf-932: portable PDFium geometry assertions

Worker: Astra (Codex independent diagnostic worker), 2026-09-12.
Base: `65e84da4ae25c6f292ef265ed5b0d69c7982a824`.
Branch: `work/codex/pdf-932`. Parent owns Beads and acceptance; independent review is pending.

The reader tests assumed that unembedded Helvetica always has a raw loose-box top of 263.44. Diagnosis showed Arial on Mac and Chrom Sans OTF on Homebase. A scratch Mac process with system font lookup disabled reproduced the Linux font hash and raw bounds exactly. The adapter already transforms those bounds correctly.

The correction reads the dollar box directly through PDFium, then computes all four expected corners from the fixture's known crop and UserUnit constants. It never uses adapter transforms to compute expectations. Rotation equality, physical dimensions, independent x anchors, and original tolerances remain. No runtime, fixture, dependency, schema, or baseline changes are included.

The pinned pypdfium2 5.8.0 implementation of `get_charbox(loose=True)` calls `FPDFText_GetLooseCharBox`. [PDFium's chromium/7825 GetLooseBounds implementation](https://pdfium.googlesource.com/pdfium/+/refs/heads/chromium/7825/core/fpdftext/cpdf_textpage.cpp) derives vertical bounds from font ascent/descent and font size. Its source was inspected during diagnosis. [pypdfium2's font documentation](https://pypdfium2.readthedocs.io/en/stable/python_api.html) describes Standard 14 font substitution. These assertions test adapter conversion of observed engine geometry, not a universal font-metric oracle.

## Executed checks

Mac checkout: `/Users/zubair/Code/Projects/pdf project/worktrees/pdf-932`.
Homebase snapshot: `/home/wertyp/.local/share/homebase-factory/worktrees/inkflip/pdf-932`.
The Linux snapshot was created with `git archive 65e84da`, then received only the changed test file. Both have their own frozen native venv. Homebase commands source the canonical project's `.tools/env.sh` for installation. No OCR was run.

| Check | Mac | Homebase Linux amd64 |
| --- | --- | --- |
| Original reader suite | 22 passed, 10 subtests passed | 5 failed, 21 passed, 6 subtests passed |
| Fixed reader suite | 22 passed, 10 subtests passed | 22 passed, 10 subtests passed |
| Mutation probe baseline | 2 tests passed | 2 tests passed |
| Double UserUnit scaling | 4 assertion failures, no errors | 4 assertion failures, no errors |
| Reversed y axis | 5 assertion failures, no errors | 5 assertion failures, no errors |
| Omitted crop x translation | 1 assertion failure, no errors | 1 assertion failure, no errors |
| Last corner alone shifted | 5 assertion failures, no errors | 5 assertion failures, no errors |

Failure counts include unittest subtests. Every mutation was rejected. The probe patches only process-local functions; it does not write source files. Both platforms use CPython 3.13.15, pypdfium2 5.8.0, PDFium 149.0.7825.0. Native binary hashes, OS details and direct raw bounds are in the mutation logs. The original Linux failures include 249.280029 versus 253.12 and all four UserUnit cases.

Commands, run from each checkout root:

```sh
uv sync --frozen --project native
native/.venv/bin/python -m pytest native/tests/readers -q
native/.venv/bin/python artifacts/tasks/T26/font-oracle/mutation_probe.py
git diff --check
```

For Linux the probe was transferred to `/tmp/pdf-932-mutation-probe.py` and invoked there from the snapshot root. Logs named `*-original.log`, `*-fixed.log` and `*-mutations.log` contain the actual output. The original suite ran before editing; its source remains available at the base commit. `checksums.json` binds the tested file and logs. `git diff --check` passed on Mac.

Initial sandboxed Mac dependency installation panicked in uv's system-configuration crate. Retrying the normal frozen install with authorized sandbox escalation succeeded. This was an environment failure before tests ran.

## Limits

Verification is restricted to the affected reader suite and the geometry mutation probe. The full native suite includes OCR and was not run. Mac's original suite passed; only Linux reproduced the five original failures. Font provenance in exported manifests and deterministic rendering remain outside this test-only change. No Beads, main, GitHub, service, or other worker state was changed. The parent will arrange independent review and merged acceptance.
