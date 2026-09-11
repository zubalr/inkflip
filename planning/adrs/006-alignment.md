# ADR 006 — Geometry-first, uncertainty-preserving comparison

Status: **accepted planning default**, not a claim of implemented production behavior.

## Decision
Align occurrences independently of reader extraction using bounded region-match-v1. Preserve duplicate strings, split/merge provenance and raw order. Require unique-enough geometric candidates for regional claims. Text-only or ambiguous matches stay page-level/unmatched and are not promoted to a precise mismatch.

## Why this decision and not the obvious alternative
Literal punctuation, amount, sign and negation differences remain visible. Whitespace equivalence is explained separately. Rank by inspectability and meaningful character classes, not a counterfeit truth probability. Native text and OCR disagreeing is a measured difference, not an accusation.

## Evidence and interpretation
[S02](../research/SOURCES.md#s02) [S15](../research/SOURCES.md#s15) [S16](../research/SOURCES.md#s16)

These sources support the named capability or constraint, not the quality of an unbuilt integration. Version selections are in `config/dependencies.json`; unresolved transitive locks and security patches are a T02 release-input obligation.

## Verification and fallback branch
T12/T20/P08 target low-noise alignment on clean and adversarial controls. If automatic grouping fails the false-finding budget, retain user-selected region comparison and show ambiguous results in details; improve matching before enabling wider automatic findings. Do not add a semantic model to hide bad alignment.

## Change control
Submit a proposal with affected schemas, consumers, assets, tests, licensing and rollback. Contract owner and integrator approve before dependent branches rebase. Do not ship both competing architectures or change fixture expectations to disguise a behavioral regression.
