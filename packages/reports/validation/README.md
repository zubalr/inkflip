# `@inkflip/reports` — validation (T24)

Hardened import boundary for untrusted `.inkflip.json` report bytes, plus
the script-free HTML export guard. Everything here is dependency-free
TypeScript built on `@inkflip/contracts` (`loadsStrict`, `validate`) — the
strict JSON parser and the closed schema are reused, never re-implemented.

## Pipeline (`importReport`)

Order is the security contract — every stage rejects before the next
stage's resource use exists:

1. **Byte + container boundary** (`sniffImportKind`) — ≤ 32 MiB; ZIP,
   gzip, 7z, RAR, xz, bzip2, zstd, MS-CAB, OLE/CFB, tar (`ustar`), bare
   PDFs, UTF-16 BOMs and HTML/XML/SVG-shaped input rejected by signature.
   There is no archive decompression surface at all (I10).
2. **`loadsStrict`** — strict UTF-8 JSON: duplicate keys, depth ≤ 24,
   nonfinite/unsafe numbers, lone surrogates; `__proto__` parses as an
   inert own property.
3. **Import-profile bounds** (`importStringBounds`, `preAuditAssets`) —
   non-payload strings ≤ 2 000 000 code points; ≤ 128 assets; encoded
   size ceiling before any decoding buffer exists.
4. **Prototype audit** (`auditPrototypeKeys`) — `__proto__`,
   `constructor`, `prototype` object members rejected as `PROTOTYPE`.
5. **`validate`** — closed schema (executable/plugin/command fields
   cannot exist) plus full semantic + hash verification.
6. **`auditAssets`** — decoded-asset accounting (≤ 20 MiB each, ≤ 20 MiB
   total), MIME-vs-signature and SHA-256/`byte_length` recomputation, and
   full PNG decode + re-encode via `sanitizePng` under pixel (≤ 4 MP) and
   edge (≤ 8192) limits. Only the sanitized re-encode may reach HTML.

## Modules

| file | contents |
| --- | --- |
| `limits.ts` | `IMPORT_LIMITS` mirrored from `planning/config/settings.json`; `MAX_BASE64_CHARS` |
| `import_gate.ts` | `importReport`, `importArtifact`, `sniffImportKind`, `importStringBounds` |
| `inflate.ts` | bounded zlib/deflate decode (`inflateZlib`), Adler-32, stored-block encoder |
| `png.ts` | PNG signature/chunk/CRC/IHDR checks, all color types + bit depths, Adam7, filters, `sanitizePng` re-encode (8-bit RGBA, ancillary-free) |
| `assets.ts` | `preAuditAssets`, `auditAssets`, strict `decodeBase64` |
| `names.ts` | `auditPrototypeKeys`, `safeFileName`, `isSafeRelativePath` |
| `html_guard.ts` | `assertScriptFreeHtml` (CSP, forbidden elements/attrs/schemes/CSS), `escapeHtml` |
| `index.ts` | public surface |

## Commands

```sh
# T24 acceptance (79 tests + 1000 bounded fuzz cases)
node --test tests/security/import/*.test.mjs
python scripts/fuzz_reports.py --fixed-seed 8090 --cases 1000
```

The fuzzer writes `artifacts/tasks/T24/fuzz/fuzz-receipt.json` +
`fuzz-cases.jsonl` and exits nonzero on any unexpected accept, unexpected
reject, crash or egress attempt. The driver
(`tests/security/import/fuzz_driver.mjs`) arms fetch/WebSocket/socket/
spawn tripwires so egress shows up as a first-class result.

## Posture

No I/O, no network, no code execution, no schema compilation, no archive
decompression — validation cannot trigger a fetch or pick an executable
(I09/I10/I11). Errors are `ContractError` with stable codes (`SIZE`,
`JSON`, `DUPLICATE_KEY`, `DEPTH`, `NONFINITE`, `NUMBER`, `UNICODE`,
`PROTOTYPE`, `SCHEMA`, `PATH`, `ASSET`, `PNG`, `HASH`, `KIND`, `ARCHIVE`,
`HTML`, `EGRESS`).
