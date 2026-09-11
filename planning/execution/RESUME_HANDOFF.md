# Fresh-session resume and evidence handoff

A new session loads only the project brief, decisions, glossary/invariants, its task and referenced contracts, plus the current repository state/commits. It does not need private chat history. A previous worker summary is a navigation aid, not proof.

## Resume procedure

Inspect Git status and current branch; do not overwrite uncommitted work. Read `execution/state.json`, verify accepted predecessors against actual merge commits and receipts, and run the planning validator. Confirm held file leases, environment/model/profile identity and current contract version. Re-run the smallest relevant acceptance before continuing; stale logs from another commit do not certify current code.

If a task was blocked by owner publication input, continue unrelated local work. If blocked by schema disagreement, find the proposal and accepted resolution before writing a consumer-specific workaround. An interrupted experiment resumes only with matching baseline/candidate/fixture/config digests; otherwise create a new attempt receipt while preserving old results.

## Required handoff record

Use [handoff.example.json](../templates/handoff.example.json) as the exact record shape. Fill actual values; null is appropriate for a genuinely unavailable provider-internal field or not-yet-run command, with an explanation. A real completed handoff cannot keep a claimed pass without a receipt path.

A handoff includes task/status, branch/working and merged commits, owned files, shared leases, contract version, exact dependencies, selected mode/model only when observable, interventions, executed commands and exits/counts, screenshots/manual checks, source/fixture/model hashes, rejected approaches, unresolved problems, rollback, next task/action and reviewer identity. Never include secrets or private PDF content in public receipts.

## State transition authority

Worker may propose `planned → in_progress → review` or `blocked`. Reviewer records accept/request-changes/blocked. Integrator alone records `accepted` after merged checks, or `rejected_complete` for a designated optional experiment with a complete negative result. Reopening a contract/dependency change invalidates affected receipts and returns consumer tasks to review/in_progress. Do not leave an old green gate attached to a new incompatible build.
