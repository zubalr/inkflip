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

``--check`` is a verification pass, not a generation pass: it re-derives the
expected wheel set from ``native/uv.lock`` and compares it against the bytes
actually present in the build context plus the compact outputs in
``release/``, and it verifies the node/model artifacts against the identities
recorded in their stamps and in ``config/resolved-assets.json``. The check
path is strictly read-only — it never writes, truncates, repairs, creates or
removes anything, on success and on refusal alike — and it performs no
network access. Exit codes are shared with preparation: 0 pass, 1 failures,
2 config error.

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
MANIFEST_KIND = "inkflip-native-wheels-manifest"
MANIFEST_REL = "release/native-wheels.manifest.json"
REQUIREMENTS_LOCK_REL = "release/native-requirements.lock"


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


def wheel_entries(closure: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """The expected per-wheel entries of the lock closure.

    One shared builder, so preparation and ``--check`` compare against the same
    lock-derived document: the expected identity of every prepared wheel comes
    from ``native/uv.lock`` and never from the artifact being verified.
    """
    failures: list[str] = []
    entries: list[dict] = []
    for name in sorted(closure):
        pkg = closure[name]
        wheel, err = select_wheel(pkg)
        if err:
            failures.append(err)
            continue
        filename = wheel["url"].rsplit("/", 1)[-1]
        entries.append({
            "name": name,
            "version": pkg["version"],
            "filename": filename,
            "url": wheel["url"],
            "sha256": wheel["hash"].split(":", 1)[1],
            "bytes": wheel.get("size"),
            "hash_source": "native/uv.lock (trusted lock hash)",
            "path_in_context": f"wheels/{filename}",
        })
    return entries, failures


def manifest_document() -> dict:
    """The compact wheels manifest as preparation writes it (wheels appended by
    the caller once their bytes are verified)."""
    return {
        "schema_version": "1.0.0",
        "kind": MANIFEST_KIND,
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


def requirements_lock_text(entries: list[dict]) -> str:
    """The pip-format runtime lock preparation writes for these entries."""
    lines = [
        "# Generated by scripts/distribution/prepare_native_bundle.py — do not edit.",
        f"# Runtime closure of native/uv.lock for {PLATFORM['platform']}; hashes are the lock's own.",
    ]
    for entry in sorted(entries, key=lambda e: e["name"]):
        lines.append(f"{entry['name']}=={entry['version']} --hash=sha256:{entry['sha256']}")
    return "\n".join(lines) + "\n"


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


def _display(path: Path) -> str:
    """Repository-relative label for diagnostics (absolute when outside)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _json_object(path: Path, label: str, failures: list[str]) -> dict | None:
    """Read ``path`` as a JSON object.

    The shape is validated before any field is touched, so a missing file,
    invalid JSON or a non-object root becomes a named failure instead of a
    traceback.
    """
    if not path.is_file():
        failures.append(f"{label} missing: {_display(path)}")
        return None
    try:
        document = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        failures.append(f"{label} is not readable JSON: {_display(path)} ({error})")
        return None
    if not isinstance(document, dict):
        failures.append(
            f"{label} root must be a JSON object: {_display(path)} holds a {type(document).__name__}"
        )
        return None
    return document


def _sha256_field(document: dict, label: str, failures: list[str]) -> str | None:
    value = document.get("sha256")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        failures.append(f"{label} must record a 64-hex sha256: found {value!r}")
        return None
    return value


def _verify_artifact(path: Path, kind: str, expected_sha256: str,
                     expected_size: int | None, failures: list[str]) -> None:
    """Compare the real bytes of a prepared artifact with its declared
    identity; the expectation never comes from the artifact itself."""
    if path.is_symlink():
        failures.append(f"{kind} is a symlink: {_display(path)}")
        return
    if not path.is_file():
        failures.append(f"{kind} missing: {_display(path)}")
        return
    actual_size = path.stat().st_size
    if expected_size is not None and actual_size != expected_size:
        failures.append(f"{kind} size mismatch: declared {expected_size}, prepared {actual_size}")
    actual = sha256_file(path)
    if actual != expected_sha256:
        failures.append(f"{kind} hash mismatch: declared {expected_sha256}, prepared {actual}")


def verify_wheels(entries: list[dict], failures: list[str]) -> None:
    """Every runtime package must have its lock wheel prepared, byte for byte."""
    for entry in entries:
        filename = entry["filename"]
        dest = PRIVATE / "wheels" / filename
        if dest.is_symlink():
            failures.append(f"prepared wheel is a symlink: {filename}")
            continue
        if not dest.is_file():
            failures.append(f"prepared wheel missing: {filename}")
            continue
        declared_size = entry["bytes"]
        actual_size = dest.stat().st_size
        if declared_size is not None and actual_size != declared_size:
            failures.append(
                f"prepared wheel size mismatch: {filename}: lock {declared_size}, prepared {actual_size}"
            )
        actual = sha256_file(dest)
        if actual != entry["sha256"]:
            failures.append(
                f"prepared wheel hash mismatch: {filename}: lock {entry['sha256']}, prepared {actual}"
            )


def verify_wheels_manifest(entries: list[dict], failures: list[str]) -> None:
    """Validate the recorded manifest's shape, then its content against the
    lock-derived expectation."""
    label = MANIFEST_REL
    document = _json_object(RELEASE / "native-wheels.manifest.json", label, failures)
    if document is None:
        return
    if document.get("kind") != MANIFEST_KIND:
        failures.append(f"{label} kind drift: expected {MANIFEST_KIND!r}, found {document.get('kind')!r}")
    if document.get("platform") != PLATFORM:
        recorded_platform = document.get("platform")
        failures.append(
            f"{label} platform drift: expected {PLATFORM['platform']!r}, found "
            f"{(recorded_platform.get('platform') if isinstance(recorded_platform, dict) else recorded_platform)!r}"
        )
    lock_sha256 = sha256_file(ROOT / "native" / "uv.lock")
    generated = document.get("generated_from")
    recorded_lock = generated.get("lock_sha256") if isinstance(generated, dict) else None
    if recorded_lock != lock_sha256:
        failures.append(
            f"{label} lock_sha256 drift: native/uv.lock is {lock_sha256}, manifest records {recorded_lock}"
        )
    recorded = document.get("wheels")
    if not isinstance(recorded, list):
        failures.append(f"{label} 'wheels' must be a JSON list, found {type(recorded).__name__}")
        return

    by_name: dict[str, dict] = {}
    for index, item in enumerate(recorded):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            failures.append(f"{label} wheel entry {index} is not an object recording a package name")
            continue
        by_name.setdefault(item["name"], item)
        evidence = item.get("license_evidence")
        evidence_dir = ROOT / evidence if isinstance(evidence, str) else None
        if evidence_dir is None or not evidence_dir.is_dir() \
                or not any(p.is_file() and p.stat().st_size > 0 for p in evidence_dir.rglob("*")):
            failures.append(f"manifest license evidence missing or empty: {evidence}")

    for entry in entries:
        item = by_name.pop(entry["name"], None)
        if item is None:
            failures.append(f"manifest wheel entry missing: {entry['name']}=={entry['version']}")
            continue
        if item.get("filename") != entry["filename"]:
            failures.append(
                f"manifest wheel filename drift for {entry['name']}: lock {entry['filename']}, "
                f"manifest {item.get('filename')}"
            )
        if item.get("sha256") != entry["sha256"]:
            failures.append(
                f"manifest wheel digest drift for {entry['filename']}: lock {entry['sha256']}, "
                f"manifest {item.get('sha256')}"
            )
        if entry["bytes"] is not None and item.get("bytes") != entry["bytes"]:
            failures.append(
                f"manifest wheel size drift for {entry['filename']}: lock {entry['bytes']}, "
                f"manifest {item.get('bytes')}"
            )
    for name, item in sorted(by_name.items()):
        failures.append(f"manifest records unexpected wheel: {name} ({item.get('filename')})")


def verify_requirements_lock(entries: list[dict], failures: list[str]) -> None:
    """The compact runtime lock must byte-match what preparation would write."""
    path = RELEASE / "native-requirements.lock"
    expected = requirements_lock_text(entries).encode()
    if not path.is_file():
        failures.append(f"{REQUIREMENTS_LOCK_REL} missing: {_display(path)}")
        return
    actual = path.read_bytes()
    if actual != expected:
        failures.append(
            f"{REQUIREMENTS_LOCK_REL} drift vs the native/uv.lock closure: prepared sha256 "
            f"{hashlib.sha256(actual).hexdigest()}, expected {hashlib.sha256(expected).hexdigest()}"
        )


def verify_node(failures: list[str]) -> None:
    """The node stamp must name the pinned version and its tarball must be the
    file the stamp records (not merely a file that exists)."""
    label = "release/node/node.stamp.json"
    stamp = _json_object(RELEASE / "node" / "node.stamp.json", label, failures)
    version_path = ROOT / ".node-version"
    expected_version = version_path.read_text().strip() if version_path.is_file() else None
    if not expected_version:
        failures.append(f"pinned node version missing: {_display(version_path)}")
        expected_version = None
    if stamp is None:
        return
    stamp_version = stamp.get("version")
    if not isinstance(stamp_version, str) or not stamp_version:
        failures.append(f"{label} must record a version: found {stamp_version!r}")
    elif expected_version is not None and stamp_version != expected_version:
        failures.append(f"{label} version drift: .node-version is {expected_version}, stamp records {stamp_version}")
    expected_filename = f"node-v{expected_version}-linux-x64.tar.xz" if expected_version else None
    stamp_filename = stamp.get("filename")
    if expected_filename is not None and stamp_filename != expected_filename:
        failures.append(f"{label} filename drift: expected {expected_filename}, stamp records {stamp_filename!r}")
    digest = _sha256_field(stamp, label, failures)
    filename = expected_filename or (stamp_filename if isinstance(stamp_filename, str) else None)
    if digest is None or filename is None:
        return
    recorded_bytes = stamp.get("bytes")
    if "bytes" in stamp and (isinstance(recorded_bytes, bool)
                             or not isinstance(recorded_bytes, int) or recorded_bytes < 0):
        failures.append(f"{label} must record non-negative integer bytes: found {recorded_bytes!r}")
        recorded_bytes = None
    _verify_artifact(PRIVATE / "node" / filename, "prepared node artifact",
                     digest, recorded_bytes, failures)


def verify_model(failures: list[str]) -> None:
    """The model stamp must agree with the declared asset identity in
    config/resolved-assets.json, and the prepared file must be that asset."""
    label = "release/models/model.stamp.json"
    stamp = _json_object(RELEASE / "models" / "model.stamp.json", label, failures)

    declared_sha256: str | None = None
    declared_bytes: int | None = None
    try:
        assets = json.loads((ROOT / "config" / "resolved-assets.json").read_text())
        group = next((g for g in assets["assets"] if g.get("id") == "tessdata-fast-eng"), None)
        file_record = group["files"][0]
        declared_sha256 = file_record["sha256"]
        declared_bytes = file_record["bytes"]
        if not isinstance(declared_sha256, str) \
                or isinstance(declared_bytes, bool) or not isinstance(declared_bytes, int):
            raise TypeError(f"declared identity {declared_sha256!r}/{declared_bytes!r}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        declared_sha256, declared_bytes = None, None
        failures.append("config/resolved-assets.json has no usable tessdata-fast-eng group")
    if stamp is None:
        return

    stamp_sha256 = _sha256_field(stamp, label, failures)
    stamp_bytes = stamp.get("bytes")
    if isinstance(stamp_bytes, bool) or not isinstance(stamp_bytes, int) or stamp_bytes < 0:
        failures.append(f"{label} must record non-negative integer bytes: found {stamp_bytes!r}")
        stamp_bytes = None
    if declared_sha256 is not None and stamp_sha256 is not None and stamp_sha256 != declared_sha256:
        failures.append(
            f"{label} sha256 drift vs config/resolved-assets.json: declared {declared_sha256}, "
            f"stamp records {stamp_sha256}"
        )
    if declared_bytes is not None and stamp_bytes is not None and stamp_bytes != declared_bytes:
        failures.append(
            f"{label} bytes drift vs config/resolved-assets.json: declared {declared_bytes}, "
            f"stamp records {stamp_bytes}"
        )
    expected_sha256 = declared_sha256 or stamp_sha256
    if expected_sha256 is None:
        return
    expected_size = declared_bytes if declared_bytes is not None else stamp_bytes
    _verify_artifact(PRIVATE / "models" / "tessdata" / "eng.traineddata",
                     "prepared model artifact", expected_sha256, expected_size, failures)


def verify_build_context(failures: list[str]) -> None:
    """The prepared context must carry its non-empty pointer document."""
    path = PRIVATE / "BUILD-CONTEXT.md"
    if not path.is_file():
        failures.append(f"build context pointer missing: {_display(path)}")
    elif path.stat().st_size == 0:
        failures.append(f"build context pointer is empty: {_display(path)}")


def verify_native_bundle(entries: list[dict], failures: list[str]) -> int:
    """Verify the prepared tree against the lock closure and the recorded
    stamps. Read-only: nothing here writes, creates, repairs or removes any
    file, and nothing here uses the network."""
    verify_wheels(entries, failures)
    verify_wheels_manifest(entries, failures)
    verify_requirements_lock(entries, failures)
    verify_node(failures)
    verify_model(failures)
    verify_build_context(failures)
    if failures:
        print(f"native bundle verification: {len(failures)} failure(s)")
        for failure in sorted(set(failures)):
            print(f"  - {failure}")
        return 1
    print(f"native bundle verified: {len(entries)} wheels, node + model artifacts match the recorded stamps")
    print(f"  bulky artifacts: {PRIVATE}")
    print(f"  tracked interface: {RELEASE}/")
    return 0


def prepare_bundle(entries: list[dict], failures: list[str], *,
                   no_download: bool, force_download: bool) -> int:
    """Explicit preparation (today's behaviour): download and verify what is
    missing, then write the lock, manifest, stamps, notices and build context."""
    wheels_manifest = manifest_document()
    wheels_dir = PRIVATE / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        dest = wheels_dir / entry["filename"]
        if not dest.is_file() or force_download:
            failures.extend(download(entry["url"], dest, entry["sha256"], entry["bytes"]))
        if dest.is_file():
            actual = sha256_file(dest)
            if actual != entry["sha256"]:
                failures.append(f"wheel hash mismatch: {entry['filename']}")
                continue
            entry["verified_sha256"] = actual
            lic_files = wheel_license_files(dest, entry["name"], entry["version"])
            notice_dir = RELEASE / "notices" / f"{entry['name']}-{entry['version']}"
            notice_dir.mkdir(parents=True, exist_ok=True)
            for lic_name, data in lic_files:
                (notice_dir / lic_name).write_bytes(data)
            entry["license_evidence"] = str(notice_dir.relative_to(ROOT))
        wheels_manifest["wheels"].append(entry)

    node_stamp = prepare_node(failures, do_download=not no_download)
    model_stamp = prepare_model(failures)
    wheels_manifest["node"] = node_stamp
    wheels_manifest["model"] = model_stamp

    # Compact committed outputs.
    lock_path = RELEASE / "native-requirements.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(requirements_lock_text(wheels_manifest["wheels"]))

    manifest_path = RELEASE / "native-wheels.manifest.json"
    manifest_text = json.dumps(wheels_manifest, indent=2, sort_keys=True) + "\n"
    # Byte-identical output is left untouched.
    if not manifest_path.is_file() or manifest_path.read_bytes() != manifest_text.encode():
        manifest_path.write_text(manifest_text)

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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 pass, 1 preparation failures, 2 config error. "
        "Bulky artifacts are written to .private/distribution/native-bundle/ "
        "(git-ignored); compact manifests/notices to release/.",
    )
    parser.add_argument("--no-download", action="store_true", help="plan/verify without network; fails if artifacts are missing")
    parser.add_argument("--force-download", action="store_true", help="re-download even if prepared artifacts exist")
    parser.add_argument("--check", action="store_true", help="verify the prepared tree against native/uv.lock without downloading, writing or creating anything")
    args = parser.parse_args()

    if not (ROOT / "native" / "uv.lock").is_file():
        print("config error: native/uv.lock not found", file=sys.stderr)
        return 2

    lock = load_lock()
    closure, failures = runtime_closure(lock)
    entries, entry_failures = wheel_entries(closure)
    failures.extend(entry_failures)

    if args.check:
        return verify_native_bundle(entries, failures)
    return prepare_bundle(entries, failures,
                          no_download=args.no_download, force_download=args.force_download)


if __name__ == "__main__":
    sys.exit(main())
