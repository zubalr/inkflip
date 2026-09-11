# Shared vocabulary and non-negotiable invariants

A **reader** is a named, versioned extraction, rendering or structural-observation implementation. An **adapter** translates its actual output into the canonical contract without deciding truth. A **reading** is what that reader returned. An **occurrence** is one position-bearing appearance in one reader's result; identical strings elsewhere remain different occurrences. **Raw** means the unmodified API-returned string, not a claim to expose the original PDF bytes as text. A **normalized view** is a reversible-indexed comparison aid. A **region** is a source location selected or aligned explicitly, never inferred from a matching string alone.

A **check plan** is the finite requested work. A **check result** states what actually ran. **Coverage** is the check results in the context of selected pages and the full page count, not a document confidence score. **Complete** means all requested checks completed, not all possible properties were checked. A **finding** is evidence-linked information, not adjudication. A **prepared result** is an actual recorded run presented without pretending to execute it again. A **contract example** is schema/sample data that is not a processing result.

A **report** packages one document's selected investigation. A **comparison** relates two stored reports. A **baseline** is an explicitly approved immutable reference. **Changed** means different; **regressed** requires a declared acceptance rule or known expectation. A **replayable bundle** includes source bytes but still requires a compatible installed environment. A hash alone cannot replay a document.

| ID | Invariant | Enforcement |
|---|---|---|
| I01 | Preserve original PDF bytes; no automatic correction or repair | SHA-256 before/after; readers accept immutable inputs |
| I02 | Every occurrence binds to document, reader, page, ordinal and geometry precision | Schema plus semantic references; duplicate-position tests |
| I03 | Raw text remains unchanged; normalization cannot erase a digit, punctuation, currency, sign or negation | Scalar-map round trips; adversarial normalization tests |
| I04 | No precise highlight without independently supplied geometry | Null polygon for page-only/unknown; alignment abstention |
| I05 | Every planned check reaches a terminal result; failure never becomes agreement | Plan/result identity and terminal-state validator |
| I06 | Disagreement/consensus do not establish truth, fraud or safety | Finding kinds, copy review, no confidence/risk aggregation |
| I07 | Events from old generation/document/run/job cannot change current UI | Generation-first reset, stale-event/property tests |
| I08 | Local file data, names, hashes, crops and reports never leave the browser automatically | Canary network test including service workers, URLs and telemetry |
| I09 | Source PDF is absent from default selected export; disclosed inclusions match actual bytes | Export allowlist and decoded contents audit |
| I10 | Imported reports cannot execute code, fetch resources or select reader executables | Closed schema, strict size/depth, no HTML/ZIP import |
| I11 | Missing evidence stays missing; no challenge defaults, dictionary snapping or guessed geometry | Fixtures for absent fields and ambiguous matches |
| I12 | Regression comparison cannot improve by losing coverage; baseline never auto-refreshes | Rule engine and immutable baseline tests |
| I13 | Source/model/adapter identity accompanies every run | Frozen manifests and environment comparison |
| I14 | Browser usefulness does not depend on a native process or public backend | Offline own-file browser acceptance gate |
| I15 | Deployed public traffic cannot invoke application compute/upload code | Asset-only configuration, build graph and deployed-route proof |
| I16 | Retain licenses and material influences; do not invent authorship or executed work | Source ledger, notices, real task/review receipts |
| I17 | Bound local work and isolate failures without erasing successful unrelated results | Parent termination and partial-artifact tests |
| I18 | Claims derive from exact shipped artifacts and stated test populations | Claims ledger + release evidence mapping |

Workers read these invariants and their own task. A discovered conflict becomes a contract-change proposal; silently weakening an invariant is not an implementation decision.
