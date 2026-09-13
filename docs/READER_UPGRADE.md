# Reader upgrade

Use two named pypdf profiles, an approved baseline and declared acceptance
rules. Do not load two incompatible pypdf versions in one process.

The operator-invoked installer may use the network. Corpus inspection, replay
and compare do not. Missing versions block that profile. Untrusted profile
paths and commands are refused.

Follow `examples/reader-upgrade/README.md`. Tests copy those shell commands
verbatim. `before` is pypdf 5.9.0 and `after` is pypdf 6.18.0. Reports must
record those identities. A known rule-failing mutation exits 5 and leaves
baseline bytes unchanged. Open the generated HTML in a local browser.

The planning template `planning/deployment/examples/reader-upgrade.sh` names
`quality/upgrade-rules.json`. This checkout's owned rules file is
`examples/reader-upgrade/upgrade-rules.json` until that shared path is
accepted.
