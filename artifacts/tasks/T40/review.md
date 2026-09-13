# Independent review — T40 (native containment + image inputs)

Independent review of assurance source at 7876213 (reviewer: independent-96362dd8, verified by Devin coordinator exec checks on merged state 1015280).

Verdict: APPROVED.

Evidence: tests/containment/run.py executes a real digest-pinned OrbStack container build and proves nonroot uid 65532, --network none egress denial (real socket failure), read-only input mounts, crash/hang/stdout-flood injections, and source-byte immutability. native/tests/security/test_containment.py launches real child processes via the real Supervisor (SIGSEGV, SIGINT, output flood, corpus-manifest symlink/traversal rejection). tests/containment/test_image_inputs.py enforces release-image input rules. Merged-state run: 27/27 on 1015280, live_container_cases=7, arch honestly labeled linux/arm64 native (amd64 would be emulated).

Non-blocking follow-ups filed: /Users/* mount-guard subtree gap in run_native_container.sh (finding 4), temp-residue in test_check_manual_receipts.py (finding 5).
