"""Inkflip version-isolated reader profiles package (T33)."""
from __future__ import annotations

from inkflip.profiles.adapter import ProfileAdapter
from inkflip.profiles.models import (
    ProfileBlockedError,
    ProfileError,
    ProfileNotFoundError,
    ReaderProfile,
    UntrustedProfileError,
)
from inkflip.profiles.registry import (
    ALLOWED_READERS,
    DEFAULT_PROFILES_DIR,
    compute_profile_sha256,
    get_profile_path,
    list_profiles,
    load_profile,
    save_profile,
    validate_profile_name,
)

__all__ = [
    "ALLOWED_READERS",
    "DEFAULT_PROFILES_DIR",
    "ProfileAdapter",
    "ProfileBlockedError",
    "ProfileError",
    "ProfileNotFoundError",
    "ReaderProfile",
    "UntrustedProfileError",
    "compute_profile_sha256",
    "get_profile_path",
    "list_profiles",
    "load_profile",
    "save_profile",
    "validate_profile_name",
]
