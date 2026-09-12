# T31 independent review — shared Node comparison bridge

- **Reviewer:** independent reviewer (not the writer `0e2f70ff` / devin-t31 worker; this code was not run by this reviewer before this review)
- **Candidate:** `510abe5` on `review/devin/t31` (impl `e260b92`, tests `ec992e6`, evidence `510abe5`)
- **Reviewed in:** `/Users/zubair/Code/Projects/pdf project/worktrees/review-devin-t31`
- **Verdict: APPROVED**

All five contract criteria were verified by independent re-execution and by
fresh probes written by this reviewer — worker claims were not taken on faith.

## Reproduced results (this checkout, verbatim contract command)

| Command (exact registered segment) | Result |
| --- | --- |
| `node --test tests/bridge/*.test.mjs` | 17 collected / 17 passed / 0 failed |
| `uv run --project native python -m pytest native/tests/bridge -q` | 28 collected / 28 passed / 0 failed / 0 skipped (2.5 s) |
| `python3 scripts/task_acceptance.py task T31` | 45/45/0/0, exit 0, no failures |
| `python3 scripts/acceptance_receipts.py verify-run T31` | `{"verified":"T31", tests 45/45/0/0}` |

`run.json` binds `evaluated_commit` `ec992e6f16e3712a79163293fb50b6d7b0368ed9`
(the test commit); freshness to HEAD `510abe5` holds because the later commit
adds only task evidence outside the freshness scopes. No stray `bridge.mjs` or
driver processes remained after the suites.

## Criterion 1 — golden cross-language cases agree exactly: PASS

- The same committed corpus `tests/bridge/cases.json` (12 normalize + 10 align)
  flows through BOTH real legs: in-process shared TS (`opNormalize`/`opAlign`
  in `packages/compare/node/protocol.mjs`, reached via
  `tests/bridge/direct_driver.mjs` — the browser-path leg) and
  Python→spawned fixed entrypoint (`CompareBridge` → `bridge.mjs`). Both
  suites assert byte-identical result payloads (`assertEqual` /
  `assert.deepEqual` on the full `{results}` JSON, not sampled fields).
- The goldens are real, not trivial strings: NBSP/ideographic-space/U+2028-29
  whitespace runs, combining sequences, `ﬁ`/`ﬂ` ligatures, supplementary
  scalars, Arabic/CJK, ZWSP/BOM preservation, CRLF; align cases carry real
  polygon geometry (box→4-point canonical-page polygons), null geometry
  (`page_only`, never rescued — I04/F23), region scoping, duplicates,
  split/merge provenance, ambiguous ties, and a supplied-`normalized_text`
  parity case. `bridge.test.mjs` "golden cases carry their claimed semantics"
  and the Python mirror pin concrete expected statuses/provenance, so the
  corpus cannot be a tautological self-agreement.
- Reviewer-authored novel cases (not in the corpus) ran byte-identical through
  both legs: `ﬄuﬀy`, enclosed digits `①②③`, `n+combining tilde`, embedded
  NBSP, soft hyphen, Devanagari+Hebrew, U+2028/U+2029 (each correctly
  collapsed/preserved per scalar-whitespace-v1), and a fractional-geometry
  region-scoped align (`[10.5, 20.25, 91.75, 33.125]` vs `[10.5001, …]`)
  producing 3 unique matches including `ﬂavor` vs `flavor` bound by geometry
  with nonzero text distance — consistent with F15 semantics.

## Criterion 2 — missing Node is a capability error, not fallback: PASS

Reviewer probes raised `BridgeCapabilityError(reason='capability')` for all
absence modes: PATH stripped to an empty dir, nonexistent explicit node path,
a non-executable regular file as node, a directory as node, missing
entrypoint, entrypoint-as-directory, plus injected spawn `FileNotFoundError`/
`PermissionError` (ENOENT/EACCES). No Python fallback exists:
`compare_bridge.py` contains zero comparison code (ops exist only as bridge
calls). `native/inkflip/contracts/core.py::normalize` is a pre-existing T03
contract port — the bridge never substitutes it; it parity-checks supplied
`normalized_text` against the shared TS code (`NORMALIZATION` rejection on
drift, verified) and `test_python_contract_normalize_and_bridge_agree` proves
the port agrees with the shared engine rather than replacing it.

## Criterion 3 — stdout bounded: PASS

- Reviewer flood probe: a real runaway child (64 MiB stdout via injected
  spawn) was SIGKILLed within ~0.04 s and its process group confirmed reaped
  (`ProcessLookupError`); typed `output_limit`, never a truncated answer.
- Entrypoint stdin cap verified directly: a 33 MiB request → `ok:false`
  `SIZE` with exit 0 (not a partial read); a just-under-32 MiB request still
  succeeds — boundary is honest.
- Python request cap (`max_request_bytes`) refuses pre-spawn
  (`request_too_large`, recorded spawn list empty); stderr cap →
  `output_limit`. `loads_strict` (contract bounded JSON, 32 MiB/depth 24)
  validates the response before envelope checks.

