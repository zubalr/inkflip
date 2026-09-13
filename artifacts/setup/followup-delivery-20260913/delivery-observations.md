# Native delivery observations

Observed 2026-09-12 23:12 UTC. This is evidence and a handoff, not a second task ledger. Devin owns current Beads state and acceptance.

## Review and deployment

Implementation `682cbc2` is independently approved in native Devin review commit `d4522253`, at `artifacts/followups/followup-delivery/review.md`. Evidence commit `e097072` records the Mac and disposable Homebase checks. Source remains unchanged after review.

Deployment is still pending: Devin deliberately holds the scripts change until the G1 run so it does not invalidate the nineteen refreshed prerequisite receipts mid-run. An approved patch is not proof of production delivery. After integration and required validation, publish code and Beads, publish the relay, fast-forward the clean Homebase canonical checkout, and verify a real structured grant, existing Goal pickup and returned checkpoint.

## AGY implementation delivered

The canonical `pdf-8hn` note was converted to an implementation grant at 22:57:13 UTC. The existing Antigravity conversation's recurring monitor continued reading the old empty assignment list without examining that changed note. A message pointing to the grant remained queued even after a periodic poll completed. The visible Send Now control delivered it at approximately 23:01 UTC.

The existing worker then implemented the four granted fixes and committed `40db355df84d3f98ff02cbba509962b897eaea09` on `work/antigravity/pdf-8hn`. Worktree `../pdf-8hn` is clean. The six changed files match the grant: three `apps/web/src/features/open/` files, `tests/browser/pdf-8hn.spec.ts`, and two `artifacts/followups/pdf-8hn/` files. Its report records four passing focused browser tests, a passing reproduction script, lint and web build. Those product checks have not been independently rerun by this setup worker; Devin must obtain independent review before accepting or merging. The canonical G1 candidate is untouched.

## ZCode audit delivered through a historical ref

The owner supplied current output from the existing Homebase Goal: it is actively polling, has completed all granted work and is awaiting coordinator action. Direct SSH reads of the existing relay confirm `92cd11fd3f8d48ac00fe933b871632e352e3fb6a` on `hb/inkflip/t05`. That commit adds only `artifacts/tasks/T05/g78-fixture-audit-zcode-20260912.md` (136 lines).

Collect this as follow-up audit evidence without redispatching closed T05, changing its acceptance or treating the historical ref as authority for new source work. The audit text names `hb/inkflip/g78`; the actual advertised ref is `hb/inkflip/t05`.

The audit correctly identifies eleven missing families: F09, F12–F16, F22–F26. Its suggestion that the remaining recipes might already exist on the preserved Mac branch is unsupported by that tracked branch: `work/codex/pdf-g78` at `911367c` is already an ancestor of main, its triple-dot diff against main is empty, and its generator contains none of those eleven family IDs. The tracked branch delivered the ten priority families already integrated. Preserve its untracked `artifacts/tasks/T05/followup-g78-next/` evidence; do not infer that missing implementations were written or reviewed.

## Recovery and remaining acknowledgment

Devin's replacement T18 child `f14bbd1d` is on the existing grant/worktree, continuing the salvaged `eb56c74` spec. Backend command evidence confirms activity through 23:11 UTC. No cancellation was issued to deliver the queued ZCode audit reference.

The exact ZCode checkpoint was queued in the existing Devin conversation. A separate pickup/correction update was drafted; submission was not yet verified because native accessibility state and screenshots disagreed. Do not equate queue presence with coordinator acknowledgment. The same observations are available in `/private/tmp/inkflip-orchestration-repair-ready.md`.

When adopting existing note-only grants into structured metadata, preserve their worker, branch, actual base, current work and evidence. The new dispatcher intentionally refuses assigned issues; do not clear an active claim merely to make dispatch succeed. Only Devin should reconcile such existing assignments and publish the resulting metadata.
