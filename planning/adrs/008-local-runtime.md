# ADR 008 — Bounded workers and process supervisors

Status: **accepted planning default**, not a claim of implemented production behavior.

## Decision
Browser coordinator uses generation/digest/run/job/sequence envelopes, acknowledged bounded chunks and explicit terminal check records. PDF parsing, OCR and matching run in appropriate workers; main-thread render is bounded/yielding where required. Native parents supervise disposable parser/OCR children, kill process groups and atomically retain completed results.

## Why this decision and not the obvious alternative
Cancellation revokes authority before cleanup. File replacement increments generation before starting the new file. One explicit transient retry is allowed within the original deadline; no retry of a completed empty result. Device limits and failed capabilities never become an all-clear.

## Evidence and interpretation
[S06](../research/SOURCES.md#s06) [S17](../research/SOURCES.md#s17)

These sources support the named capability or constraint, not the quality of an unbuilt integration. Version selections are in `config/dependencies.json`; unresolved transitive locks and security patches are a T02 release-input obligation.

## Verification and fallback branch
T11/T29/T40 test crash/hang/stale/cleanup behavior. P06 here tests protocol logic only, not all parser confinement. Unsupported OS containment is reported by doctor/profile checks and requires the supported container route for hostile files. No claim of infallible browser/container sandboxing.

## Change control
Submit a proposal with affected schemas, consumers, assets, tests, licensing and rollback. Contract owner and integrator approve before dependent branches rebase. Do not ship both competing architectures or change fixture expectations to disguise a behavioral regression.
