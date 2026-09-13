#!/usr/bin/env python3
"""Explicit installer for version-isolated reader profiles (T33).

Creates isolated environments for a fixed allowlisted reader family/version
and writes an owner-controlled profile with interpreter identity and artifact
digest. Network is used only because the operator invoked setup. Inspection
and replay never call this helper.
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

REPO_ROOT = Path(__file__).resolve().parent.parent
NATIVE_DIR = REPO_ROOT / "native"
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from inkflip.profiles.models import (  # noqa: E402
    ProfileBlockedError,
    ProfileError,
    ReaderProfile,
    UntrustedProfileError,
)
from inkflip.profiles.registry import (  # noqa: E402
    ALLOWED_READERS,
    BUNDLED_WRAPPERS,
    compute_profile_sha256,
    file_sha256,
    save_profile,
    validate_profile_name,
)


def _get_artifact_digest(python_exe: Path, package_name: str) -> str | None:
    code = (
        "import importlib.metadata, hashlib\n"
        "from pathlib import Path\n"
        f"dist = importlib.metadata.distribution({package_name!r})\n"
        "p = getattr(dist, '_path', None)\n"
        "meta = Path(p) / 'METADATA' if p else None\n"
        "print(hashlib.sha256(meta.read_bytes()).hexdigest() if meta and meta.is_file() else '')\n"
    )
    try:
        proc = subprocess.run(
            [str(python_exe), "-c", code],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except Exception:
        return None
    out = proc.stdout.strip()
    return out or None


def install_pypdf_profile(
    name: str,
    version: str,
    profile_dir: Path,
    *,
    offline: bool = False,
) -> ReaderProfile:
    venv_dir = profile_dir / name / "venv"
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    uv_path = shutil.which("uv")
    if uv_path:
        cmd_venv = [uv_path, "venv", str(venv_dir)]
    else:
        cmd_venv = [sys.executable, "-m", "venv", str(venv_dir)]
    try:
        subprocess.run(cmd_venv, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise ProfileError(
            f"Failed to create virtual environment for profile {name!r}: {exc.stderr}"
        ) from exc

    venv_python = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not venv_python.is_file():
        raise ProfileBlockedError(f"Virtualenv python not found at {venv_python}")

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
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(venv_dir.parent, ignore_errors=True)
        raise ProfileBlockedError(
            f"missing version install blocks that profile: failed to install {req}: "
            f"{(exc.stderr or '').strip()}"
        ) from exc

    probe = (
        "import pypdf, sys\n"
        "print(getattr(pypdf, '__version__', 'unknown'))\n"
        "print(sys.version)\n"
    )
    try:
        proc = subprocess.run(
            [str(venv_python), "-c", probe],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        lines = proc.stdout.strip().splitlines()
        installed_version = lines[0] if lines else "unknown"
        python_ver = lines[1] if len(lines) > 1 else sys.version
    except Exception as exc:
        raise ProfileBlockedError(f"Failed to probe installed pypdf in {venv_python}: {exc}") from exc
    if installed_version != version:
        raise ProfileBlockedError(
            f"Installed pypdf version mismatch (expected {version}, got {installed_version})"
        )

    wrapper_path = BUNDLED_WRAPPERS["pypdf"]
    if not wrapper_path.is_file():
        raise ProfileError(f"Worker wrapper not found at {wrapper_path}")
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw_data = {
        "name": name,
        "reader": "pypdf",
        "version": installed_version,
        "executable": str(venv_python),
        "platform": platform.platform(),
        "python_version": python_ver,
        "artifact_digest": _get_artifact_digest(venv_python, "pypdf"),
        "wrapper_path": str(wrapper_path.resolve()),
        "wrapper_sha256": file_sha256(wrapper_path),
        "created_at": created_at,
    }
    digest = compute_profile_sha256(raw_data)
    profile = ReaderProfile(
        name=name,
        reader="pypdf",
        version=installed_version,
        executable=venv_python,
        platform=raw_data["platform"],
        python_version=python_ver,
        artifact_digest=raw_data["artifact_digest"],
        profile_sha256=digest,
        wrapper_path=wrapper_path.resolve(),
        wrapper_sha256=raw_data["wrapper_sha256"],
        created_at=created_at,
    )
    save_profile(profile, base_dir=profile_dir)
    return profile


def install_pdfjs_profile(name: str, version: str, profile_dir: Path) -> ReaderProfile:
    node_path = shutil.which("node")
    if not node_path:
        raise ProfileBlockedError("missing version install blocks that profile: node executable not found")
    wrapper_path = BUNDLED_WRAPPERS["pdfjs-node"]
    if not wrapper_path.is_file():
        raise ProfileBlockedError(f"Node wrapper not found at {wrapper_path}")
    node_dir = wrapper_path.parent
    if not (node_dir / "node_modules" / "pdfjs-dist").exists():
        raise ProfileBlockedError(
            "missing version install blocks that profile: pdfjs-dist is not installed "
            f"in {node_dir}"
        )
    try:
        proc = subprocess.run(
            [node_path, str(wrapper_path)],
            input=json.dumps({"action": "describe"}),
            capture_output=True,
            text=True,
            check=False,
            timeout=30.0,
            shell=False,
        )
        res = json.loads(proc.stdout)
        if not res.get("ok", True) and res.get("error"):
            raise ProfileBlockedError(f"Failed to probe node wrapper: {res.get('error')}")
        reader_info = res.get("reader") or {}
        actual_ver = reader_info.get("version") or res.get("pdfjs_version")
    except ProfileBlockedError:
        raise
    except Exception as exc:
        raise ProfileBlockedError(f"Failed to probe node wrapper: {exc}") from exc
    if actual_ver and version and actual_ver != version:
        raise ProfileBlockedError(
            f"Installed pdf.js version mismatch (expected {version}, got {actual_ver})"
        )
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    node_version = subprocess.run(
        [node_path, "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    raw_data = {
        "name": name,
        "reader": "pdfjs-node",
        "version": actual_ver or version,
        "executable": str(Path(node_path).resolve()),
        "platform": platform.platform(),
        "python_version": f"Node {node_version}",
        "artifact_digest": None,
        "wrapper_path": str(wrapper_path.resolve()),
        "wrapper_sha256": file_sha256(wrapper_path),
        "created_at": created_at,
    }
    digest = compute_profile_sha256(raw_data)
    profile = ReaderProfile(
        name=name,
        reader="pdfjs-node",
        version=raw_data["version"],
        executable=Path(node_path).resolve(),
        platform=raw_data["platform"],
        python_version=raw_data["python_version"],
        artifact_digest=None,
        profile_sha256=digest,
        wrapper_path=wrapper_path.resolve(),
        wrapper_sha256=raw_data["wrapper_sha256"],
        created_at=created_at,
    )
    save_profile(profile, base_dir=profile_dir)
    return profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install version-isolated reader profile (T33)")
    parser.add_argument("--name", required=True, help="Safe profile identifier (e.g. before, after)")
    parser.add_argument("--reader", default="pypdf", help="Allowlisted reader family (default: pypdf)")
    parser.add_argument("--version", required=True, help="Pinned package version (e.g. 5.9.0)")
    parser.add_argument("--profile-dir", default="profiles", help="Profiles directory")
    parser.add_argument("--offline", action="store_true", help="Do not make network requests")
    args = parser.parse_args(argv)

    try:
        validate_profile_name(args.name)
    except UntrustedProfileError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 2
    if args.reader not in ALLOWED_READERS:
        sys.stderr.write(
            f"Error: Untrusted reader {args.reader!r}. Allowlisted: {sorted(ALLOWED_READERS)}\n"
        )
        return 2

    profile_dir = Path(args.profile_dir)
    if not profile_dir.is_absolute():
        profile_dir = (Path.cwd() / profile_dir).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        if args.reader == "pypdf":
            profile = install_pypdf_profile(
                args.name, args.version, profile_dir, offline=args.offline
            )
        elif args.reader == "pdfjs-node":
            profile = install_pdfjs_profile(args.name, args.version, profile_dir)
        else:
            sys.stderr.write(f"Error: Unsupported reader: {args.reader}\n")
            return 2
    except ProfileBlockedError as exc:
        sys.stderr.write(f"Profile installation blocked: {exc}\n")
        return 3
    except ProfileError as exc:
        sys.stderr.write(f"Profile error: {exc}\n")
        return 2

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
