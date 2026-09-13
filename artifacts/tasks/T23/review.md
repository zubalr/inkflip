# T23 review — export selection, annotations and privacy preview

Independent reviewer: `subagent_explore` agent `38b0eb9d` (two rounds).

## Round 1 — CHANGES-REQUIRED

Reviewed `295acb0` (spec + implementation). One major, three minors, three nits:

- **F1 (major)** — `Workspace.tsx` built `source` as an inline literal; every
  note add/remove rebuilt `ExportController`, resetting `findings` to `"all"`.
  A deselected finding's text would silently re-enter the next download.
  **Fixed** in `8bb9823`: `probeReportId`/`sourceReportId` +
  `controller.restoreRequest` (sanitized to availability and finding ids);
  `ExportPanel` restores only when the sealed report identity matches.
  Covered by a new spec leg: deselect → author note → checkbox stays
  unchecked, download contains neither the finding nor the note.
- **F2 (minor)** — notes on deselected findings were pruned without a
  note-level line. **Fixed**: `notesExcludedWithFindings` count +
  `notes-excluded-with-findings` manifest line.
- **F3 (minor)** — `run.json` predated the committed spec layout.
  **Resolved**: command re-run on `8bb9823` (6/6). Residual line-number
  question from round 2 verified a Playwright transform artifact: `--list`
  on the committed file reproduces the recorded numbers deterministically;
  the report is faithful to the committed source.
- **F4/F5 (nits)** — redundant `context.close()` removed; "Notes" row added
  to the preview grid.
- **F6 (nit/a11y)** — notes controls nested in `role="option"`; deferred to
  T37 accessibility pass (pre-existing shared pattern).

## Round 2 — APPROVE-WITH-NOTES

Verified at `f4976a9` (fixes in `8bb9823`):

- F1 fix verified honest: restore runs during render (no flash of
  defaults), sanitizes to `findingChoices`/`availability`, and the
  engine still fails closed on unknown ids. A `report_id` collision can
  produce a displayed projection error, never dishonest bytes.
- F2 verified: counts only source annotations whose `finding_id` is absent
  from the projected findings, only under the notes opt-in; page-level
  notes correctly never counted.
- Regression check on the fix itself: `restoreRequest` confined to
  controller+panel; privacy defaults still hold for genuinely new reports.

Remaining nits (accepted, not blocking): `probeReportId` accepts any
string id (HEX64 tightening possible but a same-id collision still cannot
ship dishonest content); exclusion message wording also covers
unsupported-omission cases unreachable from the UI; per-render controller
rebuild is mildly wasteful but bounded.

## Verdict

**APPROVE-WITH-NOTES** at `f4976a9`, fixes at `8bb9823`. Ready to
integrate; acceptance command re-run on merged state per workflow.
