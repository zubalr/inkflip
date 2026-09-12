# pdf-0hw — T22 review residuals: superseded rejected-read emit + silent pick-drop kinds

Bug bead. Source findings: `artifacts/tasks/T22/review.md` round-2
(`800c1a4`) residual **R1** (low) and info note **R2**, against candidate
`a8c9600`. Worktree `worktrees/pdf-0hw`, branch `work/devin/pdf-0hw`,
base `de63e6c` (includes accepted T22). Local commits only — no push,
no Beads.

## Defect (R1)

`ImportController.offerSource` (`apps/web/src/features/import/controller.ts`):
the round-2 F1 fix bound the *success* path of the pending byte read to
the captured report + generation (`:341` check → `superseded`, no event),
but the `catch` on `await candidate.arrayBuffer()` (`:329-336`) emitted
`source_rejected`/`source:unreadable` under
`this.host.currentGeneration` unconditionally — the NEW generation when a
replace/clear landed mid-read — before the binding check ran. Result: a
rejected read that was superseded in flight stamped its failure on the
new report, and `#source-mismatch` ("does not match the original
document checksum") would render on it — a wrong-context error for a
file that was never evaluated against that report.

## Fix

Same guard, same position as the success path (`controller.ts:330-345`):
inside the `catch`, if `this.current !== current` or
`this.host.currentGeneration !== generation`, the read returns
`{ ok:false, kind:"superseded", detail:"source:superseded" }` and emits
nothing. Only a still-bound failed read emits `source_rejected` —
stamped `this.host.currentGeneration`, which the guard has just proved
equal to the captured `generation`. Concurrent-`offerSource` dedup is
unchanged: the winner's `this.current` write makes the loser's check
fail identically on resolve or reject.

## Silent pick-drop audit (R2 — `offerSource` drop/refusal paths)

R2 noted `busy`/`superseded`/`no_report`/`not_required` emit no
`source_rejected`, so the UI clears `sourceBusy` with no notice. Audit
of every drop path, verdict per path:

| Path | Site | Emits | Verdict |
|---|---|---|---|
| `busy` — `offer`/`offerCompareSide` holds the lock | entry `:301-302` | none | **Silent by design.** Entry refusals across the whole controller are return-typed, never events — `offer`/`offerCompareSide` return `BUSY_FAILURE` with no `rejected` event; `offerSource` mirrors it. The pick was never evaluated against a report; a `source_rejected` would render the checksum-mismatch-titled notice for a transient lock — a false claim. Caller gets `kind:"busy"`; UI clears `sourceBusy`, input stays usable. |
| `no_report` — nothing open | entry `:305-306` | none | **Silent by design.** No opened report ⇒ no `SourcePanel` surface exists to render on; an emitted `source_rejected` would only set invisible `sourceError` state, cleared by the next `imported`. `kind:"no_report"` returned. |
| `not_required` — embedded/not-applicable source | entry `:308-312` | none | **Silent by design.** The picker is not even rendered for these reports (UI-unreachable; programmatic only). A mismatch-titled notice would misdescribe the refusal. `kind:"not_required"` returned. |
| `source:length-mismatch` — declared-size gate | `:316-324` | `source_rejected` | Emits — correct: the pick WAS evaluated against the open report and refused. |
| `source:unreadable` — `arrayBuffer()` rejects | `:330-345` | `source_rejected` iff still bound | **Fixed (R1)** — gated by the generation/identity check; superseded-failed reads now return `superseded` silently. |
| `superseded` — replace/clear won mid-read | `:349-351` | none | **Silent, required.** Emitting under the new generation IS the R1 defect; emitting under the old generation would race the `clear`/`imported` handlers and could still land on the new report. The pick's context is gone — nothing honest exists to render it on. `kind:"superseded"` returned. |
| `verifySource` failure (`sha256-mismatch` etc.) | `:352-360` | `source_rejected` | Emits — correct: real refusal on the open report. |

Net: the only behavioral fix needed was R1. The four silent kinds stay
silent by design — each returns its typed `kind` on the promise surface
(the contract callers, incl. `onSourceFile`, consume), and no new event
types were invented.

## Tests (`tests/reports/import.spec.ts`, +145, 0 removed)

One new case in section 6 (after the F1 superseded-read spec), using the
same deferred-`arrayBuffer` gate mechanism, driven at controller level
like its sibling:

`a superseded source read that fails emits nothing under the new report`

- **Phase 1 — entry refusals:** `offerSource` with no report open →
  `kind:"no_report"`; `offerSource` while an `offer` holds `busy` →
  `kind:"busy"`; delta of `source_rejected` events = **0** for both.
- **Phase 2 — the R1 race:** pending `offerSource` on report A whose
  `arrayBuffer()` REJECTS, released only after `offer(B)` completes →
  `kind:"superseded"`, **0** new `source_rejected` events, `current`=B,
  gen(B)=gen(A)+1. Pre-fix this returned `source_mismatch` and emitted
  `source_rejected` under gen+1 (verified red).
- **Phase 3 — same-context honesty:** an identical rejecting read while
  still bound to B → `kind:"source_mismatch"`, `source_rejected`
  emitted with `detail:"source:unreadable"` stamped `generation`=
  gen(B); UI renders `#source-mismatch` with `source:unreadable` on B —
  the gate suppresses only stale emissions, never live ones.
- **Phase 4 — `not_required`:** embedded-source replay report →
  `kind:"not_required"`, 0 `source_rejected` events, no
  `#source-mismatch` rendered.

## Checks run in this worktree

- `bun run test:browser -- tests/reports/import.spec.ts` — **13/13
  pass** (was 12/12; +1 new). New case verified RED pre-fix
  (`stale:"source_mismatch"` instead of `superseded`), green post-fix.
- `bun x --no-install tsc -b` — exit 0.
- `bun x --no-install tsc -p apps/web/tsconfig.json --noEmit` — 1008
  total / 290 in `features/import`, exactly the recorded baseline; zero
  diagnostics in `controller.ts`.
- `bun x --no-install oxlint <touched files>` — 0 warnings, 0 errors.
- `bun x --no-install oxfmt --check` — both files correctly formatted.

## Residual risk

- The entry-refusal kinds (`busy`/`no_report`/`not_required`) remain
  silent in the UI per the audit — a deliberate, documented choice, not
  an oversight; a user-facing affordance for a transient `busy` drop
  would need new copy + surface, beyond this bead.
- `source:unreadable` renders under the checksum-mismatch notice title
  (pre-existing copy pairing, unchanged); the detail string keeps the
  cause explicit.
- The race is proven at controller level (the reviewer's own level);
  the UI window via real dialogs remains narrow, as round-2 noted.
