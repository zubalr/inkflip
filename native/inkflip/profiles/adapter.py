"""Invoke a verified isolated reader profile without a shell (T33)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from inkflip.profiles.models import ProfileError, ReaderProfile

_OFFLINE_ENV_BLOCKLIST = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "all_proxy",
    "FTP_PROXY",
    "ftp_proxy",
)


def offline_child_env() -> dict[str, str]:
    env = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "NO_PROXY": "*",
        "no_proxy": "*",
    }
    path = os.environ.get("PATH")
    if path:
        env["PATH"] = path
    for key, value in os.environ.items():
        if key in _OFFLINE_ENV_BLOCKLIST:
            continue
        if key.startswith("INKFLIP_"):
            env[key] = value
    return env


class ProfileAdapter:
    """Runs the bundled wrapper under the profile's recorded interpreter."""

    def __init__(self, profile: ReaderProfile):
        self.profile = profile

    def _argv(self) -> list[str]:
        return [str(self.profile.executable), str(self.profile.wrapper_path)]

    def _run(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                self._argv(),
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
                env=offline_child_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ProfileError(f"Profile worker timed out after {timeout}s") from exc
        except OSError as exc:
            raise ProfileError(f"Failed to execute profile worker: {exc}") from exc
        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except json.JSONDecodeError as exc:
            raise ProfileError(
                f"Profile worker returned non-JSON (exit {proc.returncode}): {exc}"
            ) from exc
        if proc.returncode != 0 and not data.get("ok"):
            detail = data.get("error") or (proc.stderr or "").strip() or f"exit {proc.returncode}"
            raise ProfileError(f"Profile worker failed: {detail}")
        if data.get("ok") is False:
            raise ProfileError(f"Profile worker failed: {data.get('error')}")
        return data

    def describe(self) -> dict[str, Any]:
        data = self._run({"action": "describe"}, timeout=30.0)
        recorded = data.get("reader") or {}
        actual_version = recorded.get("version") or data.get("pypdf_version")
        if actual_version and actual_version != self.profile.version:
            raise ProfileError(
                f"Installed runtime identity mismatch: profile {self.profile.version}, "
                f"worker {actual_version}"
            )
        return data

    def extract(self, source_path: Path, pages: list[int] | None = None) -> dict[str, Any]:
        if not source_path.is_file():
            raise ProfileError(f"Source PDF does not exist: {source_path}")
        return self._run(
            {
                "action": "extract",
                "source": str(source_path),
                "pdf_path": str(source_path),
                "pages": list(pages or []),
            },
            timeout=120.0,
        )
