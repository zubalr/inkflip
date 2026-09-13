# Licensing and distribution-rights status — T47 preparation

Recorded: 2026-09-13 by the ZCode distribution-completion batch.
This file is the source-bound evidence for the documentation's licensing
facts. Update it (with a new dated entry) whenever the status legitimately
changes; the docs and `tests/docs/snapshot-facts.json` must change in the
same reviewed change.

## Current status: pending

- The recorded planning decision (ADR-003,
  `planning/adrs/003-native-license.md`) selects the MIT license for newly
  authored application/planning code and documentation, with a deliberate
  dependency boundary (no PyMuPDF in the shipped product).
- The repository-root `LICENSE` file, the `NOTICE` file's final
  copyright-holder line, and the completed redistribution notice bundle are
  **not decided or shipped** in this snapshot; they are the deliverable of
  T47 closure and the owner's recorded decision.
- The copyright holder for the project as a whole is **not** inferred from
  Git authors or upstream records in any documentation; no owner decision
  recording it has been observed.
- A dedicated security-reporting channel does **not** exist yet;
  [SECURITY.md](../../SECURITY.md) says exactly that and invents no contact.

## Provenance that IS established (for the future NOTICE)

- Upstream snapshot import: `mib-intake`, MIT, "Copyright (c) 2026 Zubair
  Jashim", pinned commit `94f35ce9f9beb1640ddebdc2c72aa379ecebb004`, license
  blob preserved byte-exact at `third_party/origin/mib-intake/LICENSE`
  (SHA-256 recorded in `docs/ORIGIN.md`). This is the upstream record — not
  a claim about this project's own copyright line.
- Dependency licenses for everything currently vendored are inventoried in
  [docs/ATTRIBUTION.md](../../docs/ATTRIBUTION.md); the T47 preparation
  inventory extends this with per-file license evidence under `licenses/`.
