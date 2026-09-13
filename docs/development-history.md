# Development history

This page reconstructs how the code in this repository came to be, from the
Git history of the default branch and the frozen planning records. Per the
project's claims rules, it says only what those observable records show —
implementation history is evidenced by commits and dated validation records,
not by invented autonomy or counts.

## Where the code comes from

The repository is a **documented snapshot import**, not a Git continuation
of an earlier project ([docs/ORIGIN.md](ORIGIN.md)). The prior repository
(`mib-intake`, MIT, pinned commit `94f35ce9f9beb…`) supplied conceptual
influences that are named and re-implemented — span metadata with explicit
reasons, output/evidence separation, bounded OCR escalation, raw-box
preservation, adversarial clean-twin tests — and its license file is
preserved byte-exact under `third_party/origin/mib-intake/`. No legacy
runtime module, classifier, calibration table or dataset was imported, and
the original repository is never a build input. The fixture generator and
all product code here are original to Inkflip.

## Timeline (from the default branch's Git history)

Work started on 2026-09-11 and has proceeded in reviewed waves since; the
branch history contains the full commit-level record.

- **Bootstrap (2026-09-11).** The Bun-workspaces monorepo, the honest
  command harness (`scripts/task_acceptance.py` + registry, whose central
  rule is that an empty or skipped required test suite is a failure, never a
  pass), the origin/provenance record, and the frozen planning snapshot.
- **Foundations.** Dependency freeze (`bun.lock`, `native/uv.lock`, exact
  toolchain pins, staged asset digests); JSON Schema, canonical report
  identity and generated types; canonical page-space geometry; the original
  fixture foundation with its rights manifest; design tokens; accessible
  controls and navigation; local file validation and page/region selection.
- **Reading pipeline.** PDF.js rendering/text adapter; selected-page and
  crop OCR; bounded run lifecycle with backpressure and cancellation; raw
  normalization and conservative alignment; the page/text/compare viewer
  with evidence navigation; findings, coverage and plain-language
  explanations; portable JSON/escaped-HTML export; the amount demo with its
  clean-mapping control.
- **Trust work.** Own-file no-egress proven by a canary suite against the
  real build; strict JSON import/reopen; hardening against hostile reports,
  text and images; large-document and narrow-device interaction.
- **Native side.** PDFium and pypdf reader adapters; rendered-region
  Tesseract; bounded structural observations; supervised parent with atomic
  partial results; the shared Node comparison bridge.
- **Capability gates and evidence UX.** The first integrated own-file
  evidence journey earned the project's first capability gate; occurrence
  candidates (repeated amounts individually addressable, order-only
  differences separated, unmatched text never counted missing) and export
  selection with opt-in notes and a pre-export privacy preview followed,
  each accepted only after independent review against a merged state.
- **Distribution preparation (2026-09-13).** The distribution inventory/SBOM
  tooling, the enforceable distribution gate, third-party license evidence
  and this documentation set (`scripts/distribution/`,
  `scripts/check_distribution.py`, `licenses/`, `NOTICE`,
  `docs/distribution/`); the owner's license decision (MIT, "Copyright
  (c) 2026 zubair") was applied to the repository root.

## How the work is organized

- **One branch, one writer, one isolated checkout per task.** Work lands on
  per-task branches and is integrated after independent review.
- **Acceptance is evidence-based.** A task closes only with executed
  acceptance commands bound to an evaluated commit plus a separate review
  record. Working records live outside source commits and are archived in
  local Git object storage; the mechanics are specified in
  [docs/ACCEPTANCE.md](ACCEPTANCE.md).
- **Live state vs frozen spec.** The planning snapshot is kept byte-identical;
  a completed specification is explicitly not an implemented feature — the
  gate system exists to keep those apart.
- **Implementation was produced with coding agents under owner direction.**
  The commit and validation records are the observable history; this page
  deliberately makes no claims beyond them.

## Where this documentation fits

The public documentation set (README, this guide family, and
[distribution/README.md](distribution/README.md)) is checked mechanically
(`tests/docs/`, `scripts/check_claims.py`). The final-release pass will
re-verify every command against the release tag — see
[limitations.md](limitations.md#what-this-documentation-still-needs-for-final-release).
