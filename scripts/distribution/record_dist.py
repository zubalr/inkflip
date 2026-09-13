#!/usr/bin/env python3
"""Record the generated static dist so the distribution checker can verify it
(T47 preparation).

Runs the documented production build (`bun run build`) from the repository
root, then walks `apps/web/dist/` and writes a deterministic manifest
(relative path + SHA-256 per file) to the local ignored working tree. The
distribution checker verifies the real built outputs against this manifest:

  python3 scripts/distribution/record_dist.py            # build + record
  python3 scripts/check_distribution.py --release \
      --dist-manifest .private/distribution/dist-manifest.json

The manifest lives in the git-ignored working tree on purpose: dist output is
regenerated, not committed. Re-record after every build that changes the
bundle. Exit codes: 0 pass, 1 build failure, 2 config error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "apps" / "web" / "dist"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=".private/distribution/dist-manifest.json")
    parser.add_argument("--skip-build", action="store_true", help="record the existing dist without rebuilding")
    args = parser.parse_args()

    if not args.skip_build:
        build = subprocess.run(["bun", "run", "build"], cwd=ROOT)
        if build.returncode != 0:
            print("build failed", file=sys.stderr)
            return 1
    if not DIST.is_dir():
        print("config error: apps/web/dist does not exist", file=sys.stderr)
        return 2

    files = []
    for path in sorted(DIST.rglob("*")):
        if path.is_file() and not path.is_symlink():
            files.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = {
        "schema_version": "1.0.0",
        "kind": "inkflip-dist-manifest",
        "dist_root": "apps/web/dist",
        "file_count": len(files),
        # Release-contract prohibition (this project's distribution policy):
        # built source maps and other development material are not shipped.
        "reject_patterns": ["\\.map$", "__pycache__", "\.log$"],
        "files": files,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"recorded {len(files)} dist files -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
