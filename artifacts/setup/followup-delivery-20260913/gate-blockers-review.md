# Live gate blocker repair

September 13, 2026. The owner authorized full orchestration repairs. Static G1 prerequisites omitted the newly recorded public-app composition blocker pdf-3g8. A gate receipt could therefore be generated despite the authoritative open dependency of pdf-t18.

scripts/gate.py now reads the gate owner's live blocking dependencies before executing scenarios and again before writing a success receipt. Open blockers, malformed state and unavailable Beads fail closed. Static acceptance, scope freshness and scenario checks remain in place. This is a bounded read, not a transaction against concurrent tracker updates; the sole coordinator must continue serializing acceptance mutations.

Four regression tests failed before implementation and now pass. They cover open/closed/malformed/unavailable dependencies, preventing scenario execution and preventing a late success receipt. Independent reviewer Pascal (01a09815-c6c5-7101-acd5-7e72f3836b78, low) approved the gate implementation and regression tests with no blocking findings; did not rerun parent tests. Nonblocking additional coverage suggested: successful main receipt, check-prereqs and late query exceptions.

The existing bootstrap missing-prerequisite test now supplies missing state in its own subprocess instead of relying on live G1 remaining unfinished. Switching that test to pre-release only postpones the defect. No production override or gate weakening was added. This small subsequent test correction was parent-reviewed; its 24-test module passed.

Final required bun run verify exited 0: 53 bootstrap tests, 2 native bootstrap tests, 102 coordination tests, and registry self-check for 16 commands. The log also includes a one-test test-runner canary. Live read-only probe: python3 scripts/gate.py G1 --check-prereqs exited 2 with `gate blocked: pdf-t18: blocked by pdf-3g8 (open)`. The public app defect remains unaccepted; these are orchestration checks, not G1 success evidence.
