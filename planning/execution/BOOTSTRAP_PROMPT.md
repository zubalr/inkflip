# Copy-ready bootstrap prompt

Implement **T01** in this new local Inkflip repository. Read `planning/START_HERE.md`, `planning/PROJECT_BRIEF.md`, `planning/architecture/REPOSITORY_AND_DEPENDENCIES.md`, `planning/architecture/ORIGIN_AND_MIGRATION.md`, `planning/execution/OWNERSHIP.md` and `planning/execution/workers/T01.md`. The original `mib-intake` repository is historical and must not be edited.

Inspect before editing. Keep the copied planning package immutable initially; root implementation code belongs outside `planning/`. Create the explicit pnpm workspace, native project boundary, shared TS package structure, root scripts, docs/origin record and credential-free early CI. Do not add empty “implemented” feature functions or UI buttons. Only create executable tests for existing bootstrap behavior; future command names must fail explicitly until registered.

Create `execution/state.json` from the planning state example without setting tasks accepted. Implement `scripts/task_acceptance.py` and `scripts/gate.py` to read task/test records, check dependencies and reject empty/missing tests; run only genuinely present test commands, never return success for an unbuilt browser suite. Gate runner receives approved manual receipts where specified. Application commands documented in planning become implemented incrementally, not fictional on day one.

T02 owns actual package installs, resolved transitive locks, compatible patched toolchain and final full action/OCI hashes. You may create initial manifests from selected dependency records but do not invent hashes, claim a frozen install or trigger deployment/network setup. Establish clear failure for unavailable dependencies and a clean owner handoff to T02. Shared schema source remains canonical; generated code has explicit generation/check commands.

Document exact origin commit `94f35ce9f9beb1640ddebdc2c72aa379ecebb004`, retained ideas/fixtures and legacy exclusions. No copied adjudicator weights, guessed missing fields or score as product metric. New core is MIT with third-party rights separately tracked. No remote creation, first publish, deployment, account discovery, secret write or paid resource creation is authorized by bootstrap.

Execute the T01 acceptance, include actual command counts/logs and confirm original repository unchanged. Make a coherent local commit with actual authorship/time, hand to a distinct reviewer, and leave task acceptance to the integrator. Report exact changed paths and blockers, not a generic “foundation ready” statement.
