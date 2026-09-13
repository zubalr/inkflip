# Hardened native container recipe (T40).
# Follows planning/security/THREAT_MODEL.md and planning/deployment/examples/Dockerfile.native:
# - Non-root execution (UID 65532:65532)
# - Read-only root filesystem compatible
# - Single-thread CPU pins (OMP/OPENBLAS)
# - Python 3.13 base with isolated native execution
ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}

WORKDIR /app

# Ensure non-root app user exists (UID/GID 65532)
RUN groupadd -g 65532 appgroup 2>/dev/null || true && \
    useradd -u 65532 -g 65532 -s /usr/sbin/nologin -d /app appuser 2>/dev/null || true

# Copy and install native Inkflip package
COPY native /app/native
RUN pip install --no-cache-dir /app/native

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    PYTHONIOENCODING=utf-8

USER 65532:65532

ENTRYPOINT ["python3", "-m", "inkflip.cli"]
CMD ["--help"]
