# ADR 007 — Portable JSON and script-free HTML, no product archive import

Status: **accepted planning default**, not a claim of implemented production behavior.

## Decision
A bounded .inkflip.json document is the machine-readable bundle; optional PNG/PDF assets are explicitly embedded with hashes. A separate script-free HTML file is the human-readable artifact. Product import accepts canonical JSON, not HTML, ZIP, arbitrary PDF attachments in archives or remote URLs.

## Why this decision and not the obvious alternative
Selected evidence export defaults to the chosen readings/crops/coverage, no source PDF, filename or annotation. A replayable bundle requires explicit original-byte inclusion or later hash-matched local source, exact reader configuration and available execution environment. Hash alone is not replay.

## Evidence and interpretation
[S18](../research/SOURCES.md#s18) [S43](../research/SOURCES.md#s43)

These sources support the named capability or constraint, not the quality of an unbuilt integration. Version selections are in `config/dependencies.json`; unresolved transitive locks and security patches are a T02 release-input obligation.

## Verification and fallback branch
T16/T22/T23/T24 and P05 verify escaping, exact preview, limits and no fetch. Missing source produces evidence-only, not a broken hidden download. Reports exceeding import limits require a selected report or the native directory workflow, not unbounded decompression.

## Change control
Submit a proposal with affected schemas, consumers, assets, tests, licensing and rollback. Contract owner and integrator approve before dependent branches rebase. Do not ship both competing architectures or change fixture expectations to disguise a behavioral regression.
