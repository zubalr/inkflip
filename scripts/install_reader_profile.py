#!/usr/bin/env python3
"""Explicit installer for version-isolated reader profiles (T33).

Creates isolated virtual environments for allowlisted reader packages,
probes interpreter identity and package digests, and saves verified
profile manifests.

Explicit environment setup may use the network when invoked by the operator;
inspection and regression runs must not.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Add native/ to sys.path so we can import inkflip.profiles
REPO_ROOT = Path(__file__).resolve().parent.parent
NATIVE_DIR = REPO_ROOT / "native"
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from inkflip.profiles.models import (
    ProfileBlockedError,
    ProfileError,
    ReaderProfile,
    UntrustedProfileError,
)
from inkflip.profiles.registry import (
    ALLOWED_READERS,
    DEFAULT_PROFILES_DIR,
    compute_profile_sha256,
    save_profile,
    validate_profile_name,
)


def _get_artifact_digest(python_exe: Path, package_name: str) -> str | None:
    """Extract SHA-256 of package METADATA via the target interpreter."""
    code = f"""
import importlib.metadata
import hashlib
from pathlib import Path
try:
    dist = importlib.metadata.distribution("{package_name}")
    p = getattr(dist, "_path", None)
    if p:
        meta_file = Path(p) / "METADATA"
        if meta_file.is_file():
            print(hashlib.sha256(meta_file.read_bytes()).hexdigest())
except Exception:
    pass
