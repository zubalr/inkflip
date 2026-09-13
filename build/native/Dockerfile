# Digest-pinned native containment image (T40).
# BASE_IMAGE is the T02-recorded python:3.13.15-slim-trixie index digest.
# This is not a floating tag. Source-only portability is not this profile.
#
# Production install uses the assembled native/dist context:
#   wheels/                 hashed third-party + Inkflip application wheel
#   requirements.lock       complete hashed lock (inkflip pin included)
#   node/*.tar.xz           official linux-x64 Node runtime
#   models/tessdata/        digest-pinned OCR model
#   tesseract/debs/         hashed Debian tesseract-ocr 5.5.0 amd64 closure
#   notices/                license texts including tesseract Apache-2.0
#
# Assemble with: python3 scripts/distribution/assemble_native_image.py
# Build for the recorded ABI: docker build --platform linux/amd64 ...
# An arm64 checkout image (Dockerfile.checkout) is not a substitute.
# Apple Silicon builds are qemu; that is not native x86_64 certification.
ARG BASE_IMAGE=python:3.13.15-slim-trixie@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285
FROM ${BASE_IMAGE}
WORKDIR /app
COPY native/dist/wheels/ /wheels/
COPY native/dist/requirements.lock /locks/requirements.lock
RUN python -m pip install --no-index --find-links=/wheels --require-hashes -r /locks/requirements.lock
COPY native/dist/node/ /tmp/node-src/
COPY native/dist/models/ /app/models/
COPY native/dist/notices/ /app/notices/
COPY native/dist/tesseract/ /tmp/tesseract-src/
RUN python - <<'PY'
import hashlib, json, tarfile, shutil
from pathlib import Path
src = Path("/tmp/node-src")
stamp = json.loads((src / "node.stamp.json").read_text())
tarball = src / stamp["filename"]
digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
if digest != stamp["sha256"]:
    raise SystemExit(f"node tarball hash mismatch: stamp {stamp['sha256']} != {digest}")
model = Path("/app/models/tessdata/eng.traineddata")
model_stamp = json.loads(Path("/app/models/model.stamp.json").read_text())
model_digest = hashlib.sha256(model.read_bytes()).hexdigest()
if model_digest != model_stamp["sha256"]:
    raise SystemExit(f"model hash mismatch: stamp {model_stamp['sha256']} != {model_digest}")
dest = Path("/opt/node")
extracted = Path("/opt") / f"node-v{stamp['version']}-linux-x64"
if dest.exists():
    shutil.rmtree(dest)
with tarfile.open(tarball) as tf:
    tf.extractall("/opt", filter="data")
if not extracted.is_dir():
    raise SystemExit(f"node unpack missing {extracted}")
extracted.rename(dest)
node = dest / "bin" / "node"
if not node.is_file():
    raise SystemExit(f"node binary missing after unpack: {node}")
node.chmod(0o755)
tess_src = Path("/tmp/tesseract-src")
tess_stamp = json.loads((tess_src / "tesseract.stamp.json").read_text())
debs = tess_src / "debs"
if not debs.is_dir():
    raise SystemExit("tesseract debs missing from assembled context")
expected = tess_stamp.get("packages") or []
if not expected:
    raise SystemExit("tesseract stamp lists no packages")
deb_paths = []
for entry in expected:
    path = debs / entry["filename"]
    if not path.is_file():
        raise SystemExit(f"tesseract deb missing: {path.name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise SystemExit(f"tesseract deb hash mismatch {path.name}: stamp {entry['sha256']} != {digest}")
    deb_paths.append(path)
import subprocess
install = subprocess.run(
    ["dpkg", "-i", *[str(p) for p in sorted(deb_paths)]],
    capture_output=True,
    text=True,
)
if install.returncode != 0:
    raise SystemExit(
        "dpkg -i tesseract closure failed:\\n"
        + (install.stdout or "")[-2000:]
        + (install.stderr or "")[-2000:]
    )
shutil.rmtree(tess_src)
tess = Path("/usr/bin/tesseract")
if not tess.is_file():
    raise SystemExit("tesseract executable missing after offline dpkg")
PY
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    PATH="/opt/node/bin:${PATH}" \
    INKFLIP_NODE=/opt/node/bin/node \
    INKFLIP_MODELS=/app/models \
    TESSDATA_PREFIX=/app/models/tessdata
USER 65532:65532
ENTRYPOINT ["inkflip"]
