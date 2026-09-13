"""Allowlisted, digest-verified model cache preparation."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from inkflip.runtime.artifacts import atomic_write_bytes

ALLOWED_KINDS = {"inkflip_model_manifest"}
ALLOWED_PURPOSES = {"ocr_language_model", "tessdata", "generic"}


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
    for entry in models:
        if not isinstance(entry, dict):
            raise ModelPrepareError("Each model entry must be an object")
        model_id = entry.get("id")
        digest = entry.get("sha256")
        source = entry.get("path")
        purpose = entry.get("purpose", "generic")
        if not isinstance(model_id, str) or not model_id:
            raise ModelPrepareError("Model id is required")
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
        destination = cache_dir / model_id / source_path.name
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
