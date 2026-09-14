#!/usr/bin/env python3
"""Prepare hash-checked third-party dependency inputs for the native bundle
(T47 preparation; the container/Dockerfile and app wheel belong to the
packaging lane).

Reads the frozen ``native/uv.lock`` and the established pinned manifests and
produces, deterministically:

  release/native-requirements.lock   pip-format lock of the runtime closure
                                     (exact versions + lock hashes)
  release/native-wheels.manifest.json per-wheel provenance: version, ABI/tags,
                                     source URL, trusted lock hash, size
  release/node/node.stamp.json       pinned Node runtime identity (official
                                     SHASUMS256-verified)
  release/models/model.stamp.json    pinned model asset identity (digest from
                                     config/resolved-assets.json)
  release/notices/                   license texts extracted from the
                                     selected wheels + bundled asset notices
  .private/distribution/native-bundle/
                                     the bulky artifacts (wheels, node
                                     tarball, model) laid out as a Docker
                                     build context; never committed

Selection is mechanical and refuses to guess: the runtime dependency closure
is walked from the root project's ``dependencies`` (dev-group packages are
excluded; a dev-only package reachable at runtime is a named failure), and
for each package exactly one wheel must match the contract's Linux platform
(CPython 3.13, glibc manylinux, x86_64 — the recorded "native Linux x86_64"
reference; see planning/quality/PERFORMANCE_AND_COMPATIBILITY.md). When
several manylinux variants match, the widest (oldest glibc) is chosen by a
recorded policy. Missing wheels, unexpected packages, incompatible tags and
hash/size mismatches are hard failures (exit 1); config problems exit 2.

Downloads happen only when this command is invoked explicitly (the official
package index / nodejs.org). Installation and processing never retrieve
anything automatically. Dependency versions and candidate selection are read
from the lock — never upgraded, downgraded or substituted.

Usage:
  python3 scripts/distribution/prepare_native_bundle.py [--no-download] [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tarfile
import tempfile
import tomllib
import os
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / ".private" / "distribution" / "native-bundle"
RELEASE = ROOT / "release"
PLATFORM = {
    "python_tag": "cp313",
    "abi_tag": "cp313",
    "platform": "linux x86_64 (glibc manylinux) — recorded contract reference",
    "arch": "x86_64",
    "excluded": "musllinux, non-x86_64, iOS/Android/macOS/Windows wheels",
}
NODE_MIRROR = "https://nodejs.org/dist"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_lock() -> dict:
    return tomllib.loads((ROOT / "native" / "uv.lock").read_text())


def runtime_closure(lock: dict) -> tuple[dict[str, dict], list[str]]:
    """BFS from the root project's dependencies. Returns (closure, failures)."""
    packages = {p["name"]: p for p in lock.get("package", []) if p.get("name")}
    root = packages.get("inkflip")
    if root is None:
        return {}, ["native/uv.lock has no root project entry (inkflip)"]
    failures: list[str] = []
    closure: dict[str, dict] = {}
    queue = [(root, dep) for dep in sorted((root.get("dependencies") or []), key=lambda d: d["name"])]
    seen_specs: set[tuple[str, str]] = set()
    while queue:
        owner, dep = queue.pop(0)
        dep_name = dep["name"]
        key = (owner["name"], dep_name)
        if key in seen_specs:
            continue
        seen_specs.add(key)
        if dep_name == "inkflip":
            continue
        pkg = packages.get(dep_name)
        if pkg is None:
            failures.append(f"lock cannot resolve runtime dependency {dep_name!r} (from {owner['name']})")
            continue
        if dep_name not in closure:
            closure[dep_name] = pkg
            for child in sorted(pkg.get("dependencies") or [], key=lambda d: d["name"]):
                queue.append((pkg, child))
    # A dev-group package must never be reachable from the runtime closure.
    dev_groups = root.get("dev-dependencies") or {}
    root_dev = {d["name"] for members in dev_groups.values() for d in members}
    for name in closure:
        if name in root_dev:
            failures.append(f"unexpected package in runtime closure: {name!r} is a dev dependency")
    return closure, failures


