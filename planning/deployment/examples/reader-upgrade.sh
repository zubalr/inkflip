#!/usr/bin/env sh
# Implementation-repository example: requires completed T29–T35 command contracts.
# Explicit environment preparation may use the network; inspection must not.
set -eu
python scripts/install_reader_profile.py --name before --reader pypdf --version 5.9.0
python scripts/install_reader_profile.py --name after --reader pypdf --version 6.18.0
inkflip corpus run --manifest planning/contracts/examples/valid/corpus.json --source-root planning/fixtures --profile before --out runs/before
inkflip corpus run --manifest planning/contracts/examples/valid/corpus.json --source-root planning/fixtures --profile after --out runs/after
inkflip baseline create --run runs/before --rules quality/upgrade-rules.json --out baselines/before.json --approved-by local-reviewer --rationale 'Explicit local reader upgrade acceptance policy'
inkflip compare baselines/before.json runs/after --rules quality/upgrade-rules.json --out comparisons/upgrade
