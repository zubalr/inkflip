# Start the Mac coordinator and Homebase worker

Private repository: https://github.com/zubalr/inkflip

Start **Devin Local** in the Mac's existing `original` checkout on `main`, with
SWE-2 Max, Normal mode and Subagents (Preview). Paste `prompts/DEVIN.md`.
Start native **ZCode Agent/Goal on Homebase** in
`/home/wertyp/.local/share/homebase-factory/projects/inkflip` and paste
`prompts/ZCODE.md`. Select the user's GLM model in ZCode's own UI.
Both prompts continue the saved work; no per-ticket prompts are needed.

Read `docs/HOMEBASE.md` for the concrete plan and transport. Devin handles
architecture, difficult implementation, review and integration. ZCode handles
assigned components, fixtures, repeated verification and supporting deliverables.
The Mac alone writes Beads and publishes GitHub commits. Homebase receives source
and read-only Beads state through a local Git relay and returns checkpoint
branches over SSH. It needs no personal GitHub login or new Workbench access.

Leave Antigravity, the old Mac ZCode session, and Cloud sessions stopped.
Keep the Mac awake and network-connected for Local coordination and publication.
Homebase must remain running; never reboot, shut down or suspend it.

The [SWE-2 promotion](https://devin.ai/pricing) applies to Desktop/CLI through
October 10, 2026 (checked September 12). It does not authorize Cloud or paid-model
fallback. Follow `docs/NATIVE_PASSES.md` for general-subagent model inheritance.
Native model/login/Goal approvals remain actual app UI choices.

`execution/passes.json` owns static allocation. Beads owns current progress,
grants, follow-ups and acceptance. Read `pdf-pass1` for the Cloud-to-Local
checkpoint and unresolved defects; do not restart completed tasks.

| Pass | Required result |
| --- | --- |
| 1 | Working browser investigation through G1 and native foundations |
| 2 | Complete browser experience and native regression through G2/G3 |
| 3 | Quality, experiments and pre-release review |

Advance only after actual gate evidence passes. There is no fixed runtime
deadline or guarantee of overnight completion. Preserve work on quota exhaustion
or a required owner/device action. T54 deployment remains separately authorized.
