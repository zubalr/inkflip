# Canonical contract guide

**Authority:** `inkflip.schema.json`, Draft 2020-12, schema version 1.0.0, local schema ID `urn:inkflip:schema:1.0.0`. The schema is one source of truth with `$defs` for Report, Reader, Page, Transform, Occurrence, Finding, CheckPlan/Result, Annotation, Export, Asset, Comparison, AcceptanceRules, CorpusManifest, Baseline and WorkerMessage. Top-level `kind` selects the artifact. No arbitrary extension objects or remote references are allowed.

`tools/contractlib.py` is the delivered Python reference validator for semantic relationships and hashes. It is not a hostile-PDF sandbox or a complete PNG decoder. The product import implementation adds full bounded image decoding/reencoding and browser security tests. JSON Schema alone cannot validate cross-references, geometry inverses, raw-index maps, actual checksums or truth claims.

## Validate and generate

```sh
python tools/validate_package.py
python tools/generate_types.py
python tools/test_validators.py
```

`generated/inkflip.d.ts` is derived from the schema, not hand-maintained. Generation supports exactly the JSON Schema constructs used here and fails on unsupported constructs. Python adapters validate dictionaries against the same schema and semantic tests. Runtime browser validation is generated with Ajv at build time; user-supplied schemas are never compiled or fetched. Keep `tools/contractlib.py` and the TypeScript semantic validator in parity using the same positive/negative examples and hash vectors.

## Identity

Document identity is SHA-256 of original bytes, not filename, page text or a reader fingerprint. `execution_id` is a random UUID for one attempt. `run_key` is the `inkflip-c14n-v1` digest of `{document_sha256, readers, plan}`. Reader entries include version/build/model/settings; plan includes selected pages, regions, requested checks and algorithm versions. A new config changes run identity.

`report_id` hashes the entire report excluding itself, `execution_id`, `started_at`, `duration_ms` and each asset's base64 payload. Assets' byte length and SHA-256 remain included, and actual decoded bytes must match before accepting that digest. Environment, result origin, terminal status, errors, coverage and omissions stay in the digest. A projection or added annotation changes report identity and can refer to `export.origin_report_id`. Two executions of identical semantic content can share the report digest while keeping distinct execution IDs.

Occurrence IDs are stable within a report/run: `o_` plus the first 32 hexadecimal characters of the canonical digest of `{run_key, reader_id, page_index, ordinal, raw_source_locator}`. Do not include the text value as the sole key; equal values at different positions remain separate. A new run's matching uses geometry/source location, not ID equality. The supplied probe example uses readable stable IDs for transparency; T03 must enforce the hash-based generator for production IDs without forbidding legitimate imported readable IDs under schema v1.

## Canonical hashing, not an accidental language default

`inkflip-c14n-v1` is a specified tagged binary canonical form, **not RFC 8785/JCS**. It avoids Python/JavaScript `1` versus `1.0`, negative-zero and float-printing disagreements. Null=`N`; true=`T`; false=`F`; numbers=`D` followed by big-endian IEEE-754 binary64 with negative zero converted to positive zero. Strings=`S` plus uint32 big-endian UTF-8 byte length then strict UTF-8 bytes. Arrays=`L` plus uint32 length then canonical children. Objects=`O` plus member count, then canonical key/value pairs sorted lexicographically by UTF-8 key bytes. Keys are strings. Reject NaN/Infinity, unpaired surrogates, and integers outside ±(2^53−1). This is a digest input, not a file encoding.

Stored coordinates are rounded to six decimal places before serialization. The canonical hash preserves the resulting binary numeric values exactly. `hash-vectors.json` includes null/bool/numbers, -0, non-ASCII and object ordering. JavaScript must use DataView for the numeric encoding and TextEncoder for strict scalar UTF-8, not hash a pretty-printed JSON string. Human JSON serialization is stable key order and LF UTF-8, but cross-platform JSON bytes are not the semantic identity guarantee.

## References and evidence

Pages index into the document; geometry uses canonical physical-point space. Transform IDs must exist, matrices must be invertible and page dimensions must agree with UserUnit/effective boxes. `page_only`/`unknown` geometry requires null polygon. Every occurrence cites its reader/page and preserves raw/normalized scalar mappings. Duplicate IDs are forbidden; duplicate text is expected.

The plan enumerates work before execution; terminal result IDs must exactly match planned IDs. Each result reports `produced_occurrence_count` and `retained_occurrence_ids`. A selected export can retain only a subset while honestly stating the produced count and omissions; it must not imply omitted raw data was absent from the original read. A reading-difference finding requires at least two actual reader IDs and completed supporting checks. It cannot cite an unsupported check as evidence. Precision or certainty must not be fabricated to make an example valid.

## Compatibility and migrations

Unknown schema versions are rejected for active interpretation with a clear compatibility message. Do not “best effort” ignore unfamiliar fields under a security-sensitive report. Patch releases fix documentation/validators without changing valid semantics. An additive optional field requires a minor schema version with generated readers and fixtures; changed coordinate, normalization or identity meaning requires a major version. Reader adapter and algorithm versions evolve independently and participate in run identity.

Migrations are explicit offline commands from a known input schema to a known output schema. Preserve the original file, original digest, provenance and omissions; never invent missing geometry/source bytes. A migration gets an example pair and semantic tests, and marks the resulting report as migrated in its limitations and origin reference. No migration is needed for the initial v1 release; no speculative migration silently runs on import.

## Worker serialization

Every WorkerMessage carries version, generation, document digest, run key, job ID and sequence. Payload shape is closed; event-specific constraints are semantic: only `chunk` carries occurrences; `check_terminal` requires check ID/status; `progress` has a nondecreasing completed count and a truthful optional total; transfer slot and byte count must agree. Start transfers a bounded `pdf_bytes` or `raster_rgba` slot outside JSON using the transport's transfer list. Clear/cancel do not carry source bytes. Transfer identity is verified against the coordinator's ownership registry, not a URL from the message. Stale generation rejection is stateful and tested in the runtime, not a schema-only promise.

## Additional conformance protections

Integral floating-point numbers outside the JavaScript safe-integer range are rejected in both languages, not merely Python `int` values. Geometry transforms, regions, annotations and supporting checks must belong to their declared page. A reading-difference finding must cite completed checks that actually retain each supporting occurrence. Degenerate polygons and duplicate check references are invalid. Privacy disclosure includes required document identity/settings/coverage, retained reading text, annotations, and a separate `page_renders` flag for complete page images; a full page must not masquerade as a small crop. The source-PDF asset must actually have PDF purpose and media type. These checks are exercised by deliberate invalid examples; full image-decoder and browser containment remain product tests.
