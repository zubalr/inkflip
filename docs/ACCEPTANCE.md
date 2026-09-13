# Validation and release evidence

`bun run verify` checks command registration, repository boundaries and the
validation harness. `python3 scripts/task_acceptance.py task Txx` executes a
task's effective commands. Neither command marks a task accepted. Empty,
failed or skipped required tests fail validation.

The harness records structured unittest, pytest, Node and Playwright results.
Custom runners write integer `collected`, `passed`, `failed` and `skipped`
counts to `INKFLIP_TEST_REPORT_FILE`. A completed task requires a nonempty
passing suite. Build commands may have no test counts.

## Record a candidate

Commit implementation changes before recording a run:

```sh
python3 scripts/task_acceptance.py task Txx --report artifacts/tasks/Txx/run.json
```

The report binds the source revision, commands, outputs, exit codes and actual
test counts. Changes to source during the run invalidate the report.

Working records remain in the ignored `artifacts/tasks/` directory. Archive a
task's current records in local Git object storage:

```sh
python3 scripts/acceptance_receipts.py archive Txx
```

This prints a full commit identity and updates `refs/local/validation/Txx`.
It does not change HEAD, source branches, the working tree or the normal
index. Ordinary branch pushes do not publish this ref. Back up the local Git
repository and working records together. A fresh clone does not contain
current local records and cannot claim release acceptance without them.

## Independent review and acceptance

An independent reviewer examines the exact source candidate, required cases
and manual observations. Record the real reviewer identity, findings, tested
revision and disposition in the task directory. Archive that review and use
its printed commit identity in the acceptance command:

```sh
python3 scripts/acceptance_receipts.py verify-run Txx
python3 scripts/acceptance_receipts.py record Txx --worker WORKER_ID --reviewer REVIEWER_ID --review-commit FULL_REVIEW_COMMIT --review-path artifacts/tasks/Txx/peer-review.md
python3 scripts/acceptance_receipts.py archive Txx
python3 scripts/acceptance_receipts.py verify Txx --commit FULL_ACCEPTANCE_COMMIT
```

`FULL_ACCEPTANCE_COMMIT` is the identity printed by the final archive command.
The state owner records it as `accepted_commit`, with the task's acceptance
JSON path as `accepted_receipt`, after source integration and successful
validation. Source and review authors must be distinct. Archive commands do
not grant approval or change task status.

Every exact acceptance criterion needs `status: executed` and a nonempty
`evidence` list in the worker receipt. Each path stays within that task's
directory and names a real nonempty file. Narrative belongs in `detail`.
Missing device checks and unavailable capabilities remain explicitly blocked.

Acceptance retains the existing version 1 schema: exact task and contract
identity, evaluated source revision and timestamp, successful command records,
evidence SHA-256 hashes, criterion references, and an independent approved
review. Historical receipts committed on source branches remain readable.

Local snapshots have exactly one source parent and may change only files in
their named task directory. Validation checks source ancestry and freshness,
immutable archived bytes, matching current evidence, command coverage and
review identity. Modified, missing or symlinked local evidence fails. Local
storage never substitutes for a test, a device observation or a review.

## Run release gates

`python3 scripts/gate.py G1` through `G4` validate accepted prerequisites and
execute their direct scenarios. They also check live blocking dependencies
before and after execution. Gates do not recursively accept their own tasks.

Freshness covers the task, its dependencies and shared scripts, configuration
and dependency manifests. Relevant source changes require affected checks
and reviews to run again. A green historical result cannot certify new code.

`pre-release` checks accepted capability gates and release prerequisites.
G5 requires an explicit HTTPS origin through `--target`. It performs checks;
publication and rollback remain separate operations.
