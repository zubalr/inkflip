# Native containment image

T40 owns the digest-pinned recipe and the `scripts/run_native_container.sh`
invocation. The image digest is the T02 python 3.13.15 slim-trixie index
digest recorded in `build/base-image.lock.json`.

## Production profile (`Dockerfile`)

Required inputs (fail closed via `scripts/check_native_image_inputs.py`):

| Path | Role |
| --- | --- |
| `native/dist/*.whl` | Hashed wheels, including the Inkflip application wheel (`inkflip-*.whl`) |
| `release/native-requirements.lock` | `--require-hashes` lock that pins `inkflip==…` and the T02 runtime closure |
| `release/node/` | Bundled Node/PDF.js assets |
| `release/models/` | Bundled OCR models |
| `release/notices/` | Third-party notices |

Runtime contract:

- Interpreter: Python **3.13.15** (`requires-python ==3.13.15`)
- Base image: `python:3.13.15-slim-trixie` at the T02 index digest
- Architecture/ABI: recorded at build time; Linux `x86_64` manylinux wheels from T47 are not macOS wheels. On Apple Silicon, `linux/arm64` is native to OrbStack; `linux/amd64` is emulated.
- Entry point: `inkflip` (console script from the application wheel)
- User: `65532:65532`
- Processing: `--network none`, read-only root, read-only `/input`, writable `/output` and scratch

A T47 third-party wheel bundle without an Inkflip wheel is incomplete. Do not invent an Inkflip wheel from that job.

## Checkout helper (`Dockerfile.checkout`)

Weaker local-build helper: copies `native/` source, installs the four runtime pins from PyPI at image **build** time, and installs a PATH wrapper named `inkflip`. Processing still uses `--network none`. This image is not the hashed release profile.

## Invocation

```sh
scripts/run_native_container.sh --source-root DIR --out DIR -- inspect /input/file.pdf --out /output/report.json
```
