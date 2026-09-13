"""Corpus manifest validation with root containment and no symlink escape (T32)."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inkflip.contracts import core


class CorpusError(Exception):
    """Base exception for corpus manifest, containment, or runtime errors."""


class ManifestValidationError(CorpusError):
    """Raised when the manifest JSON violates syntax or schema."""


class ContainmentError(CorpusError):
    """Raised when a path escapes the root, is a symlink, or traverses directories."""


class IntegrityError(CorpusError):
    """Raised when source file bytes differ from declared SHA-256."""


@dataclass(frozen=True)
class CorpusEntry:
    key: str
    source_path: str
    resolved_path: Path
    sha256: str
    group_id: str | None = None
    pages: list[int] | None = None
    ocr_pages: list[int] | None = None


def load_and_validate_manifest(
    manifest_path: Path,
    source_root: Path,
) -> tuple[dict[str, Any], list[CorpusEntry], str]:
    if not manifest_path.is_file():
        raise ManifestValidationError(f"Manifest file not found: {manifest_path}")
    raw_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        manifest_data = core.loads_strict(raw_bytes)
        core.validate(manifest_data)
    except core.ContractError as exc:
        if getattr(exc, "code", None) == "PATH":
            raise ContainmentError(f"Containment check failed: {exc}") from exc
        raise ManifestValidationError(f"Invalid corpus manifest: {exc}") from exc

    if manifest_data.get("kind") != "corpus_manifest":
        raise ManifestValidationError(
            f"Expected kind 'corpus_manifest', got {manifest_data.get('kind')!r}"
        )
    if source_root.is_symlink() or os.path.islink(source_root):
        raise ContainmentError(f"Source root cannot be a symlink: {source_root}")
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise ContainmentError(f"Source root does not exist or is not a directory: {source_root}")
    if manifest_data.get("source_root_policy") != "explicit_local_root_no_symlinks":
        raise ManifestValidationError(
            f"Unsupported source_root_policy: {manifest_data.get('source_root_policy')!r}"
        )

    seen_keys: set[str] = set()
    entries: list[CorpusEntry] = []
    for entry_dict in manifest_data.get("entries", []):
        key = entry_dict.get("key")
        if not key or not isinstance(key, str):
            raise ManifestValidationError("Corpus entry must declare a valid string 'key'")
        if key in seen_keys:
            raise ManifestValidationError(f"Duplicate corpus entry key: {key!r}")
        seen_keys.add(key)
        rel_path_str = entry_dict.get("source_path")
        if not rel_path_str or not isinstance(rel_path_str, str):
            raise ManifestValidationError(f"Entry {key!r}: source_path missing or not a string")
        rel_path = Path(rel_path_str)
        if rel_path.is_absolute():
            raise ContainmentError(f"Entry {key!r}: absolute source_path is forbidden: {rel_path_str!r}")
        if ".." in rel_path.parts:
            raise ContainmentError(f"Entry {key!r}: traversal ('..') is forbidden: {rel_path_str!r}")
        current = source_root
        for part in rel_path.parts:
            current = current / part
            if current.is_symlink() or os.path.islink(current):
                raise ContainmentError(f"Entry {key!r}: symlink path forbidden: {current}")
        if not current.is_file():
            raise ContainmentError(
                f"Entry {key!r}: source file does not exist or is not a file: {current}"
            )
        resolved_full = current.resolve()
        try:
            resolved_full.relative_to(source_root)
        except ValueError as exc:
            raise ContainmentError(f"Entry {key!r}: path escapes source root: {rel_path_str!r}") from exc
        declared = entry_dict.get("sha256")
        actual = hashlib.sha256(current.read_bytes()).hexdigest()
        if actual != declared:
            raise IntegrityError(
                f"Entry {key!r}: SHA-256 mismatch for {rel_path_str!r} "
                f"(expected {declared}, got {actual})"
            )
        entries.append(
            CorpusEntry(
                key=key,
                source_path=rel_path_str,
                resolved_path=resolved_full,
                sha256=actual,
                group_id=entry_dict.get("group_id"),
                pages=entry_dict.get("pages"),
                ocr_pages=entry_dict.get("ocr_pages"),
            )
        )
    return manifest_data, entries, manifest_sha256
