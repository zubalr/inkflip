# Origin and migration record

This repository is a **documented snapshot import**, not a continuation of the
original project's Git ancestry. The new product (Inkflip, a local-first PDF
reading inspector) has a new canonical domain model and runtime; importing the
challenge history wholesale would obscure that boundary.

## Source repository

| Field | Value |
| --- | --- |
| Repository | `mib-intake` (local sibling checkout, no remote configured here) |
| Pinned commit | `94f35ce9f9beb1640ddebdc2c72aa379ecebb004` |
| License | MIT, Copyright (c) 2026 Zubair Jashim |
| Retained file | [`third_party/origin/mib-intake/LICENSE`](../third_party/origin/mib-intake/LICENSE) |
| License SHA-256 | `3f1e48ee93685ecf2c49f768ad888dc47859b057f3b90c9f04f132315edf0c6d` |
| License Git blob | `5b86ba31f4b7605ca2a39feb2eb133313c23a7a9` (at pinned commit) |

The license file is the exact blob from the pinned commit. **No legacy runtime
module, classifier, calibration table, vocabulary, prediction file or dataset
was imported.** The original repository must remain byte- and Git-unchanged;
it is never a build input of this repository.

## Conceptual reuse (independently implemented)

The following ideas were named as material influences in
`planning/architecture/ORIGIN_AND_MIGRATION.md` and are re-implemented, not
copied:

- span metadata and explicit reason retention
- output/evidence separation
- bounded OCR escalation
- raw-box preservation
- adversarial clean-twin tests

The fixture generator in this project is original. Its ToUnicode/cover/geometry
recipes are separate from the legacy challenge examples.

## Rules for future ports

Potential copied code is not preauthorized. Before any port, record the
repository, exact commit/file, original author/notice, required license and
the modifications, and preserve the notice in the copied file and in
distribution. Material inspiration is acknowledged even when code is
independently written. Forks or derivative implementations are not counted as
independent corroboration.

## Historical reproduction

The original repository's README/Docker invocation remains a historical recipe
only. It is not rerun or repaired by this project, and the new inspector does
not depend on resolving that historical reproducibility.
