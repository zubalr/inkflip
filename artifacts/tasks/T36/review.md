# T36 independent review — held-out evaluation protocol

- **Reviewer:** independent reviewer `review/devin/t36` (not the writer;
  writer worker `devin-t36`, implementation commits `04b3969` + `33fb81b`)
- **Candidate under review:** `e5b3c4b566d3e2d81b8ada0627dda556b7d8cbc5`
  (HEAD of `review/devin-t36` worktree; = `33fb81b` + evidence-only commit)
- **Contract:** `python3 scripts/coordination.py task T36`, contract_version 1.0.0
- **Review basis:** this reviewer never ran or wrote this code before this
  review; every claim below was re-verified by adversarial execution in
  `/tmp/t36-review/` (attack scripts) and a fresh permissioned-eval demo.

## Verdict: **changes-required**

The five contract criteria hold at their cores — denominators are
declared, samples deduplicate, verdicts need a bound run, labels are
gated and scanned out of artifacts — but adversarial testing produced
one demonstrated dishonest-MET path on a declared plan target via the
exact mechanism criterion 3 exists to prevent, plus one custody-boundary
gap. Both fixes are small and local to the allowed scope.

## Reproduced results

- `python3 -m unittest discover -s tests/evaluation -v` → **Ran 84 tests,
  OK** (84 passed, 0 failed, 0 skipped), matching `run.json` and
  `unittest-output.txt`.
- Contract command says `python`; host has only `python3` (3.14.7,
  `/Users/zubair/.local/bin/python3`). Registry mapping is real:
  `config/acceptance-commands.json:4-5` `"interpreters": {"python":
  "python3"}`; `run.json` records the mapped `argv`/`executed_argv`
  transparently and the worker disclosed the mapping in receipt/handoff
  and commands.log. Honest.
- `run.json` binds `evaluated_commit 33fb81b…`; `33fb81b` is an ancestor
  of HEAD `e5b3c4b`, and `git diff 33fb81b..HEAD` is only
  `artifacts/tasks/T36/` evidence files — evidence-only delta, so the
  binding is consistent with `docs/ACCEPTANCE.md` freshness rules.
- Scope: `git diff 01690c0..HEAD` touches only the four allowed paths
  (`evaluation/protocol/`, `evaluation/manifests/`,
  `scripts/evaluate_inspector.py`, `tests/evaluation/`) plus
  `artifacts/tasks/T36/`. No reserved paths touched.
- `emit-corpus --check` passes on both committed corpora;
  `verify-splits` reports 39 entries, zero violations.
- `status --plan evaluation/manifests/evaluation.plan.json` prints
  **10/10 targets UNMET** (`no_evaluation_run`), exit 1.
- `receipt.json` `acceptance_criteria_evidence` resolves all five exact
  contract criteria through `acceptance_receipts.criterion_evidence`
  semantics (`scripts/acceptance_receipts.py:172-182`): each `status:
  executed` with nonempty task-local evidence paths that exist.
- No label payloads in task artifacts: `permissioned-eval.json` carries
  only `labels_sha256` + aggregate counts; grep for
  `consent_ref|incident_ref|truth|per_page_truth` across
  `artifacts/tasks/T36/` finds only test names/prose, no label content.
- `commands.log` honestly discloses an earlier 81-test/5-failure run
  before the fix — good-faith reporting, not a greenwashed transcript.

## Criterion-by-criterion adversarial verification

### 1. No sibling leakage — PASS (with one inherent limitation, P3)

Crafted corpora fed to `lineage.split_violations` in both directions:

- Eval-side leak (dev family member placed in `evaluation`) → flagged.
- Dev-side leak (eval family member placed in `development`) → flagged.
- Control↔variant edge across splits with **different** group_ids →
  flagged (union edge type 2 works independently of declared group).
- Identical sha256 under renamed key **and** renamed family → flagged
  (byte-identity union edge type 3).
- Transitive cluster (A~B by group, B~C by bytes) straddling → flagged.
- `public_demo`→`evaluation` and `permissioned`↔`evaluation` boundaries →
  flagged; unknown split name and duplicate keys → `LeakageError`.
- Premise confirmed: naive per-entry `assign_naive` straddles a 6-sibling
  family in 39/40 seeds; `assign_grouped` straddles in 0/200 seeds.
- Real fixture lineage verified: F01/F07 and F03/F17 pairs plus a 5-way
  F06/F10/F11/F18/F19 control set are byte-identical in
  `fixtures/manifest.json` — union-find correctly merges them (worker
  documented the F01+F07 collapse honestly in handoff limitations).

