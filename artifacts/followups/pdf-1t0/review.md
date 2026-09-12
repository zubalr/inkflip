# pdf-1t0 — independent review of fix candidate `736d640`

Reviewer: independent (not the writer `213f36a3`). Branch `review/devin/pdf-1t0`,
worktree `worktrees/review-devin-pdf-1t0`, base `51a8619`. Commits under review:
`89b994a` (impl, +22/−9), `fe4682d` (regression test, +71/−0), `736d640` (notes).

## Verdict: APPROVED

The identity-binding fix closes the T10 wave-5 residual O3 (`CROSS_READER_HANDLE`)
completely, preserves every intended semantic, and the regression test provably
fails on the unfixed code (reproduced below — not just the writer's claim).

## 1. Defect closure — all admission surfaces audited

The review reproduction (`artifacts/tasks/T10/review.md` O3): two
`TesseractOcrReader` instances under `now:()=>1000` each mint `ocrh_1_1000_1`
on their first open (per-reader `opSeq` counters align); `readerA.close(hB)`
was admitted by `.id` comparison and killed reader A's own worker
(`afterForeignClose: unsupported`).

All five guard sites now bind the handle OBJECT (`packages/readers-tesseract/src/reader.ts`):

- `guard()` :712 — `this.handle !== scope.handle` (was `?.id !==`)
- `plan()` :979 — `this.handle === handle` (was `.id ===`)
- `extract()` :1049 — `this.handle === handle` (was `?.id ===`)
- `extractOnce()` :1201 — `this.handle === handle` (was `.id ===`)
- `close()` :1438 — `this.handle !== handle` → silent no-op (was `?.id !==`)

**Sixth-path hunt — none found.** Complete handle-surface enumeration:

- `open()` installs the object itself (:602-603); its catch path at :622
  already used `this.handle === scope.handle` pre-fix (verified against
  `89b994a^`) — the fix adopts the code's own idiom, as claimed.
- `beginScope(..., handle)` :647 stores the object as `scope.handle`; it is
  only reachable after `extract()` admission (:1049 precedes :1057), and
  `guard()` re-checks it by identity at :712 after every await.
- Progress/error callback admission (`scopeAdmits` :788, `forwardProgress`
  :803, `forwardError` :816) keys on `OpScope` objects in `liveScopes` /
  `jobScopes` — engine `userJobId`s (`j_${scope.op}_${check.id}_${attempt}`
  :1293), per-reader maps; never `handle.id`. Cross-reader handle-id
  equality cannot reach these.
- Retry internals: `ownsResources` (:1163) keys on `this.opSeq === scope.op`;
  each retry re-enters `extractOnce` which re-checks identity (:1201).
- `prepareModel()` :509, `removeModelData()` :533, `describe()` :497,
  `pages()` :963 take no handle — nothing to forge.
- Raster/model paths key on `cfg.renderReaderId` (:1233) and
  `scope.handle?.model.provenance` (:1074, :1392 — a field read off the
  scope's own admitted handle object, not a comparison).
- `grep` for `handle.id` / `.id ===` / `.id !==` across
  `packages/readers-tesseract` + the spec: zero behavioral uses remain; the
  only two hits are the diagnostic assertions inside the tests themselves
  (:2157, :2193). `index.ts` :102 re-exports `type OcrHandle` only.
  App-side (`apps/web/src/features/open/controller.ts` :204-237) stores the
  object `open()` returned and passes it back — capability-token usage,
  unaffected by identity binding.

## 2. Semantics preserved

- Same-reader stale handles still refused: wave-5 test
  `same-millisecond opens mint distinct handle ids; stale close/extract
  refused (stub)` (:2140) passed in the 31/31 run — a stale handle is a
  different object, so identity covers the wave-4/5 requirement strictly
  better than the id string did.
- `close()` silent no-op for non-current handles unchanged (:1438 early
  return; no-arg `close()` still closes, per the optional-param contract).
- `OcrHandle.id` still minted `ocrh_<gen>_<floor(now)>_<op>` (:595),
  contract `[A-Za-z0-9._-]+`, now documented diagnostic-only (:222-227
  interface comment, :589-594 mint comment).
- plan/extract keep typed `unsupported` refusals.

## 3. Test genuinely exercises the collision — red check reproduced

- `tests/readers/tesseract.spec.ts` :2176: two `__rv.make` readers (each a
  fresh `TesseractOcrReader` — verified `t10-pixel-harness.ts` :406-471)
  under one `now:()=>1000`; `expect(out.ids.equal).toBe(true)` proves
  `hA.id === hB.id === 'ocrh_1_1000_1'` and `sameObject === false` proves
  distinct objects. Foreign closes both directions + forged `{...hA}`
  close → no-ops; forged extract/plan and `b.extract(hA)` → `unsupported`;
  both readers then extract `completed`, `terminatedA/B === [false]`.
- **Red check reproduced by this reviewer**: restored
  `89b994a^:reader.ts` into the working tree, ran
  `bun run test:browser -- tests/readers/tesseract.spec.ts -g 'foreign reader handles'`
  → 1 failed, `afterA` = `unsupported` (expected `completed`) — the exact
  review kill. Working tree then restored to the fix; `git status` clean.

## 4. Reproduced counts (this checkout)

- `bun install` — required first (fresh worktree; `node_modules` ignored).
- `bun x tsc -b` — exit 0.
- `node --test tests/readers/crop-math.mjs` — **13/13 pass**.
- `bun run test:browser -- tests/readers/tesseract.spec.ts -g 'light:'` —
  **31/31 pass** (6.3s), including the new pdf-1t0 case (#31), the wave-5
  same-ms stale-handle case (#30), and all 3 real-engine-init light cases
  (#12 stale-cache-slot, #13 verified-slot, #24 close-during-real-open —
  staged model present at
  `apps/web/public/models/tessdata-fast-eng/7d4322bd/eng.traineddata`,
  pdfjs-dist + tesseract.js installed via workspaces).
- Red re-run on pre-fix reader: **1/1 fail** as described above.
- Heavy 14-case real-OCR suite: intentionally not run — integrator's slot.

## 5. Diff hygiene

Range `51a8619..736d640`: `reader.ts` +22/−9, `tesseract.spec.ts` +71/−0,
`notes.md` +107 — nothing else. No unrelated changes, no test-only knobs
(the `__rv` seam predates this fix), comments updated consistently at every
touched site (interface doc, mint site, guard, close). Notes file's claims
(checks run, line refs, stub-vs-real split, residual risk) all verified
accurate.

## Residual observations (non-blocking)

- `OcrHandle.id` can still collide as a string across readers — cosmetic
  only, nothing keys on it; noted by the writer too.
- A structurally equal deep-copied handle is refused — intended
  fail-closed capability-token semantics; no repo consumer serializes
  handles.
