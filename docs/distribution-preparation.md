# Distribution preparation — integration guide (T47 preparation)

This is the handoff for the owner/integrator (Devin) who will close T47
after the remaining feature lanes land. Everything described here was
executed on the `work/zcode/distribution-completion` branch; commands are
reproducible as written.

## What this batch delivered

| Deliverable | Path | Status |
| --- | --- | --- |
| Distribution manifest | `config/distribution-manifest.json` | implemented; covers the current static browser surface |
| Distribution checker | `scripts/check_distribution.py` | implemented; registered T47 command form: `--release` |
| Checker tests | `tests/release/distribution/` | 16 tests, all failure modes proven |
| Inventory + SBOM | `scripts/distribution/build_inventory.py` → `artifacts/sbom/zcode-preparation/{inventory.json,sbom.cdx.json}` | implemented, deterministic (content-digest identity) |
| License evidence | `licenses/` (+ `licenses/README.md` provenance) | implemented for the current shipped surface; one visible gap (tr46) |
| NOTICE | `NOTICE` | implemented for the current surface; project license/copyright line still **pending owner decision** |
| Advisory evidence | `artifacts/sbom/zcode-preparation/advisory-scan/` | recorded 2026-09-13 (bun audit + OSV querybatch); re-run at closure |
| Docs corrections | README/docs/* + `tests/docs/` | delivered per the 2026-09-13 delivery review |

This is **preparation, not T47 acceptance**: final closure requires the
completed distribution after T21/T25/T30/T43/T44, the owner's
LICENSE/copyright decision, and merged-state gate evidence.

## How to rerun everything

From the repository root (after `bun install` for the npm-side inputs):

```sh
# 1. Regenerate the inventory/SBOM from current inputs (--check fails if the
#    committed outputs no longer match reality)
python3 scripts/distribution/build_inventory.py --check

# 2. Run the distribution gate
python3 scripts/check_distribution.py --release

# 3. Distribution checker tests (disposable fixtures; no repo mutation)
python3 -m unittest discover -s tests/release -v

# 4. Documentation checks
python3 -m unittest discover -s tests/docs -v && python3 scripts/check_claims.py
```

Exit codes for the gate: 0 pass, 1 verification failures (itemized), 2
config error. The report is deterministic and sorted.

## What to update when the distribution changes

The manifest is the single declaration point; the checker fails loudly when
reality drifts from it, so the workflow is: change the product → run the
gate → fix the manifest/NOTICE/licenses in the same change.

- **T21 adds gallery examples** → each new `apps/web/public/examples/<id>/`
  directory is a new explicit-file group (or extend the digest-source
  pattern) in `config/distribution-manifest.json`; the checker fails with
  `undeclared shipped asset` until declared. Regenerate example support-file
  digests from `scripts/prepare_examples.py` output.
- **T25 changes the offline/model cache surface** → if any model or cache
  material becomes part of the shipped tree, add it to
  `config/resolved-assets.json` (it becomes a declared group automatically);
  if it becomes runtime-generated instead, keep it out of the shipped roots
  and note the exclusion.
- **T30+ implement the native CLI** → the CLI's own distribution surface
  (entry point, bundled models if any) is NOT in this manifest. Add a new
  manifest section/group set when its packaging exists; the inventory's
  native packages are already listed as runtime-tooling from
  `native/uv.lock`.
- **T43/T44 introduce (or reject) model assets** → ONNX/RapidOCR models
  would require their own groups with license evidence and exact digests;
  experiment-rejected assets must remain absent (the gate's undeclared-asset
  check enforces absence from shipped roots, and the inventory's unknown
  bucket flags any unaccounted file).
- **Any dependency bump** → `bun.lock`/`native/uv.lock` changes shift the
  bundled closure: rerun the inventory (it recomputes the npm closure and
  native lock list), copy new license texts into `licenses/npm/`, update
  `NOTICE`, and re-run the advisory scans (`bun audit` + OSV querybatch —
  the scan script in the advisory-scan SUMMARY documents the exact query).

## Pending owner inputs (do not invent)

1. **Root `LICENSE` and the copyright-holder line for NOTICE** — the
   recorded planning default is ADR-003 (MIT for newly authored code), but
   no owner decision recording the final copyright statement has been made;
   `artifacts/tasks/T47/licensing-status.md` is the dated record to flip
   when the decision lands (docs + `tests/docs/snapshot-facts.json` must
   change together — the checker tests that transition).
2. **`tr46@0.0.3` license text** — upstream ships none; the NOTICE records
   the package.json declaration with the gap visible. Options for closure:
   accept declaration-only with rationale, or pin a version that ships text.
3. **T47 acceptance itself** — after the features above land: regenerate
   everything, refresh the advisory scans, run the gate at the merged
   release candidate, and record the receipt.

## Known limitations of this preparation

- The inventory/SBOM covers the static browser surface plus the native
  lockfile; the built `dist/` bundle is intentionally not hashed (it is
  generated). At T47 closure, hash the actual deployed bundle against the
  same component list.
- `licenses/` texts for PyPI packages are not collected (source+lock
  distribution, nothing bundled); revisit if wheels ever ship.
- The advisory evidence is dated 2026-09-13 and proves only that moment.
