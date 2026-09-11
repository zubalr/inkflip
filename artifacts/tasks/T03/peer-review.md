# Independent Peer Review — T03

**Reviewer:** devin-review-t03 (SWE-2 subagent, independent — did not write this code)
**Candidate:** `work/devin/t03` @ `4f6b66e0b7e84adb415f9d369cc3beaa4a98de38` (impl `521c2fa` + evidence), base `3bef697`
**Date:** 2026-09-12
**Mode:** read-only; no files modified/committed/dispatched; `planning/` verified byte-identical after probes

## Verdict: changes-needed

Faithful port — evidence honest, scope clean, heavy parity surface (schema, hash, normalize, semantic codes) verified bit-for-bit. Two defects must be fixed before merge; three more strongly recommended.

## Checks run — real results

- `git diff --name-only 3bef697..HEAD`: 17 paths, all inside allowed scope; `package.json`/`native/pyproject.toml` unchanged; `native/uv.lock` untracked side artifact, not committed
- Schema identity: sha256 identical for planning/, packages/contracts/, native/ copies
- `node --test tests/contracts/*.test.mjs`: 24/24 pass — matches commands.log
- `python3 scripts/generate_contracts.py --check`: exit 0
- `uv run --project native python -m pytest native/tests/contracts -q` (contract form): exit 1, `No module named pytest` (expected; T02 owns dev group)
- `uv run --project native --with pytest python -m pytest …`: 22 passed, 88 subtests
- `python3 -m unittest discover -s native/tests/contracts`: 22 OK
- `python3 scripts/task_acceptance.py run verify`: 30 OK, exit 0
- `npx -y -p typescript@5.9.3 tsc -b packages/contracts`: exit 0
- Generated types vs delivered `planning/contracts/generated/inkflip.d.ts`: bodies identical (header comment only); reference `generate_types.py` rerun confirms
- Golden provenance: regenerated all of `digest-golden.json` with real `contractlib.py` — 0 mismatches (22 digests, 13 normalize, 3 occurrence ids, 6 report identities)
- Independent cross-runtime digests (run_key/report_id on 6 fixtures, mixed-type digest, occurrenceId, seal()): byte-identical TS↔PY
- Differential fuzz: 34 schema-aware report mutations 33/34 identical codes; 76 strict-JSON inputs 75/76 identical (divergences = findings below)

## Findings

**F1 — MAJOR (required fix): uncaught `TypeError` on schema-legal `pixel_size: null`, `packages/contracts/src/core.ts:1169`.**
`Asset.pixel_size` is `anyOf [array,null]`. For a PNG asset passing other checks, TS evaluates `a.pixel_size![0]` on `null` → `TypeError` escaping the ContractError surface. Python → `ContractError('ASSET')`. Verified end-to-end: TS=`RAW:TypeError`, PY=`ASSET`. Reachable fail-open crash on untrusted input + failure-code parity break. Fix: `a.pixel_size !== null && wh[0] === a.pixel_size[0] && wh[1] === a.pixel_size[1]` (mirroring Python list-equality).

**F2 — MAJOR (required fix): `canonical()` silently hashes non-plain objects as records instead of `TYPE`-rejecting, `core.ts:384-406`.**
`typeof value === 'object'` branch accepts Map/Set/Date/RegExp/Uint8Array/class instances → `digest(new Map([['a',1]])) === digest({})` — silent collision in an identity function. Python raises `ContractError('TYPE')` for all of these (verified). Only reachable programmatically, but `canonical`/`digest`/`reportDigest`/`runKey` are the public identity API. Fix: restrict object branch to plain objects (prototype `Object.prototype`/`null`), else `TYPE`.

**F3 — MINOR (recommended): failure-code divergence on huge integer literals.** `loadsStrict('9'.repeat(400))` → `NONFINITE` (`Number()` → Infinity); Python arbitrary-precision int → `NUMBER` (verified incl. nested). Only pure-integer tokens overflowing to Infinity (~≥309 digits) diverge; `1e999` is NONFINITE in both. Fix: detect integer-literal overflow in `parseNumber`, report `NUMBER`.

