"""Explicit version-isolated reader profiles (T33)."""

from .adapter import ProfileAdapter, offline_child_env
from .models import (
    ProfileBlockedError,
    ProfileError,
    ProfileNotFoundError,
    ReaderProfile,
    UntrustedProfileError,
)
from .registry import (
    ALLOWED_READERS,
    BUILTIN_PROFILE_NAMES,
    BUNDLED_WRAPPERS,
    compute_profile_sha256,
    default_profiles_dir,
    file_sha256,
    list_profiles,
    load_profile,
    save_profile,
    validate_profile_name,
)

__all__ = [
    "ALLOWED_READERS",
    "BUILTIN_PROFILE_NAMES",
    "BUNDLED_WRAPPERS",
    "ProfileAdapter",
    "ProfileBlockedError",
    "ProfileError",
    "ProfileNotFoundError",
    "ReaderProfile",
    "UntrustedProfileError",
    "compute_profile_sha256",
    "default_profiles_dir",
    "file_sha256",
    "list_profiles",
    "load_profile",
    "offline_child_env",
    "save_profile",
    "validate_profile_name",
]
