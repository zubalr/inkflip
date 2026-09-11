# Assumptions and decisive probes

The architecture is selected. These are bounded empirical unknowns, not invitations to choose a different product. [Experiments](research/EXPERIMENT_MATRIX.md) and [machine records](research/experiments.json) contain inputs, sources, controls, metrics, costs, dependencies, artifacts and branches.

## Settled by execution in this planning environment

P01 creates original PDF bytes whose appearance is `$100` and whose measured PDFium reading is `$1,000`; the clean counterpart has the same rendered pixels. One native OCR crop reads `$100`. These results apply to recorded native versions, not to PDF.js/Tesseract.js or an entire browser application.

The native probe also establishes that the installed PDFium build reports dimensions without applying UserUnit in the tested files. This is an adapter-specific observation handled in the canonical coordinate model. It is not permission to double-scale PDF.js.

See [actual probe receipts](probes/results/native-probe.json). Further small utilities are executed and reported in [the package audit](PACKAGE_AUDIT.md). No proposed metric is silently promoted into an achieved result.

## Bounded unknowns and selected branches

| Unknown | Decisive procedure | Selected default | Failure branch |
|---|---|---|---|
| Exact browser stack installation and CSP behavior | T02 + P07 on real File and paired worker/model assets | PDF.js/Tesseract.js, same-origin assets, no worker server | Patch-compatible lock correction; no CDN or backend fallback; G1 blocks |
| Browser/native geometry including UserUnit | P02 + T04/T26 + visible overlay test | Canonical physical points and explicit transforms | Page-only/unsupported when adapter cannot prove geometry |
| Useful automatic comparison precision | P08, separate clean/damaged held-out evaluation | Conservative region-match-v1 and selected-region path | Abstain from ambiguous local claims; repair alignment rather than invent a winner |
| Secondary OCR/renderer gain | P11–P14 independent candidates | One browser OCR; no optional second-engine default | Reject/remove candidate with negative receipt, no accumulated dormant production code |
| No document payload egress | G1 canary + T15/T24 + G5 deployed capture | No telemetry, same-origin fixed asset allowlist | Remove offending route/script/config; privacy claim blocked until rerun |
| Reference devices and native isolation | P15 + T37/T39/T40 | Explicit supported matrix, bounded local profiles | Visible unsupported/partial capability; no promise that every phone or OS is equal |
| Model/build rights and patched dependencies | T02/T47 inventory actual resolved artifacts | Permissive original core, no PyMuPDF/runtime model download | Missing provenance or unpatched reachable vulnerability blocks distribution |
| Static deployment path in owner's account | T48 local preflight, T54 actual controlled deployment | Asset-only config with no main or metered bindings | Fix account rules/routing before publishing; local product still builds |

## Tool limitations of this planning pass

Registry network access from the container failed; consequently the chosen browser npm stack and final transitive lock were not installed or built here. Source access through web and GitHub worked. Native probes use installed versions; those exact versions are recorded. The complete product, supported-device suite, manual assistive-technology tests, real-user diagnosis study, final dependency/SBOM audit, and Cloudflare deployment have not been executed. These have full tasks and release gates, not invented results.

Owner-controlled inputs are separately listed in [OWNER_INPUTS.md](OWNER_INPUTS.md). No secrets, domain availability, provider concurrency entitlement or actual owner machine capacity can be inferred. Local bootstrap needs none of them.
