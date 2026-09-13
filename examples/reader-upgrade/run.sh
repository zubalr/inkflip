#!/usr/bin/env sh
# End-to-end runnable reader upgrade verification workflow (T35).
# Requires no hosted services, external accounts, or cloud dependencies.
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "=== 1. Install Isolated Reader Profiles ==="
python3 scripts/install_reader_profile.py --name before --reader pypdf --version 5.9.0
python3 scripts/install_reader_profile.py --name after --reader pypdf --version 6.18.0

echo "=== 2. Run Corpus Inspection with 'before' Profile ==="
python3 -m inkflip.cli corpus run \
  --manifest examples/reader-upgrade/corpus.json \
  --source-root planning/fixtures \
  --profile before \
  --out runs/before

echo "=== 3. Run Corpus Inspection with 'after' Profile ==="
python3 -m inkflip.cli corpus run \
  --manifest examples/reader-upgrade/corpus.json \
  --source-root planning/fixtures \
  --profile after \
  --out runs/after

echo "=== 4. Create Immutable Baseline from 'before' Run ==="
python3 -m inkflip.cli baseline create \
  --run runs/before \
  --rules examples/reader-upgrade/upgrade-rules.json \
  --out baselines/before.json \
  --approved-by local-reviewer \
  --rationale 'Explicit local reader upgrade acceptance policy'

echo "=== 5. Compare Baseline Against 'after' Run ==="
python3 -m inkflip.cli compare \
  baselines/before.json \
  runs/after \
  --rules examples/reader-upgrade/upgrade-rules.json \
  --out comparisons/upgrade

echo "=== 6. Generate Standalone HTML Report for Web Viewing ==="
python3 -m inkflip.cli report \
  runs/after/reports/mapping-control.json \
  --format html \
  --out runs/after/mapping-control.html \
  --replace-output

echo "Reader upgrade verification workflow completed successfully."
