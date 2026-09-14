# T40 container runtime evidence

Host: macOS arm64. OrbStack Docker 29.4.0 was started for this bounded run
(`linux/arm64` / `aarch64`, not emulated). Live restrictions executed against
`inkflip-native:t40` built from `build/native/Dockerfile.checkout`:

- non-root uid 65532
- `--network none` (egress to 1.1.1.1:80 failed)
- read-only `/input`
- crash exit 99, hang killed after 5s, 1 MiB stdout flood
- source PDF bytes unchanged; prior output retained

The production hashed `Dockerfile` was not built. `scripts/check_native_image_inputs.py`
fails closed: no `native/dist` Inkflip wheel, no `release/native-requirements.lock`
that pins `inkflip==`, and no `release/{node,models,notices}` in this checkout.
ZCode's companion lock is linux x86_64 third-party wheels only and does not
include an Inkflip wheel. Installing that lock on this native arm64 image
would be the wrong ABI; linux/amd64 would be emulation.

Image pin: `python:3.13.15-slim-trixie@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285`.
