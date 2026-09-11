# One prompt per app

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

## Bootstrap and state

Code and Beads data travel through private `zubalr/inkflip`. Use GitHub access
provided by the app; never put credentials in prompts, files, logs or URLs.
Devin Cloud needs this repository enabled in its GitHub integration.

Run `python3 scripts/bootstrap_beads.py` to install pinned Beads 1.2.2 locally
if needed (Linux amd64); matching existing installations are used. Python
3.11+ and Git are required. Add the printed `.tools/bin` directory to PATH if
installed. An independent clone then runs `bd bootstrap --yes`. A linked
worktree uses its existing canonical checkout database; never initialize a
second one there. `coordination.py` resolves the canonical root.

T02 verifies and installs Bun, Node, uv and product dependencies, produces
locks, and proves clean Linux installation. Until then,
`python3 scripts/task_acceptance.py run verify` runs the stdlib bootstrap
suites. Missing product commands deliberately fail. The application is still
a scaffold; bootstrap success is not browser/native release evidence.

Only the **Devin Cloud integration session** writes Beads. Configure its primary
clone with `git config inkflip.role integrator`; worker clones must not set
this. The flag is an accident guard, not a security boundary. Direct Beads
writes run in that clone. Never launch a second integration session.

Beads uses native Git-backed Dolt sync (`refs/dolt/data`). Git clone alone does
not restore it: new clones bootstrap; existing replicas pull. The coordinator
publishes every transition using `bd dolt commit -m 'Describe transition'`
and `bd dolt push`. Workers never write/push Beads. Do not use the historical
local-only `coordination.py start`/`start-review` admission commands here.

`python3 scripts/native_pass.py status APP --sync` serializes the pull and read
in the canonical checkout; APP is devin, antigravity or zcode. The Mac apps
share this database/lock and must use this command to synchronize. A failed
pull is a blocker, not an empty inbox. Do not continue silently on stale state.

Capture the current pass at startup as this run's target. `pdf-pass1` through
`pdf-pass3` are Beads checkpoints. Only the coordinator closes a checkpoint,
after its listed tasks have valid acceptance and its listed gates pass on the
integrated candidate. This prevents dispatch into the next pass before gates
finish. Keep T54 outside the three passes.

## Dispatch and isolation

On clean, published main the coordinator runs, for example:

```sh
python3 scripts/native_pass.py dispatch T02 --app devin
python3 scripts/native_pass.py dispatch T06 --app antigravity
python3 scripts/native_pass.py dispatch T05 --app zcode
```

The command checks actual readiness, predecessor receipts, pass membership,
ownership, scope conflicts and capacity. It claims the task and stores
`metadata.execution`: app, branch, exact base commit and pass. Launch only
after successful Beads publication. A publication failure leaves a recoverable
local claim; recover sync/publication rather than creating a second claim.
Never force-push state or discard local changes.

Budgets are **Devin 2, Antigravity 2, ZCode 1** active product workers, including
reviewers. Idle coordinators consume no slot; active implementation/review
does. Workers yield before reviewers take their slot. Native automatic
critics/auditors must honor the same app budget. Use fewer workers if needed.
Only one heavy OCR/corpus/performance run at a time; the coordinator records
the holder on its Bead.

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
2. Commit source and evidence; push the assigned branch. Write task-local
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
resumability/compaction. In Devin Dynamic Workflows, filesystem/Git/Beads work
belongs inside agent calls; deterministic workflow code cannot assume a
persistent filesystem. Separate worker VMs clone and bootstrap Beads read-only.

An app completes this run when all its tasks in the captured pass are accepted
on origin/main with no requested corrections. The integration lead completes
when the checkpoint closes with actual gate evidence. A single ticket or a
temporarily empty inbox is not completion. Report accepted tasks, actual gate
results, main commit and material blockers. Quotas, authentication, native UI
approvals or unavailable reference devices may require owner input; preserve
work and report the exact need. The same prompt resumes the unfinished pass
or selects the next one. Never reboot, shut down, power-cycle or suspend Homebase.
