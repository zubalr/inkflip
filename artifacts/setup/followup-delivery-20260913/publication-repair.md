# Publication repair: ca2336d

The coordinator's new pdf-g78 implementation grant was locally committed at Dolt vut8b6hdvpk4tt6fbcq8hjc92761lacq (issue updated 2026-09-12T23:15:12Z), but Homebase still returned the audit-only note updated 19:48:24Z after a successful bd dolt pull. Both relay transport refs still pointed to 47948539b4e640a07ae58de6001ae2f7abeee495. Local bd diff origin/main HEAD --json reports modified pdf-8hn, pdf-g78 and pdf-pass1. Comparing the transport ref to itself was not verification of new publication.

The new read-only guard rejects nonempty, malformed or unavailable Beads origin/main-to-HEAD comparisons before transfer and around the atomic push. It reports the required Dolt commit/push step without writing Beads. This fixes the observed missing-push failure; it is not an atomic snapshot of a concurrently changing database, and the documented single coordinator must serialize publication. The original follow-up delivery implementation remains 682cbc2; ca2336d adds this publication guard and the explicit coordinator cycle instructions.

Verification: the new tests failed before implementation (six failures across unpublished and unavailable-state cases), then all 31 relay tests passed. Required verify passed with 100 coordination tests plus the bootstrap/native-bootstrap/registry checks. A direct read-only probe against the live Mac database returned the expected unpublished-Beads error. No live publish was run by this setup worker.

Independent reviewer Jason (01a097ee-3551-72b1-9dff-52b24a300839, low reasoning) approved the scoped code/test diff with no blocking findings, ran 31 relay tests and diff check, and confirmed the guard adds no Beads writes. This is the parent's transcription of the read-only reviewer's returned report, not an artifact authored by the reviewer. Reviewer caveat: tests mock Beads with real disposable Git repositories; concurrent publication is not atomically bound to the fetched snapshot. Reviewer is closed.

## Concrete immediate recovery

Publish the existing coordinator-authored database changes with bd dolt commit (if changes remain uncommitted), then bd dolt push, then python3 scripts/homebase_relay.py publish from the canonical Mac clone. Pull Homebase's existing replica and compare pdf-g78's expected update timestamp and implementation-grant text with the Mac; then verify the existing Goal's pickup and returned checkpoint. Do not alter task decisions, clear claims, create another Goal, or reboot Homebase. This state-only publication does not edit the frozen application candidate. Publication is reserved to Devin by canonical AGENTS.md, so a setup-worker exception requires owner authorization.

## Native UI correction

Fresh native state confirms both queued messages reached Devin, who reviewed the audit and wrote the implementation grant. T18 f14bbd1d was canceled at 23:13:30Z while UI-delivery attempts were ongoing; exact gesture attribution was not established. Devin replaced it with 5bf96ad6 on the preserved grant. Static inspection of the installed desktop client confirms Send Now routes through interruptWithQueuedMessage and session/cancel for an active session. A keyboard shortcut may force-send an existing queued message too. Avoid all interactive writes to Devin while useful children run, not only the Cancel button. Resetting the CUA bindings exposed fresh state; the earlier accessibility tree and screenshots had disagreed.

AGY has delivered 40db355df84d3f98ff02cbba509962b897eaea09 for independent review. No merged acceptance or product completion is claimed.
