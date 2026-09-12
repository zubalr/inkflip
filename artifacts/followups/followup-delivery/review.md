# Independent review: native follow-up delivery (682cbc2)

**Verdict: APPROVED.** No blocking findings. The patch closes the claimed
delivery gap without weakening any existing guard, fails closed on malformed
state, and is well covered by new regression tests. Non-blocking observations
are listed at the end.

Reviewer: independent (did not author this code). Reviewed commit
`682cbc2` on `setup/followup-delivery`, diff `15d4d71..682cbc2`, in the
linked review worktree `review-devin-followup-delivery` on branch
`review/devin/followup-delivery`.

## What the patch does

- `scripts/native_followups.py` (new, 67 lines): `execution_grant` parses
  `metadata.execution` fail-closed; `validate_id` restricts follow-ups to
  non-product `pdf-*` IDs (rejects `pdf-tNN`, `pdf-passN`, uppercase,
  separators, over-length); `validate_scope` normalizes paths (no absolute,
  `..`, `.`, glob chars, first-part `.git`/`.beads`/`planning`) and confines
  `audit` mode to `artifacts/followups/<id>/`; `validate_grant` enforces
  `kind: followup`, known app, exact `branch_prefix + issue_id` branch,
  full-40-hex base, real pass, non-empty instructions.
- `scripts/native_pass.py`: `status` iterates all issues — granted
  follow-ups appear in `assignments` with kind/mode/scope/instructions;
  open/in-progress issues assigned to the app (or `app-*`) with no grant
  appear as `undelivered`. New `dispatch-followup` requires canonical root +
  `inkflip.role=integrator` + clean published main, then inside the
  admission lock reuses `dispatch_errors` capacity/claim checks, requires
  `bd list --ready` membership, runs `check_scope_ownership` against active
  workers, claims via `bd update --claim --add-label execution:worker
  --metadata`, and publishes before printing the grant.
- `scripts/coordination.py`: `active_workers` now counts in-progress issues
  holding an execution grant even without the `execution:worker` label
  (capacity accounting cannot be hidden by a missing label);
  `check_scope_ownership` validates `kind: followup` grants and enforces
  their `allowed_scope`, and a follow-up worker cannot launder scope through
  an `execution:review` label (coordination.py:157).
- `scripts/homebase_relay.py`: `grant_for`/`collect` accept full `pdf-*`
  follow-up IDs; discovered collection covers every active zcode grant,
  validating all grants before any transport.
- `scripts/homebase_pre_push.py`: work/zcode/pdf-* branches may push only
  to the exactly matching `hb/inkflip/<id>` ref; `pdf-tNN`/`pdf-passN`
  branch names are rejected by `validate_id`.
- Docs (`NATIVE_PASSES.md`, `HOMEBASE.md`) and prompts (`ANTIGRAVITY.md`,
  `ZCODE.md`) updated consistently with the implemented semantics
  ("notes without a grant are not a dispatched assignment", audit
  confinement, acknowledgement requirements, recovery rules).

## Guard-preservation check

- Ancestry/no-force rules unchanged: relay `require_ancestor` on grant base
  and published target, `--atomic` + `--force-with-lease` only on
  `refs/dolt/data`, pre-push `merge-base --is-ancestor` — all untouched.
- `dispatch` (product) is unchanged except a `metadata=None` hardening in
  `dispatch_errors` (old code would AttributeError on `metadata: None`).
  `dispatch-followup` is strictly stronger than `dispatch`: it adds the
  `c.ROOT.resolve() == c.canonical_root().resolve()` check the product path
  lacks.
- Beads writes (`bd(write=True)`) exist only in the two dispatch paths, both
  gated behind integrator role + canonical checkout; `status` and the relay
  issue no writes (test asserts `bd` is not called).
- `acceptance_receipts.py`, `gate.py`, `planning/`, `execution/`, `config/`
  untouched — receipt/acceptance semantics unchanged. scripts/ is in
  COMMON_INPUTS, so this commit stales prior receipts by design (normal
  churn; the coordinator refreshes in batches).
