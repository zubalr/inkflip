# Devin coordination with Mac Antigravity and Homebase ZCode

The owner approved this private Git remote, source sharing with the three
selected harnesses, implementation commits, pushes, review and integration.
Run a substantial pass with each app's native orchestration. Resolve ordinary
failures, retries, merge conflicts and context exhaustion without another task
prompt. Public release/deployment (T54) still needs a separate owner decision.

`execution/passes.json` is a static division of responsibility, not live state.
Beads owns tasks, claims, dependencies, notes, pass checkpoints and acceptance.
Native harnesses own execution. Do not create a second queue or mirror task
status into Markdown/JSON. Immutable evidence is output, not a tracker. Do not
run the frozen planning package's bootstrap helper.

## Startup and state

After a delivered user message, desktop restart or cancellation, reconcile every
unfinished native child against its actual provider status. Queued UI message
delivery can cancel descendants as well as the coordinator turn. Resume stopped
children on their saved grants and checkouts; when resume is unavailable,
preserve their findings and admit exactly one replacement writer. Verify fresh
tool activity or a checkpoint before reporting recovery. Use Beads notes for
feedback while useful children run; avoid queued UI messages until they finish.


The active setup is Devin Local SWE-2 coordinating on the Mac, Antigravity on
the Mac, and ZCode Goal mode on Homebase. Devin alone assigns work, writes Beads, publishes
GitHub state, integrates candidates and accepts product tasks. Both worker apps
remain subordinate to those grants, including their native subagents.
Read `docs/HOMEBASE.md` for the concrete work allocation, SSH relay, activation,
checkpoint/review loop and startup paths. Codex continuation and Devin Cloud are stopped.
Only the canonical Mac integration session writes Beads or publishes to GitHub.
Mac linked worktrees use its existing database; Homebase uses a native read
replica restored from its local Git relay. Neither host initializes a competing
tracker or shares an embedded database over the network.

Use Beads 1.2.2. Mac control reads use `native_pass.py status APP` without sync;
Homebase control reads use `status zcode --sync` from its canonical main after
fetching the relay's current code. A failed state read is a blocker. Mac publishes
code and native Dolt state, then `homebase_relay.py publish`; the coordinator
polls `homebase_relay.py collect` to receive ZCode checkpoints. These helpers
transfer existing Git/Beads objects and do not manage model execution or task state.
While any ZCode grant is active, every coordination cycle runs
`homebase_relay.py collect <task>` (or checks `refs/heads/hb/inkflip/<task>` on
the handoff remote) before reporting that lane's state; local and origin
`work/*` refs only advance after a collect, so they cannot show a new inbound
checkpoint. Record actual delivered/collected/reviewing/feedback states; when
polling is not continuous, report the last collected state honestly rather than
claiming a live wait.

Dispatch only from clean, published canonical Mac main with
`git config inkflip.role integrator`. Homebase's role is `worker`. These settings
are accident guards, not security identities. Keep writers in isolated task
checkouts. Before publishing Beads, commit pending native Dolt transitions and
resolve any sync error. The historical `coordination.py start`/`start-review`
self-claim commands are retired and refuse; native admission runs only
through `native_pass.py dispatch` from the canonical integration checkout.

Use the exact T02 toolchain and frozen locks; dependency installation and Linux
support require actual execution on the target platform. Read current Beads
records and acceptance evidence rather than assuming the old scaffold state or
that a macOS/Linux-arm64 result establishes Linux-amd64 behavior.

## Devin Local models and native execution

Use Normal mode with SWE-2 Max selected and Subagents (Preview) enabled. Delegate
with the built-in `subagent_general` profile, which inherits the parent's model.
Supply each subagent its task, checkout, scope, budget and applicable repository
instructions; it does not inherit the parent's conversation history. For research
or independent review, give that general subagent a read-only assignment.

The owner selected the free SWE-2 Desktop/CLI offer. Keep the parent and general
subagents on SWE-2; do not use Cloud handoffs, paid fallback models, explore
subagents, default custom profiles or Quick Review with an unverified model.
The explore/default router can choose a different model. If SWE-2 or the required
native capability is unavailable, preserve work and report the specific blocker.
Prompt text cannot choose a model for a subagent or bypass provider permissions.

Devin Local supports native foreground/background subagents and session resume;
workflows are currently unsupported. Use native agent execution without claiming
Dynamic Workflows were created. If a background subagent hits an unapproved
permission, resume it in the foreground for the native approval rather than
changing global permissions. Native subagents may run concurrently when their concrete assignments are
independent. The coordinator accounts for the parent and every descendant in
the current Beads wave; app-native execution never authorizes extra task claims.