**P3 — union-find is declaration-bound (inherent):** two documents that
ARE siblings but share neither declared `group_id`, a `controls` edge,
nor identical bytes are undetectable (verified: same-source-different-sha
renamed pair passes silently). No manifest audit can detect undeclared
ancestry; the three edge types are documented (`lineage.py:9-17`) and the
custodian owns group declarations. Acceptable as designed, recorded for
completeness.

### 2. Skipped/failed pages stay in the denominator — PASS

End-to-end through `report.compute_metrics`/`evaluate`:

- 10-page supported corpus, 1 resolved + 9 `skipped` → rate **0.1**,
  `total=10`, `uncovered_statuses={skipped:9}` — a 1-of-10-read cannot
  score 100%.
- Abstain-everywhere → 0.0 (no precision-by-silence); zero readings →
  all 10 in `never_attempted`.
- `failed`/`timeout`/`cancelled`/`unsupported`/`never_attempted` each
  tallied visibly.
- `unsupported`-truth pages excluded from supported recall but inside
  `full_coverage` (3-page accounting verified).
- `clean_false_alerts` divides by every clean labeled page and exposes
  `pages_read` so a nearly-unread corpus cannot hide.
- `check_accounting`: missing planned check = violation (fraction 0.5),
  never agreement.
- `check_labels_cover_corpus` fails closed on unlabeled corpus pages and
  stray labels — the denominator cannot shrink silently.
- Occurrence preservation uses the conservative `min` across readings;
  unread declared pages count as lost.

**P3 — docstring/code mismatch:** `occurrence_preservation` counts an
unread page with `expected_occurrences: 0` as *preserved*
(`observed=0==expected=0`) though the docstring says a never-read page
"counts as lost" (`metrics.py:88-114`). Degenerate label, but the prose
and code disagree on the conservative side.

### 3. Repeated readings are not independent samples — **FAIL on the alignment pool (P2)**

- Core verified: 5 re-reads × 20 pages → `unique_pages=20` (not 100);
  identical rate and identical Wilson bounds to the single-read corpus;
  emitted interval is `wilson(20,20)=[0.839,1.0]`, strictly wider than
  the dishonest `wilson(100,100)=[0.963,1.0]` the suite forbids.
- `grouped_bootstrap_ci` resamples whole groups (6 groups, not 30
  readings); re-surfaced finding ids dedup per page.
- **P2 — `alignment_px` pools per-reading errors (`report.py:179-204`):
  repeated readings DO masquerade as independent evidence here, and it
  flips a declared target.** Demonstrated: 5 good pages at 0.1px + 5 bad
  pages at 3.9px → honest single-read `p95=3.9` (t_alignment_p95 UNMET).
  Re-reading only the good pages 30× each → `n=155, p95=0.1` →
  **t_alignment_p95 flips to MET** on the committed plan's declared
  target, while `unique_pages` stays 10. `metric_samples` likewise counts
  readings (`n`), so a `min_samples` gate would be satisfied by re-reads.
  `max` is not dilutable (bad values persist), but p95 alone is.
  This contradicts `metrics.py:9-12`'s own invariant ("the sampling unit
  is the page … repeated OCR passes can never masquerade as independent
  evidence"). Fix is small: collapse to one representative error per page
  (e.g. max or median per `sha:page`) before pooling, matching
  `collapse_readings` semantics.

**P3 — any-resolved OR semantics:** a page that fails then resolves
counts `resolved` (documented at `metrics.py:56-64`); the failed statuses
stay on the page record but do not surface in `uncovered_statuses` once
covered. Declared best-case-of-attempts semantics; `repeat_digests` is
the guard for nondeterminism. Noted, not blocking.

### 4. Targets UNMET until a real bound run — PASS

- `status` on the committed plan: 10/10 UNMET `no_evaluation_run`,
  exit 1 — no green-by-default.
- Self-attested run rejected at every layer tried: top-level `verdict`
  key (closed `RUN_KEYS`), `targets_met` nested inside `notes`
  (recursive `SELF_ATTEST_KEYS` scan), `attested` inside a reading,
  `status:"passed"` inside a reading (non-terminal CheckResult).
- Resolutions require evidence: `useful_finding` without `finding_ids`
  and `actionable_comparison` without `comparison_ref` both rejected;
  resolution on a non-completed status rejected.
- Plan rejects verdict-carrying fields twice over: unknown top-level key
  (`ALLOWED_PLAN_KEYS`) and nested `met`/`approved` (self-attest scan).
- Run pinned to a different corpus manifest digest → `RunError`
  ("run is not bound to this corpus manifest").
