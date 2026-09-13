# Limitations

This page separates three things: what is **implemented and verified** on
this snapshot, what **exists but currently fails or is incomplete**, and what
is **specified but not built**. It also states the limits of the method
itself. Status reflects this exact snapshot and is dated evidence, not a
permanent claim.

## Implemented and verified on this snapshot

- Browser investigation flow: open local PDF → render (PDF.js) → read (text
  layer, requested OCR) → compare → findings with coverage → export JSON /
  script-free HTML with selectable scope, opt-in notes and page renders →
  reopen saved JSON through the same validation boundary. Cancel/replace of
  running work; large documents and narrow layouts stay usable.
- Evidence UX: every occurrence a finding names is individually addressable;
  identical strings are never collapsed; order-only duplication is separated
  from genuinely different readings; unmatched text is never counted as
  missing; human notes on findings are opt-in for export and never become
  machine readings.
- Privacy: no-egress canary suite (cold/warm/offline/receipt) against the
  real production build; same-origin staged engines and model data; explicit
  offline failure instead of silent network fallback.
- Native Python reader library: PDFium, pypdf, rendered-region Tesseract
  adapters; bounded structural observations; supervised runtime with atomic
  partial results.
- Original fixture generator (rights-cleared synthetic documents) and the
  prepared public amount example with its clean-mapping control.
- Command harness with fail-closed registry, acceptance receipts, gate
  runner, and the check suites enumerated in
  [quickstart.md](quickstart.md#build-and-check).

## Known snapshot defects

Real, reproducible issues on this snapshot — listed so nobody has to
rediscover them. Each is dated; when one is fixed, this list and
`tests/docs/snapshot-facts.json` change together in a reviewed change.

- **`apps/web` `typecheck` fails** with `TS5097` errors: source files under
  `packages/runtime/` import `.ts` paths in a way the web app's standalone
  `tsc --noEmit` run rejects. The production build passes (the bundler
  resolves these); the standalone typecheck wiring needs repair.
- **`apps/web` `format:check` fails**: no oxfmt config file exists yet, so
  the formatter's default check rejects the tree.
- **Setup on a never-used machine is close but not fully proven.** The
  quickstart procedure was verified on 2026-09-13 in a fresh clone with
  isolated, empty caches (network preparation recorded separately from
  offline processing, which ran behind a dead proxy). What remains unproven
  is a host where the tools themselves (Bun, uv, compilers, browsers) have
  never been installed — that step is outside this repository's control.
- **`bun run test:fixtures` has one erroring test on a fresh checkout**
  (found 2026-09-13): `tests/fixtures/test_catalog_followup.py` reads a
  baseline-hashes file from the working records directory, which the
  local-only migration removed from tracking — the test needs its baseline
  re-homed into tracked files. The other 69 fixture tests pass.
- **`bun run test:regression` and `bun run check:static-dist` fail closed**
  with their owning tasks named: the regression suite and the
  static-dist/deployment preflight do not exist yet. This is the registry
  working as designed, not a defect.

## Specified but not built

The following are **not available in this snapshot** and must not be
presented as working:

- **The `inkflip` native CLI.** The command contract
  ([planning/architecture/CLI_AND_REGRESSION.md](../planning/architecture/CLI_AND_REGRESSION.md))
  specifies `inspect`, `compare-readers`, `models prepare`, `corpus run`,
  `baseline create`, `compare`, `report`, `replay`, `validate` — the full
  CLI and corpus workflow is still being integrated. Only the Python reader
  library underneath it exists.
- **Corpus runs, version-isolated reader profiles, immutable regression
  baselines, and the local reader-upgrade CI example.**
- **The complete public gallery** — one synthetic example is prepared and
  verified; the full six-example set with prepared manifests is in progress.
- **Measured performance budgets, native containment/failure-recovery
  hardening, and browser/native parity verification** — open work.
- **Deployment preflight and any public deployment** — the static-dist
  check is fail-closed until its owner lands it, and any deployment is a
  separate owner decision.
- **Gates beyond G1.** Only the first integrated own-file evidence gate has
  been earned so far.
- **Experiment-derived reader improvements**: no experiment candidate
  (secondary reader, native RapidOCR complement, raster-geometry variants)
  is present in this snapshot; none was accepted.

## Method limits (what the tool cannot establish)

These are product invariants, not missing features:

- **A reading difference is not a verdict.** Named readers disagreeing about
  an occurrence establishes only that those readers returned different
  text. The app does not decide which reading is correct, and never
  characterizes a document as fraudulent, malicious, unsafe or authentic.
- **OCR is evidence, not ground truth.** OCR reads the rendered pixels of
  the pages you select, in English only (pinned `tessdata_fast` `eng` pack),
  with a bounded per-run page/time budget. Reader identity and version are
  recorded with every reading, so an OCR result is always traceable to the
  engine that produced it.
- **Coverage is finite.** Absence of findings on unselected pages, or on
  checks that did not run, means nothing. The UI reports what was checked;
  the tool deliberately refuses to imply completeness it does not have.
- **Alignment abstains.** When correspondence between readings is ambiguous,
  the comparator records uncertainty instead of forcing a match; a clean
  alignment is evidence, an abstention is honesty, and neither is a score.
- **Replay is bounded.** An exported report carries the evidence needed to
  review it elsewhere, but "replay" in the strong sense (re-deriving a
  report from original bytes in a recorded environment) is not a property of
  today's exports.
- **No security guarantee by slogan.** The no-egress canary suite verifies
  the *implemented browser path* on the tested build and browsers. It does
  not claim that browsers are immune to compromise, that every conceivable
  exfiltration channel is impossible, or anything about other software on
  your machine.

## Environment and platform limits

- Browser suites are exercised in Chromium. Other browsers are untested here
  (parity is open work).
- One active document per workspace; the workspace session is in-memory and
  exports are the persistence mechanism.
- Native tooling targets the pinned Python 3.13.15 on macOS/arm64 (verified
  here) and Linux (exercised in task evidence); other platforms are untested.
- Measured performance envelopes (device budgets, cold/warm timings) are not
  established and are not claimed anywhere in this documentation.

## Licensing and support status

- Inkflip is licensed under the MIT License ("Copyright (c) 2026 zubair"),
  the owner's recorded 2026-09-13 decision; see the repository LICENSE.
  Third-party notices: [NOTICE](../NOTICE) and
  [distribution/README.md](distribution/README.md). One third-party item
  (tr46 0.0.3) has a recorded MIT declaration whose text body could not be
  established from authoritative sources — kept visible there.
- **No support commitments exist.** There is no support channel, SLA or
  roadmap commitment; [SECURITY.md](../SECURITY.md) describes exactly what
  reporting paths do and do not exist today.

## What this documentation still needs for final release

Re-verification of every command against the release tag, the
never-used-host install proof, screenshots re-tied to the tagged build (the
prepared gallery may change them), the finished capability matrix once the
gallery and deployment preflight land, and links checked together with the
other documentation owners.
