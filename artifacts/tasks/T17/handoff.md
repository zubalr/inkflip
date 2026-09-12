# Handoff: T17 (pdf-t17) — Earn the browser amount demo and prepared manifest

## Status
- **State**: Implemented, verified, ready for Devin Local independent review.
- **Worker**: `antigravity-t17`
- **Branch**: `work/antigravity/t17`
- **Base commit**: `b2b5db3ad497c27ca7988dffcfdec618e697b89a`
- **Candidate implementation commit**: `d39e607feda6f8d6c3443c678ac013435c5533b1`

## Delivered Components
1. `apps/web/public/examples/amount/`:
   - `index.html`: Browser amount demo card ("The amount that reads differently", F01 & F02).
   - `amount.css`: Strictly semantic design tokens from `tokens.css` (zero raw hex or rgba literals).
   - `amount.js`: Real PDF.js canvas rendering, pixel comparison engine (0 diff with clean control), and live file intake with hash audit.
   - `manifest.json`: Example manifest linking source, control, and covered twins.
   - `report.json`: Canonical sealed report artifact passing `@inkflip/contracts` validation.
   - Fixture PDFs: `mapping-amount.pdf`, `mapping-control.pdf`, `covered-amount.pdf`, `covered-control.pdf`.
2. `scripts/prepare_examples.py`:
   - Deterministic example generation script with `--check` support.
3. `tests/browser/amount.spec.ts`:
   - Playwright test suite covering all 6 acceptance criteria and WCAG AA accessibility.

## Verification Evidence
- `bun run test:browser -- tests/browser/amount.spec.ts && bun run test:fixtures`: 57/57 tests passed (7 browser + 50 fixtures) in 3.9s.
- `python3 scripts/task_acceptance.py task T17 --report artifacts/tasks/T17/run.json`: exit 0.
- `python3 scripts/acceptance_receipts.py verify-run T17`: verified with 57 tests passed.
- `python3 scripts/prepare_examples.py --check`: OK.
- `bun run build:web`: static web artifact built cleanly in 560ms (`dist/examples/amount/` verified).
- `bun run oxlint`: 0 errors.
- `bun run oxfmt --check tests/browser/amount.spec.ts`: formatted cleanly.
- `bun run verify`: 116/116 tests passed (49 bootstrap + 2 native boundary + 65 coordination + self-check).

## Boundaries & Constraints Respected
- All work committed strictly on local branch `work/antigravity/t17`.
- Zero pushes to `origin` or `homebase`.
- Zero writes to Beads (`bd`).
- Homebase untouched (never rebooted or power-cycled).
