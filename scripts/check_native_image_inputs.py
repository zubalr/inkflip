#!/usr/bin/env python3
"""Fail closed when production native image inputs are missing.

The hardened Dockerfile copies:
  native/dist/                  hashed wheels (T47 third-party + Inkflip wheel)
  release/native-requirements.lock
  release/node/  release/models/  release/notices/

This script does not download anything. A missing bundle is an error with
the exact path, not a silent fallback to PyPI or Dockerfile.checkout.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELS = ROOT / "native" / "dist"
LOCK = ROOT / "release" / "native-requirements.lock"
ASSETS = (
    ROOT / "release" / "node",
    ROOT / "release" / "models",
    ROOT / "release" / "notices",
)


def problems() -> list[str]:
    missing: list[str] = []
    if not WHEELS.is_dir():
        missing.append(f"missing wheel directory: {WHEELS}")
    else:
        wheels = list(WHEELS.glob("*.whl"))
        if not wheels:
            missing.append(f"no .whl files in {WHEELS}")
        else:
            inkflip = [p for p in wheels if p.name.startswith("inkflip-")]
            if not inkflip:
                missing.append(f"Inkflip application wheel missing under {WHEELS} (third-party wheels are not a substitute)")
    if not LOCK.is_file():
        missing.append(f"missing hashed requirements lock: {LOCK}")
    else:
        text = LOCK.read_text(encoding="utf-8")
        if "inkflip==" not in text and not any(line.startswith("inkflip==") for line in text.splitlines()):
            missing.append(f"{LOCK} does not pin inkflip (T47 third-party lock is incomplete for ENTRYPOINT inkflip)")
        if "--hash=" not in text:
            missing.append(f"{LOCK} has no --hash= pins")
    for path in ASSETS:
        if not path.is_dir():
            missing.append(f"missing required asset directory: {path}")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check production native image inputs")
    parser.add_argument("--inventory", action="store_true", help="list gaps without implying the image is buildable")
    args = parser.parse_args(argv)
    gaps = problems()
    if args.inventory:
        print("\n".join(gaps) if gaps else "native image inputs: complete")
        return 0
    if gaps:
        print("inkflip: production native image inputs incomplete:", file=sys.stderr)
        for item in gaps:
            print(f"  {item}", file=sys.stderr)
        print("Use Dockerfile.checkout only as a weaker local helper; do not treat it as the hashed release image.", file=sys.stderr)
        return 2
    print("native image inputs: complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
