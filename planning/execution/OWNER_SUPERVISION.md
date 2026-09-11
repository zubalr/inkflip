# Owner supervision guide

## What to inspect at each acceptance

Ask for the exact branch, merged commit, changed-file list, task ID, command output, test counts and one failure/control case. Open the real app rather than only a screenshot. For evidence work, ask “Which bytes, reader version, physical page and transform produced this?” For no-difference output, ask “What did not run?” For a report, ask “What sensitive data is actually inside, and can another machine replay without the missing original?”

You do not need to manually reimplement PDF parsing. You do need to reject unjustified claims and require a minimal reproducible case whenever an agent proposes changing a foundational assumption. A nice animation, a green badge, a confident paragraph or more agents is not evidence of a correct result.

## Gate-specific owner checks

| Gate | Try yourself | Evidence to demand | Stop condition |
|---|---|---|---|
| G1 | Open mapping PDF, then its renamed clean twin; cancel A and open B; export/reopen one finding | Real named outputs, correctly placed region, fresh network trace | Mocked own-file output, wrong highlight or payload egress |
| G2 | Open ordinary scan, repeated values and large file on narrow screen; remove model cache and work offline | Explicit limits/coverage, functional controls, honest preview and report contents | All-clear wording, hidden skipped pages, private bytes auto-included |
| G3 | Run before/after profiles; trigger one rule regression and one file failure | Exact versions, exit5 only for rule failure, immutable baseline and retained good reports | Auto-updated baseline, lost coverage looking improved, untrusted executable |
| G4 | Use keyboard/screen reader; inspect clean false alarms, OOM/hang and license manifests | Real device/AT/environment receipts, split identity, full denominators and notices | Missing critical test/rights, adjusted goldens to conceal a failure |
| G5 | Open actual domain with network panel, download assets/report, inspect and practice rollback | Deployed artifact hashes, no application compute route, exact rollback manifest | Undeclared script injection, dynamic endpoint, mismatched release artifact |

## Agent record without theater

Record which task each session performed, provider/tool name, selected mode/model only as exposed in the interface, actual session/commit identifiers, your interventions and decisions, outcomes, rejected alternatives and limits. Keep private provider logs/credentials out of published history. Do not claim the model operated autonomously if you selected fixtures, corrected architecture or manually rescued it; those are valuable owner contributions to document accurately.

A fair case study distinguishes “agent wrote this implementation” from “I defined the product/contracts, reviewed evidence, rejected a failure and integrated the release.” Do not manufacture either role. Actual Git authorship/coauthor attribution and timestamps stand as they happened.

## When to intervene

Intervene when a worker expands into accounts/backends, silently chooses a reader, changes a shared schema, proposes a generic confidence score, treats invisible text as malicious, tries to deserialize an untrusted model, normalizes away digits, ignores native limits or changes test labels to pass. Require a small reproducible proposal, not a broad rewrite. Intervene on product clarity when the page disappears behind settings or users confuse “no differences” with safety.

Do not intervene merely because a legitimate experiment failed, an optional engine was rejected or there are fewer active workers than available accounts. Useful concurrency follows independence and hardware. When too many model processes compete, queue runs; do not lower the release bar.

## Owner-only actions

Account/domain and publication decisions remain in [OWNER_INPUTS.md](../OWNER_INPUTS.md). Supply secrets only through the provider's secure environment/auth flow, not the repository, report or prompt. Review the exact target/account/command before deployment. Never let a bootstrap script silently create a remote, enable a paid service or publish a private incident sample.
