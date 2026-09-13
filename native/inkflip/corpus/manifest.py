"""Inkflip corpus manifest validation and path containment (T32).

Enforces:
- Schema validation against inkflip.schema.json (CorpusManifest)
- Root path containment and rejection of symlinks / directory traversal
- Source file hashing (SHA-256) matching manifest declarations
- Preservation of distinct keys even when filenames collide
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inkflip.contracts import core


class CorpusError(Exception):
    """Base exception for corpus manifest, containment, or runtime errors."""
    pass


class ManifestValidationError(CorpusError):
    """Raised when the manifest JSON violates syntax or schema."""
    pass


class ContainmentError(CorpusError):
    """Raised when a path escapes the root, is a symlink, or traverses directories."""
    pass


class IntegrityError(CorpusError):
    """Raised when source file bytes differ from declared SHA-256."""
    pass


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
) -> tuple[dict[str, Any], list[CorpusEntry]]:
    """Load corpus manifest, validate schema, enforce containment and verify source hashes.

    Returns (raw_manifest_dict, list_of_validated_corpus_entries).
    """
    if not manifest_path.is_file():
        raise ManifestValidationError(f"Manifest file not found: {manifest_path}")

    try:
        raw_bytes = manifest_path.read_bytes()
        manifest_data = core.loads_strict(raw_bytes)
        core.validate(manifest_data)
    except core.ContractError as e:
        if getattr(e, "code", None) == "PATH":
            raise ContainmentError(f"Containment check failed: {e}") from e
        raise ManifestValidationError(f"Invalid corpus manifest: {e}") from e
    except Exception as e:
        raise ManifestValidationError(f"Invalid corpus manifest: {e}") from e

    if manifest_data.get("kind") != "corpus_manifest":
        raise ManifestValidationError(
            f"Expected kind 'corpus_manifest', got '{manifest_data.get('kind')}'"
        )

    # Reject symlinked source root
    if source_root.is_symlink() or os.path.islink(source_root):
        raise ContainmentError(f"Source root cannot be a symlink: {source_root}")

    # Validate source_root
    source_root = source_root.resolve()
    if not source_root.exists() or not source_root.is_dir():
        raise ContainmentError(f"Source root does not exist or is not a directory: {source_root}")

    # Check root policy
    policy = manifest_data.get("source_root_policy")
    if policy != "explicit_local_root_no_symlinks":
        raise ManifestValidationError(f"Unsupported source_root_policy: '{policy}'")

    entries_data = manifest_data.get("entries", [])
    seen_keys: set[str] = set()
    entries: list[CorpusEntry] = []

    for entry_dict in entries_data:
        key = entry_dict.get("key")
        if not key or not isinstance(key, str):
            raise ManifestValidationError("Corpus entry must declare a valid string 'key'")

        if key in seen_keys:
            raise ManifestValidationError(f"Duplicate corpus entry key: '{key}'")
        seen_keys.add(key)

        rel_path_str = entry_dict.get("source_path")
        if not rel_path_str or not isinstance(rel_path_str, str):
            raise ManifestValidationError(f"Entry '{key}': source_path missing or not a string")

        rel_path = Path(rel_path_str)
        if rel_path.is_absolute():
            raise ContainmentError(f"Entry '{key}': absolute source_path is forbidden: '{rel_path_str}'")

        # Check for directory traversal components
        if ".." in rel_path.parts:
            raise ContainmentError(f"Entry '{key}': traversal ('..') is forbidden: '{rel_path_str}'")

        full_path = source_root / rel_path

        # Symlink check on full path and each component
        curr = source_root
        for part in rel_path.parts:
            curr = curr / part
            if curr.is_symlink():
                raise ContainmentError(f"Entry '{key}': symlink path forbidden: '{curr}'")

        if not full_path.exists() or not full_path.is_file():
            raise ContainmentError(f"Entry '{key}': source file does not exist or is not a file: '{full_path}'")

        # Containment check: must resolve within source_root
        resolved_full = full_path.resolve()
        try:
            resolved_full.relative_to(source_root)
        except ValueError:
            raise ContainmentError(f"Entry '{key}': path escapes source root: '{rel_path_str}'")

        # Check hash
        declared_sha256 = entry_dict.get("sha256")
        if not declared_sha256:
            raise ManifestValidationError(f"Entry '{key}': sha256 is required")

        actual_sha256 = hashlib.sha256(full_path.read_bytes()).hexdigest()
        if actual_sha256 != declared_sha256:
            raise IntegrityError(
                f"Entry '{key}': SHA-256 mismatch for '{rel_path_str}' "
                f"(expected {declared_sha256}, got {actual_sha256})"
            )

        entries.append(
            CorpusEntry(
                key=key,
                source_path=rel_path_str,
                resolved_path=resolved_full,
                sha256=actual_sha256,
                group_id=entry_dict.get("group_id"),
                pages=entry_dict.get("pages"),
                ocr_pages=entry_dict.get("ocr_pages"),
            )
        )

    return manifest_data, entries
