#!/usr/bin/env python3
"""Download the hashed Debian tesseract-ocr amd64 closure (setup network only).

Writes ``.private/tesseract/debs/*.deb`` and verifies them against
``release/tesseract/tesseract.stamp.json``. Never used by the production
image build; that path is offline ``dpkg -i``.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAMP = ROOT / "release" / "tesseract" / "tesseract.stamp.json"
DEST = ROOT / ".private" / "tesseract" / "debs"
BASE = (
    "python:3.13.15-slim-trixie@"
    "sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    stamp = json.loads(STAMP.read_text(encoding="utf-8"))
    DEST.mkdir(parents=True, exist_ok=True)
    inner = (
        "set -eu\n"
        "apt-get update\n"
        "apt-get install --download-only -y --no-install-recommends tesseract-ocr\n"
        "cp -a /var/cache/apt/archives/*.deb /out/\n"
    )
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "-v",
            f"{DEST}:/out",
            BASE,
            "sh",
            "-c",
            inner,
        ],
        cwd=ROOT,
    )
    if proc.returncode != 0:
        return proc.returncode
    problems = []
    for entry in stamp.get("packages") or []:
        path = DEST / entry["filename"]
        if not path.is_file():
            problems.append(f"missing {entry['filename']}")
            continue
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            problems.append(f"hash mismatch {entry['filename']}: stamp {entry['sha256']} != {actual}")
    if problems:
        print("prepare_tesseract_debs: verification failed", file=sys.stderr)
        for item in problems:
            print(f"  {item}", file=sys.stderr)
        return 2
    print(f"tesseract debs verified: {len(stamp.get('packages') or [])} files in {DEST}")
    print("setup used the network; production image install stays offline dpkg -i")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