- No self-dispatch: `dispatch-followup` requires the canonical checkout, so
  a linked worker worktree cannot run it even though `inkflip.role` is
  readable from shared git config (verified live below). Product-task
  impersonation (`pdf-t05`, `pdf-t54`, `pdf-pass1`) is rejected by
  `validate_id`; `--app codex` is always capacity-blocked (budget 0);
  non-ready issues are rejected by the `--ready` check; assigned/closed/
  in-progress issues are rejected by `dispatch_errors`.
- No leak: `undelivered` entries carry only the issue ID + fixed reason (no
  notes); `assignments` deliver grant fields/notes/instructions only to the
  granted app (`grant.app == app` filter).

## Executed checks

- `python3 -m unittest discover -s tests/coordination -v`: **97 tests, all
  pass** (includes 12 new `test_followup_delivery.py` tests, 13
  `FollowupPrePushTests` cases incl. `test_followup_identity_is_exact`, 8
  new relay follow-up tests with real local Git transport).
- `bun run verify`: **passes** — self-check (16 registered commands),
  test:bootstrap 49, test:native-bootstrap 2, check:coordination 97.
- Live probes in this linked review worktree against the real Beads
  replica:
  - `native_pass.py status antigravity` → `pdf-8hn` (open, assignee
    `antigravity`, note-only) correctly appears in `undelivered`;
    `status devin` shows the T18 grant plus `pdf-g78`/`pdf-pass1`
    undelivered entries; zcode/codex inboxes clean.
  - `dispatch-followup pdf-8hn --app antigravity ...` → refused:
    "Only the canonical integrator may dispatch follow-ups".
  - `dispatch-followup pdf-t05 --app zcode ...` → refused:
    "Follow-up requires a non-product pdf issue ID".
  - `homebase_relay.py collect bogus-task` / `collect pdf-8hn` → refused:
    canonical-clone guard fires first in a linked worktree.
  - Direct function probes: codex follow-up dispatch always hits "App
    worker capacity is occupied"; cross-app branch prefixes, foreign audit
    evidence dirs, and all impersonating IDs (`pdf-t00`, `pdf-pass0`,
    `pdf-UPPER`, `pdf-a.b`, 70-char) are rejected.
- `bd update --add-label`/`--claim` confirmed real flags in the installed
  bd 1.2.2.
- Live DB sanity: all 88 issues parsed; every `metadata.execution` record
  is a product task with a valid app — the stricter `execution_grant`
  parser breaks nothing currently stored.

## Non-blocking observations

1. `status` flags `pdf-pass1`-style pass-checkpoint beads as `undelivered`
   when they carry a `devin-*` assignee, but `validate_id` permanently
   bars `pdf-passN` from grants — "coordinator dispatch required" is
   misleading there. Cosmetic; consider excluding pass checkpoints.
2. `validate_scope` blocks `.git`/`.beads`/`planning` first-parts but not
   the reserved evidence namespaces `artifacts/tasks/` and
   `artifacts/gates/`; an implementation follow-up grant could be pointed
   at another task's evidence dir. Coordinator-chosen, so not
   worker-exploitable, and acceptance integrity is protected by
   hash-bound receipts — a defense-in-depth extension to consider.
3. The scope blocklist is case-sensitive: `Planning/x` passes validation
   and would resolve into `planning/` on the case-insensitive macOS
   filesystem. Advisory mechanism; a `casefold` comparison would tighten.
4. `status` runs `execution_grant` over every issue including closed and
   unrelated ones, so a single structurally malformed bead fails all apps'
   status output. Deliberate fail-closed per the new tests; noted
   brittleness only.
5. `check_scope_ownership` re-reads `execution/passes.json` inside the
   per-worker loop (coordination.py:162). Performance nit only.
6. `product_ids` in `status` covers only `passes[].tasks`; `pdf-t01`
   (completed_bootstrap) and `pdf-t54` (owner_release) are excluded, so a
   hypothetical in-progress grant on `pdf-t54` makes status raise
   "requires a non-product pdf issue ID". Unreachable via the tooling —
   `dispatch_errors` can never dispatch owner-release tasks — and still
   fail-closed.
7. Import ordering nit: `import native_followups` sits inside the stdlib
   import block (coordination.py:13).

## Test-quality note

The new tests use real local Git remotes for relay/pre-push coverage and
mock only the Beads/Git boundary for dispatch paths; the publication-
failure test asserts the claim persists with no success output, matching
the documented recovery semantics.
