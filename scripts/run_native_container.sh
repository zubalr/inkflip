#!/usr/bin/env sh
# Run Inkflip in hardened OCI container with strict containment (T40).
#
# Threat mitigations enforced:
# - --network none (strictly no egress or ingress)
# - --read-only (immutable container root)
# - --tmpfs /tmp:rw,noexec,nosuid,size=512m (bounded non-executable scratch)
# - --cap-drop ALL (no Linux capabilities)
# - --security-opt no-new-privileges (prevent privilege escalation)
# - -u 65532:65532 (non-root UID)
# - read-only input volume mount
# - dedicated writable output volume mount
# - --pids-limit 64 (prevent fork bombs)
# - --memory 1g (memory cap)
# - thread caps (OMP_NUM_THREADS=1, etc.)
set -eu

IMAGE_NAME="${INKFLIP_IMAGE:-inkflip-native:latest}"
INPUT_DIR=""
OUTPUT_DIR=""
DRY_RUN=false

usage() {
  echo "Usage: $0 --input <dir> --output <dir> [--image <tag>] [--dry-run] [--] [inkflip args...]"
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --input)
      INPUT_DIR="$2"
      shift 2
      ;;
    --output)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --image)
      IMAGE_NAME="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --)
      shift
      break
      ;;
    -h|--help)
      usage
      ;;
    *)
      break
      ;;
  esac
done

if [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ]; then
  usage
fi

INPUT_ABS="$(cd "$INPUT_DIR" && pwd)"
mkdir -p "$OUTPUT_DIR"
OUTPUT_ABS="$(cd "$OUTPUT_DIR" && pwd)"

RUN_CMD="docker run --rm \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=512m \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  -u 65532:65532 \
  -v \"$INPUT_ABS\":/input:ro \
  -v \"$OUTPUT_ABS\":/output:rw \
  --pids-limit 64 \
  --memory 1g \
  -e OMP_NUM_THREADS=1 \
  -e OPENBLAS_NUM_THREADS=1 \
  -e MKL_NUM_THREADS=1 \
  -e NUMEXPR_NUM_THREADS=1 \
  -e PYTHONIOENCODING=utf-8 \
  \"$IMAGE_NAME\""

if [ "$DRY_RUN" = "true" ]; then
  echo "$RUN_CMD $@"
  exit 0
fi

# Detect runtime
CONTAINER_RUNTIME=""
if command -v docker >/dev/null 2>&1; then
  CONTAINER_RUNTIME="docker"
elif command -v podman >/dev/null 2>&1; then
  CONTAINER_RUNTIME="podman"
else
  echo "Error: neither docker nor podman found on PATH" >&2
  exit 1
fi

exec "$CONTAINER_RUNTIME" run --rm \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=512m \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  -u 65532:65532 \
  -v "$INPUT_ABS":/input:ro \
  -v "$OUTPUT_ABS":/output:rw \
  --pids-limit 64 \
  --memory 1g \
  -e OMP_NUM_THREADS=1 \
  -e OPENBLAS_NUM_THREADS=1 \
  -e MKL_NUM_THREADS=1 \
  -e NUMEXPR_NUM_THREADS=1 \
  -e PYTHONIOENCODING=utf-8 \
  "$IMAGE_NAME" \
  "$@"
