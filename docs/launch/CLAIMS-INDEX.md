# Launch claims index

Prepared 2026-09-13 for T50. Each publishable claim maps to its verifiable
evidence in this repository, with its current status. Nothing here is a claim
of deployment, adoption, gate completion or final release; those are separate
owner actions after independent acceptance.

Status vocabulary:

- **ready** — evidence exists in this snapshot and is reproducible by the
  listed command/path.
- **source-preview** — capability and executed evidence exist on a yielded
  branch; not merged/accepted main-line capability.
- **pending** — evidence requires work not yet delivered (named below).

## Public claims and their evidence

| # | Claim (allowed wording) | Status | Evidence |
| --- | --- | --- | --- |
| 1 | "The example gallery shows six synthetic investigations, including a PDF whose painted `$100` extracts as `$1,000`" — scoped to this synthetic file under named reader versions | ready | `apps/web/public/examples/` (six dirs, `index.json`); `scripts/prepare_examples.py --check`; fixtures rights in `fixtures/manifest.json` |
| 2 | "The browser processes documents locally — no account, no upload endpoint" | ready | `bun run test:privacy` (canary: cold/warm/offline/receipt, real Chromium build); no upload path in `apps/web/src` |
| 3 | "Prepared pages keep working offline; preparation is explicit and digest-verified" | ready | T25 offline suite `tests/privacy/cache.spec.ts`; UI copy "Prepare for offline use" / "Remove offline assets" |
| 4 | "Reports are portable JSON or script-free HTML, with user-controlled scope and opt-in notes/renders" | ready | T23 accepted (merge `972406b`); `tests/reports/selection.spec.ts`; export docs in user guide |
| 5 | "Repeated occurrences stay individually addressable; order-only differences and unmatched text are classified, not collapsed" | ready | T20 accepted; `apps/web/src/features/viewer/occurrences/`; `tests/browser/ambiguity.spec.ts` |
| 6 | "A reader-upgrade workflow compares version-isolated profiles against an immutable baseline; changed ≠ regressed" | ready | CLI merged on main; executed 2026-09-13 on this branch (sequence + results in [case-study.md](../case-study.md)); `tests/examples/test_reader_upgrade.py` |
| 7 | "The static site deploys as pure Workers Static Assets — no Worker script, no compute bindings; unknown paths 404" | ready (preflight only) | `wrangler.json` + `scripts/check_static_dist.py` (exit 0 on real build); 12 tests in `tests/deployment/`; live `wrangler dev` route/header records (local evidence). **No deployment has been performed**; G5 hostname verification is an owner gate |
| 8 | "The shipped browser surface is license-cleared: every declared file hash-verified, third-party notices shipped" | ready (preparation gate) | `python3 scripts/check_distribution.py --release` (scope-explicit); `licenses/` + NOTICE; inventory/SBOM deterministic (twice-run identical). The **native application image is pending** — the gate's scope note says exactly what passed |
| 9 | "Known vulnerabilities: none recorded against the exact shipped versions as of 2026-09-13" | ready (dated) | `.private/distribution/advisory-scan/` raw OSV + bun audit outputs; evidence of a moment, re-run at closure |
| 10 | "tr46@0.0.3 MIT declaration carries no license text; it is not shipped in browser bytes" | ready (resolved classification) | content search of built dist (no tr46/whatwg-url markers); `licenses/README.md` |
| 11 | "Accessibility: WCAG-targeted checks pass" | ready (suite-scoped) | `bun run test:a11y` + merged T37 flows suite (14/14 at merge); **manual assistive-technology review and final visual polish remain pending** — do not publish an accessibility-conformance claim |
| 12 | "Performance budgets" | pending | T39 measured envelopes not established; no performance claims anywhere |
| 13 | "Fast / memory efficient" | pending | same as 12 — do not publish |
| 14 | "Used by teams / adoption" | forbidden | no such evidence exists; never publish |
| 15 | "Deployment URL" | forbidden until owner action | no live URL exists; publication is a separate owner decision |

## Pending external inputs (name, don't invent)

1. Merged-state acceptance of the native CLI/corpus/upgrade delivery and its
   documentation (integration owner) — the code is merged; acceptance and
   any remaining review are the owner's.
2. The container/application image (packaging lane) — the distribution gate
   explicitly scopes its pass to exclude it.
3. Manual assistive-technology evidence (a11y lane) and final visual
   captures (visual-polish lane) — dated current-build figures only.
4. Deployment, hostname verification and publication (owner).
