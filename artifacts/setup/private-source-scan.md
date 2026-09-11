# Private source publication review

Gitleaks 8.30.1 scanned all 14 existing local Git commits (all refs) and the
389-file publication candidate. The scanner archive was verified against the
official release API SHA-256 before execution:
b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5.

Both scans reported 34 generic-api-key alerts. Every alert was an explicit
run_key in a planning contract example. All 34 values were independently
matched to deterministic valid-fixture digests recomputed by
planning/tools/contractlib.py: run_key hashes document SHA-256, readers and
plan. Two worker-terminal examples reuse the same fixture digest. These are
content identities, not service credentials. No actual credential was found.
No scan rules were suppressed, and the frozen fixtures were not altered.

Source, tests, planning contracts, origin notices and selected evidence are
included for the three approved harnesses. Private scratch, recovery copies,
environments, caches and the embedded database are ignored. The database
travels separately using native Beads/Dolt transport. The private history
retains local provenance paths and earlier task handoffs; public source
selection/privacy and final OSS publication review remain T55 work.

This is a bounded scan plus review, not a guarantee that a repository contains
no sensitive information. Only the approved private repository is published.
