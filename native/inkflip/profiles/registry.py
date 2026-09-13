"""Reader profile registry, containment, and manifest resolution (T33)."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from inkflip.profiles.models import (
    ProfileBlockedError,
    ProfileError,
    ProfileNotFoundError,
    ReaderProfile,
    UntrustedProfileError,
)

ALLOWED_READERS: frozenset[str] = frozenset({"pypdf", "pdfjs-node"})
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
DEFAULT_PROFILES_DIR: Path = Path("profiles")


def validate_profile_name(name: str) -> None:
    """Ensure profile name is safe and does not contain traversals or metacharacters."""
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise UntrustedProfileError(
            f"Untrusted profile name: '{name}'. Must match ^[a-zA-Z0-9_-]{{1,64}}$"
        )


def compute_profile_sha256(data: dict[str, Any]) -> str:
    """Deterministic SHA-256 over profile identity fields."""
    canonical_keys = [
        "name",
        "reader",
        "version",
        "executable",
        "platform",
        "python_version",
        "artifact_digest",
        "wrapper_path",
    ]
    subset = {k: data.get(k) for k in canonical_keys if k in data}
    serialized = json.dumps(subset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def get_profile_path(name: str, base_dir: Path | None = None) -> Path:
    validate_profile_name(name)
    root = (base_dir or DEFAULT_PROFILES_DIR).resolve()
    target = (root / f"{name}.json").resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise UntrustedProfileError(f"Profile path escapes profiles root: '{name}'")
    return target


def load_profile(name_or_path: str | Path, base_dir: Path | None = None) -> ReaderProfile:
    """Load, validate, and verify an installed reader profile.
    
    Enforces:
    - Safe identifiers and containment (no directory traversal or shell commands)
    - Allowlisted reader family
    - Executable existence and runnable permissions (missing version blocks profile)
    - Digest verification
    """
    root = (base_dir or DEFAULT_PROFILES_DIR).resolve()

    if isinstance(name_or_path, str) and not name_or_path.endswith(".json"):
        validate_profile_name(name_or_path)
        profile_path = root / f"{name_or_path}.json"
        if not profile_path.is_file():
            raise ProfileNotFoundError(f"Profile '{name_or_path}' not found at {profile_path}")
    else:
        p = Path(name_or_path)
        if ".." in p.parts:
            raise UntrustedProfileError(f"Directory traversal forbidden in profile path: '{name_or_path}'")
        resolved = (root / p).resolve() if not p.is_absolute() else p.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            raise UntrustedProfileError(f"Profile path escapes profiles root: '{name_or_path}'")
        if not resolved.is_file():
            raise ProfileNotFoundError(f"Profile file not found: {resolved}")
        profile_path = resolved

    try:
        raw_text = profile_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except Exception as e:
        raise ProfileError(f"Failed to read profile JSON '{profile_path}': {e}") from e

    if data.get("kind") != "reader_profile":
        raise ProfileError(f"Expected kind 'reader_profile', got '{data.get('kind')}'")

    reader = data.get("reader")
    if reader not in ALLOWED_READERS:
        raise UntrustedProfileError(
            f"Untrusted reader '{reader}'. Only allowlisted readers are supported: {sorted(ALLOWED_READERS)}"
        )

    exe_str = data.get("executable")
    if not exe_str or not isinstance(exe_str, str):
        raise ProfileBlockedError("missing version install blocks that profile: executable not defined")

    # Untrusted command check: cannot contain shell piping, injection, quotes, or arguments
    if any(c in exe_str for c in [";", "|", "&", "`", "$", "\n", " ", "'", '"']):
        raise UntrustedProfileError(f"Untrusted command/executable path: '{exe_str}'")

    exe_path = Path(exe_str).absolute()
    if not exe_path.is_file():
        raise ProfileBlockedError(
            f"missing version install blocks that profile: executable not found at '{exe_path}'"
        )
    if not os.access(exe_path, os.X_OK):
        raise ProfileBlockedError(
            f"missing version install blocks that profile: '{exe_path}' is not executable"
        )

    wrapper_str = data.get("wrapper_path")
    if not wrapper_str:
        raise ProfileError("Missing wrapper_path in profile")
    wrapper_path = Path(wrapper_str).resolve()
    if not wrapper_path.is_file():
        raise ProfileBlockedError(f"Profile wrapper not found at '{wrapper_path}'")

    expected_sha256 = compute_profile_sha256(data)
    stored_sha256 = data.get("profile_sha256")
    if stored_sha256 and stored_sha256 != expected_sha256:
        # If sha256 was explicitly provided, it must match
        raise ProfileError(f"Profile SHA-256 mismatch (expected {expected_sha256}, got {stored_sha256})")

    data["profile_sha256"] = expected_sha256
    return ReaderProfile.from_dict(data)


def save_profile(profile: ReaderProfile, base_dir: Path | None = None) -> Path:
    """Save profile descriptor to JSON."""
    validate_profile_name(profile.name)
    root = (base_dir or DEFAULT_PROFILES_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    out_path = root / f"{profile.name}.json"
    data = profile.to_dict()
    data["profile_sha256"] = compute_profile_sha256(data)
    out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return out_path


def list_profiles(base_dir: Path | None = None) -> list[ReaderProfile]:
    """List all valid profiles in the profile directory."""
    root = (base_dir or DEFAULT_PROFILES_DIR).resolve()
    if not root.is_dir():
        return []
    profiles = []
    for item in sorted(root.glob("*.json")):
        try:
            p = load_profile(item, base_dir=root)
            profiles.append(p)
        except Exception:
            continue
    return profiles
