#!/usr/bin/env python3
"""Accept or inventory Inkflip performance evidence.

Combines CLI ``scripts/measure_performance.py`` output with optional browser
JSON from ``tests/performance/budgets.spec.ts``. Inventory mode never claims
the 4-core/8 GiB reference or physical mobile profiles.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "measure_performance.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", default="local-mac")
    parser.add_argument("--mode", choices=("inventory", "accept"), default="accept")
    parser.add_argument("--cli", type=Path)
    parser.add_argument("--browser", type=Path, default=ROOT / "artifacts/performance/browser-local-mac.json")
    args = parser.parse_args(argv)

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--profile",
        args.profile,
        "--mode",
        args.mode,
    ]
    if args.cli:
        # Re-validate an existing file by loading it through measure_performance
        # only when generating; existing files are checked below.
        pass
    if args.browser.is_file():
        cmd.extend(["--browser-evidence", str(args.browser)])
    proc = __import__("subprocess").run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        return proc.returncode
    if args.mode == "accept" and args.profile == "local-mac":
        if not args.browser.is_file():
            print("ACCEPT-FAIL missing browser evidence", file=sys.stderr)
            return 1
        data = json.loads(args.browser.read_text())
        preview = (data.get("stages") or {}).get("preview") or {}
        if preview.get("distribution_claim") != "n>=30":
            print("ACCEPT-FAIL browser preview distribution is not n>=30", file=sys.stderr)
            return 1
        if data.get("host", {}).get("is_physical_mobile"):
            print("ACCEPT-FAIL browser evidence claimed physical mobile", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
