# Current repository audit and disposition

Audit reference: `zubalr/mib-intake@94f35ce9f9beb1640ddebdc2c72aa379ecebb004`. Source pointers below are pinned in [the ledger](../research/SOURCES.md). Code inspection is not challenge-runtime reproduction. No binary classifier was unpickled, no original repository was modified, and no score is transferred to this product.

| Treatment | Actual source anchor | Observed constraint / selected destination |
|---|---|---|
| Keep historical | README, MEMO, APPENDIX, LICENSE, frozen source commit | Preserve original repository and qualified public score; link origin from new docs |
| Reimplement concept | `mib/pdfio.py::Span`, `extract_spans`, `relative_luminance` | Bboxes exist, but near-white assumes a background and crop intersection is not complete visibility; new explicit capability/geometry contract |
| Replace model | `mib/extract.py::Observation`, `PacketEvidence`, `_absorb` | Field/value/source/page/trust lacks occurrence geometry; deduplication can collapse repeated values; keep every source occurrence instead |
| Refactor design, not import runtime | `mib/ocr.py` segmentation/rotation and `fallback_ocr.py` region reads | Bounded escalation and raw boxes useful; fixed MIB labels/closed menus removed; every new read gets new geometry/settings |
| Remove | `mib/pipeline.py` winning-value resolution and postprocessing defaults | Inspector preserves competing readings rather than choosing the printed answer |
| Legacy only | `mib/policy.py`, `features.py`, `model.py`, `policy/adjudicator.joblib` | Visa/sponsor/risk rules and confidence are challenge-specific; no generic trust score |
| Legacy only | `policy/calibration.json`, vocabulary artifacts | Source says fitted over 1,000 training rows; path priors cannot calibrate new reading-disagreement claims |
| Replace | `mib/schema.py::Prediction`, fallback sponsor/date | Well-formed plausible values satisfy evaluator but would conceal missingness here |
| Replace | `mib/cli.py::main` extraction/finalization/write phases | Collects batch outputs then writes at end; new parent watchdog and atomic per-file partial reports |
| Learn tests | `tests/test_pdfio.py` and printed-output/policy safety tests | Retain separation discipline; add white-on-dark, clipping, mapping, repeated/crop/rotation controls |
| Replace dependency policy | requirements.txt, Dockerfile | Floating base/apt and PyMuPDF licensing require new explicit locks and notices; primary runtime is PDF.js/PDFium, not accidental AGPL stack |
| Replace evaluation | `tools/train_adjudicator.py`, official evaluator | New finding/geometry/coverage metrics; no MIB payoff optimization or validation labels in inspector |

`pdfio.py` reads span color and alpha, temporarily widens the crop and records offcrop/rotation flags. It does not provide complete paint-order/background/OCG/clipping/compositing provenance. Some broader wording in the memo must therefore be read as approach description, not proof that every mechanism is implemented. White text on a dark page is the canonical negative control. [S01](../research/SOURCES.md#s01), [S09](../research/SOURCES.md#s09).

The observation schema and fallback-box side channel explain why a thin frontend over the final JSONL cannot produce reliable source-linked evidence. Some lower-level objects retain boxes, but the winning printed fields do not preserve the entire transformation/occurrence chain. [S02](../research/SOURCES.md#s02), [S03](../research/SOURCES.md#s03).

The final reported 137.89/150 is in-sample. The historical commit `634daacb02a944ddf41733ddd2e969449681ec3c` explicitly replaces “out of fold” framing with “model-fold diagnostic” because globally fitted path priors affect held-out examples. Its older intermediate score differs from the final README score; that is a historical sequence, not a contradiction to erase. The current calibration JSON states a 1,000-row fitting source. These are primary-source-supported methodology caveats, not independently measured new results. [Historical correction](https://github.com/zubalr/mib-intake/commit/634daacb02a944ddf41733ddd2e969449681ec3c), [calibration source](https://github.com/zubalr/mib-intake/blob/94f35ce9f9beb1640ddebdc2c72aa379ecebb004/policy/calibration.json), [S04](../research/SOURCES.md#s04), [S08](../research/SOURCES.md#s08).

The classifier loader uses joblib and falls back on load failure. The new tool never loads arbitrary pickle/joblib from a report. Its report format is a strict data contract. Legacy binary sizes/history are inventoried as origin evidence, not copied into the public app.

## Audit depth and remaining limitations

Pinned code, relevant tests, dependency/Docker files, README/MEMO/APPENDIX sections, evaluator section, calibration JSON and a meaningful correction commit were inspected. Several large source files were examined by relevant definitions/sections, not every branch. Legacy tests, images, training and challenger benchmarks were not executed. The only runtime proof in this package is explicitly recorded under `probes/results/`, on new harmless fixtures and different documented local versions.
