"""Trusted named-profile registry, containment, and identity verification (T33)."""
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
_SHELL_META = set(';&|`$<>\n\r')
REPO_ROOT = Path(__file__).resolve().parents[3]
NATIVE_DIR = Path(__file__).resolve().parents[2]
BUNDLED_WRAPPERS: dict[str, Path] = {
    "pypdf": Path(__file__).resolve().parent / "pypdf_worker.py",
    "pdfjs-node": REPO_ROOT / "packages" / "readers-pdfjs" / "node" / "bridge.mjs",
}
BUILTIN_PROFILE_NAMES: frozenset[str] = frozenset(
    {"native-default", "native", "desktop", "mobile"}
)


def default_profiles_dir() -> Path:
    env = os.environ.get("INKFLIP_PROFILES_DIR")
    if env:
        return Path(env)
    return REPO_ROOT / "profiles"


def validate_profile_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise UntrustedProfileError(
            f"Untrusted profile name: {name!r}. Must match ^[a-zA-Z0-9_-]{{1,64}}$"
        )
    if name in BUILTIN_PROFILE_NAMES:
        raise UntrustedProfileError(
            f"Profile name {name!r} is reserved for built-in execution profiles"
        )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_profile_sha256(data: dict[str, Any]) -> str:
    canonical_keys = (
        "name",
        "reader",
        "version",
        "executable",
        "platform",
        "python_version",
        "artifact_digest",
        "wrapper_path",
        "wrapper_sha256",
    )
    subset = {key: data.get(key) for key in canonical_keys}
    serialized = json.dumps(subset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _refuse_shell_injection(executable: str) -> None:
    if any(ch in executable for ch in _SHELL_META):
        raise UntrustedProfileError(
            f"Untrusted command/executable path: {executable!r}"
        )


def _require_bundled_wrapper(reader: str, wrapper_path: Path) -> Path:
    expected = BUNDLED_WRAPPERS.get(reader)
    if expected is None or not expected.is_file():
        raise ProfileError(f"Bundled wrapper missing for reader {reader!r}")
    resolved = wrapper_path.resolve()
    if resolved != expected.resolve():
        raise UntrustedProfileError(
            f"Untrusted wrapper path {wrapper_path}; only bundled adapters are allowed"
        )
    return resolved


def load_profile(name: str, base_dir: Path | None = None) -> ReaderProfile:
    """Load a trusted *named* installed profile. Paths and commands are refused."""
    if isinstance(name, Path) or (isinstance(name, str) and name.endswith(".json")):
        raise UntrustedProfileError(
            "Profile path/command refused; select an installed profile name"
        )
    if isinstance(name, str) and ("/" in name or "\\" in name or name.startswith(".")):
        raise UntrustedProfileError(
            "Profile path/command refused; select an installed profile name"
        )
    validate_profile_name(name)
    root = (base_dir or default_profiles_dir()).resolve()
    profile_path = (root / f"{name}.json").resolve()
    try:
        profile_path.relative_to(root)
    except ValueError as exc:
        raise UntrustedProfileError(f"Profile path escapes profiles root: {name}") from exc
    if not profile_path.is_file():
        raise ProfileNotFoundError(f"Profile {name!r} not found at {profile_path}")
    if profile_path.is_symlink() or os.path.islink(profile_path):
        raise UntrustedProfileError(f"Symlinked profile descriptors are refused: {profile_path}")

    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProfileError(f"Failed to read profile JSON {profile_path}: {exc}") from exc
    if data.get("kind") != "reader_profile":
        raise ProfileError(f"Expected kind 'reader_profile', got {data.get('kind')!r}")
    reader = data.get("reader")
    if reader not in ALLOWED_READERS:
        raise UntrustedProfileError(
            f"Untrusted reader {reader!r}. Allowlisted: {sorted(ALLOWED_READERS)}"
        )

    exe_str = data.get("executable")
    if not exe_str or not isinstance(exe_str, str):
        raise ProfileBlockedError("missing version install blocks that profile: executable not defined")
    _refuse_shell_injection(exe_str)
    exe_path = Path(exe_str)
    if not exe_path.is_file():
        raise ProfileBlockedError(
            f"missing version install blocks that profile: executable not found at {exe_path}"
        )
    if not os.access(exe_path, os.X_OK):
        raise ProfileBlockedError(
            f"missing version install blocks that profile: {exe_path} is not executable"
        )

    wrapper_str = data.get("wrapper_path")
    if not wrapper_str:
        raise ProfileError("Missing wrapper_path in profile")
    wrapper_path = _require_bundled_wrapper(reader, Path(wrapper_str))
    expected_wrapper = data.get("wrapper_sha256")
    actual_wrapper = file_sha256(wrapper_path)
    if expected_wrapper and expected_wrapper != actual_wrapper:
        raise ProfileError(
            f"Wrapper digest mismatch for {name}: expected {expected_wrapper}, got {actual_wrapper}"
        )

    expected_sha = compute_profile_sha256(data)
    stored_sha = data.get("profile_sha256")
    if stored_sha and stored_sha != expected_sha:
        raise ProfileError(
            f"Profile SHA-256 mismatch (expected {expected_sha}, got {stored_sha})"
        )
    data["profile_sha256"] = expected_sha
    data["wrapper_sha256"] = actual_wrapper
    return ReaderProfile.from_dict(data)


def save_profile(profile: ReaderProfile, base_dir: Path | None = None) -> Path:
    validate_profile_name(profile.name)
    root = (base_dir or default_profiles_dir()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    out_path = root / f"{profile.name}.json"
    if out_path.exists():
        raise ProfileError(f"Refusing to overwrite existing profile {out_path}")
    data = profile.to_dict()
    data["profile_sha256"] = compute_profile_sha256(data)
    out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return out_path


def list_profiles(base_dir: Path | None = None) -> list[ReaderProfile]:
    root = (base_dir or default_profiles_dir()).resolve()
    if not root.is_dir():
        return []
    profiles: list[ReaderProfile] = []
    for item in sorted(root.glob("*.json")):
        try:
            profiles.append(load_profile(item.stem, base_dir=root))
        except ProfileError:
            continue
    return profiles
