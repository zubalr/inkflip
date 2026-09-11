# Decisions

These are the selected defaults. Change them only through a recorded contract/ADR proposal and the listed tests; workers do not reselect the stack independently. Evidence access date: 2026-09-11. The source ledger separates code/document inspection from execution.

| ADR | Decision | Required verification |

|---|---|---|

| [001](adrs/001-static-client.md) | Static React application, no hosted processor | T02 verifies package engines, installs exact compatible releases and freezes a real lock; T48 checks static output/config and T54 proves the deployed path. |

| [002](adrs/002-reader-set.md) | Named browser and native readers, no parity by assumption | G1 requires actual browser fixture/control/own-file processing. |

| [003](adrs/003-native-license.md) | Permissive original core, deliberate dependency boundary | T02 and T47 block redistribution of any asset without provenance, license and digest. |

| [004](adrs/004-geometry.md) | Unrotated physical-point canonical page space | P02 analytical and round-trip tests plus T04/T26 and G1 browser overlays decide acceptance. |

| [005](adrs/005-contracts.md) | One schema, deterministic evidence identity | P03/P04 test invalid fixtures and Python/Node hash equivalence. |

| [006](adrs/006-alignment.md) | Geometry-first, uncertainty-preserving comparison | T12/T20/P08 target low-noise alignment on clean and adversarial controls. |

| [007](adrs/007-reports.md) | Portable JSON and script-free HTML, no product archive import | T16/T22/T23/T24 and P05 verify escaping, exact preview, limits and no fetch. |

| [008](adrs/008-local-runtime.md) | Bounded workers and process supervisors | T11/T29/T40 test crash/hang/stale/cleanup behavior. |

| [009](adrs/009-regression.md) | Changed is not regressed without a rule | T31–T35/P10 exercise upgrades with separately installed interpreters and unchanged sources. |

| [010](adrs/010-public-quality.md) | Six curated examples, full release behind capability gates | G1 proves one honest end-to-end slice but is not the end of the project. |

Canonical limits: [settings](config/settings.json). Runtime parameters are safety profiles, never development effort limits. Input precedence: master brief → accepted ADR/schema/settings → task contract → supporting research. If schema and prose disagree, stop the affected task and get a coordinated correction, not a silent local override.
