# pdf-3oz report-boundary repair

Astra owns this follow-up from base `37ae85e`; the implementation and merged candidate have now passed independent conventional review and the registered checks below. This follow-up is separate from refreshing T24 acceptance. Original T24 artifacts remain historical. The repair owns its new evidence here.

The original registered security suite passed 79 tests. A new 24-test reproducer had 22 failures and two controls passing (`red.log`). The duplicate-transparency test originally reached a different existing rejection; its corrected RGB control was rerun before the PNG edit and failed for the intended missing duplicate rejection (`png-red.log`). This correction is not counted as another independent bug. All 24 focused tests then passed (`first-green-attempt.log`). Wiring the previously dangling reports package entry/typecheck exposed excluded-file type errors; these were fixed without relaxing strictness. The existing eight-byte PNG-signature-only HTML control was replaced with a generated valid one-pixel PNG, matching the full-decode requirement.

The 104-test full suite includes one actual Chromium case: a browser bundle of the shipped guard accepts a generated escaped report, whose exact CSS hash authorizes rendering, whose embedded PNGs decode, and which makes no remote resource requests. There is no real OCR or product T16 exporter claim. The first 1000-case fixed-seed fuzz run passed (172 accepted, 828 rejected, no unexpected results, crashes or egress). It wrote the script's default T24 fuzz directory; those new outputs were copied to this repair's `fuzz/`, and the prior tracked T24 outputs were restored byte-for-byte from Git. The log retains its actual original output path. Final source-bound registered verification follows.

## Primary sources checked

- [CSP Level 3](https://www.w3.org/TR/CSP/#parse-serialized-policy): duplicate directives and source-list semantics explain why substring membership is insufficient. The owned policy permits only exact restricted lists and a stylesheet hash.
- [CSS Syntax Level 3](https://www.w3.org/TR/css-syntax-3/): identifiers can contain escaped code points, and comments are consumed separately. The conservative scanner does not claim every rejected spelling would fetch in a browser.
- [PNG Third Edition, chunk ordering](https://www.w3.org/TR/png-3/#5ChunkOrdering): singleton and image-data ordering is checked before inflation.
- [RFC 1951, section 3.2.7](https://www.rfc-editor.org/rfc/rfc1951#section-3.2.7): literal-only blocks may lack distance codes. The generated stream is independently accepted by Node zlib before it reaches the owned decoder.

No external code or new dependency is introduced. Existing source-level complexity outside the changed path is retained; newly introduced production helper functions have complexity at most ten under the stated branch-count measure.

## Source-bound merged verification

Source `656848e` merged published main into candidate `9f60ea01e0c61e00c2e185bed729a307d4bd096f`. That committed candidate passed frozen Bun install without lock drift, strict reports package typecheck, the registered T24 command (104 Node tests including the Chromium case, followed by 1000 fixed-seed fuzz cases), and 115 verify tests. See `registered-run.json`, `registered-task.log`, `registered-fuzz/`, `merged-install.log`, `merged-typecheck.log`, and `merged-verify.log`. The registered fuzzer output was again preserved here and the older tracked T24 fuzz artifacts restored byte-for-byte. Existing T24 acceptance remains stale until the integrated refresh. The initial reviewer Averroes (`01a09460-9c54-7f40-bf7e-0241d6d8e394`) ended with an automated possible-cybersecurity content flag and produced no verdict. That attempt is not approval.

## Independent review disposition

Helmholtz (`01a09467-215d-7a30-827e-e60905c3d73d`), separate from Astra as author, approved exact `9f60ea01e0c61e00c2e185bed729a307d4bd096f` within a narrower conventional code-correctness and standards-review scope. See `independent-review.md` for the full verdict and its limits. The clean isolated review checkout passed 103 of 104 tests initially; the remaining browser case failed to bind loopback under sandbox and passed its authorized targeted rerun. Thus all 104 passed across those runs, not a single independent all-green run. Strict reports typecheck passed. The reviewer inspected the author's 1000-case fuzz and 115-test verification evidence without rerunning them. No actionable findings were identified; the reviewer documented nonblocking branch-coverage and assurance limits. No comprehensive security assurance or completed T16 exporter is claimed. All reviewer commands ended and the review session was closed.
