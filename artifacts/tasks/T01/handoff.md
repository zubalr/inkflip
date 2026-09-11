# T01 handoff — worker report (not an independent review)

**Task:** T01 — Bootstrap the separate monorepo and honest origin
**Branch:** `work/pdf-t01` · **Beads:** `pdf-t01` (claimed as `swe2-t01`)
**Commits:** `28b3ed8405f8365262bac6d28c55b35efc3f3181` implementation;
the commit containing this file adds the evidence receipt and handoff.

## What now works

- `bun run verify` / `python3 scripts/task_acceptance.py run verify` → exit 0
  (self-check, 24 bootstrap tests, 2 native boundary tests, 20 coordination tests).
- `bun run <documented-name>` resolves for the whole command surface; declared
  suites fail explicitly with the missing prerequisite and owner (`exit 2`).
- `python3 scripts/task_acceptance.py task Txx` executes effective task commands
  through the shared overrides; unittest discovery is pre-counted and re-parsed —
  zero collected/ran tests is always a failure.
- `python3 scripts/gate.py Gx` verifies Beads acceptance (closed + disposition +
  ancestor commit + committed receipt blob) then runs adapted scenario commands
  non-recursively; writes `artifacts/gates/<G>/receipt.json` only on success.
- Origin: exact MIT LICENSE blob preserved; `docs/ORIGIN.md` documents
  provenance, conceptual reuse, and the no-legacy-runtime boundary.
- Styles: `apps/web/src/styles/` holds central tokens + global baseline +
  the CSS Modules contract; T06 takes ownership after acceptance.

## Acceptance evidence

Executed results with exits and counts are in `receipt.json` and
`commands.log`; a labeled scaffold-style screenshot is `scaffold-preview.png`
(static approximation — React/Vite are not installed until T02).

## Known limits / requests

- `python` is absent on this host; the harness's recorded interpreter map
  resolves it to `python3`. CI uses `python3` directly.
- No installs/locks (T02). Node observed v26.7.0 ≠ planned 22.16.0 (T02 pins).
- `review.md` left for the independent reviewer; `docs/ATTRIBUTION.md` is
  outside T01 scope — attribution lives in `docs/ORIGIN.md`.
- Registering suites in `config/acceptance-commands.json` later is a
  root-manifest-owner change (T02 after this task) — later suite owners cannot
  edit it within their own scope; route via the owner/coordinator.

## For the reviewer

Suggested checks: `python3 -m unittest discover -s tests/bootstrap -v`,
`... -s native/tests/bootstrap -v`, `python3 scripts/task_acceptance.py run verify`,
`python3 scripts/task_acceptance.py task T01`, `python3 scripts/gate.py G1`
(expect exit 1 — nothing is accepted yet), `bun run test:browser`
(expect exit 2). Confirm `planning/` stays byte-identical and
`third_party/origin/mib-intake/LICENSE` sha256 is
`3f1e48ee93685ecf2c49f768ad888dc47859b057f3b90c9f04f132315edf0c6d`.