**F4 — MINOR (recommended): Python port leaks raw exceptions on pathological programmatic inputs, asymmetrically vs TS.**
- `loads_strict('\ud800')` → raw `UnicodeEncodeError` at size check (`core.py:73`); TS → `ContractError('JSON')`
- `canonical('x\ud800')` / lone-surrogate dict keys → raw `UnicodeEncodeError` (`core.py:155,167`); TS → `ContractError('UNICODE')` (reference also leaks here — TS deviates upward; "identical in both languages" doc claim imprecise at this edge)
- `loads_strict(bytearray(b'{}'))` → raw `AttributeError`; TS coerces then rejects `JSON`
All unreachable via decoded bytes; contradicts "every rejection is a ContractError" only for programmatic callers.

**F5 — recommended: add regression cases for F1/F2** (PNG `pixel_size: null`; `canonical` on Map/Date/class instances) so the delivered-fixture gap can't regress silently.

## Notes (non-blocking)

- `date-time` parity is environment-conditional: FormatChecker() has no `rfc3339-validator` here, so it conforms — matching the generated checker. If the lock ever pulls `jsonschema[format]`, Python enforces `started_at` while TS stays lax. T02 must freeze the dependency set so the checker set stays pinned.
- uuid parity verified exact (jsonschema 4.26.0 `is_uuid` ≡ TS regex; 32-hex/braces/`urn:` reject in both).
- `validateJson` has no Python `validate_json` counterpart (cosmetic asymmetry); ephemeral `tsc@5.9.3` vs root `typescript@6.0.2` (unresolved, T02); `packages/contracts/` has no README; `docs/ATTRIBUTION.md` correctly deferred to coordinator; generator latent edges (bare-`$ref` `$defs`, `default`/`contentEncoding`/`contentMediaType` unemitted — unused by this schema); Python `zip` truncation vs TS index-NaN only on schema-invalid direct calls.

## Per-criterion assessment

| Criterion | Assessment |
|---|---|
| Fixtures + expected codes pass in TS/Python | Substantiated — 12/12 valid, 30/30 invalid, both runtimes, independently rerun. Caveat: F1 is a code-parity hole outside delivered fixtures. |
| Hash vectors agree | Substantiated — 11/11 vectors byte-exact; goldens regenerated from contractlib; independent cross-runtime digests identical. |
| Type generation deterministic | Substantiated — `--check` exit 0; body identical to delivered inkflip.d.ts. |
| Untrusted report never compiles schema | Substantiated — generated static checker (no eval/Function/dynamic import); VALIDATOR built once at import; executable tests both suites. |
| Array order / hash-excluded timestamps | Substantiated — order significant in arrays, canonical in objects; report_id excludes only report_id/execution_id/started_at/duration_ms/data_base64. |
| Required rejections | dup keys ✓, lone surrogates ✓ (pair-safety verified), nonfinite/unsafe ✓ (F3 edge), unknown versions ✓ fail-closed, broken refs ✓; I02/I03/I05/I10/I13 hold. |

## Deviations judgment

Malformed JSON → `ContractError('JSON')`, bad UTF-8 → `ContractError('UNICODE')`: acceptable exact-port equivalents — identical accept/reject on every reachable path, required by the stable-failure-code surface. Not contract drift; no proposal needed. (F4 notes residual unwrapped pathological escapes in Python.)

## Evidence integrity

receipt.json: all 5 criteria `executed` with real non-empty evidence paths; every claimed count reproduced exactly. commands.log accurate incl. honest pytest-leg failure. review.md explicitly disclaims reviewer approval. No fabricated results.

## Required before merge

1. F1: guard `a.pixel_size` before indexing (`core.ts:1169`) — restore `ContractError('ASSET')` parity on `pixel_size: null`.
2. F2: `canonical()` `TYPE`-rejects non-plain objects — restore reference parity, eliminate silent identity collisions.

Strongly recommended: F3 (`NUMBER` not `NONFINITE` for integer-literal overflow), F4 (wrap pathological raw escapes in Python or document asymmetry), F5 (regression cases for F1/F2).
