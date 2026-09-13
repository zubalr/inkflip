# T40 Task Review: Native Containment and Failure Recovery

## Task Information
- **Task ID**: T40
- **Beads ID**: pdf-t40
- **Gate**: G4
- **Deliverables**:
  - `native/tests/security/`
  - `tests/containment/`
  - `artifacts/containment/`
  - `build/native/`
  - `scripts/run_native_container.sh`
  - `artifacts/tasks/T40/`

## Acceptance Criteria Verification
1. **Source bytes unchanged (I01)**:
   - Verified that input PDF fixture bytes and SHA-256 remain byte-identical across inspection operations.
2. **Output cannot escape root (I10)**:
   - Output path traversal (`../`) is rejected.
   - Corpus manifest path traversal (`../../etc/passwd`) and symlink escapes are rejected with `ContainmentError`.
3. **Child / descendants terminated (I17)**:
   - Verified that when a child process spawns grandchildren and hangs/sleeps, the supervisor wall timeout terminates the entire process group with `SIGKILL`.
   - Verified no orphan or zombie processes remain.
4. **Successful unrelated files remain valid**:
   - In a multi-job batch where one job fails/crashes, supervisor continues and atomically commits valid reports for completed jobs.
   - Valid reports pass schema validation.
5. **Unsupported OS limits reported**:
   - Platform capability probes honestly record `rlimit_support`. On macOS Darwin, `RLIMIT_AS` is reported as `False`.
6. **Actual container no-network test uses owned synthetic files and records image digest**:
   - Hardened container recipe `build/native/Dockerfile` and invocation script `scripts/run_native_container.sh` enforce:
     - `--network none`
     - `--read-only` root mount
     - `--cap-drop ALL`
     - `--security-opt no-new-privileges`
     - Non-root UID `65532:65532`
     - `--pids-limit 64`
     - `--memory 1g`
     - Thread clamps (`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`)
     - Tested with owned synthetic file `mapping-control.pdf`.
     - Output and recipe digests recorded in `artifacts/containment/receipt.json`.

## Evidence Summary
- **Tests**: 10 collected, 10 passed, 0 failed, 0 skipped.
- **Verification Commands**:
  - `uv run --project native python -m pytest native/tests/security -q` (7/7 passed)
  - `python tests/containment/run.py` (3/3 passed)