Policy checked September 12, 2026 in Qatar:
[pricing](https://devin.ai/pricing) limits the SWE-2 offer to Desktop/CLI through
October 10, 2026; [quota docs](https://docs.devin.ai/desktop/accounts/quota) say
free models do not consume quota. The [Local agent docs](https://docs.devin.ai/desktop/devin-local)
and [subagent docs](https://docs.devin.ai/cli/subagents) describe these capabilities
and model routing. Recheck pricing when the offer expires; do not silently switch
to a paid route.

The active independent workbench routes are in `execution/passes.json` and
`docs/plans/independent-workbenches/README.md`. Admission mode `dependencies`
selects the task's actual stage, then checks Beads readiness, fresh accepted
predecessors and scope/capacity. A later stage number alone does not block work.
`pdf-pass1` through `pdf-pass3` remain completion checkpoints: only the coordinator
closes them after all listed tasks and actual gates pass. T54 remains separate.

## Dispatch and isolation

On clean, published main Devin runs, for example:

```sh
python3 scripts/native_pass.py dispatch T29 --app devin
python3 scripts/native_pass.py dispatch T13 --app antigravity
python3 scripts/native_pass.py dispatch T05 --app zcode
```

The command checks actual readiness, predecessor receipts, implementation-stage membership,
ownership, scope conflicts and any configured finite capacity. It claims the task and stores
`metadata.execution`: app, branch, exact base commit, actual task pass and workbench (for routed tasks). Launch only
after successful Beads publication. A publication failure leaves a recoverable
local claim; recover sync/publication rather than creating a second claim.
Never force logical Beads conflict resolution or discard local changes. The
relay alone handles native Git storage rollover for `refs/dolt/data` with an
exact observed-SHA lease; see `docs/HOMEBASE.md`. Publish each ZCode grant
to the Homebase relay before expecting its worker to see it.

For a non-product follow-up, use its existing Beads ID and an explicit grant:

```sh
python3 scripts/native_pass.py dispatch-followup pdf-g78 --app zcode \
  --mode audit --scope artifacts/followups/pdf-g78/ \
  --instructions-file /tmp/inkflip-g78-audit.txt
```

Write the concrete assignment to the instructions file first. The issue must be
open, unassigned and dependency-ready. Audit grants allow writes only to that
follow-up's evidence directory. Implementation grants require explicit write
scopes and the same exclusive ownership checks as product tasks. Grants retain
their exact base, branch and pass. Workers cannot turn an audit into implementation.
Do not use follow-ups to bypass product task ownership, dependencies or acceptance.

`status APP` includes these grants in `assignments`, with `kind: followup`,
the original `pdf-...` ID, `instructions`, `mode` and `allowed_scope`.
An assignee without an execution grant appears in `undelivered`; notes alone
do not authorize execution. Only Devin reconciles legacy note assignments:
confirm the old writer has yielded, preserve its work, then publish a proper
grant or record completed evidence. Do not clear a live assignment to redispatch it.

During the upgrade, preserve an explicitly scoped coordinator grant that the
existing native worker already acknowledged under the previous note protocol.
That worker may finish its current revision and return a checkpoint on its
already-authorized branch; an empty new inbox does not revoke that grant.
The coordinator records the actual acknowledgement, branch/base and return ref,
then reconciles the structured grant after the writer yields. Do not rename a
live branch, reuse a completed product task's acceptance, or treat this migration
rule as permission to start new work from an unacknowledged note.

After publishing a grant, verify it appears in the target worker's synced inbox.
Then require a native-session acknowledgement or a committed checkpoint before
reporting pickup. A successful relay publication proves delivery, not execution.
Record acknowledgements, native session IDs and exact collected commits in Beads.
Workers return these facts through evidence or their existing native messages.
An overdue acknowledgement calls for inspection of the existing session, not a
second writer. Resume only confirmed stopped work, retaining its branch and edits.

If grant publication fails, preserve the local claim and repair publication.
Commit pending Dolt transitions only when present, push state, and publish the
relay before resuming the existing grant. Do not rerun dispatch to replace it.
When a provider ends a worker turn, use its supported resume facility; an empty
inbox or a shell process alone does not prove that native execution is waiting.

Keep at most five active execution slots across all workbenches, including native
children; lower provider limits apply. The dispatcher limits active grants to
five. A must additionally count actual sessions and descendants in Beads before
launch: a grant count alone cannot observe provider processes. A null app budget
does not waive the global limit. Reserve independent review capacity and replace
a yielded writer with its reviewer instead of adding a sixth session. Historical
native UI cards are not a live count. Do not spawn idle recursive supervisors.
Use native general SWE-2 subagents and Antigravity's installed native facilities.
ZCode uses its existing Goal on Homebase. Codex stays inactive after this transfer.
Only one heavy OCR/corpus/performance run may execute at a time; record its holder
in Beads and obtain an explicit release before transferring the reservation.

For a grant, fetch origin/main and the assigned branch. Use one isolated
worktree/clone per writer. If the branch exists, resume its committed work;
otherwise create it at the grant's exact base. The prepared Mac app folder is
a reusable starting checkout, not permission to overwrite it. Inspect status
and history, preserve dirty state/extra commits, attach to an existing session
where possible and recover autonomously. Never reset, clean, force-push or
start a second writer on a live branch.

Read `python3 scripts/coordination.py task Txx`, then its named inputs. Honor
effective scopes/contracts. Shared locks/dependencies belong to T02; schema
to T03; fixture setup to T05/T21; tokens to T06/T07; app composition to T13.
Request scope/dependency changes through committed task-local handoff evidence;
the coordinator resolves them in Beads and overrides. The owner need not
relay them. Preserve planning and origin notices.

Each checkout owns dependencies, venvs, mutable databases, generated assets
and scratch. Use its app port from passes.json, with a distinct offset for a
second writer. Enable strict ports; tests use OS-assigned ports. Share only
immutable download caches.

## Work, review, integrate, continue

1. Implement, run real commands, inspect results and fix failures. Native
   subagents handle bounded work; keep related edits with one owner. Held-out
   labels require a restricted evaluator environment: another same-user
   worktree or reviewer persona is not access isolation.
2. Commit source and evidence on the assigned branch. Mac workers return the
   local commit to Devin; only Devin publishes to GitHub. Homebase workers push
   their local handoff branch through `docs/HOMEBASE.md`. Write task-local
   `handoff.json` with task, worker, exact implementation_commit, executed
   commands/counts, evidence paths, limitations, dependency requests and
   ready_for_review. It requests review of that commit; it is not task status.
   `receipt.json` maps every criterion to executed evidence: use status
   `executed`, an `evidence` list of actual task-local paths, and optional
   narrative in `detail`. Every cited file is bound into acceptance. Do not fabricate
   reviewer approval, manual/device checks or test counts.
3. The coordinator polls assigned remote branches and obtains independent
   review of each exact candidate and its tests. The writer yields first.
   Commit task-local `peer-review.md` with actual reviewer identity, candidate
   commit, findings, checks and verdict. Cross-app requests use committed
   task-local evidence or coordinator-written Beads notes; native messages
   work within an app. Do not send messages to people. Workers handle revisions
   on the same branch until review is resolved.
4. Merge reviewed commits locally and rerun acceptance on the merged candidate.
   Use an integration candidate branch while fixing failures; publish main only
   after checks. Material integration changes need independent review. Commit
   source, then run `python3 scripts/task_acceptance.py task Txx --report
   artifacts/tasks/Txx/run.json`. Follow `docs/ACCEPTANCE.md` to build, commit
   and validate the receipt.
5. Push accepted code/evidence before publishing Beads closure. Set
   accepted_commit to the commit containing the receipt, accepted_receipt to
   its path, disposition to accepted; close with actual evidence rationale.
   Only T41–T45 allow a measured rejected_experiment. Publish Beads, dispatch
   newly ready work and continue without an owner turn.

Shared-code changes can invalidate predecessor receipts. Rerun affected
acceptance/review and update references before gates. Never weaken freshness
or use an old green run to avoid revalidation.

When blocked on another app, do independent work first, then use bounded
30–60 second waits and synchronize again. No tight polling. Preserve native
resumability/compaction. Local workers read the shared canonical Beads state
without remote pulls; the coordinator handles remote synchronization.

Workers continue through ready granted work in their standing queues as Devin
publishes grants after actual dependency checks. A wave ending is a checkpoint, not permission to
dispatch themselves. Devin finishes when the authorized product scope is
accepted with actual gate evidence, or records a specific external blocker. A single ticket or a
temporarily empty inbox is not completion. Report accepted tasks, actual gate
results, main commit and material blockers. Quotas, authentication, native UI
approvals or unavailable reference devices may require owner input; preserve
work and report the exact need. The same prompt resumes the unfinished pass
or selects the next one. Never reboot, shut down, power-cycle or suspend Homebase.

## Independent workbench inboxes

Use `python3 scripts/native_pass.py status devin --workbench B` for the native
CLI lane, `--workbench E` for review/quality, and `--workbench A` for integration.
Antigravity uses `status antigravity --workbench C`; Homebase uses
`status zcode --workbench D --sync`. Run control commands from current canonical
main even when a task's implementation checkout has older scripts. The unfiltered
`status APP` remains the migration/audit view and preserves original saved grants.
Explicit saved workbench IDs take precedence; compatible legacy grants are only
filtered, never rewritten. Every grant still fixes its exact branch and base.

A processes delivered candidates and eligible standing queues at each checkpoint.
Workers communicate through committed task-local handoffs/reviews and Beads reads,
without agent chat. End a worker turn cleanly when its grants are exhausted; A
resumes its exact native session on the next published grant. A PID or published
inbox proves neither pickup nor progress: record the native acknowledgement and
actual tool/checkpoint activity. Never queue Desktop messages while productive
children run: queued delivery can cancel the descendant family too.
