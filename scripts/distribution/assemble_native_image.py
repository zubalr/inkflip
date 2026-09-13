#!/usr/bin/env python3
"""Assemble the production native image build context.

Consumes ZCode's hash-verified third-party bundle (``.private/distribution/native-bundle``
plus ``release/`` stamps) and adds the Inkflip application wheel. Writes
``native/dist/``:

  wheels/*.whl              third-party + inkflip (hash-verified)
  requirements.lock         complete hashed lock the Dockerfile installs
  node/node-v*-linux-x64.tar.xz
  models/tessdata/eng.traineddata
  notices/                  license texts
  BUILD-CONTEXT.json        identities (platform/ABI, hashes, stamps)

Does not download. Does not modify ZCode's committed third-party
``release/native-requirements.lock`` (adding inkflip there would make
``scripts/check_distribution.py`` reject an unexpected package until the
shared ``config/distribution-manifest.json`` grows an app-wheel field).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / ".private" / "distribution" / "native-bundle"
DIST = ROOT / "native" / "dist"
RELEASE = ROOT / "release"
NATIVE = ROOT / "native"
PLATFORM = {
    "python_tag": "cp313",
    "abi_tag": "cp313",
    "arch": "x86_64",
    "platform": "linux x86_64 (glibc manylinux) — recorded contract reference",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str, code: int = 1) -> int:
    print(f"assemble_native_image: {message}", file=sys.stderr)
    return code


def _extract_zip_licenses(wheel: Path, dest: Path) -> list[dict]:
    copied: list[dict] = []
    with zipfile.ZipFile(wheel) as zf:
        for name in zf.namelist():
            lower = name.lower()
            if not (
                "/licenses/" in lower
                or lower.endswith("license")
                or lower.endswith("license.txt")
                or lower.endswith("licence")
                or "build_licenses/" in lower
            ):
                continue
            if name.endswith("/"):
                continue
            rel = Path(name).name
            # Keep BUILD_LICENSES and nested license paths.
            parts = Path(name).parts
            if "BUILD_LICENSES" in parts:
                idx = parts.index("BUILD_LICENSES")
                target = dest / "BUILD_LICENSES" / Path(*parts[idx + 1 :])
            elif "LICENSES" in parts:
                idx = parts.index("LICENSES")
                target = dest / "LICENSES" / Path(*parts[idx + 1 :])
            else:
                target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            data = zf.read(name)
            target.write_bytes(data)
            copied.append({"source": name, "bytes": len(data)})
    return copied


def build_inkflip_wheel(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["uv", "build", "--project", str(NATIVE), "--wheel", "--out-dir", str(out_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"uv build failed:\n{proc.stdout}\n{proc.stderr}")
    wheels = sorted(out_dir.glob("inkflip-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one inkflip wheel, found {wheels}")
    return wheels[0]


def install_image_notices(
    *,
    dist: Path,
    notices_dest: Path,
    node_stamp: dict,
    app_name: str,
    app_sha: str,
) -> dict:
    """Ship PDFium binary appendix, Node LICENSE, and application MIT in the image."""
    entries: list[dict] = []
    license_src = ROOT / "LICENSE"
    if license_src.is_file():
        dest = notices_dest / "inkflip-MIT.txt"
        shutil.copyfile(license_src, dest)
        entries.append(
            {
                "id": "inkflip-mit",
                "path": str(dest.relative_to(dist)),
                "sha256": sha256_file(dest),
                "bytes": dest.stat().st_size,
            }
        )

    wheels_dir = dist / "wheels"
    for wheel in sorted(wheels_dir.glob("pypdfium2-*.whl")):
        dest = notices_dest / "pypdfium2-binary"
        dest.mkdir(parents=True, exist_ok=True)
        extracted = _extract_zip_licenses(wheel, dest)
        pdfium_txt = dest / "BUILD_LICENSES" / "pdfium.txt"
        if not pdfium_txt.is_file():
            raise RuntimeError(f"pypdfium2 wheel {wheel.name} has no BUILD_LICENSES/pdfium.txt")
        entries.append(
            {
                "id": "pdfium-binary-appendix",
                "wheel": wheel.name,
                "path": str(pdfium_txt.relative_to(dist)),
                "sha256": sha256_file(pdfium_txt),
                "bytes": pdfium_txt.stat().st_size,
                "extracted": len(extracted),
            }
        )

    node_name = node_stamp["filename"]
    tarball = dist / "node" / node_name
    if tarball.is_file():
        import tarfile

        node_notice_dir = notices_dest / "node"
        node_notice_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tarball) as tf:
            members = [
                m
                for m in tf.getmembers()
                if m.isfile()
                and Path(m.name).name in {"LICENSE", "license", "LICENSE.md"}
                and "node_modules" not in Path(m.name).parts
            ]
            # Prefer the runtime root LICENSE (shortest path).
            members.sort(key=lambda m: (len(Path(m.name).parts), m.name))
            if not members:
                raise RuntimeError(f"Node tarball {node_name} has no LICENSE")
            member = members[0]
            extracted = tf.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"cannot extract {member.name} from {node_name}")
            data = extracted.read()
            dest = node_notice_dir / "LICENSE"
            dest.write_bytes(data)
            entries.append(
                {
                    "id": "node-license",
                    "source": member.name,
                    "path": str(dest.relative_to(dist)),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
            )

    index = {
        "kind": "inkflip-native-image-notices",
        "schema_version": "1.0.0",
        "application_wheel": {"filename": app_name, "sha256": app_sha},
        "required": ["inkflip-mit", "pdfium-binary-appendix", "node-license"],
        "entries": entries,
    }
    missing = [key for key in index["required"] if not any(e.get("id") == key for e in entries)]
    if missing:
        raise RuntimeError(f"image notices missing required entries: {missing}")
    (notices_dest / "INDEX.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return index
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["uv", "build", "--project", str(NATIVE), "--wheel", "--out-dir", str(out_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"uv build failed:\n{proc.stdout}\n{proc.stderr}")
    wheels = sorted(out_dir.glob("inkflip-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one inkflip wheel, found {wheels}")
    return wheels[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--bundle",
        type=Path,
        default=PRIVATE,
        help="prepared third-party context from prepare_native_bundle.py",
    )
    args = parser.parse_args()
    bundle = args.bundle
    manifest_path = RELEASE / "native-wheels.manifest.json"
    third_party_lock = RELEASE / "native-requirements.lock"
    node_stamp_path = RELEASE / "node" / "node.stamp.json"
    model_stamp_path = RELEASE / "models" / "model.stamp.json"

    if not manifest_path.is_file():
        return fail(f"missing {manifest_path}", 2)
    if not third_party_lock.is_file():
        return fail(f"missing {third_party_lock}", 2)
    if not bundle.is_dir():
        return fail(
            f"third-party bundle missing at {bundle}; run "
            "python3 scripts/distribution/prepare_native_bundle.py first "
            "(or copy the yielded ZCode context)",
            2,
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    node_stamp = json.loads(node_stamp_path.read_text(encoding="utf-8"))
    model_stamp = json.loads(model_stamp_path.read_text(encoding="utf-8"))

    wheels_src = bundle / "wheels"
    copied: list[dict] = []
    dest_wheels = DIST / "wheels"
    if dest_wheels.exists():
        shutil.rmtree(dest_wheels)
    dest_wheels.mkdir(parents=True, exist_ok=True)

    for entry in manifest.get("wheels") or []:
        name = entry["filename"]
        src = wheels_src / name
        if not src.is_file():
            return fail(f"prepared wheel missing: {src}")
        actual = sha256_file(src)
        expected = entry.get("verified_sha256") or entry.get("sha256")
        if actual != expected:
            return fail(f"wheel hash mismatch for {name}: manifest {expected} != file {actual}")
        dest = dest_wheels / name
        shutil.copy2(src, dest)
        copied.append(
            {
                "name": entry["name"],
                "filename": name,
                "sha256": actual,
                "bytes": dest.stat().st_size,
                "path": str(dest.relative_to(ROOT)),
            }
        )

    with tempfile.TemporaryDirectory(prefix="inkflip-app-wheel-") as raw:
        built = build_inkflip_wheel(Path(raw))
        app_name = built.name
        app_dest = dest_wheels / app_name
        shutil.copy2(built, app_dest)
    if not zipfile.is_zipfile(app_dest):
        return fail(f"built Inkflip artifact is not a wheel zip: {app_dest}")
    app_sha = sha256_file(app_dest)
    copied.append(
        {
            "name": "inkflip",
            "filename": app_name,
            "sha256": app_sha,
            "bytes": app_dest.stat().st_size,
            "path": str(app_dest.relative_to(ROOT)),
            "platform": "py3-none-any (pure Python; runtime ABI is the linux x86_64 third-party wheels)",
        }
    )

    lock_lines = [
        "# Complete hashed lock installed by build/native/Dockerfile.",
        "# Third-party pins match release/native-requirements.lock; inkflip is the application wheel.",
        f"# platform: {PLATFORM['platform']}",
    ]
    # Preserve ZCode third-party pins, then add inkflip.
    for line in third_party_lock.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lock_lines.append(stripped)
    lock_lines.append(f"inkflip==0.0.0 --hash=sha256:{app_sha}")
    (DIST / "requirements.lock").write_text("\n".join(lock_lines) + "\n", encoding="utf-8")

    node_name = node_stamp["filename"]
    node_src = bundle / "node" / node_name
    if not node_src.is_file():
        return fail(f"prepared Node tarball missing: {node_src}")
    if sha256_file(node_src) != node_stamp["sha256"]:
        return fail("Node tarball hash does not match release/node/node.stamp.json")
    node_dest_dir = DIST / "node"
    if node_dest_dir.exists():
        shutil.rmtree(node_dest_dir)
    node_dest_dir.mkdir(parents=True)
    shutil.copy2(node_src, node_dest_dir / node_name)
    shutil.copy2(node_stamp_path, node_dest_dir / "node.stamp.json")

    model_src = bundle / "models" / "tessdata" / "eng.traineddata"
    if not model_src.is_file():
        return fail(f"prepared model missing: {model_src}")
    if sha256_file(model_src) != model_stamp["sha256"]:
        return fail("model hash does not match release/models/model.stamp.json")
    model_dest = DIST / "models" / "tessdata"
    model_dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model_src, model_dest / "eng.traineddata")
    shutil.copy2(model_stamp_path, DIST / "models" / "model.stamp.json")

    notices_src = RELEASE / "notices"
    notices_dest = DIST / "notices"
    if notices_dest.exists():
        shutil.rmtree(notices_dest)
    if notices_src.is_dir():
        shutil.copytree(notices_src, notices_dest)
    else:
        notices_dest.mkdir(parents=True)
    notice_index = install_image_notices(
        dist=DIST,
        notices_dest=notices_dest,
        node_stamp=node_stamp,
        app_name=app_name,
        app_sha=app_sha,
    )

    identity = {
        "kind": "inkflip-native-image-context",
        "schema_version": "1.0.0",
        "platform": PLATFORM,
        "python": "3.13.15",
        "node": node_stamp,
        "model": {
            "path": "models/tessdata/eng.traineddata",
            "sha256": model_stamp["sha256"],
        },
        "wheels": copied,
        "requirements_lock": "native/dist/requirements.lock",
        "notices": notice_index,
        "dockerfile": "build/native/Dockerfile",
        "docker_platform": "linux/amd64",
        "note": "linux/arm64 checkout images are not this production hashed image",
    }
    (DIST / "BUILD-CONTEXT.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    app_stamp = {
        "name": "inkflip",
        "version": "0.0.0",
        "filename": app_name,
        "sha256": app_sha,
        "bytes": app_dest.stat().st_size,
        "wheel_tag": "py3-none-any",
        "lock_line": f"inkflip==0.0.0 --hash=sha256:{app_sha}",
        "assembled_path": "native/dist/wheels/" + app_name,
    }
    (DIST / "app.wheel.json").write_text(json.dumps(app_stamp, indent=2, sort_keys=True) + "\n")

    print(f"native image context assembled: {len(copied)} wheels")
    print(f"  {DIST}")
    print(f"  inkflip {app_name} sha256:{app_sha}")
    print(
        "  docker build --platform linux/amd64 -f build/native/Dockerfile "
        "-t inkflip-native:prod ."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
