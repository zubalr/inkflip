# T40 container runtime evidence

Host: macOS arm64. `docker` CLI is present (`/usr/local/bin/docker`, 29.4.0,
context `orbstack`). The daemon API at
`unix:///Users/zubair/.orbstack/run/docker.sock` is not running.

This prompt forbids installing another VM, starting an idle VM, changing
machine-wide limits, or touching Homebase services to unblock the batch.
The container no-network criterion therefore remains **blocked**. Native OS
supervisor tests (hang/crash/flood/escape/source-bytes) execute on this
host and are distinct from container restrictions.

Image pin recorded in `build/native/image.lock.json`:
`python:3.13.15-slim-trixie@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285`.
Production `Dockerfile` still needs T47 hashed wheels under `native/dist/`
and `release/native-requirements.lock`.
