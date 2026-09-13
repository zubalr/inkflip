# Native containment image

T40 owns the digest-pinned recipe and the `scripts/run_native_container.sh`
invocation. The image digest is the T02 python 3.13.15 slim-trixie index
digest recorded in `build/base-image.lock.json`.

`Dockerfile` is the recommended hardened profile (hashed wheels, non-root).
`Dockerfile.checkout` exists only because T47 wheels are not published yet
and must not be treated as the release containment image.

Invoke through `scripts/run_native_container.sh`. That script applies
`--network none`, a read-only root, read-only source, writable output/scratch,
`--cap-drop ALL`, `--security-opt no-new-privileges`, and pid/cpu/memory
bounds. It does not mount the Docker socket, `$HOME`, or credentials.

Container restrictions are not the same as native OS supervisor limits.
Host process-group kill, RLIMIT probes and corpus path checks still apply
outside the image; the container is the hardened no-network/non-root route.
