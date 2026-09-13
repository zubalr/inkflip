# Reader Upgrade Verification Workflow (T35)

This guide documents Inkflip's provider-independent, offline workflow for verifying PDF reader engine upgrades without guessing or silent regressions.

## Architecture Overview

When upgrading a PDF reader engine (such as transitioning from `pypdf 5.9.0` to `6.18.0`), differences in text extraction, whitespace normalization, font decoding, or reading order can introduce regressions into downstream applications.

Inkflip provides a deterministic, five-phase verification pipeline:
1. **Isolated Environments**: Both versions run in dedicated virtual environments. Incompatible packages are never loaded into the same Python process.
2. **Corpus Execution**: Supervised execution over a curated PDF corpus with process limits, atomic reports, and crash isolation.
3. **Immutable Baselines**: Sealed baseline records requiring explicit human reviewer approval and stated rationale. Baselines can never be silently overwritten or auto-refreshed.
4. **Acceptance Rule Evaluation**: Explicit rule evaluation covering coverage loss, text stability, geometry deltas, and expected occurrences.
5. **Report Export**: Evidence reports can be exported to standalone HTML and reopened in the browser inspector.

## Acceptance Rules & Policy

Acceptance rules are defined in an `acceptance_rules.json` file conforming to `inkflip.schema.json`:

```json
{
  "kind": "acceptance_rules",
  "schema_version": "1.0.0",
  "rules": [
    {
      "id": "rule_cov_sample",
      "type": "required_coverage",
      "document_sha256": "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80",
      "page_index": 0,
      "reader_id": "pypdf-native",
      "region_id": null,
      "expected_text": null,
      "expected_count": null,
      "max_delta_pt": null,
      "capability": "native_text",
      "explanation": "Ensure non-empty text extraction"
    },
    {
      "id": "rule_stable_sample",
      "type": "stable_reading",
      "document_sha256": "19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed",
      "page_index": 0,
      "reader_id": "pypdf-native",
      "region_id": null,
      "expected_text": null,
      "expected_count": null,
      "max_delta_pt": null,
      "capability": "native_text",
      "explanation": "Extracted text must match approved baseline"
    }
  ],
  "policy": {
    "fail_on_coverage_loss": true,
    "fail_on_error": true,
    "unruled_change": "changed"
  }
}
```

### Rule Types
- `required_coverage`: Fails if occurrence count drops to 0 or required elements are missing.
- `stable_reading`: Fails if candidate extraction text differs from the approved baseline reading.
- `expected_text`: Fails if candidate extraction does not contain the specified expected string.
- `expected_occurrence_count`: Fails if candidate occurrence count deviates from the expected count.
- `max_geometry_delta`: Fails if bounding box vertices deviate by more than `max_delta_pt`.

### Exit Codes
- `0`: Success (all rules passed, or changes are unruled/informational).
- `2`: Invalid CLI arguments or schema violations.
- `4`: Missing input report, baseline, or rules file.
- `5`: **Regression**: One or more acceptance rules failed, or coverage was lost under `fail_on_coverage_loss`.

## Execution Workflow

```sh
# 1. Install isolated environments
python3 scripts/install_reader_profile.py --name before --reader pypdf --version 5.9.0
python3 scripts/install_reader_profile.py --name after --reader pypdf --version 6.18.0

# 2. Run corpus inspection
inkflip corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile before --out runs/before
inkflip corpus run --manifest examples/reader-upgrade/corpus.json --source-root planning/fixtures --profile after --out runs/after

# 3. Create immutable baseline
inkflip baseline create --run runs/before --rules examples/reader-upgrade/upgrade-rules.json --out baselines/before.json --approved-by reviewer-name --rationale "Upstream pypdf upgrade verification"

# 4. Compare runs
inkflip compare baselines/before.json runs/after --rules examples/reader-upgrade/upgrade-rules.json --out comparisons/upgrade

# 5. Export HTML report
inkflip report runs/after/mapping-control.inkflip.json --format html --out runs/after/mapping-control.html --replace-output
```
