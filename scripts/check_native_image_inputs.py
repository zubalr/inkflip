#!/usr/bin/env python3
"""Fail closed when production native image inputs are missing or fake.

The hardened Dockerfile installs hashed wheels from ``native/dist`` using
``native/dist/requirements.lock`` (third-party T47 wheels **plus** the
Inkflip application wheel). Stamps under ``release/`` are identities;
empty directories, arbitrary ``.whl`` filenames, and a lock that merely
contains the substring ``inkflip`` are not a buildable image.

This script never downloads anything. A missing assembled context is an
error with the exact path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WHEEL_NAME_RE = re.compile(
    r"^(?P<dist>[A-Za-z0-9_]+)-(?P<version>[^-]+)-"
    r"(?P<py>cp313|py3)-(?P<abi>cp313|abi3|none)-"
    r"(?P<plat>.+)\.whl$"
)
FORBIDDEN_PLAT = re.compile(
    r"(?:aarch64|arm64|musllinux|macosx|win32|win_amd64|iphone|android|i686)",
    re.IGNORECASE,
)
LOCK_LINE_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.+-]+)==(?P<version>\S+)\s+--hash=sha256:(?P<sha>[0-9a-f]{64})\s*$"
)
PINNED_NODE = "22.23.2"
PINNED_PYTHON_TAG = "cp313"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _dist_root(root: Path) -> Path:
    return root / "native" / "dist"


def _wheel_dirs(dist: Path) -> list[Path]:
    nested = dist / "wheels"
    dirs = []
    if nested.is_dir():
        dirs.append(nested)
    if dist.is_dir():
        dirs.append(dist)
    return dirs


def _wheels(dist: Path) -> list[Path]:
    found: dict[str, Path] = {}
    for directory in _wheel_dirs(dist):
        for path in directory.glob("*.whl"):
            if path.is_file() and not path.is_symlink():
                found.setdefault(path.name, path)
    return sorted(found.values(), key=lambda p: p.name)


def _parse_lock(path: Path) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """Return {normalized_name: (version, sha256)} and problems."""
    problems: list[str] = []
    pins: dict[str, tuple[str, str]] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, [f"cannot read lock {path}: {exc}"]
    if "inkflip" in text and not re.search(r"^inkflip==", text, re.MULTILINE):
        problems.append(
            f"{path} mentions inkflip but does not pin inkflip==<version> --hash=sha256:…"
        )
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LOCK_LINE_RE.match(line)
        if not match:
            problems.append(f"{path} has a non-hashed or malformed pin: {line!r}")
            continue
        name = match.group("name").replace("_", "-").lower()
        pins[name] = (match.group("version"), match.group("sha"))
    return pins, problems


def _wheel_identity(path: Path) -> tuple[str | None, str | None, str | None, list[str]]:
    match = WHEEL_NAME_RE.match(path.name)
    if not match:
        return None, None, None, [f"wheel filename is not a PEP 427 tag: {path.name}"]
    dist = match.group("dist").replace("_", "-").lower()
    version = match.group("version")
    plat = match.group("plat")
    problems: list[str] = []
    if FORBIDDEN_PLAT.search(plat):
        problems.append(
            f"wrong architecture/ABI wheel (linux x86_64 glibc manylinux or any required): {path.name}"
        )
    if plat != "any" and "manylinux" not in plat:
        problems.append(f"wheel platform is not manylinux/any: {path.name}")
    if plat != "any" and "x86_64" not in plat:
        problems.append(f"wheel is not x86_64: {path.name}")
    if match.group("py") not in {PINNED_PYTHON_TAG, "py3"}:
        problems.append(f"wheel python tag is not cp313/py3: {path.name}")
    return dist, version, plat, problems


def _inspect_inkflip_wheel(path: Path) -> list[str]:
    problems: list[str] = []
    if not zipfile.is_zipfile(path):
        return [f"Inkflip wheel is not a zip archive: {path.name}"]
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if not any(n.endswith("entry_points.txt") for n in names):
            problems.append(f"{path.name} has no entry_points.txt")
        else:
            entry = next(n for n in names if n.endswith("entry_points.txt"))
            text = zf.read(entry).decode("utf-8", "replace")
            if "inkflip = inkflip.cli.main:main" not in text:
                problems.append(f"{path.name} entry_points.txt does not define the inkflip console script")
        if "inkflip/contracts/schema/inkflip.schema.json" not in names:
            problems.append(f"{path.name} is missing packaged schema inkflip/contracts/schema/inkflip.schema.json")
        if not any(n.startswith("inkflip/cli/main.py") for n in names):
            problems.append(f"{path.name} is missing inkflip/cli/main.py")
        compare = "inkflip/resources/packages/compare/node/bridge.mjs"
        if compare not in names:
            problems.append(f"{path.name} is missing packaged comparison entrypoint {compare}")
        if any(n.endswith(".so") for n in names):
            problems.append(f"{path.name} unexpectedly contains native extensions")
    return problems


def _nonempty_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(child.is_file() and child.stat().st_size > 0 for child in path.rglob("*"))


def problems_for(root: Path) -> list[str]:
    missing: list[str] = []
    dist = _dist_root(root)
    lock = dist / "requirements.lock"
    manifest_path = root / "release" / "native-wheels.manifest.json"
    node_stamp_path = root / "release" / "node" / "node.stamp.json"
    model_stamp_path = root / "release" / "models" / "model.stamp.json"
    notices = root / "release" / "notices"

    if not dist.is_dir():
        missing.append(f"missing assembled image context: {dist}")
        return missing

    wheels = _wheels(dist)
    if not wheels:
        missing.append(
            f"no .whl files in {dist} or {dist / 'wheels'} "
            "(an empty directory or a lock that only mentions wheels is not enough)"
        )

    if not lock.is_file() or lock.stat().st_size == 0:
        missing.append(
            f"missing complete hashed lock actually installed by the production Dockerfile: {lock}"
        )
        pins: dict[str, tuple[str, str]] = {}
    else:
        pins, lock_problems = _parse_lock(lock)
        missing.extend(lock_problems)
        if "inkflip" not in pins:
            missing.append(f"{lock} does not pin inkflip with a sha256 hash")

    wheel_by_name: dict[str, Path] = {}
    for wheel in wheels:
        dist_name, version, _plat, tag_problems = _wheel_identity(wheel)
        missing.extend(tag_problems)
        if dist_name is None:
            continue
        wheel_by_name[dist_name] = wheel
        digest = sha256_file(wheel)
        pin = pins.get(dist_name)
        if pin is None:
            missing.append(f"assembled wheel {wheel.name} is not in {lock}")
        else:
            pin_version, pin_sha = pin
            if version is not None and pin_version != version:
                missing.append(
                    f"lock version {dist_name}=={pin_version} does not match wheel {wheel.name}"
                )
            if pin_sha != digest:
                missing.append(
                    f"application/third-party hash mismatch for {wheel.name}: "
                    f"lock {pin_sha} != file {digest}"
                )
        if dist_name == "inkflip":
            missing.extend(_inspect_inkflip_wheel(wheel))

    if "inkflip" not in wheel_by_name:
        fake = [p.name for p in wheels if "inkflip" in p.name.lower()]
        if fake:
            missing.append(
                f"Inkflip application wheel missing: files {fake} are not a tagged "
                "inkflip-<version>-py3-none-any.whl with a real entry point"
            )
        else:
            missing.append(
                f"Inkflip application wheel missing under {dist} (third-party wheels are not a substitute)"
            )

    manifest = _load_json(manifest_path)
    if manifest is None:
        missing.append(f"missing or unreadable third-party wheels manifest: {manifest_path}")
    else:
        expected = []
        for entry in manifest.get("wheels") or []:
            if isinstance(entry, dict) and entry.get("name"):
                expected.append(str(entry["name"]).replace("_", "-").lower())
        closure = sorted(set(expected))
        if not closure:
            missing.append(f"{manifest_path} lists no third-party wheels (incomplete transitive closure)")
        for name in closure:
            if name == "inkflip":
                continue
            if name not in wheel_by_name:
                missing.append(f"incomplete transitive closure: missing wheel for {name}")
            if name not in pins:
                missing.append(f"incomplete transitive closure: {lock} has no hashed pin for {name}")

    node_stamp = _load_json(node_stamp_path)
    if node_stamp is None:
        missing.append(f"missing or unreadable Node stamp: {node_stamp_path}")
    else:
        for field in ("version", "sha256", "filename", "url"):
            if not node_stamp.get(field):
                missing.append(f"incorrect Node stamp: {node_stamp_path} lacks {field!r}")
        if node_stamp.get("version") and node_stamp.get("version") != PINNED_NODE:
            missing.append(
                f"incorrect Node stamp version {node_stamp.get('version')!r}; pinned toolchain is {PINNED_NODE}"
            )
        tarball_name = str(node_stamp.get("filename") or f"node-v{PINNED_NODE}-linux-x64.tar.xz")
        tarball = dist / "node" / tarball_name
        if not tarball.is_file():
            alt = dist / tarball_name
            tarball = alt if alt.is_file() else tarball
        if not tarball.is_file() or tarball.stat().st_size == 0:
            missing.append(
                f"Node runtime tarball missing from assembled context: {dist / 'node' / tarball_name} "
                f"(release/node stamp-only / empty placeholder is not a runnable runtime)"
            )
        elif node_stamp.get("sha256") and sha256_file(tarball) != node_stamp["sha256"]:
            missing.append(
                f"incorrect Node tarball hash: stamp {node_stamp['sha256']} != file {sha256_file(tarball)}"
            )

    model_stamp = _load_json(model_stamp_path)
    if model_stamp is None:
        missing.append(f"missing or unreadable model stamp: {model_stamp_path}")
    else:
        for field in ("name", "sha256"):
            if not model_stamp.get(field):
                missing.append(f"incorrect model stamp: {model_stamp_path} lacks {field!r}")
        model_file = dist / "models" / "tessdata" / "eng.traineddata"
        if not model_file.is_file() or model_file.stat().st_size == 0:
            missing.append(
                f"model data missing from assembled context: {model_file} "
                "(empty release/models placeholder is not model data)"
            )
        elif model_stamp.get("sha256") and sha256_file(model_file) != model_stamp["sha256"]:
            missing.append(
                f"incorrect model hash: stamp {model_stamp['sha256']} != file {sha256_file(model_file)}"
            )

    dist_notices = dist / "notices"
    index_path = dist_notices / "INDEX.json"
    if not index_path.is_file():
        missing.append(f"missing assembled notices index: {index_path}")
    else:
        index = _load_json(index_path)
        if index is None:
            missing.append(f"unreadable notices index: {index_path}")
        else:
            ids = {entry.get("id") for entry in index.get("entries") or [] if isinstance(entry, dict)}
            required_ids = ("inkflip-mit", "pdfium-binary-appendix", "node-license")
            tess_stamp_path = root / "release" / "tesseract" / "tesseract.stamp.json"
            if tess_stamp_path.is_file():
                required_ids = (*required_ids, "tesseract-apache")
            for required in required_ids:
                if required not in ids:
                    missing.append(f"image notices missing required {required}")
            pdfium = dist_notices / "pypdfium2-binary" / "BUILD_LICENSES" / "pdfium.txt"
            node_license = dist_notices / "node" / "LICENSE"
            app_mit = dist_notices / "inkflip-MIT.txt"
            if not pdfium.is_file() or pdfium.stat().st_size == 0:
                missing.append(f"PDFium binary license appendix missing: {pdfium}")
            if not node_license.is_file() or node_license.stat().st_size == 0:
                missing.append(f"Node bundled LICENSE missing: {node_license}")
            if not app_mit.is_file() or app_mit.stat().st_size == 0:
                missing.append(f"application MIT notice missing: {app_mit}")

    tess_stamp_path = root / "release" / "tesseract" / "tesseract.stamp.json"
    tess_stamp = _load_json(tess_stamp_path)
    if tess_stamp_path.is_file() and tess_stamp is None:
        missing.append(f"unreadable tesseract stamp: {tess_stamp_path}")
    elif tess_stamp is not None:
        packages = tess_stamp.get("packages") or []
        if not packages:
            missing.append(f"{tess_stamp_path} lists no hashed debs")
        dest_debs = dist / "tesseract" / "debs"
        for entry in packages:
            if not isinstance(entry, dict) or not entry.get("filename") or not entry.get("sha256"):
                missing.append(f"{tess_stamp_path} has a malformed package entry")
                continue
            deb = dest_debs / str(entry["filename"])
            if not deb.is_file() or deb.stat().st_size == 0:
                missing.append(
                    f"tesseract deb missing from assembled context: {deb} "
                    "(stamp-only is not a runnable OCR executable)"
                )
            elif sha256_file(deb) != entry["sha256"]:
                missing.append(
                    f"incorrect tesseract deb hash {entry['filename']}: "
                    f"stamp {entry['sha256']} != file {sha256_file(deb)}"
                )
        tess_notice = dist_notices / "tesseract" / "copyright"
        if not tess_notice.is_file() or tess_notice.stat().st_size == 0:
            missing.append(f"tesseract copyright notice missing: {tess_notice}")

    release_node = root / "release" / "node"
    release_models = root / "release" / "models"
    if release_node.is_dir() and not any(p.suffix in {".xz", ".gz"} or p.name == "node" for p in release_node.rglob("*") if p.is_file()):
        # Stamp-only is expected in git; assembled tarball is required above.
        pass
    if release_models.is_dir() and not list(release_models.glob("*.json")):
        missing.append(f"empty placeholder model directory: {release_models}")

    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check production native image inputs")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root (tests inject a fixture tree)",
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="list gaps without implying the image is buildable",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    gaps = problems_for(root)
    if args.inventory:
        print("\n".join(gaps) if gaps else "native image inputs: complete")
        return 0
    if gaps:
        print("inkflip: production native image inputs incomplete:", file=sys.stderr)
        for item in gaps:
            print(f"  {item}", file=sys.stderr)
        print(
            "Assemble with: python3 scripts/distribution/assemble_native_image.py\n"
            "Use Dockerfile.checkout only as a weaker local helper; do not treat it as the hashed release image.",
            file=sys.stderr,
        )
        return 2
    print("native image inputs: complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
