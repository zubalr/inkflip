# artifacts/a11y — T37 accessibility run receipts

Per-run evidence for TEST-37. Layout:

- `run-YYYY-MM-DD-test-a11y.json` — receipt for an actual
  `bun run test:a11y` invocation: date, environment, collected/passed/failed
  counts, per-leg results, and any violations found.
- `axe-expanded-finding.json` — machine-written by the expanded-finding axe
  leg of `tests/a11y/flows.spec.ts` on every run: full node targets and HTML
  for each serious/critical violation observed (overwritten per run).
- `manual/` — drop zone for manual AT receipts (NVDA/VoiceOver checklists,
  screenshots, DOM snapshots) consumed by
  `scripts/check_manual_receipts.py accessibility` once that checker exists.
  See `docs/accessibility/flows.md` for the checklist these receipts cover.
