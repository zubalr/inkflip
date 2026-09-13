# T22 independent review — strict local JSON import and reopen flow

- **Reviewer:** independent read-only reviewer (Devin Local subagent, coordinator-requested)
- **Candidate:** `a2f7e3cc83ea0bb461863eaf88d8d5a71c045d06` (impl `9742daf`, tests `d802819`, evidence `a2f7e3c`; base `3b70baa`)
- **Review branch/checkout:** `review/devin/t22` @ `worktrees/review-devin-t22`, HEAD `a2f7e3c`, clean tree
- **Round-1 verdict: changes-needed** — all five acceptance criteria verify and the security boundary is sound, but a deterministic TOCTOU in `ImportController.offerSource` corrupts controller state and can display a false "attached"/"replay-ready" claim (F1, medium). Fix is small (busy guard + generation binding, the pattern `offer`/`offerCompareSide` already use). All other findings are low/info.
- **Round-2 verdict (current): approved** — F1 resolved at `610eee3`/`6d3951b`, verified on candidate `a8c9600`; see the Round-2 section below.

## Reproduced commands (this worktree, real counts)

| Command | Worker claim | Reproduced |
|---|---|---|
| `bun run test:browser -- tests/reports/import.spec.ts` | 11/11 pass | **11/11 pass, 0 fail/skip, exit 0 (4.8s)** — real Chromium, already installed |
| `bun x --no-install tsc -b packages/reports` | exit 0 | exit 0 (composite decl. build incl. `import/**/*.ts`) |
| `bun x --no-install oxlint <touched dirs>` | 0/0 | 0 warnings, 0 errors on candidate files (96 rules, 15 files) |
| `bun x --no-install oxfmt --check <touched>` | formatted | all matched files correctly formatted |
| `bun x --no-install tsc -p apps/web/tsconfig.json --noEmit` | 1008 baseline, 290 in feature | **exactly 1008 / 290**; feature diagnostics = 279×TS7026 + 5×TS7016 + 6×TS7006 — zero non-baseline codes (worker's "TS7031" listed but absent; immaterial) |
| `bun run verify` | — | 49 + 2 + 65 OK, self-check 16 commands; `test_planning_snapshot_is_byte_identical` passes → `planning/` untouched |

## Verification items (coordinator's ten)

1. **Gate purity — PASS.** `open.ts:64` routes all untrusted bytes through T24 `importReport`; nothing else parses. `errors.ts:77` `sniffSchemaVersion` re-invokes **`loadsStrict`** — the gate's own strict parser — only on the SCHEMA failure path, to bound-extract a declared version for classification. It is not a parallel parser and never `JSON.parse`s; see F2. Compare sides cross the same `engine.openReport` (`controller.ts:399`); `mount.tsx:59-79` binds the real engine; no `JSON.parse`/`eval`/`new Function`/dynamic `import()` anywhere in `packages/reports/import` or `features/import` (grep clean).
2. **Egress — PASS.** Committed spec arms fetch/XHR/sendBeacon/WebSocket/EventSource/`window.open` tripwires + same-origin `request` assertions + storage/cookie/URL checks; my probe **added `Worker`, `serviceWorker.register` and frame-navigation tripwires** and offered `source_url`/`$ref`/`assets[].href`/`binary_path` payloads plus a contract-valid report carrying live URLs in legal string fields through the **real file input**: pointer fields → SCHEMA/`invalid`, zero non-Vite egress, zero workers, zero navigations, `__pwn3` unset.
3. **Hostile corpus — REAL assertions.** 24-case corpus each asserted `toMatchObject({ok:false, kind})` (archive magics ×10, tar, bare PDF, UTF-16 BOMs ×2, HTML/SVG/XML, malformed/deep/dupkey/nonfinite/unsafe JSON, comparison artifact) + 12 report-shaped attacks asserted per-name kind (`__proto__`/`constructor`/`prototype`, `executable`/`command`/`profile`/`$ref`/`source_url`/`binary_path`/`fetch`/`href`, worker_message) + 3 UI-level hostile offers through the real input. Not presence checks; kinds asserted per case, codes confirmed by my probes (see below).
4. **Source binding — PASS.** `source.ts:37-55` requires `byte_length` **and** `sha256` equality. My P1: same-size different-hash PDF (1437 B, last byte XOR'd) → `source:sha256-mismatch`, verbatim copy, never attached — the committed spec's `WRONG_PDF` is 1429 B so it only exercises `length-mismatch` (F4 coverage gap; implementation correct).
5. **Reader classification — PASS.** `readers.ts:34-40` matches recorded `Reader.id`s against the host-supplied allowlist by exact equality; allowlist = pdf.js adapter identities (`mount.tsx:57`). `executable`/`binary_path`/`profile` fields die at closed schema (probed). Reader-substituted variant test proves the honest positive path. F5 notes a display nuance.
6. **Generation-first — PASS with exception.** `requestClear` increments generation before any teardown (`coordinator.ts:775-779`); `offer` emits `clear` at the old generation then clears before parsing new bytes; spec asserts teardowns at gen+1 and a stale-stamped `MessageFactory` message rejected `stale_generation`. **But `offerSource` participates in neither the `busy` guard nor generation binding** → F1.
7. **DOM safety — PASS.** Every report-controlled string renders inside `<bdi>` text nodes (React-escaped); zero `innerHTML`/`dangerouslySetInnerHTML` (grep); no autolinking (`a[href*=evil]` count 0 probed); images only `data:image/png` built from the gate's `sanitizedPngs` re-encode (`view.ts:161-174`) — stored `data_base64` never reaches the DOM; non-PNG assets render "not rendered" text.
8. **F24/F25/F26 — specified-not-generated confirmed** (`planning/quality/fixture-catalog.json` status `"specified"` for all three). Constructed variants on real delivered examples (reader id substitution + reseal, `annotations:true` opt-in + hostile annotation text, asset tamper/reseal) exercise the import-facing semantics honestly; documented in spec header.
9. **Scope + shared touches — PASS, adjudicated.** `git diff 3b70baa...HEAD` = 24 files: 8 `packages/reports/import/`, 8 `apps/web/src/features/import/`, 1 spec, 5 task artifacts — plus `packages/reports/package.json` (+`"./import"` subpath only) and `packages/reports/tsconfig.json` (+`"import/**/*.ts"` include only). Identical in kind to T16's adjudicated-sanctioned `./export` additions; additive, required for `tsc -b` + importability. **Adjudicated: sanctioned minimal wiring, stands.** No reserved paths, lockfiles, routing, goldens, or planning touched.
10. **Copy — PASS.** All 13 canonical strings verified verbatim against `planning/product/copy.json` (`import.*`, `export.replay.*`, `export.noassets`, `compare.title`, `compare.incomparable`); replace dialog mirrors `input.replace.*` adapted to reports.

## My novel probes (scratch spec `tests/reports/t22-review-probe.spec.ts`, 8/8 pass, deleted after run)

| Probe | Result |
|---|---|
| P1 same-size different-sha256 source via real input | `source:sha256-mismatch`, verbatim copy, never attached; engine-level same |
| P2 `source_url`/`$ref`/`href`/`binary_path` + live-URL strings via real input, +Worker/SW/nav tripwires | pointers → SCHEMA/`invalid`; valid report opens; **zero non-Vite egress, 0 workers, 0 navigations, 0 http imgs, 0 autolinks** |
| P3 `__proto__`/`constructor`/`prototype` nested inside `geometry`/`checks[0]`/`findings[0]`/`assets[0]` (committed spec probes root only) | all `PROTOTYPE`/`not_a_report` |
| P4 depth boundary | 24-deep parses → `SCHEMA`/`invalid`; 25-deep → `DEPTH`/`not_a_report`; 30-deep member inside a valid report → `DEPTH`/`not_a_report`. Boundary exact, no off-by-one. See F3. |
| P5 tampered `limitations`/`display_name` unsealed → `HASH`/`invalid`; **resealed** asset with self-consistent sha256/byte_length of `<script>` bytes → `ASSET`; PNG-sig+garbage resealed → `ASSET` | signature re-check and bounded decode both enforced after reseal |
| P6 valid JSON + trailing `{"x":1}` / concatenated report / trailing `<script>` | all `not_a_report` |
| P7 member-order fully reversed export | **accepted and reopens** — digests are over canonical member order (producer property); semantically identical non-canonical serialization validates. Sound; reported for the record. |
| P8 edges: `offerSource` with no report → `source:no-report-open`; unreadable candidate → `BYTES` failure no crash; concurrent `offer`×2 → second `BUSY`, first completes | fail-closed |

## Findings

- **F1 — medium — `apps/web/src/features/import/controller.ts:288-354` (`offerSource`).** No `busy` guard (contrast `offer`:179-182, `offerCompareSide`:366-369) and no generation binding: `current` is captured at :293, `await candidate.arrayBuffer()` at :316, then `this.sourceAttached = true` (:335), `host.own(bytes,...)` (:336) and `this.current = {...current, replay}` (:346) execute unconditionally under whatever generation exists then. **Reproduced deterministically** (script-level, delayed `arrayBuffer`):
  - `offerSource` × `offer(replace)`: after B opens, `controller.current` is **stale report A** and a `source_attached` event under the new generation carries A's `replay.source:"attached"`; the workspace applies it to B's view — a **false "attached"/potentially "replay-ready" claim** even when B records a *different document* (verified: B doc `aaaa…` displays attached with A-doc bytes).
  - `offerSource` × `clear()`: `controller.current` becomes a **zombie resurrected report** while `fileState` is `idle`.
  - Impact: state corruption + replay-honesty display defect — squarely against the explicit-local-source guarantee this task exists for. No security boundary crossed (bytes are always verified against the report they bound to; no egress/exec). UI window is narrow (file read vs. replace-confirm click) but real for large sources; programmatic callers hit it always. Fix: guard `busy` on entry and bind `current`/emit only if `host.currentGeneration` and `this.current` are unchanged after the await (or hold busy through the read). `clear()` likewise doesn't respect an in-flight `offerSource`.
- **F2 — info — `packages/reports/import/errors.ts:75-89`.** `sniffSchemaVersion` re-parses rejected input via `loadsStrict` — a second parse of the same bytes, only on the SCHEMA failure path, bounded (input already ≤32 MiB and previously parse-successful), extracting a ≤40-char string. It reuses the gate's own strict parser, so the "no re-parse" intent (no parallel parser) holds; noted for the record.
- **F3 — low — `errors.ts:51-67` + `ImportWorkspace.tsx:44-49`.** Classification nuance: well-formed JSON that is not report-shaped (`[]`, `42`, `{}`, ≤24-depth arrays) fails `SCHEMA` → `invalid`, not `not_a_report` — the doc comment scopes `not_a_report` to "not a report at all". Both kinds refuse identically; only the Notice `id` differs. Also `too_large` shows the generic "invalid or unsupported format" copy (copy.json defines no size string) — honest refusal, mildly generic message.
- **F4 — low — `tests/reports/import.spec.ts:461`.** The source-mismatch UI path only exercises `length-mismatch` (`mapping-control.pdf` 1429 B vs required 1437 B); the `sha256-mismatch` branch is never covered by the committed suite. My P1 covers it — behavior is correct; suite gap only.
- **F5 — info — `readers.ts:44-46`, `ImportWorkspace.tsx:162-174`.** The `installed` badge asserts the recorded `reader.id` is installed (correct), but renders beside the report-controlled `name`/`version` label — a crafted report can pair an installed id with fabricated display text next to a trust badge. Inert text; honesty nuance.
- **F6 — info — `tests/reports/import.spec.ts:666-672`.** The 24-case corpus asserts UI `kind` only, not the gate `code`; the 12 attacks assert per-name kinds. Distinct codes (ARCHIVE/KIND/UNICODE/DEPTH/DUPLICATE_KEY/NONFINITE/PROTOTYPE/SCHEMA/HASH/ASSET) are produced; my probes confirmed PROTOTYPE/DEPTH/ASSET/HASH directly.
- **F7 — info — gate semantics (P7).** A fully member-order-reversed valid export is accepted (digest over canonical content). Canonical serialization is a producer property; import correctly validates semantics. Recorded in case the contract ever wants byte-canonical input.
- **F8 — info — handoff stash note.** `git stash list` confirms `stash@{0}` ("Preserve incomplete T01 GUI merge") preserved; working tree clean; verify suite's planning-byte-identical test passes. Worker's disclosure is accurate.
- **F9 — info — `ImportWorkspace.tsx`.** Feature-local composed strings (attached/ready hints, compare explanations, "Original PDF included in this report.") are not in copy.json; canonical strings are verbatim (verified). Consistent with feature convention; new user-facing copy could later want copy.json ownership.

## Criteria audit

1. **Real selected export reopens without upload — PASS.** Real `projectReport`+`serializeReportJson` in-page → real file input → full reopen view (scope/omissions verbatim, exact counts, cited raw texts, sanitized-PNG crop); every request same-origin GET/HEAD/OPTIONS; id/sha/occurrence text absent from URLs/payloads; storage/cookies empty; URL unchanged. Reproduced.
2. **source omission and unavailable reader explicit — PASS (with F1 caveat).** Verbatim missing-source copy + real chooser + nofetch line + named unavailable readers; embedded-source and replay-ready paths honest — except the F1 race can display a stale attach.
3. **malicious report cannot fetch/execute/select profile — PASS.** 36-case asserted corpus + hostile-strings report inert + extended tripwires; my additional probes all refused/inert.
4. **hash mismatch blocks replay — PASS.** Tampered report `HASH`, mutated occurrence `HASH`, swapped asset `ASSET`, resealed fake-PNG `ASSET`, same-size/different-hash source refused.
5. **comparison asks for exact locally selected source reports — PASS.** Two real file inputs only; ready/same_report/incomparable verdicts; invalid side shows own failure; no id/URL input exists; zero egress.

## Not verified / out of reach

- UI-level timing of the F1 race (proven deterministically at controller level; the browser window via the real confirm dialog is narrow).
- Replay execution (none exists by contract — readiness is display-only).
- F24/F25/F26 generated fixtures (status `specified`; semantics covered by constructed variants only).
- `App.tsx` composition/routing (later task — preview mount is the only wiring, same as T16).
- Non-baseline type errors hiding inside the 1008-error React-typings baseline cannot be fully excluded (all 290 feature diagnostics confirmed baseline-class; oxlint clean is the only static signal on those files).
- Evidence files were reviewed in this worktree; the worker's `work/devin/t22` branch was not fetched.

---

# Round 2 — fix verification

- **Candidate:** `a8c9600f8f29a7bcf31af7e006d5478ba841a017` (fix `610eee3`, tests `6d3951b`, evidence `a8c9600`); branch updated by merge `55db481` (round-1 review `684374f` in ancestry)
- **Round-2 verdict: approved** — F1 is resolved with the recommended shape; all reproduced corruption variants now fail closed as `superseded`; F4 batched faithfully. One low-severity residual (R1) plus info notes; nothing else regressed.

## Reproduced (this worktree, real counts)

| Check | Result |
|---|---|
| `bun run test:browser -- tests/reports/import.spec.ts` | **12/12 pass, 0 fail/skip, exit 0 (4.2s)** — new race spec included |
| `tsc -b packages/reports` | exit 0 |
| oxlint `features/import` + `tests/reports` | 0 warnings / 0 errors (96 rules, 8 files) |
| oxfmt `controller.ts` + spec | correctly formatted |
| Spec diff `a2f7e3c→a8c9600` | **purely additive/strengthening** — no assertion removed or weakened; F4 adds `source:length-mismatch` + `source:sha256-mismatch` UI asserts and ordered event details; new 12th spec covers busy/replace/clear phases |
| Evidence consistency | `run.json` evaluated `6d3951b`, 12/12; `handoff.json` review_rounds cites `684374f`, fix commits, and honestly lists unaddressed info findings |

## My own F1 reproductions replayed against the fix (script-level, independent of the committed spec)

| Variant (round-1 result) | Round-2 result |
|---|---|
| `offerSource(slow)` × `offer(B, different doc)` → stale `current`=A, false `attached` on B | **`superseded`**; `current`=B (`doc aaaa…`, replay `missing` — honest); **0** `source_attached` events |
| `offerSource(slow)` × `clear()` → zombie current while `fileState=idle` | **`superseded`**; `current`=null, `fileState=idle`, no zombie |
| Concurrent `offerSource` ×2 | deduped — first-resolver attaches (`source_attached` ×1), loser returns `superseded` via the `this.current !== current` identity check |
| `offerSource` during pending `offer` | `busy` — refused before any byte read |
| `offerSource` × `offer(BAD)` (replace fails) | `superseded`, `idle`, `current` null — correct, nothing left to attach to |

## Fix analysis (`controller.ts:295-372`)

- `:300-302` busy guard refuses while `offer`/`offerCompareSide` holds the lock — never starts a read. `offerSource` still doesn't *set* `busy`, which is correct precedence: a report offer may supersede a pending source pick, while a source pick can never interrupt an import (compare sides don't touch `current`/generation, so they neither block nor invalidate a pending read — verified reasoning).
- `:325` generation + `:341` identity binding placed after the only `await` (byte read); everything after the check is synchronous, so once it passes nothing can interleave. `this.current !== current` also dedups concurrent `offerSource` (winner writes a new object → loser sees superseded).
- Superseded path: no `source_attached`, no `host.own`, no `this.current` write, no `sourceAttached` flip — bytes dropped. Verified.

## Round-2 findings

- **R1 — low — `controller.ts:329-336`.** Residual of F1: when the byte *read itself fails* (`arrayBuffer()` rejects) after supersession, the `catch` emits `source_rejected`/`source:unreadable` under `this.host.currentGeneration` — the NEW generation — before the `:341` check runs. Reproduced: replace mid-read + rejected read → `source_rejected` event gen+1 → `#source-mismatch` notice would render on the new report (wrong-context error, clears on next interaction; nothing attaches, no state corruption). The code comment "the stale read never emits" is exact only for the success path. Narrow + cosmetic — the medium defect is closed; this is a polish item, not a blocker.
- **R2 — info — `controller.ts:300-312` + `ImportWorkspace.tsx:396-405`.** The new `busy`/`superseded`/`no_report`/`not_required` kinds emit no `source_rejected` event, so the UI silently drops the pick (clears `sourceBusy` only). Correct and transient — the file input remains usable; noted for completeness.
- **F1 — RESOLVED.** Verified by my own replays, not only the committed spec.
- **F4 — RESOLVED.** Same-length corrupt `SOURCE_PDF` (last byte XOR `0x01`) through the real `source-file-input` asserts `source:sha256-mismatch` verbatim detail + ordered `[length-mismatch, sha256-mismatch]` rejection events — genuine same-size/different-hash refusal, exactly the missing branch. Fidelity confirmed.
- **F2/F3/F5/F6/F7/F8/F9** — info-level per round 1; worker documented them as intentionally unchanged; no dispute.


---

## Delta review — 2026-09-13, evaluated `412fb9b2`

- **Reviewer:** devin-coordinator (acceptance refresh; not the implementing worker for this delta's shared changes)
- **Scope delta:** No owned files changed since the original review; the staleness was shared-input only (AGENTS.md, execution/config, bootstrap/coordination suites, merged fixture work).
- **Fresh run:** Re-ran all registered commands at `412fb9b2`: **13/13 green**, zero failures.
- **Verdict:** prior review stands; delta introduces no acceptance-relevant regression.
