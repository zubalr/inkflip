#!/usr/bin/env sh
# Local reader-upgrade example. Setup may use the network; inspection does not.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

FROZEN="$ROOT/native/.venv/bin"
if [ ! -x "$FROZEN/python" ]; then
  echo "inkflip: frozen native interpreter missing: $FROZEN/python" >&2
  echo "Create it with: uv sync --project native" >&2
  echo "Do not alias python globally; put native/.venv/bin on PATH." >&2
  exit 127
fi

export PYTHONPATH="$ROOT/native"
export INKFLIP_PROFILES_DIR="${INKFLIP_PROFILES_DIR:-$ROOT/profiles}"
export PATH="$FROZEN:$ROOT/examples/reader-upgrade/bin:$PATH"

python scripts/install_reader_profile.py --name before --reader pypdf --version 5.9.0
python scripts/install_reader_profile.py --name after --reader pypdf --version 6.18.0
inkflip corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile before --out runs/before
inkflip corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile after --out runs/after
inkflip baseline create --run runs/before --rules examples/reader-upgrade/upgrade-rules.json --out baselines/before.json --approved-by local-reviewer --rationale 'Explicit local reader upgrade acceptance policy'
# Declared-rule failure is exit 5; still emit the after HTML so the documented
# reopen path exists. Other compare failures remain fatal.
set +e
inkflip compare baselines/before.json runs/after --rules examples/reader-upgrade/upgrade-rules.json --out comparisons/upgrade
compare_status=$?
set -e
case "$compare_status" in
  0|5) ;;
  *) exit "$compare_status" ;;
esac
inkflip report runs/after/reports/mapping-control.json --format html --out runs/after/mapping-control.html --replace-output
exit "$compare_status"
