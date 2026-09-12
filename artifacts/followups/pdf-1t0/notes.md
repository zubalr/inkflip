# pdf-1t0 — cross-reader OcrHandle id collision (T10 wave-5 residual O3)

Bug bead. Source finding: `artifacts/tasks/T10/review.md` round-2 residual
observation O3 (`CROSS_READER_HANDLE`). Worktree `worktrees/pdf-1t0`, branch
`work/devin/pdf-1t0`, base `51a8619`. Local commits only — no push, no Beads.

## Defect

`OcrHandle.id = ocrh_<generation>_<floor(now)>_<scope.op>` (wave-5 F2 fix) is
unique per READER instance only — `opSeq` is a per-reader counter. Two
`TesseractOcrReader` instances whose opens land in the same clock tick with
aligned op counters mint identical ids, and every admission guard compared only
`.id`. Reproduction (fixed clock `now:()=>1000`, both readers' first opens):
`hA.id === hB.id === 'ocrh_1_1000_1'`; `readerA.close(readerB.handle)` was
admitted and killed **reader A** (the called reader), the cross-talk the review
demonstrated as `afterForeignClose: unsupported`.

## Fix approach — identity binding (chosen), not a longer id

The review suggested either a per-reader-instance component in the id string or
binding the handle to its owning reader. **Binding won**: it makes collision
impossible rather than improbable, and it matches the code's own shape — the
open() catch path already used object identity (`this.handle === scope.handle`,
reader.ts:622), and the sibling readers-pdfjs adapter treats `DocumentHandle`
as an in-process object token (`handle.closed`, live `task`/`doc` fields — it
can never be serialized anyway).

Change (`packages/readers-tesseract/src/reader.ts`, +31/−9): every `.id`
comparison replaced by object identity against the handle OBJECT the reader
installed:

- `guard()` — `this.handle !== scope.handle` (was `.id !==`)
- `plan()` — `this.handle === handle` (was `.id ===`)
- `extract()` — `this.handle === handle` (was `?.id ===`)
- `extractOnce()` — `this.handle === handle` (was `.id ===`)
- `close(handle)` — `this.handle !== handle` → silent no-op (was `.id !==`);
  same stale-handle semantics, now also covers foreign/forged objects.

Consequences:

- A foreign reader's colliding-id handle differs by OBJECT → refused at every
  site (typed `unsupported` for plan/extract; no-op for close).
- A forged same-shaped copy (`{...h}`, `{id: h.id, …}`) is a different object →
  refused. Fail closed as required.
- `OcrHandle.id` remains minted unchanged (contract `[A-Za-z0-9._-]+`,
  per-reader unique) — now a diagnostic label only; comments updated to say so.
  No external consumer reads `handle.id` (only `index.ts` re-exports the type).
- Legitimate callers pass back the object `open()` returned — unchanged
  behavior for all existing tests.

## Tests (`tests/readers/tesseract.spec.ts`, +71, 0 removed)

One new stub-level case in `light: independent lifecycle probes (stub engine)`
(after the wave-5 F2 port):

- `foreign reader handles with colliding ids are refused; foreign close
  retires nothing (stub)` — two `__rv.make` readers under `now:()=>1000`:
  asserts `hA.id === hB.id` (collision really exercised) and `hA !== hB`;
  `a.close(hB)` / `b.close(hA)` / `a.close({...hA})` resolve as no-ops;
  `a.extract(forged)`, `a.plan(forged)`, `b.extract(hA)` refuse typed
  `unsupported`; then BOTH readers still extract `completed` and neither
  stub worker shows `terminated` — pre-fix the foreign close killed the
  called reader.

Regression-verified: the same test FAILS on the pre-fix reader
(`afterA: unsupported` — the review's exact kill) and passes post-fix.

## Checks run in this worktree

- `bun x tsc -b` — exit 0.
- `node --test tests/readers/crop-math.mjs` — 13/13.
- `bun run test:browser -- tests/readers/tesseract.spec.ts -g 'light:'` —
  **31/31 pass** (includes the new case; the file now collects 45 total:
  44 + 1 new).
- `bun x oxlint <changed files>` — 0 errors, 1 pre-existing warning
  (unused `region` param in the real zombie-job probe, untouched code).
- `bun x oxfmt --check` — both files already failed default-config check
  before the edits (no project config); not a gate here, left as-is.

## Stub-only vs engine-requiring (merged-run expectation)

- Light subset (`-g 'light:'`, 31 cases): all pass here. Of these, 28 are
  pure stub-engine; **3 still exercise the REAL engine at worker-init only**
  (no recognize): 'a stale or corrupt cache slot is replaced before the
  engine sees it', 'the engine consumes the verified slot — never a second
  divergent copy', 'close during a real open aborts the raw worker init'.
  The new pdf-1t0 case is pure stub (`__rv` seam, fixed clock).
- The 14 non-light cases are the heavy suite the integrator holds the slot
  for: real recognize over the pinned traineddata/pdf.js (incl. real cache
  provenance ×2 and the real zombie-job probe). Expected count at merge:
  **45/45**.

## Residual risk

- Object identity means a *structurally equal* handle (e.g. a deep copy
  transported across a worker boundary) is refused. That is the intended
  fail-closed behavior — the contract handle is an in-process capability
  token, same as readers-pdfjs's `DocumentHandle`. No repo consumer
  serializes handles.
- `OcrHandle.id` can still collide across readers as a string; nothing keys
  on it now. If a future caller records ids for diagnostics, ambiguity is
  cosmetic only — consider adding a reader-uid component then, not needed
  for the admission fix.
- `close()` keeps the established silent no-op for non-current handles
  (stale ⇒ foreign ⇒ forged all ignored); plan/extract keep the typed
  `unsupported`. Consistent with pre-existing semantics; a loud refusal for
  close would be a behavior change beyond this bead's scope.
