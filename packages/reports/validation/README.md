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
   keys and non-payload strings (including array members) ≤ 2 000 000 code points; ≤ 128 assets; encoded
   size ceiling before any decoding buffer exists.
4. **Prototype audit** (`auditPrototypeKeys`) — `__proto__`,
   `constructor`, `prototype` object members rejected as `PROTOTYPE`.
5. **`validate`** — closed schema (executable/plugin/command fields
   cannot exist) plus full semantic + mandatory hash verification. Passing `checkHashes=false`
   to an import function is rejected; producer tooling can use the separate
   contracts validator.
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
# T24 acceptance (Node security tests, a tiny Chromium render, and 1000 fuzz cases)
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

## Serialized HTML boundary

The public package entry and `@inkflip/reports/validation` both expose this
maintained validation surface. Package typechecking includes these files and
uses the same declaration-only TypeScript configuration as contracts/geometry.

The HTML guard checks application-owned serialized templates. It requires a
real CSP meta before document content, exact source-list tokens, quoted
attribute values, no duplicate attributes/directives, and an exact SHA-256
hash of every stylesheet. Only embedded PNG image URLs are accepted, after
strict base64 and full bounded PNG decoding. The exporter must supply the
sanitized image map; the test double no longer falls back to original bytes.

Comments and processing instructions in HTML are rejected by the conservative
template grammar. CSS comments are allowed; CSS escapes and comments are
normalized for the lexical tripwire. This deliberately rejects suspicious
comment-separated constructs even when a browser would not interpret that
particular token sequence as a load. The guard is not an arbitrary HTML
sanitizer; imported markup remains disallowed. A real Chromium test bundles
the maintained validator, verifies the stylesheet actually renders, decodes
embedded images, and records attempted network resources.

PNG validation rejects repeated singleton chunks, nonconsecutive IDAT chunks,
and palette/transparency chunks after image data. The deflate decoder accepts
an empty distance table for a literal-only block, while a length that requires
an absent distance still fails. New proof and historical baselines live in
`artifacts/tasks/T24/followup-3oz/`.
