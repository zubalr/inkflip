# T03 worker self-review notes (not an independent review)

**Task:** T03 — Implement schema, strict validation, canonical identity and generated types
**Branch:** `work/devin/t03` · **Beads:** `pdf-t03` · **Worker:** `devin-t03`
**Implementation commit:** `521c2faceb5931f2f2190a6a0e3559a04a0469f4`

This file satisfies the contract's `artifacts/tasks/T03/review.md` evidence
slot with the worker's own review notes. Independent review is still owed
and remains the coordinator's step.

## Scope conformance

- Only allowed paths touched: `packages/contracts/`,
  `native/inkflip/contracts/`, `scripts/generate_contracts.py`,
  `tests/contracts/`, `native/tests/contracts/`, `artifacts/tasks/T03/`.
- `planning/` is byte-identical (`git status --porcelain -- planning/`
  empty; verified in commands.log).
- `native/uv.lock` (untracked, T02-owned) is deliberately uncommitted.
- No manifest, lockfile, coordination, or reserved-path changes.
  `packages/contracts/tsconfig.json` adds only contract-package-local
  compiler options (`emitDeclarationOnly`, `allowImportingTsExtensions`,
  `lib` for TextEncoder/TextDecoder) required by the new sources.

## Provenance / attribution

- `native/inkflip/contracts/core.py` is an exact port of the delivered
  reference `planning/tools/contractlib.py` (same project, owner-approved
  reuse per task contract). The function-level diff is recorded in
  commands.log: only formatting plus the new `occurrence_id` and the two
  documented error-surface refinements (`JSON`, `UNICODE` instead of raw
  decode exceptions — kept identical in both languages).
- `packages/contracts/src/core.ts` is the TypeScript port of that module;
  `scripts/generate_contracts.py` reuses the delivered
  `planning/tools/generate_types.py` type-mapping rules and adds the
  precompiled structural validator emitter.
- `docs/ATTRIBUTION.md` is outside T03's allowed scope; the coordinator
  should record this reuse there (required_updates item).

## What was verified (all in commands.log)

- 12/12 valid planning examples validate; 30/30 invalid examples fail with
  the indexed expected code — in both languages, same test IDs/fixtures.
- 11/11 hash vectors byte-exact; the reference-computed golden
  (`tests/contracts/fixtures/digest-golden.json`, produced by
  `planning/tools/contractlib.py`) matches both ports, including the
  identical occurrence id `o_41f8b9e2e8dd5346dd2b1cf33bef596f`.
- Node suite: 24 tests pass; Python suite: 22 tests + 88 subtests under
  real pytest (ephemeral overlay) and 22 under unittest.
- `generate_contracts.py --check` exit 0 (deterministic, drift-free);
  vendored schemas byte-identical via `cmp -s`.
- Strict typecheck `tsc -b` exit 0 (ephemeral typescript@5.9.3; repo
  toolchain pending T02).
- `task_acceptance.py run verify` exit 0 — no regressions.

## Parity decisions a reviewer should confirm

- `loadsStrict`/`loads_strict` report malformed syntax as
  `ContractError('JSON')` and bad UTF-8 as `UNICODE` (reference propagated
  `JSONDecodeError`/`UnicodeDecodeError`). Deliberate, documented,
  identical in both languages.
- Format checking matches the pinned jsonschema `FormatChecker()` without
  extras: `uuid` enforced; `date-time` unregistered upstream →
  annotation-only. Mirrored in the generated TS validator.
- `__proto__` parses as an ordinary own member (defineProperty) so
  duplicate detection and canonicalization see it — matching Python dict
  semantics.
- Python `canonical` rejects non-string dict keys (`TYPE`); unreachable
  from parsed JS objects (keys are always strings) — asserted as
  documentation, parity holds for all JSON-representable input.
- Python's `float.is_integer()` bound maps to
  `Number.isInteger(v) && !Number.isSafeInteger(v)` — identical for all
  doubles.
- Index units in normalization maps are Unicode code points in both
  languages (Python `str` iteration ↔ JS `[...s]` iteration).
- `date-time`/`uuid` format behavior, `re.search` `$`-before-newline, and
  code-point `len()` semantics are preserved in the generated validator's
  helpers (`testPattern`, `strlen`, `isUuid`).

## Known gaps / blockers

- `uv run --project native python -m pytest native/tests/contracts -q`
  exits 1: `No module named pytest`. T02 owns the dev group + lockfile;
  requested in `dependency_requests`. Supplementary evidence: the same
  suite passes 22 tests/88 subtests under real pytest via
  `uv run --with pytest` and under `python -m unittest`.
- No repo tsc/oxlint/oxfmt yet (T02). No runtime schema compilation in
  either runtime — asserted by executable tests, not just inspection.

## Post-review update (devin-review-t03, verdict changes-needed → addressed in `f5bfff1`)

- **F1 (required):** `core.ts` PNG check indexed `a.pixel_size[0]` on
  schema-legal `null` → uncaught `TypeError`. Now guarded
  (`a.pixel_size !== null && …`), failing `ContractError('ASSET')`
  exactly like the Python list-equality. Repro in commands.log.
- **F2 (required):** `canonical()` hashed non-plain objects as records —
  `digest(new Map([['a',1]])) === digest({})`, a silent identity
  collision. The object branch now requires prototype
  `Object.prototype`/`null` else `ContractError('TYPE')`, matching the
  Python `dict` check.
- **F3:** `'9'.repeat(400)` reported `NONFINITE`; Python's
  arbitrary-precision int reports `NUMBER`. Pure-integer literals that
  overflow to Infinity now report `NUMBER` in `parseNumber`; `1e999`
  stays `NONFINITE` in both.
- **F4:** Python port now wraps its remaining pathological escapes:
  bytes-like inputs (`bytearray`/`memoryview`) decode like `bytes`,
  non-str input raises `ContractError('TYPE')`, lone-surrogate
  strings/dict keys raise `ContractError('UNICODE')` in `canonical` and
  `ContractError('JSON')` from `loads_strict` (surrogatepass keeps the
  size check defined; both match the TS codes). Also added
  `validate_json` to mirror the TS `validateJson` surface.
- **F5:** regression cases added in both suites: PNG `pixel_size:null` →
  `ASSET`; `canonical`/`digest` on Map/Set/Date/RegExp/Uint8Array/class
  instance → `TYPE`; integer-literal overflow → `NUMBER` with `1e999`
  staying `NONFINITE`; Python pathological-input cases.

Counts after fixes: node `--test` 27/27; unittest 26/26; real pytest
(ephemeral overlay) 26 passed + 92 subtests; `generate --check` exit 0;
`tsc -b` exit 0; `task_acceptance.py run verify` 30/30. The contract
pytest leg remains blocked only by the missing T02 dev dependency.

## Suggested reviewer commands

```sh
node --test tests/contracts/*.test.mjs
uv run --project native python -m pytest native/tests/contracts -q   # needs T02 pytest
uv run --project native --with pytest python -m pytest native/tests/contracts -q
uv run --project native python -m unittest discover -s native/tests/contracts -v
python3 scripts/generate_contracts.py --check
npx -y -p typescript@5.9.3 tsc -b packages/contracts
git status --porcelain -- planning/
diff <(grep -E '^def |^    def ' planning/tools/contractlib.py) \
     <(grep -E '^def |^    def ' native/inkflip/contracts/core.py)
```
