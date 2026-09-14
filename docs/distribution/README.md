# Distribution reference

What this repository ships, how the shipped surface is verified, and how the
third-party inputs for the native bundle are prepared. This is the public
reference for the distribution work; the enforcing tools live in the
repository (`scripts/check_distribution.py`, `scripts/distribution/`).

The browser app is published at
[inkflip-rose.vercel.app](https://inkflip-rose.vercel.app). Browser publication
and native-image validation are separate workflows. The build, artifact
checks and rollback procedures are in
[release-and-rollback.md](../release-and-rollback.md).

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
  zubair"; see the repository LICENSE).
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

The assembler adds the application wheel, CLI entry point and notices to
the dependency bundle. See [application artifacts](application-artifact-interface.md).

## Release-candidate binding (declarative, no hardcoded image)

The gate no longer hardcodes an image tag or digest. The trusted expected
identity comes from a **declared release candidate** —
`config/release-candidate.json` (template:
[release-candidate.template.json](release-candidate.template.json)). When the
candidate is not yet bound (digest pending the final rebuild), image runtime
verification is skipped with a visible note; when bound, `--docker` verifies
the actual image against it. Expected identity is trusted declared input and
is never adopted from the artifact being checked. Generated example
declarations for observed fixed images live next to the template
(`release-candidate.merged-example.json` for
`inkflip-native:merged` / `sha256:cd2598829fbb…` — an amd64 emulated-on-Mac
artifact that predates later native fixes; `inkflip-native:pc-prod`
(`sha256:1923b04a…`) is preserved locally as the previous candidate).

## Inventory and SBOM

`scripts/distribution/build_inventory.py` generates a deterministic
inventory and CycloneDX 1.5 SBOM from the frozen inputs (production npm
closure, staged assets, prepared example, native lock packages). Outputs
depend only on input-content digests — never on HEAD or wall-clock — so two
runs over identical content are byte-identical. Working output goes to the
local ignored tree (`.private/distribution/`); a compact public digest of
the current surface lives in [SURFACE.md](SURFACE.md).

## The native CLI in Docker (macOS + Docker)

Two container profiles exist for the native CLI. Both run as UID 65532 with
`--network none` during processing; image *setup* may use the network. Docker
is a required, supported delivery surface.

**Checkout image (functional verification).** Built directly from a source
checkout; it is explicitly *not* the digest-pinned release profile.

```sh
git checkout <candidate>
docker build -f build/native/Dockerfile.checkout -t inkflip-native:checkout .
docker run --rm --network none --user 65532:65532 \
  -v "$PWD/fixtures/public:/data/in:ro" -v "$PWD/out:/data/out" \
  inkflip-native:checkout inspect /data/in/mapping-amount.pdf --out /data/out/report.json
docker run --rm --network none --user 65532:65532 \
  -v "$PWD/out:/data/out:ro" inkflip-native:checkout validate /data/out/report.json
```

**Production profile (digest-pinned, linux/amd64).** Built for
**linux/amd64** via `--platform linux/amd64` (qemu emulation on an Apple
Silicon Mac is acceptable and labeled — it is not native x86_64 hardware
certification, which remains deferred). Assembled from the third-party
bundle plus the built application wheel:

```sh
python3 scripts/distribution/prepare_native_bundle.py   # third-party inputs (explicit network step)
python3 scripts/distribution/assemble_native_image.py   # adds the Inkflip wheel + notices + identities
docker build --platform linux/amd64 -f build/native/Dockerfile -t inkflip-native:prod .
```

**Production profile — built and verified on this Mac (2026-09-13,
candidate `84c839c`):** image `inkflip-native:pc-prod`, digest
`sha256:1923b04a483b7744c49bc3d7530d7dea98c71aa689355810cfdaeba024f6da33`,
amd64/linux, containing the hashed application wheel (`c9d76022…`), the
digest-pinned OCR model (`7d4322bd…`), Debian `tesseract-ocr 5.5.0-1+b1`
(70-deb hashed closure) and a four-id notice inventory
(`inkflip-mit`, `pdfium-binary-appendix`, `node-license`, `tesseract-apache`).

Executable offline workflow (verified; note the quoted path with a space and
the read-only input mount):

```sh
docker run --rm --network none --user 65532:65532 \
  -v "/path with spaces/in:/data/in:ro" -v "/path with spaces/out:/data/out" \
  inkflip-native:pc-prod inspect /data/in/mapping-amount.pdf \
    --pages 1 --ocr-pages 1 --out /data/out/report-ocr.json
docker run --rm --network none --user 65532:65532 \
  -v "/path with spaces/out:/data/out:ro" \
  inkflip-native:pc-prod validate /data/out/report-ocr.json
docker run --rm --network none --user 65532:65532 \
  -v "/path with spaces/out:/data/out" \
  inkflip-native:pc-prod report /data/out/report-ocr.json --format html \
    --out /data/out/report-ocr.html
docker run --rm --network none --user 65532:65532 \
  -v "/path with spaces/in:/data/in:ro" -v "/path with spaces/out:/data/out" \
  inkflip-native:pc-prod replay /data/out/report-ocr.json \
    --source /data/in/mapping-amount.pdf --profile native-default \
    --out /data/out/replay.json --replace-output
```

Observed behavior (executed): inspect exits 0 (with OCR through the image's
tesseract 5.5.0); validate exits 0; report/replay refuse overwriting existing
outputs (exit 2) unless `--replace-output` is given; `replay` refuses a
profile that does not match the recorded run profile; remote URL sources are
refused. Preparation steps that use the network (deb/wheel download, image
build) are explicit and separate from offline processing.

Verified on 2026-09-13 on this Mac's local Docker (linux/aarch64): the
checkout image built from a clean clone of candidate `b50c9d2` (image ID
`9012f41fb6b9`, manifest digest `sha256:9012f41fb6b9…d6d52a`) and completed
the offline sequence above — inspect (exit 0), validate (`VALID`, 98
occurrences), script-free HTML report, and the remote-source refusal (exit 2,
"Remote URL sources are not permitted"). The production assembly chain also
completed on this Mac: third-party bundle → application wheel
(`inkflip-0.0.0-py3-none-any.whl`, sha256 `4fc4fa1b265813ae…`, built from
this source by `assemble_native_image.py`) → notices index →
`native/dist/BUILD-CONTEXT.json`.

Platform and reproducibility limits:

- The production wheel lock targets linux/amd64. Building this profile on
  Apple Silicon requires `--platform linux/amd64` and emulation. The arm64
  checkout image is a separate functional build.
- The assembled wheel's provenance is this checkout's source built by
  `assemble_native_image.py`; reproducibility of the wheel bytes across
  machines is expected (pure-Python wheel) but cross-host reproduction has
  not been independently verified yet.

The gate can verify the declared image identity read-only against the actual
Docker daemon, using the identity declared in `config/release-candidate.json`
(never the artifact being checked):

```sh
python3 scripts/check_distribution.py --release \
  --docker inkflip-native:pc-prod
```

This checks image identity and architecture, hashes the application wheel
and model inside the image, verifies the tesseract version and hashes every
required notice entry from the image's own `INDEX.json`. A tag or JSON label
alone is not proof. Re-running it against a rebuilt image requires the
declared digest in `config/release-candidate.json` to be updated through
the normal recorded-artifact flow.

## Advisory evidence

Dated advisory scans against the exact selected versions are recorded with
their raw output in the working tree evidence directory; a failed scan
service request is recorded as an unknown result, never as a clean scan.
Re-run the scans whenever the dependency surface changes and at release
closure.
