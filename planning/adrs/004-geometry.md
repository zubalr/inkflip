# ADR 004 — Unrotated physical-point canonical page space

Status: **accepted planning default**, not a claim of implemented production behavior.

## Decision
Canonical geometry is top-left, unrotated, relative to effective CropBox, measured in 1/72-inch physical points after UserUnit. Raw PDF user space, canonical page, display rotation, CSS viewport, raster and OCR crop spaces are distinct. Every transform is named and invertible or explicitly unsupported.

## Why this decision and not the obvious alternative
The executed PDFium build reports size without UserUnit; its adapter compensates once. PDF.js viewport already applies UserUnit. No text-string-only fabricated boxes; exact/estimated/page_only/unknown refer to geometry, not truth.

## Evidence and interpretation
[S22](../research/SOURCES.md#s22) [S26](../research/SOURCES.md#s26) [S27](../research/SOURCES.md#s27)

These sources support the named capability or constraint, not the quality of an unbuilt integration. Version selections are in `config/dependencies.json`; unresolved transitive locks and security patches are a T02 release-input obligation.

## Verification and fallback branch
P02 analytical and round-trip tests plus T04/T26 and G1 browser overlays decide acceptance. A reader that cannot supply a verified transform downgrades geometry to page_only or fails the check; it never emits a plausible but wrong highlight. Canonical transform changes require schema/adapter review and migration.

## Change control
Submit a proposal with affected schemas, consumers, assets, tests, licensing and rollback. Contract owner and integrator approve before dependent branches rebase. Do not ship both competing architectures or change fixture expectations to disguise a behavioral regression.
