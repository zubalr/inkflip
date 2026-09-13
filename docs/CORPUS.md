# Corpus runs

`inkflip corpus run` reads a root-scoped `corpus_manifest`. Paths stay under
`--source-root`. Symlinks, traversal and absolute `source_path` values are
refused. Each entry is hashed against its declared SHA-256. Duplicate
filenames remain distinct corpus keys.

The parent resolves the named profile, then supervises one child per file.
Resume binds source SHA-256, manifest SHA-256, profile SHA-256, algorithm id
and settings. Changed identities require a new run directory. Completed
reports are reused only when the committed bytes still match.

Per-file reports are written under `out/reports/<key>.json`. `index.json`
records every intended key and terminal status. `journal.jsonl` is append-only.
A crashing file cannot erase a successful sibling report. Partial runs keep
explicit completed/failed counts.

```sh
inkflip corpus run \
  --manifest examples/reader-upgrade/corpus.json \
  --source-root planning/fixtures \
  --profile native-default \
  --out runs/demo
```
