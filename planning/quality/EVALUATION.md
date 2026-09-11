# Evaluation method and release targets

Evaluate an inspector, not the MIB adjudicator. The main dimensions are factually valid findings, useful findings, correct source alignment, coverage, false alarms, repeatability, latency/memory/download cost and ability to hand off a diagnosis. The 150-point historical challenge score is not a metric here.

## Population and splitting

Maintain four distinct collections: public demonstration cases, development/optimization cases, untouched evaluation cases, and optional real permissioned incidents. Public/demo cases and their generated siblings never enter the untouched claim denominator. Group by generator family, producer/layout and shared source ancestry, not random page. A cover/no-cover twin and all its seed variations stay in one split. Pages from one real document/producer family stay together where leakage is plausible.

T36's independent evaluator prepares a minimum reference evaluation of 300 clean/control pages and 300 supported failure pages across at least 12 mechanism/layout groups. This is a measurement design target, not an existing dataset. Include different generator implementations/typography/layouts, not 600 cosmetic variants of the public amount sample. Optimization workers get development fixtures and the protocol, not final labels/seeds. The evaluator holds labels in a separate local checkout/directory with access not shared to those sessions. Merely putting labels in a different folder in a shared repo is not access control.

Freeze the candidate commit/lock/model/configuration before evaluating. If a failure is used to tune a candidate, retire that case from untouched claims and obtain a new evaluation version. Archive negative results and denominators. Multiple readers of one source are not independent source witnesses; bootstrap uncertainty by document/generator group, not by individual tokens.

## Labels and metrics

**Factual validity**: the finding accurately quotes actual reader output, cites the correct source/reader/check, and uses a defensible location/precision. Any fabricated reading, wrong-file/page anchor, falsely completed check or incorrect source-inclusion claim is a release blocker. This is separate from whether a difference is useful to the task.

**Useful-finding precision**: among surfaced localized findings, a blinded reviewer judges that the finding helps investigate the specified reading incident and does not merely create irrelevant review noise. Two reviewers independently label a sample using original page, raw readings and the stated task. Disagreements remain reported and are adjudicated with rationale, not hidden as correct. Count duplicate cards for one issue as review burden. Report results before and after grouping.

**Supported-case coverage/recall**: fraction of predeclared supported failure cases with a factually valid useful finding or explicit actionable comparison, not fraction of only the cases the algorithm chose to answer. Abstentions, unsupported checks and timeouts remain in the denominator and are reported separately. Unsupported mechanisms are outside supported recall but inside full-corpus coverage reporting; this prevents selective denominators from implying generality.

**Alignment**: verify transform fiducial positions separately from OCR word localization. A self-consistent inverse is insufficient; rendered known anchors provide an independent check. Compare known geometry, source page ID, projected pixel positions, precise versus estimated labels, and repeated occurrence retention. OCR bounding-box uncertainty is not mistaken for transform error.

**Comparison validity**: changed versus improved/regressed is tested against explicit rules. Missing OCR, reduced selected pages and unsupported adapters cannot produce an apparent improvement. Baseline immutability and file/config identity are correctness properties, not optional regression metrics.

## Numeric targets (not measured achievements)

| Dimension | Release target | Rationale / scope |
|---|---|---|
| Hard factual invariants | 100% contractual hard fixtures; zero wrong-file/page or fabricated precise anchors | A compelling wrong highlight defeats the product |
| Useful localized precision | >=0.95 point estimate; Wilson 95% lower bound >=0.90, at least 100 emitted evaluated findings | Conservative headline findings; sample-size/selection disclosed |
| Supported failure coverage | >=0.90 over predeclared supported cases, not just accepted matches | Prevent abstain-everywhere from appearing precise |
| Clean false-alert burden | Mean <=0.05 surfaced non-informational false alerts/page; report clustered interval and max | Ordinary OCR layers must not flood the app |
| Transform alignment | p95 <=2 CSS px, max <=4 at reference zoom/DPR on independent fiducials | Small enough for reliable source localization; API box precision separately labeled |
| Repeated occurrence preservation | 100% on supported hard duplicate fixtures | A dedupe convenience cannot erase evidence |
| Check accounting | 100% planned tasks terminal; no missing/error treated as agreement | Coverage is core product truth |
| Repeatability | Identical semantic digests on repeated same-environment supported fixtures, or explicit nondeterminism block | Versioned reports must be usable regressions |
| Browser preview | p95 <=3 s for <=2 MiB/10-page native fixture files on reference desktop, warm app | Useful before optional OCR/model preparation |
| Browser OCR | p95 <=20 s for one selected <=4 MP printed-English page, warm model | Below the 30 s per-page safety timeout; no universal scan promise |
| Browser cancellation | UI feedback <=100 ms target; stale-generation unreachable immediately; worker termination target <=500 ms | Keeps control with user even during heavy reading |
| Browser memory | Tracked allocations <=256 MiB, measured peak process target <=512 MiB on supported fixtures | Targets, not a portable hard heap cap |
| Initial/cold assets | Entry JS gzip <=250 KB; selected English OCR cold transfer <=20 MiB | Avoid forcing large model download for a first example |
| Native bounded execution | One bad file cannot erase successful peers; parent kills all its child processes within termination policy | Local tool remains useful on an imperfect corpus |
| Privacy | Zero document-bearing network writes or unexpected resource fetches in specified capture | Required before local-only public claim |
| Accessibility | Zero blocked core keyboard flows / serious-critical automated issues; manual AT receipts | A canvas-only screenshot is insufficient |

Performance measurements use at least 30 runs per relevant fixture profile, record cold versus warm model/cache, p50/p95/max, CPU/RAM/OS/browser/version and actual page/pixel counts. Include failures/timeouts, not only completed samples. Do not publish a p95 from a single run. The native probe included here is mechanism evidence, not a benchmark distribution.

## Diagnosis usefulness and portfolio completion

Use a randomized/counterbalanced task comparison against a PDF viewer plus raw text dump. Ask a tester to locate the disagreement, explain the check's limits and send/reopen a report. Target >=4/5 early testers understanding the result without calling it fraud/safety proof, and >=30% median diagnosis-time improvement on repeated relevant tasks without correctness loss. These are formative targets, not adoption claims or statistically conclusive market evidence. If recruitment is unavailable, record it and complete deterministic functional/accessibility tests; there is no customer quota blocking the agreed portfolio release.

A confusing UI is fixed by interaction/copy work, not adding models. A low-noise operating point is achieved by conservative alignment and explicit selection, not hiding all unsupported results. The full downstream plan remains in scope regardless of whether public novelty converts to a startup.
