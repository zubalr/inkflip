# Contributing

Start with the setup commands in [README.md](README.md). Use the recorded
toolchain and frozen lockfiles. Keep changes focused on one behavior and
preserve unrelated work.

## Validate a change

Run `bun run verify`, then the tests for the changed package or feature.
Browser changes need the relevant Playwright checks and a production build.
Native changes need the affected Python tests. Include the commands you ran
and any remaining limitations in the pull request.

Preserve original PDF bytes, raw reader output, occurrence identities and
explicit missing or failed checks. A reading disagreement must not become a
claim about document safety or truth. See the
[project invariants](planning/architecture/GLOSSARY_AND_INVARIANTS.md).

Use synthetic PDFs for reproducers. Do not attach private documents, exported
personal data, credentials or model files with unresolved distribution rights.
Retain applicable notices and record material reuse in
[ATTRIBUTION](docs/ATTRIBUTION.md).

## Submit a patch

Explain the problem, the resulting behavior and the relevant verification.
Keep generated build output and local working records out of source commits.
Repository and release validation are described in
[ACCEPTANCE](docs/ACCEPTANCE.md).
