# T18 handoff — G1 integrated own-file evidence gate

**Status:** `implemented_pending_review` · **Commit:** `c3f2c84c157c0e22a5cb4e4751761a6f21d0453e` · **Branch:** `work/devin/t18` (pushed)

## Summary for reviewer

`tests/gates/g1.spec.ts` implements the registered G1 scenario as 3 serial
Playwright tests against **real built production mounts** — the salvaged
spec was rewritten because it targeted nonexistent APIs/fixtures
(`fixtures/development/scan-rendered-text.pdf`, invented `__t15` signatures).

| Leg | Surface | Covers |
|---|---|---|
| 1 | `__t08` open mount | file chooser, F01 amount vs control, pdf.js extract/raster, region commit, real coordinator plan/admission/cancel/replace, stale-generation rejection |
| 2 | `__t15` privacy harness | real tesseract OCR (staged same-origin assets), text-vs-OCR comparison, F07 rotation/UserUnit, F03 searchable scan, F21 canary markers, egress capture |
| 3 | harness + `__t22` import + main shell | sealed report → T16 ExportPanel → real JSON/HTML downloads → T22 import/replay/source-verify → main-app reopen → cache-warm + offline OCR |

**Result:** `bun x --no-install playwright test tests/gates/g1.spec.ts` →
**3 passed (3.9s)**. Captures: `artifacts/gates/G1/captures/` (0 disallowed
marker hits; the only violations are the whitelisted downloads channel).

## What the reviewer should check

1. Assertions are honest, not weakened — the three iteration fixes moved
   assertions *to* the contract-truthful values (`estimated` precision,
   dependency-gated OCR dispatch, never-retry failure reason), documented in
   `commands.log`.
2. No mocks/skips: grep for `skip|fixme|route(` in the spec — the only route
   use is `context.setOffline(true)` for the offline leg.
3. Egress scan is real: `assertCaptureClean` fails on any marker in
   request/console/storage/server channels; `downloads` is whitelisted only.
4. **Gate command status:** `python3 scripts/gate.py G1` exits 1 on this
   branch — prerequisite ancestry vs HEAD (this branch predates main's
   receipt-refresh merges). Verified 19/19 prerequisites pass against
   `origin/main`; post-merge the same Playwright command runs. This is the
   designed gate-on-merged-branch flow per the T18 contract ("Run G1 on the
   merged branch").
5. F24 is named in the contract's `fixture_ids` but does not exist in the
   repo — flagged, not exercised.

## Known limitations (carried from run.md)

- T13 composition gap: the spec composes real feature mounts + harness + app
  shell rather than one unified page (same pattern as accepted T15).
- In-page capture cannot see OS/browser-level channels; release profile needs
  proxy/firewall capture.
- Offline = warm-page `setOffline`; no service worker shipped.