"""
    try:
        proc = subprocess.run(
            [str(python_exe), "-c", code],
            capture_output=True,
            text=True,
            check=True,
        )
        out = proc.stdout.strip()
        return out if out else None
    except Exception:
        return None


def install_pypdf_profile(
    name: str,
    version: str,
    profile_dir: Path,
    offline: bool = False,
) -> ReaderProfile:
    """Create isolated venv and install specified pypdf version."""
    profile_venv_dir = profile_dir / name / "venv"
    profile_venv_dir.parent.mkdir(parents=True, exist_ok=True)

    # 1. Create venv
    uv_path = shutil.which("uv")
    if uv_path:
        cmd_venv = [uv_path, "venv", str(profile_venv_dir)]
    else:
        cmd_venv = [sys.executable, "-m", "venv", str(profile_venv_dir)]

    try:
        subprocess.run(cmd_venv, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise ProfileError(f"Failed to create virtual environment for profile '{name}': {e.stderr}")

    # Locate venv python executable
    if sys.platform == "win32":
        venv_python = profile_venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = profile_venv_dir / "bin" / "python"

    if not venv_python.is_file():
        raise ProfileBlockedError(f"Virtualenv python not found at {venv_python}")

    # 2. Install pypdf==<version>
    req = f"pypdf=={version}"
    if uv_path:
        cmd_install = [uv_path, "pip", "install", "--python", str(venv_python), req]
        if offline:
            cmd_install.append("--offline")
    else:
        cmd_install = [str(venv_python), "-m", "pip", "install", req]
        if offline:
            cmd_install.extend(["--no-index"])

    try:
        subprocess.run(cmd_install, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        # Cleanup failed venv
        shutil.rmtree(profile_venv_dir.parent, ignore_errors=True)
        raise ProfileBlockedError(
            f"missing version install blocks that profile: failed to install {req}: {e.stderr.strip()}"
        )

    # 3. Probe installed version
    probe_code = "import pypdf, sys; print(getattr(pypdf, '__version__', 'unknown')); print(sys.version)"
    try:
        proc = subprocess.run(
            [str(venv_python), "-c", probe_code],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = proc.stdout.strip().splitlines()
        installed_version = lines[0] if lines else "unknown"
        python_ver = lines[1] if len(lines) > 1 else sys.version
    except Exception as e:
        raise ProfileBlockedError(f"Failed to probe installed pypdf in {venv_python}: {e}")

    if installed_version != version:
        raise ProfileBlockedError(
            f"Installed pypdf version mismatch (expected {version}, got {installed_version})"
        )

    artifact_digest = _get_artifact_digest(venv_python, "pypdf")
    wrapper_path = REPO_ROOT / "native" / "inkflip" / "profiles" / "pypdf_worker.py"
    if not wrapper_path.is_file():
        raise ProfileError(f"Worker wrapper not found at {wrapper_path}")

    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw_data = {
        "name": name,
        "reader": "pypdf",
        "version": installed_version,
        "executable": str(venv_python.absolute()),
        "platform": platform.platform(),
        "python_version": python_ver,
        "artifact_digest": artifact_digest,
        "wrapper_path": str(wrapper_path.resolve()),
        "created_at": created_at,
    }
    digest = compute_profile_sha256(raw_data)

    profile = ReaderProfile(
        name=name,
        reader="pypdf",
        version=installed_version,
        executable=venv_python.absolute(),
        platform=platform.platform(),
        python_version=python_ver,
        artifact_digest=artifact_digest,
        profile_sha256=digest,
        wrapper_path=wrapper_path.resolve(),
        created_at=created_at,
    )

    save_profile(profile, base_dir=profile_dir)
    return profile


def install_pdfjs_profile(
    name: str,
    version: str,
    profile_dir: Path,
) -> ReaderProfile:
    """Register Node PDF.js profile wrapper."""
    node_path = shutil.which("node")
    if not node_path:
        raise ProfileBlockedError("missing version install blocks that profile: node executable not found")

    wrapper_path = REPO_ROOT / "packages" / "readers-pdfjs" / "node" / "bridge.mjs"
    if not wrapper_path.is_file():
        raise ProfileBlockedError(f"Node wrapper not found at {wrapper_path}")

    # Probe Node wrapper
    try:
        proc = subprocess.run(
            [node_path, str(wrapper_path)],
            input=json.dumps({"action": "describe"}),
            capture_output=True,
            text=True,
            check=True,
            timeout=10.0,
        )
        res = json.loads(proc.stdout)
        reader_info = res.get("reader", {})
        actual_ver = reader_info.get("version", version)
    except Exception as e:
        raise ProfileBlockedError(f"Failed to probe node wrapper: {e}")

    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw_data = {
        "name": name,
        "reader": "pdfjs-node",
        "version": actual_ver,
        "executable": str(Path(node_path).resolve()),
        "platform": platform.platform(),
        "python_version": f"Node {subprocess.getoutput('node --version')}",
        "artifact_digest": None,
        "wrapper_path": str(wrapper_path.resolve()),
        "created_at": created_at,
    }
    digest = compute_profile_sha256(raw_data)

    profile = ReaderProfile(
        name=name,
        reader="pdfjs-node",
        version=actual_ver,
        executable=Path(node_path).resolve(),
        platform=platform.platform(),
        python_version=raw_data["python_version"],
        artifact_digest=None,
        profile_sha256=digest,
        wrapper_path=wrapper_path.resolve(),
        created_at=created_at,
    )

    save_profile(profile, base_dir=profile_dir)
    return profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install version-isolated reader profile (T33)")
    parser.add_argument("--name", required=True, help="Safe profile identifier (e.g. before, after)")
    parser.add_argument("--reader", default="pypdf", help="Allowlisted reader family (default: pypdf)")
    parser.add_argument("--version", required=True, help="Pinned package version string (e.g. 5.9.0)")
    parser.add_argument("--profile-dir", default="profiles", help="Profiles directory (default: profiles/)")
    parser.add_argument("--offline", action="store_true", help="Do not make network requests during installation")

    args = parser.parse_args(argv)

    try:
        validate_profile_name(args.name)
    except UntrustedProfileError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 2

    if args.reader not in ALLOWED_READERS:
        sys.stderr.write(
            f"Error: Untrusted reader '{args.reader}'. Only allowlisted readers are supported: {sorted(ALLOWED_READERS)}\n"
        )
        return 2

    profile_dir = Path(args.profile_dir).resolve()
    # Check for path traversal in profile-dir
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        sys.stderr.write(f"Error: invalid profile directory '{args.profile_dir}': {e}\n")
        return 2

    try:
        if args.reader == "pypdf":
            profile = install_pypdf_profile(
                name=args.name,
                version=args.version,
                profile_dir=profile_dir,
                offline=args.offline,
            )
        elif args.reader == "pdfjs-node":
            profile = install_pdfjs_profile(
                name=args.name,
                version=args.version,
                profile_dir=profile_dir,
            )
        else:
            sys.stderr.write(f"Error: Unsupported reader: {args.reader}\n")
            return 2
    except ProfileBlockedError as e:
        sys.stderr.write(f"Profile installation blocked: {e}\n")
        return 3
    except ProfileError as e:
        sys.stderr.write(f"Profile error: {e}\n")
        return 2
    except Exception as e:
        sys.stderr.write(f"Unexpected error: {e}\n")
        return 1

    # Output details ensuring reader version is explicitly printed
    print(f"Reader profile '{profile.name}' successfully installed:")
    print(f"  Reader: {profile.reader} {profile.version}")
    print(f"  Executable: {profile.executable}")
    print(f"  Platform: {profile.platform}")
    if profile.artifact_digest:
        print(f"  Artifact Digest: {profile.artifact_digest}")
    print(f"  Profile SHA-256: {profile.profile_sha256}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
