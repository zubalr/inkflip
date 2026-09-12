# pdf-0hw — independent review: superseded rejected-read emit + silent pick-drop audit

- **Reviewer:** independent read-only reviewer (Devin Local subagent, coordinator-requested)
- **Candidate:** `a50ecbe` (impl `516193d`, spec `d1e31e0`, notes `a50ecbe`; base `de63e6c`)
- **Review branch/checkout:** `review/devin/pdf-0hw` @ `worktrees/review-devin-pdf-0hw`, HEAD `a50ecbe`
- **Verdict: approved** — R1 is genuinely closed (red reproduced pre-fix, green post-fix); the R2 per-path audit is honest on every row; no regression; diff minimal. Zero findings.

## Reproduced commands (this worktree, real counts)

| Command | Writer claim | Reproduced |
|---|---|---|
| `bun run test:browser -- tests/reports/import.spec.ts` | 13/13 | **13/13 pass, 0 fail/skip, exit 0 (3.5s)** — real Chromium; fresh `bun install` in this worktree (isolated linker, lockfile-frozen pins) |
| `bun x --no-install tsc -b` | exit 0 | exit 0 |
| `bun x --no-install oxlint <touched>` | 0/0 | 0 warnings, 0 errors (96 rules, 2 files) |
| `bun x --no-install oxfmt --check <touched>` | formatted | both files correctly formatted |
| `bun x --no-install tsc -p apps/web/tsconfig.json --noEmit` | 1008 / 290 | **exactly 1008 total / 290 in `features/import`** — identical to the recorded baseline; zero diagnostics in `controller.ts` or `import.spec.ts` |
| Spec diff `de63e6c…HEAD` | +145 additive | **purely additive** — zero removed lines; one new `test()` inserted between the F1-race spec and the declared-size spec |

## 1. R1 closure — verified, red check reproduced

Round-2 R1 (`git show 800c1a4:artifacts/tasks/T22/review.md`): a read rejected by
`arrayBuffer()` after supersession emitted `source_rejected`/`source:unreadable`
under `this.host.currentGeneration` — the NEW generation — stamping a
wrong-context `#source-mismatch` on the reopened report.

**Red reproduction:** restored `516193d^:controller.ts` into the working tree,
ran only the new spec → fails exactly as claimed:
`expect(race.stale).toBe("superseded")` received `"source_mismatch"`
(`import.spec.ts:1186`). Restored; post-fix 13/13. The unconditional emit in the
old `catch` makes the accompanying gen+1 `source_rejected` certain — the same
statement that produced `source_mismatch` emitted it first.

**Green behavior, independently read:** `controller.ts:335-337` — inside the
`catch`, `this.current !== current || this.host.currentGeneration !== generation`
→ returns `{ok:false, kind:"superseded"}` and emits nothing; a still-bound
rejected read falls through to `:338-344` and emits `source_rejected`/
`source:unreadable` stamped `this.host.currentGeneration` — which the guard has
just proved equal to the captured generation. The new spec asserts both halves:
`stale === "superseded"` + `staleEmitted === 0`, and `unreadable ===
"source_mismatch"` + `unreadableDetail === "source:unreadable"` +
`unreadableGen === genB`. Matches the bead requirement exactly.

## 2. Binding-check placement — identical strength, no reopened race

- **Identical check.** `:335` is verbatim the success-path guard `:349`:
  `this.current !== current` (object identity) `||`
  `this.host.currentGeneration !== generation`. Same operands, same order, same
  conjunction — not a weaker variant.
- **No await between check and emit.** `:335→:344` is `if → return | const →
  emit → return` — fully synchronous, and `emit` itself (`:144-147`) iterates
  listeners synchronously. Once the guard passes, nothing can interleave before
  the event lands.
- **Completeness of the guard.** `this.current` is only ever replaced by (a)
  `offer` success → new object *and* a `requestClear` that already bumped the
  generation whenever a report was live, (b) attach → `{...current, replay}` new
  object, (c) `clear()`/teardown → `null`. `current===current && gen===gen`
  therefore strictly means same report, same lifecycle, no attach since —
  genuinely still bound.

## 3. R2 audit verdicts — all four confirmed honest (`notes.md` table)

