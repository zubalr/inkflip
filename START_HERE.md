# Start one session in each app

Private repository: https://github.com/zubalr/inkflip

Start **Devin Cloud first**, with this repository connected and SWE-2 Max selected.
Paste `prompts/DEVIN.md`. Then start Antigravity in the prepared UI checkout and
paste `prompts/ANTIGRAVITY.md`; start ZCode in the prepared native checkout and paste
`prompts/ZCODE.md`. Each file is the complete entry prompt.

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
