# Reader Upgrade Verification Example (T35)

This example demonstrates an end-to-end reader upgrade verification workflow using Inkflip's version-isolated execution profiles, corpus inspection, immutable baselines, and acceptance-rule regression comparison.

No hosted cloud service, SaaS account, or third-party credential is required. Everything runs locally and deterministically.

## Quick Start

You can run the full sequence using the included script:

```sh
sh examples/reader-upgrade/run.sh
```

## Step-by-Step Commands

The workflow consists of five explicit, reproducible steps:

### 1. Install Isolated Reader Profiles
Install the baseline version (`5.9.0`) and the upgrade candidate (`6.18.0`) in separate virtual environments:

```sh
python3 scripts/install_reader_profile.py --name before --reader pypdf --version 5.9.0
python3 scripts/install_reader_profile.py --name after --reader pypdf --version 6.18.0
```

### 2. Execute Corpus Inspection for Baseline
Run the corpus manifest under the `before` profile:

```sh
python3 -m inkflip.cli corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile before --out runs/before
```

### 3. Execute Corpus Inspection for Upgrade Candidate
Run the corpus manifest under the `after` profile:

```sh
python3 -m inkflip.cli corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile after --out runs/after
```

### 4. Create Immutable Baseline
Create a sealed, schema-valid baseline record from the `before` run:

```sh
python3 -m inkflip.cli baseline create --run runs/before --rules examples/reader-upgrade/upgrade-rules.json --out baselines/before.json --approved-by local-reviewer --rationale 'Explicit local reader upgrade acceptance policy'
```

### 5. Compare Baseline Against Upgrade Candidate
Compare the baseline against the candidate run under the acceptance rules:

```sh
python3 -m inkflip.cli compare baselines/before.json runs/after --rules examples/reader-upgrade/upgrade-rules.json --out comparisons/upgrade
```

### 6. Export Standalone HTML Report for Web Viewing
Export a standalone HTML evidence report that can be opened in any browser:

```sh
python3 -m inkflip.cli report runs/after/reports/mapping-control.json --format html --out runs/after/mapping-control.html --replace-output
```

## Invariants Enforced
- **I12**: Regression comparison cannot improve by losing coverage; baseline never auto-refreshes.
- **I13**: Source/model/adapter identity accompanies every run.
- **I18**: Claims derive from exact shipped artifacts and stated test populations.
- **Exit 5 on Regression**: Any violation of explicit acceptance rules immediately terminates with exit code 5.
