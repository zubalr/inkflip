# T17 Review — Browser Amount Demo and Prepared Manifest

- **Task:** T17 (pdf-t17)
- **Status:** Implemented, pending independent review
- **Candidate Implementation Commit:** `d39e607feda6f8d6c3443c678ac013435c5533b1`
- **Branch:** `work/antigravity/t17`
- **Base:** `b2b5db3ad497c27ca7988dffcfdec618e697b89a`
- **Worker:** `antigravity-t17`

## Implemented Deliverables

1. `apps/web/public/examples/amount/`:
   - `index.html`: Interactive demo card matching design tokens and accessibility standards.
   - `amount.css`: Pure token consumption (zero raw hex or rgba literals).
   - `amount.js`: Pinned PDF.js 6.3.289 browser reader integration, pixel comparison engine, and live file intake.
   - `manifest.json`: Example metadata cataloging F01 and F02 fixture files, hashes, and durations.
   - `report.json`: Canonical sealed report artifact validated by `@inkflip/contracts`.
   - 4 fixture files: `mapping-amount.pdf`, `mapping-control.pdf`, `covered-amount.pdf`, `covered-control.pdf`.
2. `scripts/prepare_examples.py`:
   - Standalone generation script with `--check` support.
   - Validates byte identity of generated files against disk.
3. `tests/browser/amount.spec.ts`:
   - Comprehensive Playwright test suite covering all 6 acceptance criteria and WCAG AA accessibility.

## Verification Summary

- `bun run test:browser -- tests/browser/amount.spec.ts && bun run test:fixtures`: 57 passed (7 browser + 50 fixtures), exit 0.
- `python3 scripts/task_acceptance.py task T17 --report artifacts/tasks/T17/run.json`: exit 0.
- `python3 scripts/acceptance_receipts.py verify-run T17`: verified, 57 passed, exit 0.
- `python3 scripts/prepare_examples.py --check`: OK, exit 0.
- `bun run build:web`: built in 560ms, exit 0.
- `bun run oxlint`: 0 errors.
- `bun run oxfmt --check tests/browser/amount.spec.ts`: 0 format issues.
- `bun run verify`: 116/116 tests passed, exit 0.
