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
CHECK_MOUNTS=0

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
    --check-mounts)
      CHECK_MOUNTS=1
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
      echo "unknown argument: $1" >&2
      usage
      ;;
  esac
done

[ -n "$SOURCE_ROOT" ] && [ -n "$OUT_DIR" ] || usage
if [ "$CHECK_MOUNTS" != 1 ]; then
  [ "$#" -gt 0 ] || usage
fi

strip_slash() {
  p=$1
  while [ "$p" != "/" ] && [ "${p%/}" != "$p" ]; do
    p=${p%/}
  done
  printf '%s\n' "$p"
}

literal_forbidden() {
  p=$(strip_slash "$1")
  case "$p" in
    /|/etc|/private/etc|/var/run|/private/var/run|/home|/Users|/System/Volumes/Data/Users)
      return 0
      ;;
  esac
  return 1
}

resolve_existing_dir() {
  (CDPATH= cd -- "$1" && pwd -P)
}

resolve_maybe_new_dir() {
  if [ -d "$1" ]; then
    resolve_existing_dir "$1"
  else
    parent=$(dirname -- "$1")
    base=$(basename -- "$1")
    parent_r=$(resolve_existing_dir "$parent")
    printf '%s/%s\n' "$parent_r" "$base"
  fi
}

forbidden_mount() {
  resolved=$(strip_slash "$1")
  role=$2
  case "$resolved" in
    /|/etc|/etc/*|/private/etc|/private/etc/*|/var/run|/var/run/*|/private/var/run|/private/var/run/*|/home|/Users|/System/Volumes/Data/Users)
      echo "inkflip: refusing to mount a broad host root as ${role}: $resolved" >&2
      return 0
      ;;
  esac
  if [ -n "${HOME:-}" ]; then
    home_phys=$(strip_slash "$HOME")
    if [ "$resolved" = "$HOME" ] || [ "$resolved" = "$home_phys" ]; then
      echo "inkflip: refusing to mount a home directory as ${role}: $resolved" >&2
      return 0
    fi
  fi
  case "$resolved" in
    /Users/*|/System/Volumes/Data/Users/*)
      rest=${resolved#/Users/}
      rest=${rest#/System/Volumes/Data/Users/}
      case "$rest" in
        */*) ;;
        *)
          echo "inkflip: refusing to mount a home directory as ${role}: $resolved" >&2
          return 0
          ;;
      esac
      ;;
    /home/*)
      rest=${resolved#/home/}
      case "$rest" in
        */*) ;;
        *)
          echo "inkflip: refusing to mount a home directory as ${role}: $resolved" >&2
          return 0
          ;;
      esac
      ;;
  esac
  return 1
}

if literal_forbidden "$SOURCE_ROOT"; then
  echo "inkflip: refusing to mount a broad host root as source: $SOURCE_ROOT" >&2
  exit 2
fi
SOURCE_ROOT="$(resolve_existing_dir "$SOURCE_ROOT")"
if forbidden_mount "$SOURCE_ROOT" "source"; then
  exit 2
fi

if literal_forbidden "$OUT_DIR"; then
  echo "inkflip: refusing to mount a broad host root as output: $OUT_DIR" >&2
  exit 2
fi
OUT_DIR="$(resolve_maybe_new_dir "$OUT_DIR")"
if forbidden_mount "$OUT_DIR" "output"; then
  exit 2
fi
mkdir -p "$OUT_DIR"
OUT_DIR="$(resolve_existing_dir "$OUT_DIR")"
if forbidden_mount "$OUT_DIR" "output"; then
  exit 2
fi

if [ -n "$SCRATCH_DIR" ]; then
  if literal_forbidden "$SCRATCH_DIR"; then
    echo "inkflip: refusing to mount a broad host root as scratch: $SCRATCH_DIR" >&2
    exit 2
  fi
  SCRATCH_DIR="$(resolve_maybe_new_dir "$SCRATCH_DIR")"
  if forbidden_mount "$SCRATCH_DIR" "scratch"; then
    exit 2
  fi
  mkdir -p "$SCRATCH_DIR"
  SCRATCH_DIR="$(resolve_existing_dir "$SCRATCH_DIR")"
  if forbidden_mount "$SCRATCH_DIR" "scratch"; then
    exit 2
  fi
fi

if [ "$CHECK_MOUNTS" = 1 ]; then
  echo "inkflip: mount guard ok source=${SOURCE_ROOT} out=${OUT_DIR} scratch=${SCRATCH_DIR:-}" >&2
  exit 0
fi

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
