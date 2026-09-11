# ADR 003 — Permissive original core, deliberate dependency boundary

Status: **accepted planning default**, not a claim of implemented production behavior.

## Decision
License newly authored application/planning code and documentation MIT. Prefer PDFium/pypdf/Tesseract rather than import PyMuPDF into the shipped product. Do not ship any inherited adjudicator weights, training calibration or challenge answer machinery. Retain required third-party notices by exact build and credit material ideas.

## Why this decision and not the obvious alternative
This avoids making a convenience dependency silently determine the distribution obligations of the complete native tool. It is not a legal conclusion that every future component is compatible. System/base image libraries, binaries and model licenses remain individually inventoried.

## Evidence and interpretation
[S12](../research/SOURCES.md#s12) [S25](../research/SOURCES.md#s25) [S26](../research/SOURCES.md#s26) [S39](../research/SOURCES.md#s39)

These sources support the named capability or constraint, not the quality of an unbuilt integration. Version selections are in `config/dependencies.json`; unresolved transitive locks and security patches are a T02 release-input obligation.

## Verification and fallback branch
T02 and T47 block redistribution of any asset without provenance, license and digest. If deeper tracing needs PyMuPDF later, a separately reviewed AGPL-compatible or commercially licensed distribution is a new owner-approved decision, not an optional-plugin loophole. Existing core capabilities must work without it.

## Change control
Submit a proposal with affected schemas, consumers, assets, tests, licensing and rollback. Contract owner and integrator approve before dependent branches rebase. Do not ship both competing architectures or change fixture expectations to disguise a behavioral regression.
