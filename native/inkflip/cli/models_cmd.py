"""Allowlisted, digest-verified model cache preparation."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from inkflip.runtime.artifacts import atomic_write_bytes

ALLOWED_KINDS = {"inkflip_model_manifest"}
ALLOWED_PURPOSES = {"ocr_language_model", "tessdata", "generic"}

# A model id names one directory under the cache root and a source file names one
# leaf inside it. Both come from an untrusted manifest, so both are restricted to a
# single safe path segment: without this an id such as "../../outside/x" or
# "/tmp/escape" made the cache write outside the cache root entirely.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


def _safe_segment(value: str, what: str) -> str:
    """A model id names one cache directory, so it stays a strict identifier."""
    if not _SAFE_SEGMENT.match(value) or value in {".", ".."}:
        raise ModelPrepareError(
            f"{what} {value!r} must be a single safe path segment "
            "(letters, digits, dot, underscore or hyphen; no separators)"
        )
    return value


_UNSAFE_NAME = re.compile(r"[\x00-\x1f/:\\]")


def _safe_file_name(value: str, what: str) -> str:
    """A local artifact name must not escape its directory, but is otherwise free.

    Rejecting non-ASCII here would be a gratuitous restriction: the cache holds
    local model artifacts, and the contract puts no character repertoire on their
    names. Only path separators, NUL/control characters and the two dot names are
    refused, which is what containment actually requires.
    """
    if not value or value in {".", ".."} or _UNSAFE_NAME.search(value):
        raise ModelPrepareError(
            f"{what} {value!r} must be a single file name without path separators"
        )
    return value


class ModelPrepareError(ValueError):
    """Invalid model manifest or failed verification."""


class ModelUnavailableError(RuntimeError):
    """A requested model is missing or failed digest verification."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def prepare_models(manifest_path: Path, cache_dir: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise ModelPrepareError(f"Models manifest file not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelPrepareError(f"Failed to parse models manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("kind") not in ALLOWED_KINDS:
        raise ModelPrepareError(
            "Models manifest must declare kind 'inkflip_model_manifest'; "
            "untyped JSON is not a prepared cache"
        )
    models = manifest.get("models")
    if not isinstance(models, list) or not models:
        raise ModelPrepareError("Models manifest must list at least one allowlisted model")

    cache_dir.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for entry in models:
        if not isinstance(entry, dict):
            raise ModelPrepareError("Each model entry must be an object")
        model_id = entry.get("id")
        digest = entry.get("sha256")
        source = entry.get("path")
        purpose = entry.get("purpose", "generic")
        if not isinstance(model_id, str) or not model_id:
            raise ModelPrepareError("Model id is required")
        _safe_segment(model_id, "Model id")
        if model_id in seen_ids:
            # Two entries sharing an id would land in one cache directory and the
            # index could claim two different artifacts for the same id.
            raise ModelPrepareError(
                f"Duplicate model id {model_id!r}: each model id may be declared once"
            )
        seen_ids.add(model_id)
        if not isinstance(digest, str) or len(digest) != 64:
            raise ModelPrepareError(f"Model {model_id!r} is missing a 64-hex sha256")
        if purpose not in ALLOWED_PURPOSES:
            raise ModelPrepareError(f"Model {model_id!r} has unallowlisted purpose {purpose!r}")
        if not isinstance(source, str) or not source:
            unavailable.append({"id": model_id, "reason": "path missing"})
            continue
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = (manifest_path.parent / source_path).resolve()
        if not source_path.is_file():
            unavailable.append({"id": model_id, "reason": f"file not found: {source_path}"})
            continue
        actual = _sha256(source_path)
        if actual != digest:
            unavailable.append(
                {
                    "id": model_id,
                    "reason": f"digest mismatch: expected {digest}, got {actual}",
                }
            )
            continue
        _safe_file_name(source_path.name, "Model file name")
        destination = cache_dir / model_id / source_path.name
        # Defence in depth: the composed destination must stay inside the cache root.
        cache_root = cache_dir.resolve()
        if cache_root not in destination.resolve().parents:
            raise ModelPrepareError(
                f"Model {model_id!r} would write outside the cache directory {cache_root}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(destination, source_path.read_bytes())
        prepared.append(
            {
                "id": model_id,
                "sha256": digest,
                "path": str(destination),
                "purpose": purpose,
            }
        )
    record = {
        "kind": "inkflip_model_cache",
        "prepared": prepared,
        "unavailable": unavailable,
        "ready": len(unavailable) == 0,
        "prepared_count": len(prepared),
        "unavailable_count": len(unavailable),
    }
    atomic_write_bytes(
        cache_dir / "index.json",
        (json.dumps(record, indent=2) + "\n").encode("utf-8"),
    )
    if unavailable:
        raise ModelUnavailableError(
            "one or more models remain unavailable: "
            + "; ".join(f"{item['id']} ({item['reason']})" for item in unavailable)
        )
    return record
