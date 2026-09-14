# Release and rollback

The current public path from a source checkout to a published static site, and
the rollback of a bad publication, using only commands that exist in this
repository. The frozen `planning/` snapshot is historical: it still describes
an earlier `pnpm`-era toolchain and is not this path.

Nothing here publishes anything. Publication and rollback are owner-authorized
actions performed outside this repository; the repository's job is to make the
exact bytes identifiable and verifiable before and after a release.

## 1. Build the browser bundle

```sh
bun run build
```

The registered `build` group compiles the shared packages and then the static
site. The production bundle is written to `apps/web/dist/`.

## 2. Record the static dist manifest

```sh
python3 scripts/distribution/record_dist.py --skip-build # record the dist built in §1
```

The recorder walks `apps/web/dist/` and writes a deterministic manifest —
relative path, byte count and SHA-256 per file, plus a `file_set_sha256` over
the whole set — to `.private/distribution/dist-manifest.json` (override with
`--out PATH`). With `--skip-build` it records the dist that §1 just built, so
following this guide in order builds exactly once. The default form,
`record_dist.py` with no flag, first runs `bun run build` and then records:
that one-shot "build and record" is the convenience for when you have not
built yet.

It is **recorded rather than committed** on purpose: the built bundle is
regenerated, not committed, and a manifest only means something while it
describes the bytes actually built. The manifest lives in the git-ignored
working tree, so re-record it after every build that changes the bundle; a
stale manifest is a build-identity mismatch, not a pass. Exit codes: 0 pass,
1 build failure, 2 config error.

## 3. Static preflight (fail-closed)

```sh
bun run check:static-dist
```

That registered command resolves to the recorded argv:

```sh
python3 scripts/check_static_dist.py apps/web/dist \
  --config wrangler.json \
  --dist-manifest .private/distribution/dist-manifest.json
```

Fail-closed contract: a missing dist manifest is a failure, never a skipped
check; any Worker script, binding or application-compute feature in
`wrangler.json` is rejected; and `_headers` CSP/cache rules are parsed and
validated (same-origin sources only, immutable rules bound to the paths they
claim, freshness rules for `index.html`, `sw.js` and `release.json`). Exit
codes: 0 pass, 1 verification failures, 2 config/usage error. A local pass is
not proof of a deployed hostname.

## 4. Distribution gate

```sh
python3 scripts/check_distribution.py --release
python3 scripts/check_distribution.py --release \
  --dist-manifest .private/distribution/dist-manifest.json
```

The first form verifies the declared distribution surface against actual
bytes; `--dist-manifest` additionally verifies the built static output against
its recorded manifest. Exit codes: 0 pass, 1 verification failures, 2 config
error.

The native-bundle scope of the gate fails closed until the native bundle
context has been prepared by the explicit network step in §5
(`scripts/distribution/prepare_native_bundle.py`), which is a separate,
network-using step. The gate's exit-code contract stays 0 pass,
1 verification failures, 2 config error; an unprepared native context is a
verification failure, never a skip.

## 5. Native bundle and container image (explicit network step)

Preparation and assembly are separate, explicitly network-using steps; the
application itself never retrieves anything automatically:

```sh
python3 scripts/distribution/prepare_native_bundle.py   # third-party inputs (network)
python3 scripts/distribution/assemble_native_image.py   # adds the Inkflip wheel + notices + identities
python3 scripts/distribution/prepare_native_bundle.py --check  # read-only verification of the prepared context
docker build --platform linux/amd64 -f build/native/Dockerfile -t inkflip-native:prod .
```

`--check` re-derives the expected wheel identities from `native/uv.lock` and
verifies the prepared artifacts, the recorded stamps and the manifest without
downloading, writing or creating anything; it must exit 0 before the image
build.

The production profile is pinned to **linux/amd64**: on this arm64 Mac it
needs emulation, and a plain non-emulated build must fail — that failure is
the lock working, not a defect to route around. The arm64 checkout image is a
quick offline functional check of the CLI, not the recorded release profile:

```sh
docker build -f build/native/Dockerfile.checkout -t inkflip-native:checkout .
docker run --rm --network none --user 65532:65532 \
  -v "$PWD/fixtures/public:/data/in:ro" -v "$PWD/out:/data/out" \
  inkflip-native:checkout inspect /data/in/mapping-amount.pdf --out /data/out/report.json
docker run --rm --network none --user 65532:65532 \
  -v "$PWD/out:/data/out:ro" inkflip-native:checkout validate /data/out/report.json
```

