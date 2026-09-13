# Native Hardened Container Recipe (T40)

This directory contains the digest-pinned, hardened OCI container definition for running Inkflip native CLI in an isolated, unprivileged Linux environment per `planning/security/THREAT_MODEL.md`.

## Hardened Attributes
- Non-root UID: `65532:65532`
- Root filesystem: Read-only compatible (`--read-only`)
- Network: Disabled (`--network none`)
- Capabilities: All dropped (`--cap-drop ALL`)
- Privilege Escalation: Blocked (`--security-opt no-new-privileges`)
- Concurrency / Threads: Clamped to 1 (`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`)
- Limits: Process limit (`--pids-limit 64`), Memory bound (`--memory 1g`)
