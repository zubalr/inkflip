# Command and acceptance evidence

Run `bun run verify` for the checks currently implemented in the registry.
Run `python3 scripts/task_acceptance.py task Txx` for a task's effective
commands. Both fail when required tests are empty, skipped or unsuccessful.
Declared commands remain unavailable until their owners install the tools and
implement the suites. Neither command accepts a task in Beads.

The harness reads unittest result objects and JUnit XML from Node, pytest and
Playwright. Custom test runners must write a JSON object with integer
`collected`, `passed`, `failed` and `skipped` counts to the temporary path in
`INKFLIP_TEST_REPORT_FILE`. Every collected required case must pass. An expected
failure counts as skipped evidence. Check/build commands can have no test
counts, but a complete task or gate must include a nonempty passing suite.
Nested registered commands and gates propagate their counts to the task runner.
JUnit arguments and temporary report paths are added by the harness; suite
owners must not disable its reporter. T02 verifies the adapters against the
resolved pytest/Playwright versions before registering those suites as active.

After committing implementation changes, the coordinator records a run:

```sh
python3 scripts/task_acceptance.py task T01 --report artifacts/tasks/T01/run.json
```

`--report` requires committed source before and after the run. The JSON records
the evaluated commit, actual commands, output, exit codes and test counts.
Evidence and Beads audit files may still change so the coordinator can record
the results without pretending they existed before execution.

The coordinator writes `artifacts/tasks/Txx/acceptance.json` only after review
and merged-branch checks. Its version 1 format contains:

- `schema_version: 1`, exact `task_id` and `beads_id`, and `disposition` matching
  the permitted Beads disposition.
- `evaluated_commit` as a full Git commit, `evaluated_at` as the actual run time,
  and `contract_digest` from `acceptance_receipts.contract_digest(effective_task)`.
- `commands`: the task run's ordered records. Each `segment` matches the
  effective contract and executed `argv`; every command exits zero and every
  required suite supplies passing counts. `cwd` is `.` relative to the absolute
  recorded `checkout`, so receipts stay portable between prepared worktrees.
- `evidence`: task-local paths mapped to their SHA-256 digests. Include the
  worker receipt, command log, independent review, run JSON and any manual
  evidence relied on by the review. Required artifacts must be nonempty.
- `criteria`: every exact acceptance criterion mapped to one or more bound
  evidence paths. Reviewers assess whether those files substantiate the claim.
- `worker` and `review`: the review has `disposition: approved`, a bound `path`,
  and a nonempty `reviewers` list distinct from the worker. Reviewer approval
  remains a human/agent review decision; the validator checks its evidence
  structure and does not infer that a manual test happened.

Commit the evidence before setting `accepted_commit`, `accepted_receipt` and
`disposition` in Beads and closing the task. `task Txx --require-evidence` then
reruns commands and validates that committed acceptance. A worker's pending
receipt cannot satisfy it. Empty JSON, failed/skipped commands, missing review,
wrong criteria, changed evidence and stale code all fail.

Freshness compares the evaluated commit with the accepted commit and current
candidate over the task and dependency ownership scopes plus shared scripts,
tool configuration and dependency manifests. Changes there require a new
evaluation. This is conservative: later ownership handovers can require earlier
tasks to be revalidated before a release gate. Unrelated evidence-only commits
do not invalidate a result. Material scope changes need a coordinated contract
update; do not narrow freshness inputs to reuse old results.

`python3 scripts/gate.py G1` validates prerequisite acceptance and runs the
gate's direct scenarios. It never calls task acceptance recursively. A successful
gate writes its own candidate receipt. `pre-release` checks accepted G1–G4
owner tasks and T48–T50, then runs the final-review scenarios. G5 requires an
explicit HTTPS origin through `--target`; it runs checks only. Publication,
deployment and rollback remain separately authorized runbook operations.
