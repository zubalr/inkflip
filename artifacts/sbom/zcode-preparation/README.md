# Distribution inventory / SBOM preparation (T47 preparation, ZCode batch)

This directory holds the **preparation-phase** distribution inventory and
SBOM for the snapshot recorded in `config/distribution-manifest.json`:

- `inventory.json` — detailed, deterministic inventory of what this snapshot
  distributes (shipped browser assets and their bundles, native tooling,
  fixtures), classified runtime/shipped vs development-only vs optional vs
  unknown.
- `sbom.cdx.json` — the same shipped surface expressed as CycloneDX 1.5 JSON.
- `advisory-scan/` — raw vulnerability-advisory query output against the
  exact frozen versions, with timestamps (network-preparation evidence; scan
  results are evidence, not a clean bill of health).

Regeneration is deterministic — two runs over identical input produce
byte-identical output:

```sh
python3 scripts/distribution/build_inventory.py --out artifacts/sbom/zcode-preparation
python3 scripts/check_distribution.py --release
```

Status: **preparation, not the completed T47 gate.** The final release-bundle
SBOM/notices are produced at T47 closure after T21/T25/T30/T43/T44 change the
distribution. See [docs/distribution-preparation.md](../../../docs/distribution-preparation.md)
for the integration guide.
