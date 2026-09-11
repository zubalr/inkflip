#!/usr/bin/env python3
"""Install verified Beads locally on Linux amd64; never alter machine settings."""
import hashlib
import io
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request

VERSION = "1.2.2"
URL = f"https://github.com/gastownhall/beads/releases/download/v{VERSION}/beads_{VERSION}_linux_amd64.tar.gz"
DIGEST = "8140098a51d3b81d5548d1c5e6db1a2d9930e5d141efe2a4bff7d079c4d321e8"
ROOT = Path(__file__).resolve().parents[1]


def install() -> Path:
    destination = ROOT / ".tools/bin/bd"
    existing = shutil.which("bd")
    if destination.is_file():
        existing = str(destination)
    if existing:
        result = subprocess.run([existing, "version"], text=True, capture_output=True, check=True)
        if result.stdout.startswith(f"bd version {VERSION} "):
            return Path(existing)
    if (platform.system(), platform.machine()) != ("Linux", "x86_64"):
        raise ValueError("Install Beads 1.2.2 for this host from the official release; only Linux amd64 is bundled here")
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != DIGEST:
        raise ValueError("Official Beads archive checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = [m for m in archive.getmembers() if Path(m.name).name == "bd" and m.isfile()]
        if len(members) != 1:
            raise ValueError("Expected exactly one regular bd binary in the archive")
        binary = archive.extractfile(members[0]).read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    temporary.write_bytes(binary)
    temporary.chmod(0o755)
    os.replace(temporary, destination)
    subprocess.run([str(destination), "version"], check=True)
    return destination


if __name__ == "__main__":
    try:
        result = install()
        print(f"Beads ready: {result}\nAdd this directory to PATH: {result.parent}")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Beads bootstrap failed: {error}")
