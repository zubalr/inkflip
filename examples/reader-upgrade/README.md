# Reader upgrade example

This example runs locally with named pypdf profiles. It does not use a hosted
service, account, or upload. Setup may download the pinned pypdf wheels because
the operator invoked install. Corpus inspection, baseline creation and compare
run offline.

The documented `python` name is this checkout's frozen native interpreter at
`native/.venv/bin/python`. Create it with `uv sync --project native` if it is
missing. Put that directory and the `inkflip` wrapper on `PATH`. Do not create
a global `python` alias.

```sh
export PATH="$PWD/native/.venv/bin:$PWD/examples/reader-upgrade/bin:$PATH"
export PYTHONPATH="$PWD/native"
export INKFLIP_PROFILES_DIR="$PWD/profiles"
```

## Commands

```sh
python scripts/install_reader_profile.py --name before --reader pypdf --version 5.9.0
python scripts/install_reader_profile.py --name after --reader pypdf --version 6.18.0
inkflip corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile before --out runs/before
inkflip corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile after --out runs/after
inkflip baseline create --run runs/before --rules examples/reader-upgrade/upgrade-rules.json --out baselines/before.json --approved-by local-reviewer --rationale 'Explicit local reader upgrade acceptance policy'
inkflip compare baselines/before.json runs/after --rules examples/reader-upgrade/upgrade-rules.json --out comparisons/upgrade
inkflip report runs/after/reports/mapping-control.json --format html --out runs/after/mapping-control.html --replace-output
```

Or run the same sequence as a script. `run.sh` applies the same frozen
interpreter `PATH` itself, so it is usable from an ordinary shell:

```sh
sh examples/reader-upgrade/run.sh
```

`before` is pypdf 5.9.0 and `after` is pypdf 6.18.0 in separate virtualenvs.
Reports record those versions. Baseline bytes are immutable; a known rule
failure exits 5 without rewriting `baselines/before.json`. Open
`runs/after/mapping-control.html` or `comparisons/upgrade/comparison.html` in a
local browser.
