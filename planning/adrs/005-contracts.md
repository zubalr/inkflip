# ADR 005 — One schema, deterministic evidence identity

Status: **accepted planning default**, not a claim of implemented production behavior.

## Decision
Canonical JSON Schema 2020-12 defines reports, comparisons, reader manifests, corpus manifests, baselines, acceptance rules and worker messages. Generate TypeScript types and static Ajv validation from it; Python uses the same schema plus semantic checks. No independent hand-maintained domain model.

## Why this decision and not the obvious alternative
Use inkflip-c14n-v1 binary canonicalization and SHA-256. Raw strings are Unicode scalar sequences; normalization only collapses Unicode White_Space runs and preserves maps. Semantic validators enforce IDs, references, coordinate relations, coverage and export claims beyond structural JSON Schema.

## Evidence and interpretation
[S32](../research/SOURCES.md#s32) [S43](../research/SOURCES.md#s43)

These sources support the named capability or constraint, not the quality of an unbuilt integration. Version selections are in `config/dependencies.json`; unresolved transitive locks and security patches are a T02 release-input obligation.

## Verification and fallback branch
P03/P04 test invalid fixtures and Python/Node hash equivalence. Unknown schema versions fail closed. In a future migration, preserve original imported bytes/report identity and create a new explicitly migrated artifact; no silent permissive parser. Imported reports can never carry executable code or schemas.

## Change control
Submit a proposal with affected schemas, consumers, assets, tests, licensing and rollback. Contract owner and integrator approve before dependent branches rebase. Do not ship both competing architectures or change fixture expectations to disguise a behavioral regression.