| Path | Audit verdict | Independent check |
|---|---|---|
| `busy` | silent by design | **Confirmed.** `offer`/`offerCompareSide` return `BUSY_FAILURE` with zero events (`:179-181`, `:392-394`); `offerSource` mirrors the convention with `kind:"busy"`. A `source_rejected` would render the checksum-mismatch-titled notice for a file never evaluated — a false claim. |
| `no_report` | silent by design | **Confirmed — stronger than stated.** `SourcePanel` mounts only inside `{opened !== null && …}` (`ImportWorkspace.tsx:436-444`), so the picker itself doesn't exist; the path is programmatic-only. An emitted event would set invisible `sourceError`, cleared on the next `imported`/`clear`. No UX gap exists to defer — the bead is right to leave it silent. |
| `not_required` | UI-unreachable | **Confirmed.** `open.ts:67-75`: `source.kind==="required"` iff no `source_asset_id` and `export.replay==="requires_original"`; `view.ts:231-237`: `required`+unattached → `replay.source==="missing"`; `ImportWorkspace.tsx:198-209` renders `FilePick` only for `"missing"`. `kind!=="required"` ⇒ picker unmounted ⇒ UI-unreachable. |
| `superseded` | silent, required | **Confirmed — if anything understated.** The workspace `source_rejected` handler (`ImportWorkspace.tsx:357-359`) calls `setSourceError(event.detail)` with **no generation check anywhere in the chain** (`controller.emit` is synchronous; the host snapshot's generation is never compared). An old-generation emit arriving after `clear`/`imported` processed would *deterministically* render on the new report — exactly the R1 defect under a different stamp. Silence is the only correct option. |

Non-silent rows also verified: `source:length-mismatch` (`:318-323`),
`source:unreadable` still-bound (`:339-343`), `verifySource` failure
(`:354-358`), `source_attached` (`:373-378`) all still emit.

## 4. No regression

- **Concurrent `offerSource` dedup intact on both paths.** The winner's attach
  writes `this.current = {...current, replay}` — a new object — so the loser's
  identity check fails identically whether its read resolves or rejects →
  `superseded`, no emit. Side benefit: a rejected read losing to a successful
  concurrent pick now drops silently instead of stamping `source:unreadable` on
  the just-attached report (pre-fix it emitted; same-generation identity check
  catches it).
- **`offer`/`offerCompareSide` busy semantics unchanged** — the diff touches
  only `offerSource`'s catch + doc comment; `offerSource` still doesn't set
  `busy` (correct precedence: a report offer may supersede a pick, never the
  reverse).
- **Caller handling:** `onSourceFile` (`ImportWorkspace.tsx:396-405`) clears
  `sourceBusy` on any `!check.ok` resolution — `superseded` included; the input
  never wedges.
- Every emitting path still emits (listed above); the `superseded` return shape
  fits the declared promise union (`tsc -b` clean).

## 5. Reproduce — all green

See the commands table. 13/13 including the new spec; `tsc -b` exit 0; web
`--noEmit` exactly the 1008/290 recorded baseline with zero diagnostics in the
touched files; oxlint 0/0; oxfmt clean. Spec is purely additive (+145, no
weakened or removed assertions — the only `-` in the diff is the file header).

## 6. Diff minimality

`git diff de63e6c…HEAD` = 3 files, +257/−1: `controller.ts` +9/−1 (the −1 is
the doc-comment line extended by one sentence — accurate post-fix), spec +145,
notes +103. No unrelated files, no planning/, no lockfile, no config.

## Findings

None. Info notes only:

- **N1 (info)** — The phase-3 honesty half of the new spec is what makes the fix
  safe: it proves the gate suppresses only stale emissions (`unreadableGen ===
  genB`), not live ones — the exact over-suppression risk this pattern carries.
- **N2 (info)** — `notes.md` claims verified: every per-path verdict and every
  check count (13/13, 1008/290) reproduced exactly; the residual-risk section is
  honest (entry refusals remain deliberately silent; `source:unreadable` still
  renders under the checksum-mismatch title — pre-existing copy pairing).
- **N3 (info)** — This worktree lacked `node_modules`; ran `bun install`
  (isolated linker, frozen lockfile) to execute the suite — gitignored, no tree
  changes. The red check was run by materializing `516193d^:controller.ts` in
  the working tree and restoring it afterward; tree clean at review end.
