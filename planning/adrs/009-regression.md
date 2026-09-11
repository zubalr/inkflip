# ADR 009 — Changed is not regressed without a rule

Status: **accepted planning default**, not a claim of implemented production behavior.

## Decision
Store immutable source/config/run manifests. Compare named readers and isolated old/new versions locally. Preserve coverage deltas. Output statuses unchanged/changed/unsupported/errored/incomparable are separate from improved/regressed rule judgments.

## Why this decision and not the obvious alternative
Baselines require explicit approval identity and rationale, refuse overwrite, and do not update during test execution. Shared TypeScript comparison semantics are used in browser and installed Node bridge; Python orchestrates native readers. No hosted corpus service.

## Evidence and interpretation
[S08](../research/SOURCES.md#s08) [S18](../research/SOURCES.md#s18) [S45](../research/SOURCES.md#s45)

These sources support the named capability or constraint, not the quality of an unbuilt integration. Version selections are in `config/dependencies.json`; unresolved transitive locks and security patches are a T02 release-input obligation.

## Verification and fallback branch
T31–T35/P10 exercise upgrades with separately installed interpreters and unchanged sources. Different files remain incomparable for reader-upgrade judgments; document revisions can be shown as changed-document comparisons. Coverage loss fails the chosen CI coverage rule even when disagreement count falls.

## Change control
Submit a proposal with affected schemas, consumers, assets, tests, licensing and rollback. Contract owner and integrator approve before dependent branches rebase. Do not ship both competing architectures or change fixture expectations to disguise a behavioral regression.
