#!/usr/bin/env python3
"""Validate committed manual receipts for a named evidence kind.

Used by T37 (accessibility), T46 (compatibility) and T53 (release).
T46 implements the compatibility kind against docs/compatibility/.
Other kinds fail closed if their receipt files are missing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

KINDS = {
    "compatibility": ROOT / "docs" / "compatibility" / "manual-receipt.json",
    "accessibility": ROOT / "docs" / "compatibility" / "accessibility-manual-receipt.json",
    "release": ROOT / "artifacts" / "gates" / "G4" / "manual-receipt.json",
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] in {"-h", "--help"}:
        print("usage: check_manual_receipts.py <accessibility|compatibility|release>", file=sys.stderr)
        return 2
    kind = argv[0]
    if kind not in KINDS:
        print(f"unknown receipt kind: {kind}", file=sys.stderr)
        return 2
    path = KINDS[kind]
    if kind != "compatibility":
        if not path.is_file() or path.stat().st_size == 0:
            print(f"{kind}: receipt missing (owned by another task): {path}", file=sys.stderr)
            return 1
    if not path.is_file() or path.stat().st_size == 0:
        print(f"{kind}: empty or missing receipt: {path}", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ("schema_version", "kind", "status", "platforms")
    missing = [key for key in required if key not in data]
    if missing:
        print(f"{kind}: receipt missing keys {missing}", file=sys.stderr)
        return 1
    if data.get("kind") != kind:
        print(f"{kind}: receipt kind {data.get('kind')!r} does not match", file=sys.stderr)
        return 1
    platforms = data["platforms"]
    if not isinstance(platforms, list) or not platforms:
        print(f"{kind}: platforms must be a nonempty list", file=sys.stderr)
        return 1
    for row in platforms:
        if row.get("status") not in {"executed", "blocked", "unavailable", "pending"}:
            print(f"{kind}: invalid platform status {row}", file=sys.stderr)
            return 1
        if row.get("status") == "executed" and not row.get("evidence"):
            print(f"{kind}: executed platform missing evidence: {row}", file=sys.stderr)
            return 1
    print(f"{kind}: ok ({len(platforms)} platforms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
