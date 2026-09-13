# T21 review — six public examples + gallery

Independent reviewer: `subagent_explore` agent `0d3aa389` (round 1).

## Round 1 — CHANGES-REQUIRED

All five acceptance criteria **passed on substance** — the reviewer
verified sealed captures bound to committed bytes on all six cards, real
import through the session gate, deterministic manifest derivation, and
rights text. Required items were process and hygiene:

- **F1 (high, process)** — `App.tsx`/`Home.tsx`/`Workspace.tsx` edits
  exceeded the frozen `allowed_scope`; `OWNERSHIP.md` requires an
  explicit composition lease for gallery integrations. **Resolved** by
  `docs/proposals/T21.md` §1: the integrator grants the lease — the
  seams are additive-only, required (a gallery needs an entry point),
  and verified non-breaking by smoke + T13/T16/T17 regressions.
- **F2 (medium, process)** — shipped cards `F01,F02,F03,F07,F11,F12`
  deviate from planned `F01,F03,F04,F07,F12,F14`. **Resolved** by
  `docs/proposals/T21.md` §2: F04/F14 ship as executed companion
  variants (contrast-* under `covered`, unicode_* under `amount`);
  F02/F11 promoted as the more distinct standalone mechanisms; every
  planned fixture still has executed evidence. Accepted — strengthens
  the no-padding criterion.
- **F3 (low-med, honesty)** — `examples/amount/index.html` static
  `142 ms` disagreed with the sealed 249 ms; dead `tokens.css` link;
  orphan `covered-*.pdf`. **Fixed** — static timing mirrors the sealed
  report, dead link and orphans removed; the dev-only pdfjs import path
  is disclosed as a pre-existing T17 limitation in the scope record.
- **F4 (medium, test strength)** — the suite never recomputed seals.
  **Fixed** — every committed report (6 primary + 16 variants) now
  re-verifies `report_id`/`run_key` via `@inkflip/contracts`, schema-
  validates variants, binds documents to staged sources, and
  cross-checks `index.json` fields against manifests (7/7).
- **F5–F9** — commands.log path/wording corrected; smoke.spec header
  fixed (committed suite, not temporary); CSS token nits; loader now
  rejects `..` segments; stale `exampleError` cleared on new example id.

## Verified-clean highlights (reviewer evidence)

- All six cards: `report.document.sha256` == index source sha256 ==
  manifest file sha256; `report_id`/`run_key` recompute; `live`+`complete`.
- `capture.mjs` is genuine — real build, real Chromium, session-state
  reports re-verified against offered bytes before writing.
- The `?example=<id>` flow runs the fetched report through the real
  strict import gate (seal recompute included); traversal impossible via
  the `[a-z0-9-]+` id charset.
- `prepare_examples.py` is deterministic and fully derived — every
  evidence field read verbatim from committed reports/bytes.

## Verdict

**APPROVE** after the recorded resolutions — implementation substance
unchanged; process records and hygiene items closed in `afe15b9`.
