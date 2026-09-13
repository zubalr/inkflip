# Review notes — T49 preparation (user/developer docs and honest limitations)

## What this batch is

Two commits on `work/antigravity/independent-volume-2`, intentionally separate
so they can be integrated independently:

1. `4981999` — documentation: rewritten `README.md` plus new
   `docs/quickstart.md`, `docs/user-guide.md`, `docs/developer-guide.md`,
   `docs/architecture.md`, `docs/limitations.md`,
   `docs/development-history.md`, `CONTRIBUTING.md`, `SECURITY.md`.
2. `57eaa22` — docs-check tooling: `scripts/check_claims.py` +
   `tests/docs/` (rules, verified-commands manifest, unittest suites).

Evidence: `artifacts/tasks/T49/commands.log` (every command and exit code)
and `artifacts/tasks/T49/receipt.json` (worker-level, `disposition:
not_accepted` — acceptance belongs to the coordinator after review).

## What the reviewer should check

- **Claims wording** against `planning/launch/CLAIMS_LEDGER.md`: the README
  scopes the amount example to "this synthetic file under named reader
  versions"; privacy wording claims only what the T15 canary suite verifies;
  no safe/fraud/score/autonomy claims. The forbid-list in
  `tests/docs/claims-rules.json` is deliberately narrow — review whether any
  unsupported claim phrasing slipped through that a substring rule cannot
  catch.
- **Screenshots**: README links committed evidence images
  (`artifacts/tasks/T17/screenshots/amount-demo-card.png`,
  `artifacts/tasks/T13/screenshots/accessible-text-layer.png`) with captions
  naming the exact reader versions. Captions were written from the images and
  the T17 criteria evidence — verify they match your reading.
- **Command truth**: every command presented as working appears in
  `tests/docs/verified_commands.json` and exits 0 via
  `python3 scripts/check_claims.py --run-commands`. Commands that fail on
  this snapshot are documented as failing (test:browser, typecheck,
  format:check) with causes.
- **Licensing**: recorded as pending everywhere; ADR-003 cited as the
  planning decision; no "licensed under MIT" assertion anywhere (enforced by
  a must-not rule).

## Deliberate scope boundaries of this batch

- App help screens (`apps/web/src/pages/help/` — a T49 contract deliverable)
  were **not** touched: they are product UI owned by the browser lane. This
  is recorded as a gap for the final T49 pass.
- `config/acceptance-commands.json` was **not** edited (registry is a shared
  surface), so `tests/docs` is not registered as a registry command; it runs
  via the T49 contract command directly.
- No `.gitignore` change was made: the audit found no missing pattern; the
  only untracked debris observed during work was transient and ignored
  already (e.g. `__pycache__`).
- Stale `description` fields ("Scaffold: unfinished") in root and
  apps/web `package.json` are flagged in limitations.md but not edited —
  root/app manifests are another lane's shared surface.

## Known follow-ups for the final T49/T50 release pass

See `receipt.json → pending_for_final_release`: clean-machine install test,
release-tag re-verification, screenshot re-tie, capability-matrix update when
T20/T21/T23 land, native CLI docs when T30+ land, LICENSE/NOTICE via T47,
and a real SECURITY reporting channel when one exists.
