"""Data models and exceptions for version-isolated reader profiles (T33)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ProfileError(Exception):
    """Base exception for reader profile failures."""
    pass


class ProfileNotFoundError(ProfileError):
    """Raised when a named reader profile does not exist."""
    pass


class UntrustedProfileError(ProfileError):
    """Raised when an untrusted profile path, command, or reader is requested."""
    pass


class ProfileBlockedError(ProfileError):
    """Raised when a profile cannot run because its version/executable is missing."""
    pass


@dataclass(frozen=True)
class ReaderProfile:
    """Installed, allowlisted reader profile configuration."""

    name: str
    reader: str
    version: str
    executable: Path
    platform: str
    python_version: str
    artifact_digest: str | None
    profile_sha256: str
    wrapper_path: Path
    created_at: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "reader_profile",
            "schema_version": "1.0.0",
            "name": self.name,
            "reader": self.reader,
            "version": self.version,
            "executable": str(self.executable),
            "platform": self.platform,
            "python_version": self.python_version,
            "artifact_digest": self.artifact_digest,
            "profile_sha256": self.profile_sha256,
            "wrapper_path": str(self.wrapper_path),
            "created_at": self.created_at,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReaderProfile:
        return cls(
            name=data["name"],
            reader=data["reader"],
            version=data["version"],
            executable=Path(data["executable"]),
            platform=data.get("platform", ""),
            python_version=data.get("python_version", ""),
            artifact_digest=data.get("artifact_digest"),
            profile_sha256=data.get("profile_sha256", ""),
            wrapper_path=Path(data["wrapper_path"]),
            created_at=data.get("created_at", ""),
            extra=data.get("extra", {}),
        )
