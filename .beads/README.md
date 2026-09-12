# Beads task state

Beads owns live Inkflip task state. See [the execution protocol](../docs/NATIVE_PASSES.md)
before any task mutation. Only the designated Devin Local integration checkout
writes and publishes this database. Mac workers read the shared canonical database through
`python3 scripts/native_pass.py status APP` without `--sync`. Homebase reads its
native local-relay replica with `status zcode --sync`; only the Mac coordinator
writes or publishes authoritative state. See [Homebase transport](../docs/HOMEBASE.md).

An independent clone restores native Git-backed Dolt data using
`BD_SYNC_REMOTE="$(git remote get-url origin)" bd bootstrap --yes` with Beads
1.2.2; this uses the clone’s already authenticated SSH or HTTPS origin. A linked worktree uses its canonical
checkout database. Do not initialize another one there. The coordinator
publishes with `bd dolt commit` and `bd dolt push`; workers never push Beads.
The Git code branch and Beads database are separate, ordered publications.

Do not import planning status into a live database or create a second JSON
tracker. Native app execution is not task acceptance. Preserve the stored
dependencies, independent evidence and coordinator-owned acceptance.
