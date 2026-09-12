# Astra coordinates the native worker team

Private repository: https://github.com/zubalr/inkflip

Continue the existing **Codex/Astra task** as the sole coordinator, Beads writer,
GitHub publisher and integrator. Its durable entry prompt is `prompts/CODEX.md`.
Astra owns hard implementation and independent acceptance, delegates substantial
implementation to **Devin Local SWE-2 Max** on the Mac, and bounded volume work
to **ZCode Goal mode** on Homebase.

Worker entry prompts are `prompts/DEVIN.md` and `prompts/ZCODE.md`. Both require
current Beads grants and canonical instructions; earlier Devin-as-lead prompts
are superseded. Do not run another integration lead. Read `docs/HOMEBASE.md`
for paths, native execution, transport and the initial work sequence.

The owner explicitly removed fixed worker maxima. Astra sizes each wave to
ready independent work, machine resources and review capacity. SWE may run
native general subagents, Astra may use Codex subagents, and ZCode may use its
available native parallelism. Each writer needs an isolated worktree and scope.
Native platform limits remain; additional agents must serve concrete work.

Keep the Mac awake and Codex running for local coordination and same-task
heartbeat continuation. Leave Cloud, Antigravity and the old Mac ZCode stopped.
Never reboot, shut down, suspend or power-cycle Homebase.

Homebase receives code and native read-only Beads state from a local Git relay
and returns checkpoint branches over SSH. It needs no personal GitHub login.
The actual source/state transfer, T27 checkpoint return and retry were verified.
The local SWE CLI exposes model selection, session resume and ACP; its actual
runtime control must be verified before a swarm is considered launched.

`execution/passes.json` owns static allocation; Beads owns current work, notes
and acceptance. Advance passes only after actual gates. Preserve unfinished work
on quota or external blockers. Public deployment T54 remains an owner decision.