WHEEL_PLATFORM_RE = re.compile(
    r"manylinux(?:_(\d+)_\d+|2014|1)_x86_64\.whl$|manylinux1_x86_64\.whl$"
)


def select_wheel(pkg: dict) -> tuple[dict | None, str | None]:
    """Pick the contract-platform wheel. Returns (entry, error)."""
    name, version = pkg["name"], pkg["version"]
    dist_norm = name.replace("-", "_")  # wheel filenames use normalized names
    matches = []
    for w in pkg.get("wheels", []):
        filename = w["url"].rsplit("/", 1)[-1]
        if not filename.startswith(f"{dist_norm}-{version}-"):
            continue
        tags = filename[len(dist_norm) + len(version) + 2 : -4]  # python-abi-platform
        parts = tags.split("-")
        if len(parts) != 3:
            continue
        py, abi, plat = parts
        if py not in ("cp313", "py3") or abi not in ("cp313", "abi3", "none"):
            continue
        if plat == "any":
            matches.append((0, filename, w))
            continue
        if "musllinux" in plat or "x86_64" not in plat:
            continue
        if not re.search(r"manylinux(?:_\d+_\d+|2014|1)", plat):
            continue
        glibc = int(m.group(1)) if (m := re.search(r"manylinux_(\d+)_", plat)) else (2014 if "manylinux2014" in plat else 1)
        matches.append((glibc, filename, w))
    if not matches:
        return None, (
            f"no wheel for {name}=={version} matches the contract platform "
            f"(cp313/py3, cp313/abi3/none, glibc manylinux x86_64 or any)"
        )
    matches.sort(key=lambda m: (-m[0]))  # widest compatibility = oldest glibc first
    return matches[0][2], None


def download(url: str, dest: Path, expected_sha256: str, expected_size: int | None) -> list[str]:
    failures = []
    with urllib.request.urlopen(url, timeout=120) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    actual = sha256_file(dest)
    if actual != expected_sha256:
        failures.append(f"hash mismatch for {dest.name}: lock {expected_sha256} != downloaded {actual}")
    if expected_size is not None and dest.stat().st_size != expected_size:
        failures.append(f"size mismatch for {dest.name}: expected {expected_size}, got {dest.stat().st_size}")
    return failures