## 6. Artifact identity: declared, never adopted

The expected identity of the production image is declared in
`config/release-candidate.json` (template:
[release-candidate.template.json](distribution/release-candidate.template.json)).
The gate's `--docker` verification takes its expected identity from that
declared candidate (`--candidate` defaults to `config/release-candidate.json`)
and never adopts identity from the artifact being checked: a requested image
whose ref does not match the declared candidate fails, and a missing,
unreadable, malformed, wrong-kind or incomplete candidate fails closed
(nonzero exit), never a skip-to-success.

The verification command and the checks it performs are documented in
[distribution/README.md](distribution/README.md); pass `--docker <image-ref>`
with the ref declared in the candidate file. This guide deliberately quotes no
image digest and certifies no artifact: read the declared candidate file for
the current expected identity instead of trusting a digest in prose.

## 7. Rollback to a known prior immutable asset set

Rollback restores the exact bytes of the last accepted static artifact. It does
not rebuild, patch, or re-record anything on the way.

1. **Stop promotion.** An owner action; no command in this repository starts or
   stops a publication.
2. **Identify the last accepted static artifact from the release record.** The
   record for the static tree is its recorded dist manifest: the per-file
   SHA-256 list and `file_set_sha256` for the accepted build (output of
   `scripts/distribution/record_dist.py`, kept in the git-ignored working
   tree). Archive the accepted manifest together with its static tree — the
   manifest alone cannot restore bytes, and the tree alone cannot prove them.
3. **Verify its checksum before deploying anything.**

   ```sh
   python3 scripts/check_static_dist.py apps/web/dist \
     --config wrangler.json \
     --dist-manifest <retained dist manifest>
   ```

   This must exit 0 with the recomputed file-set digest equal to the accepted
   build's recorded `file_set_sha256`.
   `python3 scripts/check_distribution.py --release --dist-manifest
   <retained dist manifest>` adds the distribution-surface checks. A mismatch
   stops the rollback.
4. **Redeploy that exact static tree with the same reviewed uploader** used for
   the original publication. The current reviewed path is the Vercel adapter
   documented in `docs/vercel-static-deploy.md`: `scripts/vercel_output.py
   prepare` + `check`, `vercel deploy --prebuilt`, then `vercel promote
   <deployment>` of the staged bytes.
5. **Verify the retained artifact itself** — the restored static tree is
   re-verified against the retained manifest, not against a freshly built
   one:

   ```sh
   python3 scripts/check_static_dist.py apps/web/dist \
     --config wrangler.json \
     --dist-manifest <retained dist manifest>
   ```

   This must exit 0 with the recomputed `file_set_sha256` equal to the
   accepted build's recorded value; optionally re-run the distribution gate
   with `--dist-manifest <retained dist manifest>` to re-add the
   distribution-surface checks. On the destination, capture the response
   headers and confirm the deployed `_headers` CSP/cache rules are present
   and the configuration still contains no Worker script or bindings.
   `bun run test:privacy` is its **own local regression build** that
   compiles and serves its own test output, so it does **not** certify a
   retained or restored artifact, nor a deployed hostname.
6. **Document the rollback and the affected capability** so the defect and the
   temporary capability loss are both on the record.

Rollback rules:

- Rollback never edits user reports and never refreshes goldens, baselines or
  captured evidence to hide a defect; a rollback reports the defect rather than
  making the evidence agree with the release.
- Publication and rollback are owner-authorized actions. The repository's job
  is to make the exact prior bytes identifiable — not to approve, promote or
  conceal a release.

## 8. Automated browser publication

`.github/workflows/deploy-web.yml` runs after successful verification of a
push to main. It checks that the revision is still current, builds the
static app, validates Vercel Build Output and runs a production browser
smoke test. It uploads an immutable candidate and checks main again before
promoting it. The live address is
[inkflip-rose.vercel.app](https://inkflip-rose.vercel.app).

The Vercel token is supplied by the production GitHub Environment. Native
image validation is separate from browser deployment. See
[Vercel deployment](vercel-static-deploy.md) for setup and failure handling.

Verification state (2026-09-14): in this checkout the build, the manifest
recording, the static preflight and the distribution gate (both with and
without `--dist-manifest`) were executed. The native bundle preparation, the
assembly step and both `docker build` commands were **not** run while writing
this guide.
