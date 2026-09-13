#!/usr/bin/env python3
"""Validate existing Inkflip performance receipts. Never generates benchmarks.

``--cli`` is required. A missing, empty, or malformed receipt is a diagnostic
failure, not a traceback. ``--mode inventory`` lists incomplete/unavailable
criteria and exits 0. ``--mode accept`` exits 1 for any unmet mandatory
criterion. A browser JSON that only contains ``distribution_claim: n>=30``
is not accepted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import performance_receipt as receipt  # noqa: E402


def _settings(root: Path) -> dict:
    path = root / "planning" / "config" / "settings.json"
    data, error = receipt.load_json_object(path)
    if error or data is None:
        return {}
    return data


def _print_problems(problems: list[str], *, mode: str, profile: str) -> None:
    for line in receipt.inventory_lines(problems, profile=profile, mode=mode):
        stream = sys.stdout if mode == "inventory" else sys.stderr
        print(line, file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", default="local-mac")
    parser.add_argument("--mode", choices=("inventory", "accept"), default="accept")
    parser.add_argument(
        "--cli",
        type=Path,
        help="existing CLI or combined receipt (required; this wrapper does not re-run measure_performance.py)",
    )
    parser.add_argument(
        "--browser",
        type=Path,
        default=None,
        help="optional browser JSON from tests/performance/budgets.spec.ts",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return 2 if code is None else int(code)

    root = args.root.resolve()
    if args.cli is None:
        print("ACCEPT-FAIL missing --cli receipt; checker does not generate measurements", file=sys.stderr)
        return 1

    cli_path = args.cli if args.cli.is_absolute() else root / args.cli
    body, error = receipt.load_json_object(cli_path)
    if error or body is None:
        print(f"ACCEPT-FAIL {error}", file=sys.stderr)
        return 1

    browser_path = args.browser
    if browser_path is None:
        default_browser = root / "artifacts" / "performance" / "browser-local-mac.json"
        browser_path = default_browser if default_browser.is_file() else None
    elif not browser_path.is_absolute():
        browser_path = root / browser_path

    if browser_path is not None:
        browser, browser_error = receipt.load_json_object(browser_path)
        if browser_error or browser is None:
            print(f"ACCEPT-FAIL {browser_error}", file=sys.stderr)
            return 1
        body = dict(body)
        body["browser"] = browser

    settings = _settings(root)
    current = receipt.source_binding(root)
    try:
        problems = receipt.validate_receipt(
            body,
            mode=args.mode,
            profile=args.profile,
            settings=settings,
            current_binding=current,
        )
    except Exception as error:  # pragma: no cover — last-resort diagnostic
        print(f"ACCEPT-FAIL unsupported malformed input: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    if args.mode == "inventory":
        _print_problems(problems, mode="inventory", profile=args.profile)
        return 0
    if problems:
        print("performance accept: unmet mandatory criteria", file=sys.stderr)
        for item in problems:
            print(f"ACCEPT-FAIL {item}", file=sys.stderr)
        return 1
    print(f"performance accept: ok ({cli_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
