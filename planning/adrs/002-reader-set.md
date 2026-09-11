# ADR 002 — Named browser and native readers, no parity by assumption

Status: **accepted planning default**, not a claim of implemented production behavior.

## Decision
Browser: paired PDF.js legacy main/worker 6.3.289 for page rendering/text, Tesseract.js/core 7.0.0 over bounded rendered crops, English data hash pinned. Native: pypdfium2 5.8.0 for independent rendering/character geometry and object properties, pypdf 6.18.0 for structural metadata/text-only comparison, Tesseract 5.5.0 over rendered crops. Do not treat pypdf text as precisely positioned.

## Why this decision and not the obvious alternative
PDF.js getTextContent/getViewport are public supported seams. Operator lists do not supply a universal glyph-to-paint provenance map. PDFium character boxes and documented text-object render mode support stronger but bounded native observations. Multiple OCR interpretations share one physical source.

## Evidence and interpretation
[S22](../research/SOURCES.md#s22) [S23](../research/SOURCES.md#s23) [S24](../research/SOURCES.md#s24) [S26](../research/SOURCES.md#s26) [S27](../research/SOURCES.md#s27) [S28](../research/SOURCES.md#s28)

These sources support the named capability or constraint, not the quality of an unbuilt integration. Version selections are in `config/dependencies.json`; unresolved transitive locks and security patches are a T02 release-input obligation.

## Verification and fallback branch
G1 requires actual browser fixture/control/own-file processing. Browser evidence remains useful without native checks. Unsupported mechanisms are capability records. T43 tests a secondary browser PDFium build; only adopt if useful independent readings fit asset/memory/rights limits. Default is unavailable, not an extra compulsory download.

## Change control
Submit a proposal with affected schemas, consumers, assets, tests, licensing and rollback. Contract owner and integrator approve before dependent branches rebase. Do not ship both competing architectures or change fixture expectations to disguise a behavioral regression.