def wheel_license_files(wheel_path: Path, name: str, version: str) -> list[tuple[str, bytes]]:
    """Extract embedded license material from a wheel's dist-info (files only,
    recursing into licenses/ subdirectories), plus the METADATA license fields."""
    out = []
    dist_info = f"{name.replace('-', '_')}-{version}.dist-info"
    with zipfile.ZipFile(wheel_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.startswith(dist_info + "/"):
                continue
            remainder = info.filename[len(dist_info) + 1 :]
            if re.search(r"LICENSE|COPYING|NOTICE|AUTHORS", Path(remainder).name, re.IGNORECASE):
                out.append((remainder.replace("/", "__"), zf.read(info)))
        metadata = zf.read(f"{dist_info}/METADATA").decode("utf-8", "replace")
    out.append(("METADATA-license-header.json", json.dumps(extract_license_fields(metadata), indent=2).encode()))
    return out


def extract_license_fields(metadata: str) -> dict:
    fields = {}
    for key in ("License", "License-Expression"):
        m = re.search(rf"^{key}:(.*)$", metadata, re.MULTILINE | re.IGNORECASE)
        if m and m.group(1).strip():
            fields[key] = m.group(1).strip()
    classifiers = re.findall(r"^Classifier: License :: [^:]* :: (.*)$", metadata, re.MULTILINE)
    if classifiers:
        fields["License-Classifiers"] = sorted(set(classifiers))
    return fields


def _fetch_shasums(shasums_url: str) -> str:
    return urllib.request.urlopen(shasums_url, timeout=120).read().decode()


def _fetch_to(url: str, dest: Path) -> None:
    urllib.request.urlretrieve(url, dest)


def prepare_node(failures: list[str], do_download: bool, *,
                 fetch_shasums=_fetch_shasums, fetch_to=_fetch_to) -> dict:
    """Prepare the pinned Node runtime tarball with verified-cache semantics.

    States are distinguished and never conflated:

      missing        no cached tarball (needs the network step, or --no-download failure)
      corrupt        cached tarball present but its sha256 does not match the
                     pinned expected digest (zero bytes, truncation, wrong
                     bytes are all 'corrupt')
      offline        --no-download blocked the repair of missing/corrupt state

    The pinned expected digest always comes from the trusted source (official
    SHASUMS256.txt, or a previously published stamp whose recorded digest was
    itself verified at publish time) — never from the artifact being checked.
    A corrupt cached file is kept intact until a verified replacement has been
    downloaded and swapped in; a failed download never publishes a success
    stamp and never overwrites the trusted expected digest with the observed
    digest of bad bytes.
    """
    version = (ROOT / ".node-version").read_text().strip()
    url_base = f"{NODE_MIRROR}/v{version}"
    shasums_url = f"{url_base}/SHASUMS256.txt"
    filename = f"node-v{version}-linux-x64.tar.xz"
    download_url = f"{url_base}/{filename}"
    stamp_path = RELEASE / "node" / "node.stamp.json"
    dest = PRIVATE / "node" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Trusted expected digest: a previously published stamp (whose digest was
    # verified at its own publish time) or the official SHASUMS256 source.
    expected: str | None = None
    stamp: dict = {}
    if stamp_path.is_file():
        try:
            stamp = json.loads(stamp_path.read_text())
        except json.JSONDecodeError:
            stamp = {}
        if stamp.get("version") == version and isinstance(stamp.get("sha256"), str) \
                and re.fullmatch(r"[0-9a-f]{64}", stamp["sha256"]):
            expected = stamp["sha256"]

    present = dest.is_file() and not dest.is_symlink() and dest.stat().st_size > 0
    actual = sha256_file(dest) if present else None
    verified = present and actual == expected

    if verified:
        # Cache intact and matching the pinned digest: no network needed.
        stamp.update({"filename": filename, "url": download_url,
                      "shasums256_source": shasums_url, "sha256": actual,
                      "version": version, "platform": "linux-x64"})
        return stamp

    if present and expected:
        failures.append(
            f"node runtime cache corrupt: {dest} (cached sha256 {actual[:12]}… "
            f"does not match pinned {expected[:12]}…)"
        )
    elif not present:
        failures.append(
            f"node runtime cache missing: {dest} — run "
            "python3 scripts/distribution/prepare_native_bundle.py (explicit network step)"
        )
    if not do_download:
        # Offline refusal: keep any existing artifact intact for later repair.
        if present and expected:
            failures.append(
                "node runtime cache left unrepaired because --no-download was set; "
                "re-run without --no-download to replace the corrupt file"
            )
        elif present:
            failures.append(
                "node runtime cache present but cannot be verified offline "
                "(no pinned digest for this version); re-run without --no-download"
            )
        return {}

    # Network repair: fetch expected digest, download to a temporary file,
    # verify BEFORE publishing, then atomically swap in. The previously
    # cached file stays untouched until the replacement is verified.
    try:
        if expected is None:
            shasums = fetch_shasums(shasums_url)
            for line in shasums.splitlines():
                digest, _, fname = line.partition(" ")
                if fname.strip() == filename:
                    expected = digest
                    break
            if expected is None:
                failures.append(
                    f"official SHASUMS256.txt for node v{version} lists no entry for {filename}"
                )
                return {}
        temp = dest.with_name(dest.name + ".downloading")
        fetch_to(download_url, temp)
        downloaded = sha256_file(temp)
        if downloaded != expected:
            failures.append(
                f"node tarball download rejected: sha256 {downloaded[:12]}… does not match "
                f"pinned {expected[:12]}…; the previous cache file is left in place"
            )
            temp.unlink(missing_ok=True)
            return {}
        os.replace(temp, dest)
    except (OSError, urllib.error.URLError) as error:
        failures.append(
            f"node runtime download failed ({error}); the previous cache file is left in place"
        )
        return {}

    actual = sha256_file(dest)
    try:
        with tarfile.open(dest) as tf:
            binary = tf.extractfile(f"node-v{version}-linux-x64/bin/node")
            node_sha = hashlib.sha256(binary.read()).hexdigest() if binary else None
    except (tarfile.TarError, OSError, EOFError) as error:
        failures.append(
            f"node runtime tarball unreadable after verification ({error}); "
            "treated as failed preparation — no stamp published"
        )
        return {}
    stamp = {
        "name": "node",
        "version": version,
        "platform": "linux-x64",
        "filename": filename,
        "url": download_url,
        "shasums256_source": shasums_url,
        "sha256": actual,  # equals the pinned expected digest (verified above)
        "binary_sha256": node_sha,
        "license": "MIT (Node.js; bundled third-party components per official NOTICE — fetched with the runtime at build time)",
        "purpose": "comparison-bridge runtime for the native bundle",
    }
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n")
    return stamp


def prepare_model(failures: list[str]) -> dict:
    assets = json.loads((ROOT / "config" / "resolved-assets.json").read_text())
    group = next((g for g in assets["assets"] if g["id"] == "tessdata-fast-eng"), None)
    if group is None:
        failures.append("config/resolved-assets.json has no tessdata-fast-eng group")
        return {}
    src = ROOT / "apps" / "web" / "public" / group["files"][0]["staged_path"]
    if not src.is_file():
        failures.append(f"model asset missing: {src}")
        return {}
    actual = sha256_file(src)
    declared = group["files"][0]["sha256"]
    if actual != declared:
        failures.append(f"model asset hash drift: manifest {declared} != actual {actual}")
    dest = PRIVATE / "models" / "tessdata" / "eng.traineddata"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    stamp = {
        "name": "tessdata_fast (eng.traineddata)",
        "version": f"pinned commit {group['files'][0]['staged_path'].split('/')[-2]}",
        "sha256": declared,
        "bytes": group["files"][0]["bytes"],
        "license": group["license"],
        "rights": group["rights"],
        "source": "config/resolved-assets.json (staged same-origin asset)",
        "path_in_context": "models/tessdata/",
    }
    stamp_path = RELEASE / "models" / "model.stamp.json"
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n")
    notice_src = ROOT / "licenses" / "tessdata-fast-eng" / "NOTICE.txt"
    if notice_src.is_file():
        notices = RELEASE / "notices"
        notices.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(notice_src, notices / "tessdata-fast-eng-NOTICE.txt")
    return stamp


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 pass, 1 preparation failures, 2 config error. "
        "Bulky artifacts are written to .private/distribution/native-bundle/ "
        "(git-ignored); compact manifests/notices to release/.",
    )
    parser.add_argument("--no-download", action="store_true", help="plan/verify without network; fails if artifacts are missing")
    parser.add_argument("--force-download", action="store_true", help="re-download even if prepared artifacts exist")
    parser.add_argument("--check", action="store_true", help="verify the prepared tree against release/native-wheels.manifest.json without downloading")
    args = parser.parse_args()

    failures: list[str] = []
    if not (ROOT / "native" / "uv.lock").is_file():
        print("config error: native/uv.lock not found", file=sys.stderr)
        return 2

    lock = load_lock()
    closure, closure_failures = runtime_closure(lock)
    failures.extend(closure_failures)

    wheels_manifest = {
        "schema_version": "1.0.0",
        "kind": "inkflip-native-wheels-manifest",
        "recorded_at": "2026-09-13",
        "platform": PLATFORM,
        "python": "3.13.15 (pinned; requires-python ==3.13.15)",
        "generated_from": {
            "lock": "native/uv.lock",
            "lock_sha256": sha256_file(ROOT / "native" / "uv.lock"),
        },
        "policy": "runtime closure from root dependencies only; one wheel per package; widest manylinux chosen when several match",
        "wheels": [],
        "missing_app_wheel": "Inkflip's own application wheel and CLI entry point are prepared by the packaging lane and are NOT part of this third-party bundle",
    }

    wheels_dir = PRIVATE / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)

    for name in sorted(closure):
        pkg = closure[name]
        wheel, err = select_wheel(pkg)
        if err:
            failures.append(err)
            continue
        filename = wheel["url"].rsplit("/", 1)[-1]
        expected_hash = wheel["hash"].split(":", 1)[1]
        entry = {
            "name": name,
            "version": pkg["version"],
            "filename": filename,
            "url": wheel["url"],
            "sha256": expected_hash,
            "bytes": wheel.get("size"),
            "hash_source": "native/uv.lock (trusted lock hash)",
            "path_in_context": f"wheels/{filename}",
        }
        dest = wheels_dir / filename
        if args.check:
            if not dest.is_file():
                failures.append(f"prepared wheel missing: {filename}")
                continue
        elif not dest.is_file() or args.force_download:
            failures.extend(download(wheel["url"], dest, expected_hash, wheel.get("size")))
        if dest.is_file():
            actual = sha256_file(dest)
            if actual != expected_hash:
                failures.append(f"wheel hash mismatch: {filename}")
                continue
            entry["verified_sha256"] = actual
            lic_files = wheel_license_files(dest, name, pkg["version"])
            notice_dir = RELEASE / "notices" / f"{name}-{pkg['version']}"
            notice_dir.mkdir(parents=True, exist_ok=True)
            for lic_name, data in lic_files:
                (notice_dir / lic_name).write_bytes(data)
            entry["license_evidence"] = str(notice_dir.relative_to(ROOT))
        wheels_manifest["wheels"].append(entry)

    if not args.check:
        node_stamp = prepare_node(failures, do_download=not args.no_download)
        model_stamp = prepare_model(failures)
        wheels_manifest["node"] = node_stamp
        wheels_manifest["model"] = model_stamp

    # Compact committed outputs.
    lock_path = RELEASE / "native-requirements.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Generated by scripts/distribution/prepare_native_bundle.py — do not edit.",
        f"# Runtime closure of native/uv.lock for {PLATFORM['platform']}; hashes are the lock's own.",
    ]
    for entry in sorted(wheels_manifest["wheels"], key=lambda e: e["name"]):
        lines.append(f"{entry['name']}=={entry['version']} --hash=sha256:{entry['sha256']}")
    lock_path.write_text("\n".join(lines) + "\n")

    manifest_path = RELEASE / "native-wheels.manifest.json"
    manifest_path.write_text(json.dumps(wheels_manifest, indent=2, sort_keys=True) + "\n")

    # Build-context pointer so the prepared tree is directly consumable.
    context_readme = PRIVATE / "BUILD-CONTEXT.md"
    context_readme.parent.mkdir(parents=True, exist_ok=True)
    context_readme.write_text(
        "Docker build context layout (prepared by scripts/distribution/prepare_native_bundle.py)\n"
        "========================================================================================\n\n"
        "  wheels/      third-party Python wheels (hash-verified against native/uv.lock)\n"
        "  node/        pinned Node.js runtime tarball (node-v%s-linux-x64.tar.xz)\n"
        "  models/      tessdata/eng.traineddata (pinned, digest-verified)\n\n"
        "The compact tracked interface lives in release/: native-requirements.lock,\n"
        "native-wheels.manifest.json, node/node.stamp.json, models/model.stamp.json and\n"
        "notices/. The application wheel and CLI entry point are the packaging lane's\n"
        "delivery and are deliberately absent here.\n" % (json.loads((RELEASE / "node" / "node.stamp.json").read_text())["version"] if (RELEASE / "node" / "node.stamp.json").is_file() else "?")
    )

    if failures:
        print(f"native bundle preparation: {len(failures)} failure(s)")
        for f in sorted(set(failures)):
            print(f"  - {f}")
        return 1
    print(f"native bundle prepared: {len(wheels_manifest['wheels'])} wheels, node + model stamps written")
    print(f"  bulky artifacts: {PRIVATE}")
    print(f"  tracked interface: {RELEASE}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
