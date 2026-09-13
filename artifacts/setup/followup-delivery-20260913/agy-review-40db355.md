# Independent review of pdf-8hn candidate 40db355

Reviewer: Descartes, Codex subagent 01a097f9-fac6-7353-9fa2-f5f55a0393a0 (low), September 13, 2026. Parent transcription of returned report; not reviewer-authored file. Reviewed full six-file diff from aa6d039a00916193b34c4df019bb5c8e75e1acc1, audit 4fe6be0, clean candidate 40db355df84d3f98ff02cbba509962b897eaea09. Verdict: changes required; Devin retains independent acceptance and integration authority.

P2: existing browser acceptance regression in tests/browser/open.spec.ts:746. New capped plan yields native_text,render after OCR cap; test still expects native_text,ocr,render for every selected page. Real run of four new regressions plus existing 25-page selection test: 4 passed, 1 failed. Preserve complete native/render coverage and assert intentional OCR cap in the affected expectation.

P2: mount.tsx:123 silently truncates OCR selection. Six selected region-bearing desktop pages lead to one explicit region receiving no OCR check; UI still shows all six selected and only technical post-start plan exposes the omission. Surface the cap and affected selection before starting, preserving explicit user selection and honest coverage. Do not solve by dropping tests or raising caps.

Evidence: /private/tmp/pdf-8hn-independent-40db355-results (reviewer's actual focused browser run, one worker, ephemeral ports). First sandbox loopback refusal resolved by approved escalation; successful test execution then 4 pass/1 fail. Stale-reference, label propagation and busy-event focused tests pass. Repro cap/label sections duplicate implementation logic and aren't independent verification.

Owner has explicitly authorized fixing the complete flow. Continue revisions in the existing AGY branch/worktree. The narrowly affected existing browser spec is within the owner's authorized bug fix/verification scope; no new product task is being claimed. Keep product decisions/merge/acceptance with Devin, preserve all existing scopes and frozen main, no Beads writes. Return exact revised candidate and real evidence.
