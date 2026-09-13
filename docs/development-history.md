# Development history

This page reconstructs how the code in this repository came to be, using only
observable records: the Git history of this branch, the per-task evidence
directories (`artifacts/tasks/`), and the live task tracker. It follows the
project's own rule that development-process claims must say only what those
records show ([planning/launch/CLAIMS_LEDGER.md](../planning/launch/CLAIMS_LEDGER.md)).

## Where the code comes from

The repository is a **documented snapshot import**, not a Git continuation of
an earlier project ([docs/ORIGIN.md](ORIGIN.md)). The prior repository
(`mib-intake`, MIT, pinned commit `94f35ce9f9beb…`) supplied conceptual
influences that are named and re-implemented — span metadata with explicit
reasons, output/evidence separation, bounded OCR escalation, raw-box
preservation, adversarial clean-twin tests — and its license file is
preserved byte-exact under `third_party/origin/mib-intake/`. No legacy
runtime module, classifier, calibration table or dataset was imported, and
the original repository is never a build input. The fixture generator and
all product code here are original to Inkflip.

## Timeline (from Git)

All dates are from this branch's commit history — 508 commits between
2026-09-11 and 2026-09-13.

### 2026-09-11 — honest scaffold (14 commits)

Coordination and bootstrap only: the workspace layout, agent prompts, review
standards, and **T01** — the Bun-workspaces monorepo with the "honest command
harness" (`scripts/task_acceptance.py` + registry) whose central rule is that
an empty or skipped required test suite is a failure, never a pass. The
origin/provenance record and the frozen planning snapshot land in this same
window. Commit `28b3ed8` is the bootstrap; the same day records its review
and integration receipts.

### 2026-09-12 — the implementation wave (404 commits)

The bulk of the product was implemented, reviewed and integrated task by
task, each with its own branch, receipt and review files:

- **Contracts and geometry:** T02 froze the real dependency locks
  (`bun.lock`, `native/uv.lock`, exact toolchain pins, staged asset digests);
  T03 landed the JSON Schema, canonical identity and generated types; T04 the
  canonical geometry and transform conformance; T05 the original fixture
  foundation with its rights manifest.
- **Interface foundations:** T06 design tokens and visual foundations; T07
  accessible controls, dialogs and navigation; T08 local file validation and
  page/region selection.
- **Reading pipeline:** T09 PDF.js rendering/text adapter; T10 selected-page
  and crop OCR; T11 run lifecycle with backpressure and cancellation; T12 raw
  normalization and conservative alignment; T13 the page/text/compare viewer
  with evidence navigation; T14 findings, coverage and plain-language
  explanations.
- **Trust work:** T15 proved own-file no-egress with a canary suite against
  the real build; T16 the portable JSON/escaped-HTML export foundation.
- **Native side:** T26 PDFium and pypdf reader adapters; T27 rendered-region
  Tesseract; T28 bounded structural observations; T29 supervised parent with
  atomic partial results; T31 the shared Node comparison bridge.

### 2026-09-13 — gates, hardening, experiments (90 commits)

- **T17** earned the browser amount demo: the prepared synthetic example with
  its clean-mapping control, generated from this repo's own fixtures
  (`scripts/prepare_examples.py`, byte-stable with digest checks).
- **T18 + pdf-3g8** composed the public own-file journey and earned the
  **G1 gate** — the first integrated end-to-end evidence run, with gate
  receipts bound to the merged state (`artifacts/gates/G1/`).
- **T19** completed large-document and narrow-device interaction (5/5 on its
  large-mobile acceptance spec); **T22** strict JSON import/reopen; **T24**
  hardened malicious report/text/image boundaries — with the earlier
  prerequisite receipts deliberately re-run and re-bound to the merged
  composition state rather than left stale.
- **Experiments T41–T45** (P09, P11–P14) evaluated paint-order
  counterexamples, targeted OCR escalation, a secondary browser reader, a
  native RapidOCR complement, and original-preserving raster geometry — each
  with an implementation commit, an evidence receipt and an independent
  review record (`docs/experiments/`, `artifacts/tasks/`).
- Native repairs (Tesseract worker cancellation, language-payload
  initialization) were landed as reviewed follow-ups (`pdf-ebz`, `pdf-q38`).

## How the work is organized

Observable mechanics, all visible in the repository:

- **One branch, one writer, one isolated checkout per task.** Work lands on
  per-task branches in isolated Git worktrees and is integrated after
  independent review; the review files sit next to the receipts in
  `artifacts/tasks/<task>/`.
- **Acceptance is evidence-based.** A task closes only with executed
  acceptance commands (real exit codes and test counts, bound to an evaluated
  commit) plus a separate review record — `artifacts/tasks/<task>/receipt.json`,
  `acceptance.json`, `review.md`. [docs/ACCEPTANCE.md](ACCEPTANCE.md) is the
  format contract.
- **Live state vs frozen spec.** The planning snapshot is kept byte-identical;
  live task state lives in the Beads tracker. A completed specification is
  explicitly not an implemented feature — the gate system exists to keep
  those apart.
- **Specialist lanes.** The work is split across persistent workbenches
  (integration/coordination, native CLI/corpus, browser UX/docs, fixtures/
  experiments, independent review) described in
  `docs/plans/independent-workbenches/README.md`. The implementation was
  produced with coding agents under owner direction; the commit and receipt
  trail above is the observable record of who did what — this history
  deliberately makes no claims beyond it.

## Where this documentation fits

This documentation set was written as **T49 preparation** (user/developer
docs and honest limitations) on the `work/antigravity/independent-volume-2`
branch, against the snapshot described in
[limitations.md](limitations.md). The final-release pass will re-verify every
command against the release tag, add the clean-machine install evidence, and
re-check links together with the other documentation owners — see
[limitations.md § What this documentation still needs](limitations.md#what-this-documentation-still-needs-for-final-release).
