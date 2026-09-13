# Distribution reference

What this repository ships, how the shipped surface is verified, and how the
third-party inputs for the native bundle are prepared. This is the public
reference for the distribution work; the enforcing tools live in the
repository (`scripts/check_distribution.py`, `scripts/distribution/`).

Status: **preparation**. The final distribution gate (SBOM, vulnerability
review, notices over the built release bundle) closes with the release
tasks; nothing here claims completed release acceptance.

## The shipped browser surface

The static site serves three roots from `apps/web/public/`:

- `assets/` — the same-origin PDF.js runtime (cmaps, standard fonts, WASM
  codecs, ICC profiles, license file) and Tesseract.js OCR worker/WASM
  engines;
- `models/` — the pinned `tessdata_fast` English OCR language data;
- `examples/` — the prepared public amount example (source PDF, clean
  control, covered variants, prepared report and viewer).

Every file is declared with its byte count and SHA-256 in
`config/distribution-manifest.json` (digests resolve from the
digest-verified sources `config/resolved-assets.json` and the prepared
example manifest), together with the license declaration and license
evidence path for each group. `scripts/check_distribution.py --release`
verifies declared files against actual bytes, rejects unlisted shipped
files, symlinks, private/development content, missing license evidence and
notice inconsistencies (exit 0 pass, 1 failures, 2 config error).

## Third-party license evidence

- `licenses/` — exact license texts copied from the installed npm
  distributions (or the canonical Apache-2.0 text for the OCR language
  data), with per-copy source identity and SHA-256 in
  [licenses/README.md](../../licenses/README.md).
- [NOTICE](../../NOTICE) — the third-party component list for the shipped
  browser bytes and the project's own license (MIT, "Copyright (c) 2026
  zubair", owner decision recorded 2026-09-13; see the repository LICENSE).
- Known unresolved item: `tr46@0.0.3` declares MIT in `package.json`, but no
  license text exists in the exact npm tarball or the upstream repository
  tag — recorded with source identities in `licenses/README.md`; resolution
  is a packaging-policy decision for the integrator.

## Native bundle inputs (for the container build)

The native side ships as the application's own code plus third-party inputs
prepared from the frozen `native/uv.lock`:

```sh
python3 scripts/distribution/prepare_native_bundle.py --help
```

The generator resolves the full runtime dependency closure from the lock,
selects wheels for the contract's Linux platform (version, ABI and tags
checked mechanically), downloads them explicitly from the official package
index, verifies every digest against the lock's recorded hashes, and writes
them to the local ignored working tree under the paths the container build
consumes (`release/native-requirements.lock`, `release/notices/`,
`.private/distribution/` for bulky artifacts). It refuses missing wheels,
unexpected packages, incompatible tags and hash mismatches, and never
changes dependency versions or candidate selection. Installation and
processing never retrieve anything automatically.

Node runtime and model assets are copied into the same interface from the
established pins (`.node-version`, `config/resolved-assets.json`) with their
license texts indexed in `release/notices/` and NOTICE.

The application wheel, CLI entry point and container build itself are owned
by the packaging lane; until that wheel exists, the native bundle is an
explicitly incomplete distribution, not a finished container.

## Inventory and SBOM

`scripts/distribution/build_inventory.py` generates a deterministic
inventory and CycloneDX 1.5 SBOM from the frozen inputs (production npm
closure, staged assets, prepared example, native lock packages). Outputs
depend only on input-content digests — never on HEAD or wall-clock — so two
runs over identical content are byte-identical. Working output goes to the
local ignored tree (`.private/distribution/`); a compact public digest of
the current surface lives in [SURFACE.md](SURFACE.md).

## Advisory evidence

Dated advisory scans against the exact selected versions are recorded with
their raw output in the working tree evidence directory; a failed scan
service request is recorded as an unknown result, never as a clean scan.
Re-run the scans whenever the dependency surface changes and at release
closure.
