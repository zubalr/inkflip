# Digest-pinned native containment image (T40).
# BASE_IMAGE is the T02-recorded python:3.13.15-slim-trixie index digest.
# This is not a floating tag. Source-only portability is not this profile.
#
# Production install uses hashed wheels from T47 (`native/dist/` +
# `release/native-requirements.lock`). When those artifacts are absent,
# `Dockerfile.checkout` is a weaker local-build helper and must not be
# advertised as the hardened release image.
ARG BASE_IMAGE=python:3.13.15-slim-trixie@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285
FROM ${BASE_IMAGE}
WORKDIR /app
COPY native/dist/ /wheels/
COPY release/native-requirements.lock /locks/requirements.lock
RUN python -m pip install --no-index --find-links=/wheels --require-hashes -r /locks/requirements.lock
COPY release/node/ /app/node/
COPY release/models/ /app/models/
COPY release/notices/ /app/notices/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
USER 65532:65532
ENTRYPOINT ["inkflip"]