## Criterion 4 — no shell/plugin/profile selection from report: PASS

Reviewer probe with a poisoned parent environment (`NODE_OPTIONS=--require
/tmp/evil.js`, `PATH` prefixed with a hostile dir, `LD_PRELOAD`, `BASH_ENV`)
recorded argv = exactly `[resolved node, repo bridge.mjs]`, `shell=False`,
and a child env containing only `LANG`/`LC_ALL`/`TMPDIR` — no PATH or
NODE_OPTIONS forwarding. Hostile flag-shaped payloads (`--require=…`,
`-e "…"`, `--input-type=module`, `--inspect-brk`, `$(curl …|sh)`, backticks)
normalize as inert text; a foreign op → `remote_op`; smuggled page fields
(`profile`, `exec`) → `remote_field` with argv unchanged; the entrypoint's
closed envelope independently rejects unknown fields (`FIELD`). There is no
argv/env construction path for request data to reach.

## Criterion 5 — manifests retain comparator version: PASS

`comparatorIdentity()` is emitted by the installed entrypoint itself on every
response (describe, normalize, align and error replies — verified on the real
entrypoint). Algorithm ids are imported constants from the executing shared
modules (`NORMALIZATION_VERSION`, `REGION_MATCH_V1.version`, `SCORE_SEMANTICS`
— the same objects that drive matching in `match.ts`), so they cannot drift
from the installed code; `node`/`platform` are live runtime values.
`BridgeResult.manifest_entry()` surfaces the block into a manifest-shaped
record (I13); both suites assert it.

## Additional contract checks

- **Scope:** `git diff 7f41409..510abe5` touches only `packages/compare/node/`,
  `native/inkflip/compare_bridge.py`, `tests/bridge/`, `native/tests/bridge/`
  and task evidence. `native/tests/bridge/` is outside the listed
  `allowed_scope` but is mandated by the registered pytest command — see F2.
- **Wall deadline + group kill:** 0.5 s limit → `timeout` at ~0.51 s, SIGKILL
  to the child process group confirmed by pid probe.
- **`allow_nan=False`:** present at `compare_bridge.py:267`; unserializable/
  non-finite input → typed `type` error pre-spawn.
- **Selectors pump:** real `selectors.DefaultSelector` loop byte-counting
  both streams; verified with real floods, not mocks.
- **No test-only knobs:** only constructor dependency injection
  (`spawn`/`limits`/`node`/`entrypoint`); no env-var/file/debug toggles.
- **Receipt ACE dict:** `acceptance_criteria_evidence` keys exactly equal the
  five contract criteria (trailing period normalized by `criterion_evidence`
  at `scripts/acceptance_receipts.py:172-182`); all cited evidence paths exist
  and are nonempty; `verify-run` passes.
- **Evidence honesty:** `run.json` correctly records the worker's checkout
  path; worker claims (counts, POSIX-only limitation, entrypoint trust
  boundary) all matched observed behavior.

## Findings

- **P1:** none.
- **P2:** none.
- **P3 (contract data, owner fix — not a worker violation):** T31
  `allowed_scope` omits `native/tests/bridge/` while `commands` mandates
  `pytest native/tests/bridge` (the harness fails on an empty collection, so
  the command is impossible without it). T29/T27 name their pytest dirs in
  scope; this is a contract-data gap. The worker handled it honestly —
  test-only file at the mandated path plus an explicit
  `contract_observation` in `handoff.json`. Coordinator should record the
  scope correction through the contract owner.
- **P3 (hardening):** `BridgeLimits` validation (`compare_bridge.py:199-208`)
  accepts `NaN`/`inf` (`value <= 0` doesn't reject them): `wall_seconds=NaN`
  silently disables the deadline, `inf` caps never trip. Not reachable from
  request/report data and defaults are safe, but a `math.isfinite()` check
  would make the bound guarantee unconditional.
- **P3 (cosmetic):** `BridgeResult.manifest_entry()` defaults a missing
  `package` to the literal `"@inkflip/compare"` (`compare_bridge.py:130`),
  which could mask a malformed comparator block; surfacing `None` would be
  more honest. All other fields surface verbatim.
- **Observation (not a defect):** both golden legs share `protocol.mjs`'s
  `resolveOccurrence`/`resolvePage` adapter, so a semantic bug inside that
  adapter could in principle cancel across legs. Mitigated by the
  claimed-semantics assertions (concrete statuses/provenance) and the
  independent contract-port parity test; normalize has essentially no
  adapter. Adequate for TEST-31's wire-boundary purpose.

## Conclusion

Implementation `e260b92` + tests `ec992e6` satisfy all five T31 acceptance
criteria under independent verification: real shared-engine goldens agree
byte-exactly across the direct TS path and the Python→Node bridge; missing
runtime is a typed capability failure with no fallback; streams are honestly
bounded with process-group kills; argv/env are fixed and unreachable from
report data; comparator identity bound to the installed entrypoint rides
every response for manifests. **Approved.** The P3 items are for
coordinator/owner follow-up and do not block acceptance.
