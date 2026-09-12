# Astra coordinator, Mac SWE swarm and Homebase Goal worker

The owner ended Cloud execution for quota consumption and selected Devin Local
with SWE-2 Max on the Mac plus native ZCode on Homebase. The owner subsequently
selected Codex/Astra as the sole coordinator and hard-work owner, with SWE as
a local implementation swarm and ZCode continuously running in Goal mode.
Antigravity is inactive.
This document defines transport and operating priorities; Beads remains the only
live task state. `execution/passes.json` owns the static task allocation.

## Responsibilities and order

Astra owns architecture, difficult implementation, integration, failure diagnosis,
security boundaries and independent acceptance. SWE-2 owns substantial bounded
feature implementation and independent assigned reviews. ZCode owns defined components,
fixtures, repeated verification, examples and supporting deliverables. Each
ZCode grant includes the established contract, scope, real command and expected
observable result. ZCode escalates a contract ambiguity through task evidence;
Astra resolves it before expanding scope. Volume work still requires correctness.

The initial sequence is:

1. Resume Cloud's T10 branch and reproduce the remaining crop/resize failure.
   Validate the proposed arithmetic against the actual transform contract rather
   than copying the handoff's suggested fix. Complete its browser evidence.
2. Finish T27's interrupted independent review on Linux using its saved candidate
   and partial review. Reproduce the T26 PDFium drift and `pdf-p7q` tool binding
   issue before changing code. Keep product failures distinct from environment
   failures. Give ZCode concrete review revisions or missing evidence to produce.
3. Once T27 is accepted, give ZCode T28's bounded structural reader while SWE
   develops the dependency-critical browser path: file/region selection, viewer
   composition, report export/import and evidence navigation. Prefer one coherent
   integration path over a large set of unfinished branches.
4. Revalidate stale acceptance inputs on the integrated candidate before G1.
   Then advance through the defined passes: native supervision/CLI/resume and
   version comparison stay with Astra; examples, repeated experimental runs,
   layout coverage, notices and documentation use ZCode where assigned.
5. Execute the real browser investigation scenarios and native regression gates.
   Resolve failures and request missing physical-device evidence honestly. T54
   public deployment remains an owner decision.

The owner removed fixed numerical worker budgets. Astra admits concrete waves
of independent work and accounts for all native descendants in Beads. Add
workers when ready scopes, compute and review capacity justify them; retire
finished workers and avoid redundant supervisors. SWE uses native general
subagents, Astra may use Codex subagents, and ZCode uses supported native Goal
parallelism. Each writer has its own branch and checkout. Native platform
limits and resource contention still apply.

Run one heavy OCR/corpus/performance job at a time, recording its holder in the
task's Beads note. Linux review uses a separate checkout from ZCode and shares
that reservation. Assign distinct dev-server ports and generated paths to
simultaneous checkouts; app ports are defaults, not permission to reuse a busy port.

The objective is to finish the authorized product, with no invented clock
deadline. Continue useful ready work, fix ordinary failures, publish recoverable
progress and resume native sessions without new per-ticket owner prompts.
Astra continues across active turns and same-task heartbeat runs until the
objective is achieved or an actual external blocker needs the owner. Keep expensive
reasoning focused on actual uncertainty. Do not add speculative refactors,
duplicate checks or unattended quota-reset jobs. On exhaustion, preserve work and
leave a precise handoff. The Mac must remain awake and network-connected for
Astra coordination, new grants, integration and GitHub publication. Homebase can
finish an existing assignment while disconnected but must wait for the relay.

## Workspaces and state

| Role | Canonical checkout | Execution |
| --- | --- | --- |
| Astra | `/Users/zubair/Code/Projects/pdf project/original` on `main` | Existing Codex task and bounded Codex subagents; hard edits in separate worktrees |
| SWE-2 | Isolated Mac task/review worktrees under the existing project | Native Local general subagents directed by Astra; no Beads writes or GitHub pushes |
| ZCode | `/home/wertyp/.local/share/homebase-factory/projects/inkflip` on `main` | Native Goal; isolated Homebase task worktrees for granted writers |

Homebase's project-local toolchain is activated with
`source /home/wertyp/.local/share/homebase-factory/projects/inkflip/.tools/env.sh`.
Keep this canonical Homebase checkout on clean published main for control reads;
put implementation/review checkouts under
`/home/wertyp/.local/share/homebase-factory/worktrees/inkflip/`.

