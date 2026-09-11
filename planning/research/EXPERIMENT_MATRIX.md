# Experiments and decision branches

Canonical records: [experiments.json](experiments.json). Every experiment has a baseline, selected candidate, clean controls, metric, rejection branch and bounded runtime. A scoped planning probe passing does not mean its full product integration or device matrix passed.

## P01 — Real-byte amount and clean twin

**Owner task:** T05. **Dependencies:** none. **Status:** executed / passed.

**Baseline:** Native literal extraction versus generated display. **Selected candidate:** PDFium 5.8.0 + one Tesseract 5.5.0 selected-crop read.

**Fixtures:** F01, F02. **Clean controls:** mapping-control.pdf renders identically.

**Metrics:** Mapped text $1,000; control $100; raster byte equality; OCR crop $100; hashes recorded.

**Accept/reject:** All four assertions pass on recorded native environment; any mismatch blocks using that output as prepared evidence.

**Resource costs/bounds:** One crop OCR, two small renders; <4MP each.

**Procedure:** `probes/native_probe.py`. **Evidence artifact:** `probes/results/native-probe.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Keep actual native prepared evidence; browser result requires P07.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S22](SOURCES.md#s22), [S26](SOURCES.md#s26).

## P02 — Coordinate round trips and UserUnit

**Owner task:** T04. **Dependencies:** none. **Status:** executed / passed_scoped_probe.

**Baseline:** Unqualified bbox and renderer size. **Selected candidate:** Explicit C/R/S/crop transforms, per-adapter UserUnit handling.

**Fixtures:** F07, F08, F09, F10. **Clean controls:** All rotations, nonzero origins, analytic points.

**Metrics:** 10,000 deterministic affine round trips <=1e-5 pt; independent worked vector; native size observation.

**Accept/reject:** All analytic checks pass; browser p95<=2CSSpx in T04; any wrong-page highlight blocks release.

**Resource costs/bounds:** No OCR; tiny deterministic math.

**Procedure:** `probes/geometry_probe.py`. **Evidence artifact:** `probes/results/geometry-probe.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Keep canonical model. Unsupported transforms downgrade geometry; never guess.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S22](SOURCES.md#s22), [S26](SOURCES.md#s26).

## P03 — Contract examples and semantic failures

**Owner task:** T03. **Dependencies:** none. **Status:** executed / passed_scoped_probe.

**Baseline:** Shape-only JSON parsing. **Selected candidate:** Closed schema plus strict JSON and semantic checks.

**Fixtures:** F24, F25, F26. **Clean controls:** Valid empty/partial/cancelled reports.

**Metrics:** Every valid example accepted; every invalid fixture rejected at declared class; corrupted hash fails.

**Accept/reject:** No unexpected accept/reject; malformed imported data must never execute or fetch.

**Resource costs/bounds:** Bounded JSON only.

**Procedure:** `tools/test_validators.py`. **Evidence artifact:** `quality/planning-test-results.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Canonical schema remains sole domain model; fix contract coherently, not consumer exceptions.

**Execution qualification:** Python planning validator and contract examples executed; browser Ajv parity remains T03, not claimed passed.

Sources: [S32](SOURCES.md#s32), [S43](SOURCES.md#s43).

## P04 — Python and Node evidence identities

**Owner task:** T03. **Dependencies:** P03. **Status:** executed / passed_scoped_probe.

**Baseline:** JSON stringify hashes. **Selected candidate:** inkflip-c14n-v1 with explicit scalar keys and binary64 numbers.

**Fixtures:** F25. **Clean controls:** 0,-0,1,1.0,Unicode,emoji and reordered objects.

**Metrics:** All vectors produce identical SHA-256 in Python/Node; report identity exclusions tested.

**Accept/reject:** Zero identity drift; adapters use same vectors on release.

**Resource costs/bounds:** No PDF/OCR/network.

**Procedure:** `probes/hash_parity.mjs`. **Evidence artifact:** `probes/results/hash-parity.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Keep canonical encoder. Reject unsafe integer/nonfinite/lone-surrogate input.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S32](SOURCES.md#s32).

## P05 — Script-free evidence export

**Owner task:** T16. **Dependencies:** P03. **Status:** executed / passed_generation_and_escaping_tests.

**Baseline:** Screenshot-only bug report. **Selected candidate:** Escaped HTML plus disclosed canonical JSON.

**Fixtures:** F24. **Clean controls:** Legitimate < > & quotes and hostile HTML-like data.

**Metrics:** No script/event attributes/external resource URLs; selected source absent; opening makes no request.

**Accept/reject:** Zero unintended content inclusion or network; second reader can interpret recorded limits.

**Resource costs/bounds:** One bounded PNG/report.

**Procedure:** `tools/export_html.py`. **Evidence artifact:** `examples/native-evidence.html`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Evidence-only remains useful; replay label requires bytes/environment.

**Execution qualification:** Script-free HTML generated and escaping/inclusion tested. Independent human handoff and deployed browser no-egress are not executed.

Sources: [S18](SOURCES.md#s18), [S43](SOURCES.md#s43).

## P06 — Stale event and parent timeout model

**Owner task:** T11. **Dependencies:** P03. **Status:** executed / passed_scoped_probe.

**Baseline:** Blindly accepting delayed events. **Selected candidate:** Generation/digest/sequence validation and disposable child supervision.

**Fixtures:** F21, F22. **Clean controls:** Completed empty work not retried; good result survives crash.

**Metrics:** Old generation rejected; out-of-order rejected; hung test child terminated; successful data retained.

**Accept/reject:** All protocol checks pass; real browser/native integration fault tests still required.

**Resource costs/bounds:** One short synthetic child, no parser/large input.

**Procedure:** `probes/lifecycle_probe.py`. **Evidence artifact:** `probes/results/lifecycle-probe.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Keep revoke-first model. No claim of complete browser/container containment.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S17](SOURCES.md#s17).

## P07 — Actual pinned browser feasibility

**Owner task:** T18. **Dependencies:** P01, P02, P03, P05, P06. **Status:** blocked / not_run.

**Baseline:** Executed native demo only. **Selected candidate:** PDF.js + Tesseract.js actual local File, cancellation/export/import/network trace.

**Fixtures:** F01, F02, F07, F21. **Clean controls:** Mapping clean twin and ordinary native page.

**Metrics:** Correct native/browser named readings, geometric anchor, no stale result, no payload egress, actual model status.

**Accept/reject:** G1 all required checks pass; no fixture-name conditional; missing npm/browser assets blocks proof.

**Resource costs/bounds:** Desktop profile; one OCR page/crop <=4MP.

**Procedure:** `probes/browser/README.md`. **Evidence artifact:** `probes/results/browser-status.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Implement selected stack. If pinned patch needs update, T02 locks maintained compatible patch. Native proof never stands in for G1.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S22](SOURCES.md#s22), [S23](SOURCES.md#s23), [S24](SOURCES.md#s24).

## P08 — Useful disagreement versus alignment noise

**Owner task:** T12. **Dependencies:** P07. **Status:** proposed / not_run.

**Baseline:** Viewer+text dump; blanket hidden-text warnings. **Selected candidate:** region-match-v1 and benign-layer handling.

**Fixtures:** F03, F11, F12, F13, F14, F15. **Clean controls:** Clean searchable scans and repeated values.

**Metrics:** Useful-finding precision >=0.95; clean false-findings <=0.05/page; exact amounts/signs never normalized equal.

**Accept/reject:** Meet predeclared clean/damaged denominators; ambiguous alignments abstain; no safety interpretation.

**Resource costs/bounds:** Reference 300+300 pages in held-out plan; no unbounded OCR escalation.

**Procedure:** `quality/EVALUATION.md`. **Evidence artifact:** `artifacts/P08/result.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Selected-region comparison remains mandatory; only enable automatic local claims at measured operating point.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S02](SOURCES.md#s02), [S15](SOURCES.md#s15), [S16](SOURCES.md#s16).

## P09 — Paint metadata versus rectangular ink

**Owner task:** T41. **Dependencies:** P02, P08. **Status:** proposed / not_run.

**Baseline:** Near-white or any-dark-pixel bbox heuristics. **Selected candidate:** Documented object render modes plus narrowly scoped paint/ink observations.

**Fixtures:** F04, F05, F06. **Clean controls:** White-on-dark, invisible-over-border, partial alpha.

**Metrics:** Per-mechanism precision/coverage, zero normal-layer alarm, same-point timing.

**Accept/reject:** Zero hard-control misclassification; metadata reason remains distinct from visibility hypothesis; reject general all-visible claim.

**Resource costs/bounds:** One <=12MP native render; bounded objects.

**Procedure:** `research/UPSTREAM_TECHNIQUES.md`. **Evidence artifact:** `artifacts/P09/result.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Documented native object mode is selected; complex compositing remains unavailable unless independently proven.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S15](SOURCES.md#s15), [S16](SOURCES.md#s16), [S27](SOURCES.md#s27).

## P10 — Version-isolated regression and baseline integrity

**Owner task:** T34. **Dependencies:** P03, P04. **Status:** proposed / not_run.

**Baseline:** Same process resolves only one version; auto-refresh goldens. **Selected candidate:** Separate reader profiles, immutable rules/baselines, shared comparator.

**Fixtures:** F23, F25. **Clean controls:** Unchanged sources; identical run; lost coverage.

**Metrics:** Changed without rule != regression; coverage loss fails coverage rule; input mismatch incomparable; baseline unchanged.

**Accept/reject:** All exit-code cases and non-overwrite tests pass; no imported profile execution.

**Resource costs/bounds:** Two isolated local envs, explicit setup network only.

**Procedure:** `deployment/examples/reader-upgrade.sh`. **Evidence artifact:** `artifacts/P10/result.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Ship local/CI workflow. Profile install failure is explicit, no silent fallback reader.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S08](SOURCES.md#s08), [S18](SOURCES.md#s18), [S45](SOURCES.md#s45).

## P11 — Targeted OCR retry value

**Owner task:** T42. **Dependencies:** P07, P08. **Status:** proposed / not_run.

**Baseline:** Single selected-page OCR, no reread. **Selected candidate:** Padded selected/mismatched-region rerun with inverse transform.

**Fixtures:** F14, F15, F16. **Clean controls:** Adjacent-field crops and normal clean rows.

**Metrics:** >=20% more useful target recoveries at <=1pp precision loss; all transformed anchors valid; within run pixel/time limits.

**Accept/reject:** Predeclared baseline/candidate seeds and same inputs; reject if gains require clipping neighbors or more false alerts.

**Resource costs/bounds:** At most original job total20MP and120s desktop.

**Procedure:** `architecture/READER_ADAPTER_CONTRACT.md`. **Evidence artifact:** `artifacts/P11/result.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Default off until accepted; explicit user-selected OCR remains available.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S20](SOURCES.md#s20).

## P12 — Secondary browser PDFium reader

**Owner task:** T43. **Dependencies:** P07, P08. **Status:** proposed / not_run.

**Baseline:** PDF.js plus OCR. **Selected candidate:** EmbedPDF PDFium release v2.15.0; pdfium-dist.tar.gz pinned to source S48 digest; no full viewer integration..

**Fixtures:** F01, F07, F11, F12. **Clean controls:** Clean mapping twin and same-reader control.

**Metrics:** Complementary inspectable differences; all chunks <24MiB; cold OCR+optional budget disclosed; <=512MiB reference peak.

**Accept/reject:** At least one generalizable mechanism benefit at fixed review budget; public API and full notices; no private undocumented glyph claim.

**Resource costs/bounds:** Optional lazy download, max one active secondary reader.

**Procedure:** `architecture/CAPABILITIES.md`. **Evidence artifact:** `artifacts/P12/result.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Selected default unavailable. Rejection closes experiment; browser core remains complete.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S22](SOURCES.md#s22), [S26](SOURCES.md#s26), [S48](SOURCES.md#s48).

## P13 — Native RapidOCR complement

**Owner task:** T44. **Dependencies:** P08. **Status:** proposed / not_run.

**Baseline:** Tesseract native reader. **Selected candidate:** RapidOCR v3.8.1 with one PP-OCRv5 mobile English configuration; exact official weights and notices must be locked before execution..

**Fixtures:** F14, F15, F16. **Clean controls:** Same renders, clean text and missing-region negatives.

**Metrics:** Complementary useful findings at fixed precision; timing/RSS/model bytes/rights measured.

**Accept/reject:** Keep only if coverage gain survives clean controls and distribution audit; engine agreement never truth.

**Resource costs/bounds:** Native profile1GiB child cap; no runtime download.

**Procedure:** `security/LICENSE_AND_ATTRIBUTION.md`. **Evidence artifact:** `artifacts/P13/result.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Default not installed. Candidate and rejected artifacts stay in experiment namespace.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S19](SOURCES.md#s19), [S20](SOURCES.md#s20), [S21](SOURCES.md#s21), [S47](SOURCES.md#s47).

## P14 — Original-preserving geometric raster experiment

**Owner task:** T45. **Dependencies:** P02, P08. **Status:** proposed / not_run.

**Baseline:** Unmodified render OCR. **Selected candidate:** Single deskew or strip-registration candidate with full transform chain.

**Fixtures:** F06, F07, F15. **Clean controls:** Ordinary ruled forms, already aligned clean pages.

**Metrics:** No clean-control corruption; accepted alignment roundtrip; incremental recovery measured separately.

**Accept/reject:** Reject broad reconstruction or generator-only benefit. Any source registration loss rejects result.

**Resource costs/bounds:** One candidate transform per chosen crop, no PDF mutation.

**Procedure:** `quality/FIXTURE_PROGRAM.md`. **Evidence artifact:** `artifacts/P14/result.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Default rejected from production until demonstrated; never automated repair/sanitization.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S19](SOURCES.md#s19), [S21](SOURCES.md#s21).

## P15 — Runtime parity, assets and compatibility

**Owner task:** T46. **Dependencies:** P04, P07, P10. **Status:** proposed / not_run.

**Baseline:** One dev-machine success. **Selected candidate:** Pinned browser/native manifests, cold/warm renders and repeated output checks.

**Fixtures:** F07, F10, F23, F25. **Clean controls:** Same reader/build/platform repeated; explicit engine differences.

**Metrics:** Stable semantic report for repeated fixed environment; explained cross-engine differences; no stale cache mixing.

**Accept/reject:** No unexplained parity in promised equivalence; show unsupported elsewhere.

**Resource costs/bounds:** Supported Chromium/Firefox/WebKit and native platform matrix, resource profile recorded.

**Procedure:** `quality/PERFORMANCE_AND_COMPATIBILITY.md`. **Evidence artifact:** `artifacts/P15/result.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Capabilities vary explicitly; do not claim cross-engine pixel identity.

**Execution qualification:** Only the recorded execution scope is established; full release tests remain separate.

Sources: [S26](SOURCES.md#s26), [S29](SOURCES.md#s29), [S45](SOURCES.md#s45).

## P16 — Interaction reference rendering

**Owner task:** T06. **Dependencies:** P01. **Status:** executed / passed_scoped_probe.

**Baseline:** Prose-only UI plan. **Selected candidate:** Prepared-native-data HTML reference at wide/narrow widths.

**Fixtures:** F01. **Clean controls:** Source crop and sample labels always visible.

**Metrics:** No horizontal overflow; mode buttons keyboard usable; disclosure/details readable; screenshots inspected.

**Accept/reject:** Fix clipping/illegible labels before handing design to workers; not an accessibility certification.

**Resource costs/bounds:** Local Chromium, no model inference.

**Procedure:** `probes/reference_probe.py`. **Evidence artifact:** `probes/results/reference-probe.json`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.

**Integration decision:** Use reference as visual target, never production own-file processing proof.

**Execution qualification:** Owned HTML rendered with local DOM injection because localhost navigation was blocked by environment policy. Four screenshots inspected. Not a PDF.js/Tesseract.js or hosting/privacy test.

Sources: [S42](SOURCES.md#s42).
