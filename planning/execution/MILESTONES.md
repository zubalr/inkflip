# Milestones: capability and evidence, not dates

The complete release is planned now. Gates determine integration sequence; they do not shrink the final scope. Numeric latency/CPU/memory bounds protect visitors and test runners, never constrain development ambition. No revenue, customer quota, job-application date, provider promotion or worker count is a gate.

## Foundation — contracts before competing implementations

T01 creates the separate local repository, immutable planning snapshot and test harness. T02 freezes the actual toolchain/dependencies/assets; T03 establishes schema/hash/semantic boundaries; T04 geometry; T05 fixture foundations; T06–T07 visual/accessibility primitives. These streams can overlap where the DAG permits. The integrator owns shared-contract changes and resolved dependency inputs, not every file edit.

## G1 — one real browser investigation, fully joined

T18 runs on a merged candidate after T08–T17 and T22/T24 prerequisites. Required acceptance:

1. Open actual generated mapping PDF through the local File chooser, also renamed; named PDF.js reading is produced from bytes. Open its clean twin through the same path. Neither output comes from fixture-name conditions or mocked extraction.
2. Select a page/region, run actual browser OCR with pinned same-origin assets, and inspect both readings at the correct source. A prepared native report alone does not count. Test a rotated/cropped file too.
3. Verify correct geometry after zoom/rotation/DPR, raw text/normalization maps and explicit unsupported/incomplete checks. A normal searchable scan must not become suspicious merely for an invisible text layer; where its recipe is not yet available, implement that minimum F03 control now rather than waive this check.
4. Cancel actual work, replace file A with B while an A result is delayed, and prove B never displays stale A data. Already completed independent results survive an unrelated error.
5. Export a selected finding with privacy preview and no source PDF/name by default, reopen the JSON locally, inspect the human HTML and explicitly state replay limitations.
6. Capture cold/warm actual network/storage behavior with a canary; no file bytes/text/name/hash/crop/report leaves the browser. Local host logs receiving only fixed static-resource requests are not document upload.

All six need fresh receipts with exact build/browser/fixture/model identity. These are not achieved merely because this package validates. A defect reopens its owning task; independent native/evaluation work can continue.

## G2 — complete public investigation surface

T51 closes own-file lifecycle, six real sample cards and controls, duplicate/ambiguous/order/unmatched evidence, narrow/large-document behavior, complete import/export/annotation privacy, selected replay, explicit model cache/offline behavior and useful accessible text equivalents. Public experience must remain useful with native tools absent. No unfinished UI controls or prepared output pretending to be live remain.

## G3 — complete native and regression surface

T52 closes actual PDFium/pypdf/Tesseract adapters, narrower native structure checks, non-root/offline recommended execution, supervisor/partial artifacts, corpus identity/resume, Node shared comparator, isolated incompatible reader versions, acceptance-rule semantics, immutable approved baselines, exact CLI exit codes and executable local reader-upgrade example. Native reports reopen in the public viewer without upload. Changed output is not improved/regressed absent a rule; losing coverage fails a required-coverage rule.

## G4 — quality, security, rights and experimental decisions

T53 closes held-out clean/damaged evaluation, unit/property/contracts, browser/native failure injection, manual accessibility, supported-device visual/performance/memory work, privacy/import security, build/SBOM/license/asset audit and cross-environment parity. The declared numeric targets in [evaluation](../quality/EVALUATION.md) and [performance](../quality/PERFORMANCE_AND_COMPATIBILITY.md) need actual receipts. There is no requirement to merge every experimental method: T41–T45 may finish with a reviewed rejection and removal from production. A missing required test, license or critical privacy/geometry assertion is not an acceptable “partial release.”

## G5 — exact static public release and rollback

T55 performs the final adversarial review after G2/G3/G4, static preflight and completed docs/launch material. T54 then needs explicit owner publication authorization and secure account/domain access. Deploy only the archived static build; test actual headers, model assets, deep links, no-egress and no application-compute route in the owner's account. Exercise rollback to a known archived build and restore the release candidate. Publish source/media/tag only when authorized and all claims match the exact artifact.

Actual public availability cannot be claimed during a planning pass or local preflight. No need to invent a domain now. Local product development is unblocked by publication inputs.

## Gate records

`execution/gates.json` maps responsibility to each gate. `execution/tasks.json` dependencies, rather than the gate label alone, establish order. T01's gate runner follows `execution/gate-runner.json`: it validates prerequisite receipts, then executes the explicit `scenario_commands` in each gate record. It never calls the gate-owner task's aggregate acceptance command recursively. Empty test collection, absent evidence and unexplained required skips fail the gate. T55's `pre-release` is a composition of G1–G4 plus preflight/document checks; it must not invoke deployment. G5 alone consumes an explicit public target and owner approval.

A gate receipt records gate ID, reviewed/merged commit, resolved lock and source/model/fixture digests, actual environment, command exit/counts, manual receipt links, failures and limitations. Any material dependency change invalidates the affected gate; it cannot keep an unrelated earlier green receipt.

The gate owner is deliberately excluded from `required_task_ids`: its scenario is the work that earns the gate receipt. Prerequisite acceptance is checked before the scenario; the gate owner is accepted only after its independent review and fresh merged-branch receipt.