Only Astra in the Mac integration session writes Beads. Mac linked worktrees read its
canonical database without `--sync`. Homebase has a native read replica restored
from `file:///home/wertyp/.local/share/homebase-factory/git/inkflip.git`; it reads
with `python3 scripts/native_pass.py status zcode --sync` from its canonical main.
Homebase may pull this replica but never change claims, notes, statuses or remote
Dolt state. A failed sync is a blocker, not an empty queue. No network-shared
embedded database, personal GitHub login or Workbench permission change is used.

The local Git `inkflip.role` value is an accident guard, not an authentication
boundary. Canonical Mac is `integrator`; Homebase is `worker`. The source and
handoff Git remotes on Homebase both point to the local bare relay. Its worker
pre-push hook permits only task branches under `hb/inkflip/`; it does not prove
hostile same-user isolation. Preserve existing service and account configuration.

Native Dolt periodically replaces its Git transport history with a parentless
storage snapshot. The relay allows this only for `refs/dolt/data`, checks the
fetched SHA and uses an exact old-SHA lease in an atomic publication. This is
storage maintenance, not logical Beads conflict resolution: never use
`bd dolt push --force` to overwrite competing state. Source branches retain
fast-forward ancestry checks. The bare receiver keeps
`receive.denyNonFastForwards=true` and `receive.denyDeletes=true`; Git applies
these guards to branch refs, so they permit native snapshot rollover.

## One round of work

1. Mac: read the current pass, grants and blockers. Resume an unfinished grant on
   its saved branch before dispatching another task. New grants use
   `python3 scripts/native_pass.py dispatch Txx --app codex|devin|zcode`.
2. Mac: publish reviewed code and native Beads changes to GitHub, then run
   `python3 scripts/homebase_relay.py publish`. Do this after dispatch, a handoff
   note, acceptance, or any change Homebase must see. Failed publication blocks
   dependent execution; retain the existing claim and retry safely.
3. Homebase: fetch `origin`, fast-forward canonical main when clean, pull the
   native state replica, then read the ZCode grant and task contract. Create or
   resume its isolated task checkout at the exact saved branch/base. Install its
   frozen dependencies; the project-local tool PATH is shared, build outputs are
   not. Run the required checks and record honest task-local handoff evidence.
4. Homebase: commit on the granted work branch, then publish the checkpoint with
   `git push handoff HEAD:refs/heads/hb/inkflip/txx` from that checkout. This is a
   local Git transfer, not GitHub publication. Use the lowercase granted task id.
   A checkpoint may be incomplete; say so. Never push main, tags, Dolt refs or
   delete/force a remote branch. Author identity is configured per repository.
5. Mac: poll `python3 scripts/homebase_relay.py collect` during native coordination.
   It imports new active ZCode candidates and pushes their exact commit to the
   original assigned GitHub branch after ancestry checks. It does not accept or
   merge work. Astra orders independent review, resolves findings, integrates
   and records actual acceptance before dispatching dependent work.

Assigned SWE or Codex reviewers inspect ZCode independently; every implementation,
including Astra edits, receives an independent actual reviewer. Use real session identities in evidence. Homebase reviewers
must not share a writing checkout with ZCode. Held-out labels require the
repository's actual access isolation, not another folder or a reviewer persona.

During an active run, Astra uses bounded waits while native workers execute.
A same-task Codex heartbeat resumes coordination after the active turn ends;
it reads Beads and native session state before acting, reports meaningful
changes only, and is paused when work completes or the owner stops it.
ZCode keeps its native Goal loop and 30–60 second state refresh. There is no
custom daemon or mirrored work queue. Continue other
ready work during an unrelated network/model block. Do not redispatch another
writer onto an occupied branch. Resume the same native session after an ordinary
interruption; stop and save when the provider requires owner interaction.

## Transfer provenance

Cloud's final main was `e14ea4aa9433ac25fef4faa57050aa5d0a1cd802`.
The owner confirmed all Cloud sessions stopped. The actual saved T10 and T27
grants, partial review, stale-receipt findings and follow-up issues are in Beads
`pdf-pass1`; use its live records instead of treating these docs as status.
Cloud could not select SWE-2 for managed children through its session API.
For Local use the documented `subagent_general` profile with SWE-2 Max selected
on the parent; explore/default custom profiles have different routing.
