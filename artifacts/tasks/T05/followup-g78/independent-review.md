# Independent review — pdf-g78 priority checkpoint

Verdict: **approved for this ten-family fixture checkpoint only**. No actionable correctness or repository-standard findings remain in the reviewed scope. This is not acceptance or closure of pdf-g78, T05, a native adapter, or a production consumer.

Reviewer: Codex independent reviewer, sole reviewer on `review/codex/g78-priority`; implementation writer Lagrange yielded before review. No delegates used.

Exact implementation candidate: `fd822d95266272d548f0ba279edd49424b55840c`.
Base: `008ed367d6d7b462b72f00a22d8d2e40b89e442e`.
Review checkout started clean at `c1ebb2f2c58826ab363d5b95c7466197d28d997a`, which adds the checkpoint handoff. Reviewed the complete 97-file implementation diff, including generator, tests, all generated source/expectation entries and manifest, rights/proposal documents, measurement scripts/logs/JSON, and rendered contact sheet. Also reviewed the subsequent handoff. Source remained unchanged throughout review.

## Standards and specification

Read root AGENTS.md, docs/NATIVE_PASSES.md, docs/HOMEBASE.md (the repository's HOMEBASE location), docs/ACCEPTANCE.md, project brief, glossary/invariants, decisions, fixture program and catalog, demo/gallery specification, effective `coordination.py task T05`, and checkpoint proposal/rights/handoff. Assessed both spec fidelity and repository standards using the code-review skill, including its smell baseline. No speculative cleanup requested. The effective original T05 contract covers five foundation families; the explicit review assignment and checkpoint proposal define this addition.

Scope: F04/F05/F06/F10/F11/F17/F18/F19/F20/F21. Eleven deliberately unbuilt families F09/F12/F13/F14/F15/F16/F22/F23/F24/F25/F26 are not findings against this checkpoint. Their completion and Beads state remain with the coordinator.

## Fresh execution

Commands ran from this review checkout:

- `python3 scripts/make_fixtures.py --check` — exit 0; 91 generated files match. Evidence: independent-generation.log.
- `python3 -m unittest discover -s tests/fixtures -v` — exit 0; 50 tests passed, no skips. Includes two temporary generations, tamper detection, manifest/rights/structures and six bounded fault modes. Evidence: independent-tests.log.
- `PYTHONDONTWRITEBYTECODE=1 '/Users/zubair/Code/Projects/pdf project/original/native/.venv/bin/python' artifacts/tasks/T05/followup-g78/independent-probe.py > artifacts/tasks/T05/followup-g78/independent-probe.json` — exit 0. Independently compares 32 original files to `git show BASE:fixtures/PATH`, then runs 23 separate PDF reader/render subprocesses with a ten-second timeout each and a 256-pixel long-edge render request. 21 renders succeeded; the two intentionally invalid PDFs failed. No child timed out. Every assertion passed.
- `git diff --check 008ed36 fd822d9` — exit 0.

The probe records exact versions (pypdf 6.18.0, pypdfium2 5.8.0 and PDFium build in JSON), source hashes, unmodified API text, actual exceptions, page boxes, render scale/dimensions and pixel-buffer hashes/counts. It imports reader libraries only, not native adapters or OCR/models. The existing native interpreter was used without installing dependencies or writing another checkout. Pixel `dark_bytes` counts channel bytes below 128, not glyph area or OCR accuracy.

## Evidence assessment

- Preservation/determinism: all 16 original PDFs and 16 original expectations compare byte-for-byte against Git base, independently of the writer's baseline-hashes.json. The complete regenerated manifest/sidecars match committed bytes; 45 entries represent 15 families. New entries carry g78.1 recipe identity, controls, split, rights and source/expectation hashes. Original recipe fields remain frozen; generator/catalog hashes track new inputs.
- F04/F05/F06: actual content operators implement white-on-dark versus white-on-white, preceding versus following cover, partial cover and triangular clipping. Inspected the committed contact sheet. Fresh rendering confirms blank white/covered cases; partial/triangular dark-channel counts are 342/282 versus 630 for the full-text control at the same scale. These demonstrate the fixed examples, not universal compositing inference.
- F10/F11: mapping variants have identical rendered pixel hashes. Pypdf actually returns `$100` for valid/absent maps and `$00` for the malformed map; no label fills the missing digit. Four distinct text matrices produce four occurrences in actual extracted output. Occurrence binding in production remains a consumer concern.
- F17: owned bitmap control visibly contains readable text; blank/noise siblings contain no native text operators. Actual extraction is empty for all three raster-only cases, with blank/noise rendering differentiated. No OCR claim was inferred from the sidecar or image.
- F18: empty password fails, public fixture credential unlocks and yields `$100`; decrypted render equals the valid twin. Truncated and malformed page trees produce recorded failures in both reader/render paths. These are bounded synthetic inputs without live exploits.
- F19: actual source is 635 bytes with a billion-point square MediaBox. The nominal 72-dpi request is 10^18 pixels; the fresh probe computes scale before allocation and renders only 256×256. Its blank thumbnail is expected at that scale. Production limit-before-allocation is not established by a successful bounded thumbnail.
- F20: fixed double emits an earlier completed event before normal/failure/crash/hang/cancel/stale behavior; tests terminate/reap the subprocesses. Sleep has a two-second fallback, with consumers responsible for the one-second scenario budget. The suite demonstrates event survival, not production result-payload retention, supervisor terminal classification or stale-event rejection. Those limitations are consistent with checkpoint scope.
- F21: source bytes contain distinct text, XML metadata and annotation markers; filename and SHA channel bind the actual source. No URI, JavaScript or other active network action is constructed. Crop/report channels explicitly require actual consumer artifacts. The blank document is a content control; the separately documented same-actions-without-document run remains mandatory in consuming no-egress tests. No no-egress/storage proof is claimed here.
- Rights: new bytes contain fixed synthetic content and unembedded base-14 Helvetica; raster content reuses the owned bitmap recipe. No downloaded font program, private document or evaluation label was introduced. MIT notices and the encryption reference/provenance are retained. Functional unlock/render checks validate the encrypted bytes; this review does not certify the writer's historical external-document fetch.

## Limits

Writer observations remain separate from authored generator intent; fresh observations are separate again in independent-probe.json. The writer's Poppler timeout is historical environment evidence, not a passing Poppler result; it was not rerun. No OCR, model initialization, full browser, native corpus, heavy foundation checks, public publication, Beads writes or other checkout edits occurred. Parent retains foundation and integration gates, consumer proofs and all remaining-family work. Only this report and independent probe/log evidence are committed by this reviewer.
