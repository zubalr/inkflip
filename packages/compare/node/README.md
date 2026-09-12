# `@inkflip/compare/node` — fixed shared comparison entrypoint (T31)

The native comparison path invokes this directory's `bridge.mjs` as a
**fixed installed Node entrypoint**: `node <absolute path to
bridge.mjs>`, `shell=False`, nothing else on argv. It reads **one
bounded JSON request** from stdin and writes **one bounded JSON
response** to stdout. Every operation dispatches into the same
`@inkflip/compare` modules the browser uses — `normalizeText`,
`checkNormalizedView`, `alignPage` and the frozen `REGION_MATCH_V1`
parameters — so browser and native comparisons share normalized and
geometry semantics literally, not by port (ADR009). There is no Python
reimplementation to fall back to: without Node the native comparison
capability is absent, and `native/inkflip/compare_bridge.py` reports
that as a typed capability error.

## Protocol (`inkflip-compare-bridge`, version 1)

Request envelope (UTF-8 JSON, ≤ `LIMITS.maxStdinBytes` = 32 MiB):

```json
{ "protocol": "inkflip-compare-bridge", "version": 1, "op": "..." }
```

| op          | request fields                                                         | result payload                                                   |
| ----------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `describe`  | none                                                                   | `{ "comparator": {...} }` — version identity for manifests (I13) |
| `normalize` | `raws: string[]`                                                       | `{ "results": [{ "text", "map" }] }` — contract normalized view  |
| `align`     | `pages: [{ "left": [...], "right": [...], "page_index"?, "region"? }]` | `{ "results": [AlignmentResult, ...] }`                          |

Response (single line):

```json
{ "ok": true,  "protocol": "...", "version": 1, "comparator": {...}, "result": {...} }
{ "ok": false, "protocol": "...", "version": 1, "comparator": {...},
  "error": { "code": "...", "message": "..." } }
```

`comparator` rides every response: package, `bridge_version`, protocol
name/version, `normalization` (`scalar-whitespace-v1`), `alignment`
(`region-match-v1`), `score_semantics`
(`algorithm_diagnostics_not_probability`), `node` and `platform` —
surfaced to Python so run/comparison manifests retain comparator
version identity.

Occurrences inside `left`/`right` carry `id`, `page_index`, `ordinal`,
`geometry` and either `raw` (normalized here by the shared code) or a
precomputed `normalized_text`. Supplying both requires exact agreement
— a drifted port fails `NORMALIZATION` instead of silently diverging.
Envelope and page objects are closed schemas; unknown fields reject
with `FIELD` and are never interpreted as invocation options.

## Files

| file           | contents                                                                                                                                       |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `protocol.mjs` | shared request semantics: envelope validation, occurrence resolution, `describe`/`normalize`/`align` ops, comparator identity, protocol limits |
| `bridge.mjs`   | transport: bounded stdin read → `dispatch` → bounded single-object stdout write                                                                |
| `README.md`    | this file                                                                                                                                      |

## Bounds and honest limits

- stdin is capped at 32 MiB; a request over the cap gets a `SIZE`
  `ok:false` response, not a partial read. Element caps bound `raws`,
  `pages` and per-side occurrences. Responses are emitted as one JSON
  object under a 64 MiB hard bound; the Python caller enforces its own
  tighter stdout cap and kills the child group on overflow.
- `ok:false` answers carry the ContractError code (`TYPE`, `JSON`,
  `UNICODE`, `PROTOCOL`, `VERSION`, `OP`, `FIELD`, `SIZE`,
  `NORMALIZATION`, `PAGE`, `GEOMETRY`, `ID`, `RESPONSE_TOO_LARGE`,
  `INTERNAL`). Handled failures exit 0; a nonzero exit means the
  entrypoint itself could not run.
- The bridge trusts its caller, not its payload: request data can never
  become argv, an environment override or a profile/plugin selection.

## Executable example

```sh
echo '{"protocol":"inkflip-compare-bridge","version":1,"op":"normalize",
       "raws":["  Total:\t$1,000.00  "]}' |
  node packages/compare/node/bridge.mjs
```

Tests: `node --test tests/bridge/*.test.mjs` (entrypoint + protocol),
`uv run --project native python -m pytest native/tests/bridge -q`
(Python bridge + cross-language goldens).
