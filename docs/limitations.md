# Limitations

This page separates three things that scaffold-era text used to blur: what is
**implemented and verified** on this snapshot, what **exists but currently
fails or is incomplete**, and what is **specified but not built**. It also
states the limits of the method itself. Status here reflects this exact
snapshot; [development-history.md](development-history.md) explains how the
project got here and what remains.

## Implemented and verified on this snapshot

- Browser investigation flow: open local PDF → render (PDF.js) → read (text
  layer, requested OCR) → compare → findings with coverage → export JSON /
  script-free HTML → reopen saved JSON. Cancel/replace of running work.
- Privacy: no-egress canary suite (cold/warm/offline/receipt) against the
  real production build; same-origin staged engines and model data; explicit
  offline failure instead of silent network fallback.
- Native Python reader library: PDFium, pypdf, rendered-region Tesseract
  adapters; bounded structural observations; supervised runtime with atomic
  partial results; 196 tests.
- Original fixture generator (rights-cleared synthetic documents) and the
  prepared public amount example with its clean-mapping control.
- Command harness with fail-closed registry, acceptance receipts, gate
  runner, and the check suites enumerated in
  [quickstart.md](quickstart.md#run-the-checks).

## Known failures in this snapshot

These are real, reproducible defects or gaps — listed here so nobody has to
rediscover them:

- **`bun run test:browser` fails (exit 1).** The registry entry invokes
  Playwright with no path argument from the repository root, so discovery
  sweeps everything — including committed review-probe artifacts under
  `artifacts/tasks/T13/`, one of which (`independent-review-probe-r2.spec.ts`,
  an `import` statement after test bodies) is not valid module syntax. The
  harness then correctly reports "zero tests collected". The individual
  browser specs pass when invoked with an explicit path (as recorded in task
  evidence); the fix — a scoped Playwright config or registry paths — belongs
  to the browser-test owner.
- **`bun run test:regression` and `bun run check:static-dist` fail closed
  (exit 2)** with their owning tasks named (T34 and T48): the regression
  suite and the static-dist/deployment preflight do not exist yet. This is
  the registry working as designed.
- **`apps/web` `typecheck` fails (exit 2)** with `TS5097` errors: source
  files under `packages/runtime/` import `.ts` paths in a way the web app's
  standalone `tsc --noEmit` run rejects. The production build passes (the
  bundler resolves these); the standalone typecheck wiring needs repair.
- **`apps/web` `format:check` fails (exit 1)**: no oxfmt config file exists
  yet, so the formatter's default check rejects the tree.
- **A from-scratch install on a never-used machine has not been performed.**
  The quickstart commands were verified twice: on the provisioned
  macOS/arm64 development machine, and in a fresh clone with an empty
  dependency tree (`bun install` → 86 packages, exit 0; then `bun run
  verify`, `bun run build`, dev/preview servers, and the native suite — all
  passing). Bun's download cache was warm in both cases, so cold-cache
  install behavior was not measured. The full clean-environment install test
  remains release work and install success is not claimed beyond what is
  stated here (per
  [planning/launch/README_AND_CASE_STUDY.md](../planning/launch/README_AND_CASE_STUDY.md),
  install success must not be claimed until that test exists).
- **`apps/web/package.json` and root `package.json` still describe the
  project as "Scaffold: unfinished"** in their `description` fields — stale
  text, untouched here because root/app manifests are shared-surface files
  owned by another lane.

## Specified but not built

From the frozen plan ([planning/PROJECT_BRIEF.md](../planning/PROJECT_BRIEF.md))
and live task state, the following are **not available in this snapshot** and
must not be presented as working:

- **The `inkflip` native CLI.** The command contract
  ([planning/architecture/CLI_AND_REGRESSION.md](../planning/architecture/CLI_AND_REGRESSION.md))
  specifies `inspect`, `compare-readers`, `models prepare`, `corpus run`,
  `baseline create`, `compare`, `report`, `replay`, `validate` — none are
  implemented. Only the Python reader library underneath it exists.
- **Corpus runs, version-isolated reader profiles, immutable regression
  baselines, and the local reader-upgrade CI example** (the T32–T35 lane).
- **The complete public gallery** — one synthetic example is prepared and
  verified; the full six-example set with prepared manifests is pending (T21).
- **Export selection, annotations and the privacy preview** (T23) — export
  today is whole-report JSON/HTML only.
- **Explicit offline static/model cache lifecycle** (T25) beyond what the
  privacy suite already pins (warm reuse and explicit offline failure).
- **Accessibility and visual finish reviews**, measured **performance
  budgets**, **native containment/failure-recovery hardening**, and
  **browser/native parity verification** (T37–T40, T46).
- **Distribution artifacts**: SBOM, vulnerability gate, root `LICENSE`,
  `NOTICE`, complete third-party notice bundle for redistribution (T47).
- **Deployment preflight and any public deployment** (T48, and T54 which
  additionally requires an explicit owner decision).
- **Gates G2–G5.** Only G1 (first integrated own-file evidence journey) has
  been earned so far.

## Method limits (what the tool cannot establish)

These are product invariants, not missing features:

- **A reading difference is not a verdict.** PDFium, pypdf, PDF.js and
  Tesseract disagreeing about an occurrence establishes only that those named
  readers returned different text. The app does not decide which reading is
  correct, and never characterizes a document as fraudulent, malicious,
  unsafe or authentic (invariant I06).
- **OCR is evidence, not ground truth.** OCR reads the rendered pixels of the
  pages you select, in English only (pinned `tessdata_fast` `eng` pack), with
  a bounded per-run page/time budget. It is limited by rendering quality and
  its own recognition errors; the app records reader identity and version
  with every reading (invariant I13) so an OCR result is always traceable to
  the engine that produced it.
- **Coverage is finite.** Absence of findings on unselected pages, or on
  checks that did not run, means nothing. The UI reports what was checked;
  the tool deliberately refuses to imply completeness it does not have.
- **Alignment abstains.** When correspondence between readings is ambiguous,
  the comparator records uncertainty instead of forcing a match; a clean
  alignment is evidence, an abstention is honesty, and neither is a score.
- **Replay is bounded.** An exported report carries the evidence needed to
  review it elsewhere, but "replay" in the strong sense (re-deriving a
  report from original bytes in a recorded environment) is the pending
  T30/T35 work, not a property of today's exports.
- **No security guarantee by slogan.** The no-egress canary suite verifies
  the *implemented browser path* on the tested build and browsers. It does
  not claim that browsers are immune to compromise, that every conceivable
  exfiltration channel is impossible, or anything about other software on
  your machine. The native side is local-only tooling on a machine you
  control; its containment hardening is still pending (T40).

## Environment and platform limits

- Browser suites are exercised in Chromium. Other browsers are untested here
  (parity is the pending T46 task).
- One active document per workspace; the workspace session is in-memory and
  exports are the persistence mechanism.
- Native tooling targets the pinned Python 3.13.15 on macOS/arm64 (verified
  here) and Linux (exercised in task evidence); other platforms are untested.
- Very large documents are handled per-page with bounded budgets, but the
  measured performance envelopes (device budgets, cold/warm timings) are
  pending T39 and are not claimed anywhere in this documentation.

## Pending decisions recorded honestly

- **License/copyright finalization is pending.** The recorded planning
  decision (ADR-003) selects MIT for newly authored code and documentation,
  and the origin record preserves the upstream provenance
  ([docs/ORIGIN.md](ORIGIN.md)); the repository-root `LICENSE`/`NOTICE` files
  and the final copyright-holder statement are part of the unfinished T47
  distribution work. No license claim beyond that is made anywhere in this
  documentation set.
- **No support commitments exist.** There is no support channel, SLA or
  roadmap commitment; [SECURITY.md](../SECURITY.md) describes exactly what
  reporting paths do and do not exist today.

## What this documentation still needs for final release

Tracked as the T49/T50 release-refresh scope: re-verification of every
command against the release tag, a clean-machine install test, screenshots
re-tied to the tagged build, the finished capability matrix once T20/T21/T23
land, and links checked together with the other documentation owners.