- `metrics=None` → all UNMET; unknown metric → `unknown_metric`;
  unmeasured → `not_measured`; below `min_samples` →
  `insufficient_evidence`; zero evaluated findings is not a vacuous pass.

**P3 — `candidate_freeze` declared but not enforced:** `evaluate()`
requires the run to carry a full freeze triple (commit + lock + config,
all echoed into the report) but never compares it against
`plan.candidate_freeze.*`. Verified: a plan pinning commit `f…f` scored a
run claiming commit `b…b`; the report records the actual commit openly,
so nothing is hidden — but a pinned plan freeze is advisory only
(`report.py:344-401`). Worth a equality check when the plan pins values.

### 5. Permissioned incident data stays out of logs — PASS at checkout boundary; **P2 at repository boundary**

- `resolve_labels`: no root → refuse; root inside checkout (repo root,
  `evaluation/`, `artifacts/tasks/`) → refuse; outside root → resolve;
  `INKFLIP_EVAL_LABEL_ROOT` env works.
- Label file must match pinned sha256 AND `label_count` AND schema —
  one-byte tamper → digest refusal; count/schema mismatches refused;
  `sha256: null` (unpinned) fails closed.
- `labels_file` traversal (`../../etc/passwd`) and absolute paths refused.
- Permissioned labels without `consent_ref` per page → refused
  (`validate_permissioned_labels`).
- Serializer double-guard verified: `scan_forbidden_keys` refuses
  `truth`, `per_page_truth`, `page_consent_ref`, `mechanism_id`,
  `expected_outcome`, `label` (embedded tokens caught);
  `assert_labels_not_emitted` refuses actual label values anywhere in
  serialized bytes including nested lists and — demonstrated — a label
  incident-ref smuggled through the freeform `created_at` field that the
  report echoes. Only digests reach artifacts.
- Custody demo evidence is real: reproduced the full CLI flow — outside-
  root permissioned evaluate → MET with emitted report asserted free of
  `INCIDENT-*/CONSENT-*/incident_ref/consent_ref/truth`; no-root and
  in-tree-root invocations → exit 2.

**P2 — label root inside a *sibling worktree* is accepted:**
`resolve_labels` only checks `root` against THIS checkout's root
(`custody.py:83-91`). Verified: a directory inside a second worktree of
the same repository (with `.git` marker) is accepted as label root. The
refusal message claims "outside every worktree" and AGENTS.md says
worktrees are not an access boundary — a label file sitting in any
checkout of the repo is one `git add` away from committed. The letter of
"outside the checkout" is met; the stated invariant is not. A
`git -C <root> rev-parse --is-inside-work-tree` check (or a `.git` upward
walk) closes it cheaply.

**P3 — camelCase keys evade the key-token scan:** `incidentRef`,
`consentRef`, `perPageTruth`, `expectedFinding` pass `scan_forbidden_keys`
(tokens split on non-alphanumerics only after lowercasing, so
`incidentRef`→`incidentref` is one token). The value-scan still refuses
any actual label content, so this is first-line-of-defense only — add
camelCase splitting to make the key scan honest about its own coverage.

## Findings summary

- **P1:** none.
- **P2-1 (criterion 3):** `alignment_px` pools per-reading errors —
  demonstrated verdict flip UNMET→MET on declared `t_alignment_p95` by
  re-reading only good pages; `metric_samples` n counts readings.
  Fix: one representative error per page before pooling.
- **P2-2 (criterion 5):** label root inside a sibling worktree of the
  same repository accepted — "outside every worktree" not enforced.
  Fix: refuse any root inside any git work tree.
- **P3:** declaration-bound lineage audit (inherent, documented);
  `occurrence_preservation` expected=0/unread docstring mismatch;
  any-resolved OR semantics visibility gap; `candidate_freeze` advisory
  only; camelCase key-scan evasion; receipt/handoff prose says
  "32+7 entries" where the actual frozen corpora are 30+9 (total 39
  correct; artifacts themselves verified byte-exact).

## What acceptance needs

1. Collapse `alignment_errors_px` per page (or per declared sampling
   unit) before p95/max and `metric_samples`, plus a regression test
   mirroring the demonstrated flip.
2. Refuse label roots inside any git work tree (not just this checkout).
3. Recommended (non-blocking): enforce `candidate_freeze` equality when
   pinned; split camelCase in key scan; fix the 32+7 prose counts.

Everything else — the test suite honesty, the closed plan/run formats,
the declared denominators, the deduplicated samples, the custody
serialization guards, the adjudication record, and the evidence chain —
is verified sound. The protocol is well-built; the two P2s are exactly
the kind of silent-denominator defects this machinery exists to catch,
so they should be closed before acceptance.
