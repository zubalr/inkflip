# Independent pdf-27v review

Reviewer: Codex independent review task, 2026-09-12. Verdict: PASS; no material findings.

Candidate: `1aec931f03ec61acd252adbf12735f19b9a6a1bb`.
Base: `cd7935133379305d05256bdf48ebf6a764e76cca`.

Read canonical original AGENTS.md, docs/HOMEBASE.md, docs/NATIVE_PASSES.md, project brief/invariants, and code-review skill. Reviewed the complete base-to-candidate diff (four files), surrounding relay implementation and actual Git fixture setup. Candidate Mac worktree was clean before and after review. `git diff --check cd79351 1aec931` passed.

The one-line production change passes current ROOT as the Git subprocess cwd instead of relying on run's definition-time default. No guard is removed or weakened. The regression uses real Git worktree metadata, checks normal-clone canonical resolution, matches the configured path to the linked checkout so it reaches the linked guard, checks publish and collect rejection, and checks the relay receiver remains empty.

## Actual Linux verification

Host: homebase; Linux 7.1.9-arch1-2 x86_64; Python 3.13.15; Git 2.55.0.
Only a new isolated repository and linked checkout were used:
`/home/wertyp/.local/share/homebase-factory/worktrees/inkflip/pdf-27v-review/{clone,linked}`.
Both HEADs resolved to the exact candidate. Both remained clean.

Executed transfer/setup:

```sh
git bundle create /private/tmp/inkflip-pdf27v-review/candidate.bundle 1aec931f03ec61acd252adbf12735f19b9a6a1bb HEAD
scp /private/tmp/inkflip-pdf27v-review/candidate.bundle homebase:/tmp/inkflip-pdf27v-review.bundle
# On Homebase, after checking the review path did not exist:
source /home/wertyp/.local/share/homebase-factory/projects/inkflip/.tools/env.sh
export PYTHONDONTWRITEBYTECODE=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_ALLOW_PROTOCOL=file
review=/home/wertyp/.local/share/homebase-factory/worktrees/inkflip/pdf-27v-review
git clone /tmp/inkflip-pdf27v-review.bundle "$review/clone"
git -C "$review/clone" checkout --detach 1aec931f03ec61acd252adbf12735f19b9a6a1bb
git -C "$review/clone" worktree add --detach "$review/linked" 1aec931f03ec61acd252adbf12735f19b9a6a1bb
# In each of clone and linked:
git rev-parse HEAD
git rev-parse --git-common-dir
python3 scripts/task_acceptance.py run verify
git status --short
```

Each registered verify command exited 0: 49 bootstrap + 2 native bootstrap + 64 coordination = 115 passed. Registry self-check also passed. Full output: `linux-verify.log`.

A second execution in each layout captured structured results through the same registered runner:
`task_acceptance.run_command('verify', task_acceptance.load_registry(task_acceptance.ROOT/'config/acceptance-commands.json'), [])`.
`linux-structured.log` records each suite and exact HEAD: 115 collected/passed, 0 failed, 0 skipped per layout. The synthetic skipped negative fixture printed to stderr is not a skipped required suite test.

## Independent guard and regression probes

Executed `PYTHONDONTWRITEBYTECODE=1 python3 -` from the Linux linked checkout, supplying the saved `probes.py` over SSH stdin. Two tests passed: (1) real repository config inkflip.role=worker rejects both publish and collect; mismatched canonical path rejects both; origin and receiver refs remain unchanged; (2) the candidate's real linked-worktree regression passes.

Then replaced only canonical_root in memory with its exact old behavior, retaining candidate test code. The regression failed at its first canonical-root assertion (one failure, zero errors), because it resolved the outer clone rather than the temporary fixture clone. The probe asserted this expected failure and exited 0. This establishes regression sensitivity without editing candidate source. See `linux-guards-regression.log` and `probes.py`.

No source edits, Beads writes, GitHub publication, dependency installs, OCR, service operations, reboot, global configuration changes, or changes to existing canonical/T10/T27/pdf-932/snapshot checkouts. Parent owns evidence integration and publication. Review covers this coordination fix and registered stdlib suites; it does not accept product receipts or broader product gates.
