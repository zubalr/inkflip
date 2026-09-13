#!/usr/bin/env python3
"""Retrieve hashed Debian tesseract-ocr amd64 debs by digest.

Preparation may use the network. It never runs ``apt-get``: each package is
fetched from snapshot.debian.org by its recorded SHA-1 farm URL and verified
against the SHA-256 in ``release/tesseract/tesseract.stamp.json``. Production
image install stays offline ``dpkg -i``.

The cache is ``.private/cache/tesseract/debs`` inside this checkout. Writable
symlinks into other worktrees are rejected. Missing, tampered, and incomplete
cache states are distinct diagnostics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAMP = ROOT / "release" / "tesseract" / "tesseract.stamp.json"
CACHE = ROOT / ".private" / "cache" / "tesseract" / "debs"
SNAPSHOT_FILE = "https://snapshot.debian.org/file/{sha1}"
USER_AGENT = "inkflip-tesseract-prepare/1.1 (+local release closeout)"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reject_external_symlink(path: Path, root: Path) -> None:
    """Reject a cache whose resolved location escapes this checkout.

    macOS ``/var`` -> ``/private/var`` parent links are not a cache escape.
    A cache directory that itself symlinks into another worktree is.
    """
    root_res = root.resolve()
    if not (path.exists() or path.is_symlink()):
        return
    resolved = path.resolve()
    try:
        resolved.relative_to(root_res)
    except ValueError as error:
        raise RuntimeError(
            f"cache path {path} resolves to {resolved}; "
            "the distributable recipe must not depend on writable "
            "symlinks into other worktrees"
        ) from error


def snapshot_url(entry: dict) -> str:
    if isinstance(entry.get("snapshot_url"), str) and entry["snapshot_url"].startswith("https://"):
        return entry["snapshot_url"]
    sha1 = entry.get("sha1")
    if not isinstance(sha1, str) or len(sha1) != 40:
        raise RuntimeError(
            f"{entry.get('filename')} is missing sha1; cannot fetch from snapshot.debian.org/file/<sha1>"
        )
    return SNAPSHOT_FILE.format(sha1=sha1)


def download(url: str, dest: Path, opener) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener(request, timeout=120) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {status}")
        data = response.read()
    tmp.write_bytes(data)
    tmp.replace(dest)


def prepare(
    *,
    stamp_path: Path,
    cache: Path,
    root: Path,
    download_missing: bool,
    opener=urllib.request.urlopen,
) -> tuple[int, list[str]]:
    reject_external_symlink(cache, root)
    stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
    packages = stamp.get("packages") or []
    if not packages:
        return 2, [f"{stamp_path} lists no hashed packages"]
    cache.mkdir(parents=True, exist_ok=True)
    reject_external_symlink(cache, root)
    missing: list[str] = []
    tampered: list[str] = []
    fetched = 0
    verified = 0
    for entry in packages:
        if not isinstance(entry, dict) or not entry.get("filename") or not entry.get("sha256"):
            missing.append("malformed stamp package entry")
            continue
        name = str(entry["filename"])
        expected = str(entry["sha256"])
        path = cache / name
        if path.is_file():
            actual = sha256_file(path)
            if actual != expected:
                tampered.append(f"tampered {name}: stamp {expected} != cache {actual}")
                continue
            verified += 1
            continue
        if not download_missing:
            missing.append(f"missing {name}")
            continue
        try:
            url = snapshot_url(entry)
            download(url, path, opener)
        except (RuntimeError, OSError, urllib.error.URLError, TimeoutError) as error:
            missing.append(f"incomplete-cache {name}: retrieval failed: {error}")
            if path.is_file():
                path.unlink()
            continue
        actual = sha256_file(path)
        if actual != expected:
            tampered.append(f"tampered after fetch {name}: stamp {expected} != downloaded {actual}")
            path.unlink()
            continue
        fetched += 1
        verified += 1
    problems = [*tampered, *missing]
    if problems:
        kind = []
        if tampered:
            kind.append("tampered")
        if missing:
            kind.append("missing" if not download_missing else "incomplete-cache")
        header = "prepare_tesseract_debs: " + "+".join(kind)
        return 2, [header, *problems]
    return 0, [
        f"tesseract debs verified: {verified} files in {cache} "
        f"(fetched {fetched} this run; production image install stays offline dpkg -i)"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stamp", type=Path, default=STAMP)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the isolated cache only; do not download",
    )
    args = parser.parse_args(argv)
    try:
        code, lines = prepare(
            stamp_path=args.stamp,
            cache=args.cache,
            root=args.root,
            download_missing=not args.check,
        )
    except RuntimeError as error:
        print(f"prepare_tesseract_debs: {error}", file=sys.stderr)
        return 2
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
