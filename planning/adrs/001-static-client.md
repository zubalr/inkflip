# ADR 001 — Static React application, no hosted processor

Status: **accepted planning default**, not a claim of implemented production behavior.

## Decision
Choose Vite + React + TypeScript, a static document stage and hash routes. Next.js static export is technically viable, but its server/client and route/export conventions buy little for this one highly interactive local workspace. No SSR, Next server actions, Worker main, upload API, data service or authentication.

## Why this decision and not the obvious alternative
Vite emits assets that ordinary static hosting can deliver. CLI processing is a separate local surface. No Cloudflare framework adapter or dynamic catch-all is installed. Retain an owned build artifact for offline hosting and rollback.

## Evidence and interpretation
[S29](../research/SOURCES.md#s29) [S30](../research/SOURCES.md#s30) [S33](../research/SOURCES.md#s33) [S34](../research/SOURCES.md#s34) [S37](../research/SOURCES.md#s37)

These sources support the named capability or constraint, not the quality of an unbuilt integration. Version selections are in `config/dependencies.json`; unresolved transitive locks and security patches are a T02 release-input obligation.

## Verification and fallback branch
T02 verifies package engines, installs exact compatible releases and freezes a real lock; T48 checks static output/config and T54 proves the deployed path. If the selected patch cannot build, lock owner chooses a maintained compatible patch with a recorded ADR; do not switch to server rendering. If a Cloudflare account rule invokes paid execution, fix/remove that rule before publication. Local build continues.

## Change control
Submit a proposal with affected schemas, consumers, assets, tests, licensing and rollback. Contract owner and integrator approve before dependent branches rebase. Do not ship both competing architectures or change fixture expectations to disguise a behavioral regression.
