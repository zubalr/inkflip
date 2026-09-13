"""Adapter for invoking isolated reader profiles via subprocess (T33)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from inkflip.profiles.models import ProfileError, ReaderProfile


class ProfileAdapter:
    """Invokes a version-isolated reader profile in its own interpreter."""

    def __init__(self, profile: ReaderProfile):
        self.profile = profile

    def describe(self) -> dict[str, Any]:
        """Query the reader manifest and environment identity from the isolated interpreter."""
        if self.profile.reader == "pypdf":
            argv = [
                str(self.profile.executable),
                str(self.profile.wrapper_path),
                "--describe",
            ]
            try:
                proc = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30.0,
                )
                return json.loads(proc.stdout)
            except subprocess.CalledProcessError as e:
                raise ProfileError(f"Profile describe failed: {e.stderr.strip()}") from e
            except Exception as e:
                raise ProfileError(f"Failed to execute profile describe: {e}") from e

        elif self.profile.reader == "pdfjs-node":
            argv = [
                str(self.profile.executable),
                str(self.profile.wrapper_path),
            ]
            try:
                proc = subprocess.run(
                    argv,
                    input=json.dumps({"action": "describe"}),
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30.0,
                )
                res = json.loads(proc.stdout)
                if not res.get("ok"):
                    raise ProfileError(f"Node profile describe error: {res.get('error')}")
                return res
            except Exception as e:
                raise ProfileError(f"Failed to execute node profile describe: {e}") from e

        raise ProfileError(f"Unsupported profile reader: {self.profile.reader}")

    def extract(
        self,
        source_path: Path,
        pages: list[int] | None = None,
    ) -> dict[str, Any]:
        """Extract text from PDF using the isolated profile interpreter."""
        if not source_path.is_file():
            raise ProfileError(f"Source PDF does not exist: {source_path}")

        if self.profile.reader == "pypdf":
            argv = [
                str(self.profile.executable),
                str(self.profile.wrapper_path),
                "--extract",
                "--source",
                str(source_path.resolve()),
            ]
            if pages is not None:
                argv.extend(["--pages", ",".join(str(p) for p in pages)])

            try:
                proc = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60.0,
                )
                data = json.loads(proc.stdout)
                if not data.get("ok", True):
                    raise ProfileError(f"Extraction failed: {data.get('error')}")
                return data
            except subprocess.CalledProcessError as e:
                raise ProfileError(f"Profile extract failed: {e.stderr.strip()}") from e
            except Exception as e:
                raise ProfileError(f"Failed to execute profile extract: {e}") from e

        elif self.profile.reader == "pdfjs-node":
            argv = [
                str(self.profile.executable),
                str(self.profile.wrapper_path),
            ]
            payload = {
                "action": "extract",
                "pdf_path": str(source_path.resolve()),
                "pages": pages or [0],
            }
            try:
                proc = subprocess.run(
                    argv,
                    input=json.dumps(payload),
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60.0,
                )
                data = json.loads(proc.stdout)
                if not data.get("ok", True):
                    raise ProfileError(f"Node extraction failed: {data.get('error')}")
                return data
            except Exception as e:
                raise ProfileError(f"Failed to execute node profile extract: {e}") from e

        raise ProfileError(f"Unsupported profile reader: {self.profile.reader}")
