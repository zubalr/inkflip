# Reader upgrade example

This example runs locally with named pypdf profiles. It does not use a hosted
service, account, or upload. Setup may download the pinned pypdf wheels because
the operator invoked install. Corpus inspection, baseline creation and compare
run offline.

Put the `inkflip` wrapper on `PATH` and point Python at this checkout's native
package before copying the commands below:

```sh
export PYTHONPATH="$PWD/native"
export INKFLIP_PROFILES_DIR="$PWD/profiles"
export PATH="$PWD/examples/reader-upgrade/bin:$PATH"
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

Or run the same sequence as a script:

```sh
sh examples/reader-upgrade/run.sh
```

`before` is pypdf 5.9.0 and `after` is pypdf 6.18.0 in separate virtualenvs.
Reports record those versions. Baseline bytes are immutable; a known rule
failure exits 5 without rewriting `baselines/before.json`. Open
`runs/after/mapping-control.html` or `comparisons/upgrade/comparison.html` in a
local browser.
