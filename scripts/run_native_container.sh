#!/usr/bin/env sh
# Hardened native CLI invocation. Processing uses --network none.
# Setup of the image may use the network; this script does not.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
LOCK="$ROOT/build/native/image.lock.json"
IMAGE_DIGEST="sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285"
IMAGE_REF="python:3.13.15-slim-trixie@${IMAGE_DIGEST}"

usage() {
  echo "usage: $0 --source-root DIR --out DIR [--scratch DIR] [--image REF] -- inkflip-args..." >&2
  echo "Runs the native CLI inside the digest-pinned containment profile." >&2
  echo "Does not start a VM, change machine-wide limits, or mount Docker credentials." >&2
  exit 2
}

SOURCE_ROOT=""
OUT_DIR=""
SCRATCH_DIR=""
IMAGE="${INKFLIP_NATIVE_IMAGE:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root)
      SOURCE_ROOT="${2:-}"
      shift 2
      ;;
    --out)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    --scratch)
      SCRATCH_DIR="${2:-}"
      shift 2
      ;;
    --image)
      IMAGE="${2:-}"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      ;;
  esac
done

[ -n "$SOURCE_ROOT" ] && [ -n "$OUT_DIR" ] || usage
[ "$#" -gt 0 ] || usage

SOURCE_ROOT="$(CDPATH= cd -- "$SOURCE_ROOT" && pwd)"
mkdir -p "$OUT_DIR"
OUT_DIR="$(CDPATH= cd -- "$OUT_DIR" && pwd)"
if [ -n "$SCRATCH_DIR" ]; then
  mkdir -p "$SCRATCH_DIR"
  SCRATCH_DIR="$(CDPATH= cd -- "$SCRATCH_DIR" && pwd)"
fi

case "$SOURCE_ROOT" in
  /|/etc|/etc/*|/var/run|/var/run/*|/home|/Users)
    echo "inkflip: refusing to mount a broad host root as source: $SOURCE_ROOT" >&2
    exit 2
    ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  echo "inkflip: docker executable not found" >&2
  echo "container no-network test cannot execute on this host" >&2
  exit 4
fi
if ! docker info >/dev/null 2>&1; then
  echo "inkflip: docker daemon unavailable (no API at the configured socket)" >&2
  echo "container no-network test cannot execute; native OS supervisor tests remain separate" >&2
  exit 4
fi

if [ -z "$IMAGE" ]; then
  if docker image inspect "inkflip-native:t40" >/dev/null 2>&1; then
    IMAGE="inkflip-native:t40"
  else
    IMAGE="$IMAGE_REF"
  fi
fi

PLATFORM="${INKFLIP_NATIVE_PLATFORM:-}"
# linux/amd64 production images on Apple Silicon must be requested explicitly
# so qemu is an honest labeled path, not an implicit platform warning.
if [ -z "$PLATFORM" ]; then
  IMG_ARCH="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$IMAGE" 2>/dev/null || true)"
  case "$IMG_ARCH" in
    linux/amd64|linux/x86_64)
      PLATFORM="linux/amd64"
      ;;
  esac
fi

IMAGE_ID="$(docker image inspect --format '{{index .RepoDigests 0}}' "$IMAGE" 2>/dev/null || true)"
if [ -z "$IMAGE_ID" ]; then
  IMAGE_ID="$IMAGE"
fi

echo "inkflip-container image=$IMAGE_ID lock=$LOCK platform=${PLATFORM:-host-default}" >&2

run_restricted() {
  if [ -n "$PLATFORM" ]; then
    exec docker run --rm --platform "$PLATFORM" "$@"
  else
    exec docker run --rm "$@"
  fi
}

if [ -n "$SCRATCH_DIR" ]; then
  run_restricted \
    --network none \
    --read-only \
    --user 65532:65532 \
    --cap-drop ALL \
    --security-opt no-new-privileges \
    --pids-limit 64 \
    --memory 512m \
    --cpus 1 \
    --tmpfs /tmp:rw,exec,nosuid,size=64m \
    --mount "type=bind,src=${SOURCE_ROOT},dst=/input,readonly" \
    --mount "type=bind,src=${OUT_DIR},dst=/output" \
    --mount "type=bind,src=${SCRATCH_DIR},dst=/scratch" \
    -e HOME=/tmp \
    -e TMPDIR=/scratch \
    -w /output \
    "$IMAGE" \
    "$@"
fi

run_restricted \
  --network none \
  --read-only \
  --user 65532:65532 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 64 \
  --memory 512m \
  --cpus 1 \
  --tmpfs /tmp:rw,exec,nosuid,size=64m \
  --mount "type=bind,src=${SOURCE_ROOT},dst=/input,readonly" \
  --mount "type=bind,src=${OUT_DIR},dst=/output" \
  --tmpfs /scratch:rw,exec,nosuid,size=64m \
  -e HOME=/tmp \
  -e TMPDIR=/scratch \
  -w /output \
  "$IMAGE" \
  "$@"
