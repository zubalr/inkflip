# Start one session in each app

Private repository: https://github.com/zubalr/inkflip

Start **Devin Local first** in Devin Desktop, using the existing project directory
and SWE-2 Max. Use Normal mode and enable Subagents (Preview). Paste
`prompts/DEVIN.md`. Then paste `prompts/ANTIGRAVITY.md` in Antigravity and
`prompts/ZCODE.md` in ZCode. Each file is the complete entry prompt.

Prepared local folders (relative to the parent `pdf project` directory):

| App | Folder | Starting branch |
| --- | --- | --- |
| Devin Local | `original` | `main` |
| Antigravity | `worktrees/pdf-t06` | `session/antigravity` |
| ZCode | `worktrees/pdf-t05` | `session/zcode` |

Keep the Devin coordinator in the existing `original` folder. The session creates
isolated task worktrees when needed; leave the canonical checkout available for
integration. All three apps read the same Beads database. Use the current prompt
files; previously copied Cloud prompts are superseded.

The owner selected Local because the [SWE-2 promotion](https://devin.ai/pricing)
applies to Desktop and CLI through October 10, 2026 (verified September 12 in
Qatar). It does not authorize Cloud usage. Follow the model and subagent rules in
`docs/NATIVE_PASSES.md`; recheck the offer if resuming after it expires.

The app model, GitHub access and native Teamwork/goal confirmation are UI choices;
prompt text cannot grant account access or bypass those dialogs. The sessions
arrange their own branches, delegation, handoffs, reviews, commits and integration.
You do not paste a prompt for each T-number. See `docs/NATIVE_PASSES.md`.

| Pass | Result | Tasks after accepted T01 |
| --- | --- | --- |
| 1 | Browser investigation through G1, plus native foundations | 25 |
| 2 | Complete browser experience and native regression through G2/G3 | 12 |
| 3 | Quality, experiments and pre-release review | 16 |

T54 is the separate publication/deployment decision. These are intended work
boundaries, not guarantees within a provider quota/session limit. Reuse the same
prompt to resume; Beads determines where to continue. Do not use historical
T01/T02/T03/T05/T06 entry prompts.

The current implementation is the accepted T01 scaffold. Product work begins at
T02. Check the existing scaffold with:

```sh
python3 scripts/task_acceptance.py run verify
python3 scripts/coordination.py task T02
```
