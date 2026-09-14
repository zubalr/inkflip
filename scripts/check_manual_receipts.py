#!/usr/bin/env python3
"""Validate committed manual receipts for a named evidence kind.

Used by T37 (accessibility), T46 (compatibility) and T53 (release).

The registered acceptance command is:

    python scripts/check_manual_receipts.py <accessibility|compatibility|release>

It fails closed: incomplete required coverage, absent/empty/malformed
evidence, identity mismatches and invalid status/schema do not certify.
Required profiles are taken from the task contracts, not from whichever
rows a receipt happens to contain.

Optional inventory mode lists incomplete profiles without certifying:

    python scripts/check_manual_receipts.py compatibility --inventory
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

KIND_RELATIVE = {
    "compatibility": Path("docs") / "compatibility" / "manual-receipt.json",
    "accessibility": Path("docs") / "compatibility" / "accessibility-manual-receipt.json",
    "release": Path("artifacts") / "gates" / "G4" / "manual-receipt.json",
}
KINDS = {kind: ROOT / rel for kind, rel in KIND_RELATIVE.items()}

SCHEMA_VERSION = "1.0.0"
ACCEPTANCE_OVERALL = {"complete"}
PLATFORM_STATUSES = {"executed", "blocked", "unavailable", "pending"}
REQUIRED_KEYS = ("schema_version", "kind", "status", "platforms")

# Contract sources:
# - compatibility: planning/quality/PERFORMANCE_AND_COMPATIBILITY.md (Chromium
#   family, Firefox, Safari, Linux x86_64 native) and TEST-46. Playwright
#   WebKit is not physical Safari. Node PDF.js is not a browser profile.
# - accessibility: TEST-37 / planning/product/ACCESSIBILITY.md A01, A05, A08,
#   A10 plus amount-alternative announcement.
# - release: TEST-53 "all required profiles covered" = union of the above.
# Previous Chromium/Firefox ESR/Safari-previous remain T53/Devin format work.
_COMPATIBILITY = (
    {"id": "chromium", "aliases": frozenset({"chromium", "chromium-family", "chrome", "google-chrome", "chromium-current"})},
    {"id": "firefox", "aliases": frozenset({"firefox", "firefox-stable", "firefox-esr"})},
    {"id": "safari", "aliases": frozenset({"safari", "safari-macos", "safari-ios", "safari-current"})},
    {"id": "linux-amd64-native", "aliases": frozenset({"linux-amd64-native", "linux-x86_64", "linux-amd64"})},
)
# 2026-09-13 owner macOS-only release profile. Historical frozen required
# set above is unchanged. linux-amd64 / Windows / previous-stable / ESR are
# deferred, not certified. Safari inability is Mac-local, not a Linux gate.
_MACOS_COMPATIBILITY = (
    {"id": "chromium", "aliases": frozenset({"chromium", "chromium-family", "chrome", "google-chrome", "chromium-current"})},
    {"id": "firefox", "aliases": frozenset({"firefox", "firefox-stable"})},
)
_FORGED_SAFARI = ("webkit", "playwright webkit", "webkit-safari")
_FORGED_LINUX_NATIVE = ("qemu", "orbstack", "emulat", "rosetta")
_ACCESSIBILITY = (
    {"id": "keyboard", "aliases": frozenset({"keyboard", "a01"})},
    {"id": "amount-alternatives", "aliases": frozenset({"amount-alternatives", "amount-alternative"})},
    {"id": "zoom-400", "aliases": frozenset({"zoom-400", "a05", "reflow-400"})},
    {"id": "reduced-motion", "aliases": frozenset({"reduced-motion", "a08"})},
    {"id": "screen-reader-nvda-firefox", "aliases": frozenset({"screen-reader-nvda-firefox", "nvda-firefox", "a10-nvda"})},
    {"id": "screen-reader-voiceover-safari", "aliases": frozenset({"screen-reader-voiceover-safari", "voiceover-safari", "a10-voiceover"})},
)
# AT profiles the owner excluded from the macOS release scope. Waiving a
# required manual leg is an owner decision recorded in the receipt's
# 'unavailable' rows — it is never used to fabricate executed evidence, and
# the historical (full) profile still requires every profile.
_MACOS_WAIVED_AT = frozenset(
    {"screen-reader-nvda-firefox", "screen-reader-voiceover-safari"}
)


def required_profiles(kind: str, release_profile: str = "historical") -> list[dict[str, Any]]:
    if kind == "compatibility":
        if release_profile == "macos":
            return [dict(item) for item in _MACOS_COMPATIBILITY]
        return [dict(item) for item in _COMPATIBILITY]
    if kind == "accessibility":
        if release_profile == "macos":
            # Owner-approved macOS scope: NVDA/Firefox is a Windows AT profile
            # (deferred 2026-09-13, pdf-u28); VoiceOver/Safari was waived by the
            # owner on 2026-09-14. Both rows stay recorded as unavailable in the
            # receipt — waived, never fabricated. The historical profile below
            # still requires all six.
            return [
                dict(item)
                for item in _ACCESSIBILITY
                if item["id"] not in _MACOS_WAIVED_AT
            ]
        return [dict(item) for item in _ACCESSIBILITY]
    if kind == "release":
        if release_profile == "macos":
            return [dict(item) for item in _MACOS_COMPATIBILITY] + [
                item
                for item in _ACCESSIBILITY
                if item["id"] not in _MACOS_WAIVED_AT
            ]
        return [dict(item) for item in _COMPATIBILITY] + [dict(item) for item in _ACCESSIBILITY]
    raise KeyError(kind)


def _kind_path(kind: str, root: Path) -> Path:
    return root / KIND_RELATIVE[kind]


def _is_nonempty_identity(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    for item in value.values():
        if isinstance(item, str) and item.strip():
            return True
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            return True
        if isinstance(item, dict) and _is_nonempty_identity(item):
            return True
    return False


def _evidence_error(root: Path, evidence: Any) -> str | None:
    if not isinstance(evidence, list) or not evidence:
        return "evidence must be a nonempty list of repository-relative files"
    root_resolved = root.resolve()
    for rel in evidence:
        if not isinstance(rel, str) or not rel.strip() or rel.strip() != rel:
            return f"malformed evidence path: {rel!r}"
        raw = root / rel
        if raw.is_symlink():
            return f"symlink evidence is not allowed: {rel}"
        try:
            resolved = raw.resolve()
            resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            return f"evidence path escapes repository or is unreadable: {rel}"
        if not resolved.is_file():
            return f"missing evidence file: {rel}"
        if resolved.stat().st_size == 0:
            return f"empty evidence file: {rel}"
        if resolved.is_symlink():
            return f"symlink evidence is not allowed: {rel}"
    return None


def _identity_blob(row: dict[str, Any]) -> str:
    identity = row.get("identity")
    if not isinstance(identity, dict):
        return ""
    return json.dumps(identity, ensure_ascii=True).lower()


def _forged_or_stale(row: dict[str, Any]) -> str | None:
    row_id = str(row.get("id") or "")
    blob = _identity_blob(row)
    if row.get("status") == "executed" and row_id in {"safari", "safari-macos", "safari-current"}:
        if any(token in blob for token in _FORGED_SAFARI):
            return "forged platform flag: Playwright WebKit is not Safari"
    if row.get("status") == "executed" and row_id in {"linux-amd64-native", "linux-x86_64", "linux-amd64"}:
        if any(token in blob for token in _FORGED_LINUX_NATIVE):
            return "forged platform flag: emulated/qemu linux is not native amd64"
    if row.get("status") == "executed":
        identity = row.get("identity")
        if isinstance(identity, dict):
            digest = identity.get("source_sha256") or identity.get("git_head")
            if isinstance(digest, str) and digest.strip() in {"", "0" * 64, "stale"}:
                return "stale source identity"
            if row_id in {"chromium", "firefox"} and not str(identity.get("browser") or "").strip():
                return "stale source identity: executed browser missing browser version"
    return None


def _row_satisfies(row: dict[str, Any], profile: dict[str, Any], root: Path) -> str | None:
    """Return None if this executed row covers the profile, else a reason."""
    if row.get("id") not in profile["aliases"]:
        return "id does not match required profile"
    forged = _forged_or_stale(row)
    if forged:
        return forged
    status = row.get("status")
    if status != "executed":
        return f"status is {status!r}, not executed"
    evidence_error = _evidence_error(root, row.get("evidence"))
    if evidence_error:
        return evidence_error
    if not _is_nonempty_identity(row.get("identity")):
        return "executed platform missing identity"
    return None


def _coverage(
    kind: str,
    platforms: list[Any],
    root: Path,
    release_profile: str = "historical",
) -> list[tuple[str, str | None]]:
    rows = [row for row in platforms if isinstance(row, dict)]
    results: list[tuple[str, str | None]] = []
    for profile in required_profiles(kind, release_profile):
        reasons: list[str] = []
        matched = False
        for row in rows:
            if row.get("id") not in profile["aliases"]:
                continue
            matched = True
            reason = _row_satisfies(row, profile, root)
            if reason is None:
                results.append((profile["id"], None))
                break
            reasons.append(f"{row.get('id')}: {reason}")
        else:
            if not matched:
                results.append((profile["id"], "missing from receipt"))
            else:
                results.append((profile["id"], "; ".join(reasons)))
    return results


def check_kind(
    kind: str,
    root: Path | None = None,
    mode: str = "acceptance",
    release_profile: str = "historical",
) -> tuple[int, str]:
    if kind not in KIND_RELATIVE:
        return 2, f"unknown receipt kind: {kind}"
    if mode not in {"acceptance", "inventory"}:
        return 2, f"unknown mode: {mode}"
    base = ROOT if root is None else root
    path = _kind_path(kind, base)
    if not path.is_file() or path.stat().st_size == 0:
        owned = " (owned by another task)" if kind != "compatibility" else ""
        return 1, f"{kind}: empty or missing receipt{owned}: {path}"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return 1, f"{kind}: malformed JSON: {exc}"
    if not isinstance(data, dict):
        return 1, f"{kind}: receipt must be a JSON object"

    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        return 1, f"{kind}: receipt missing keys {missing}"
    if data.get("schema_version") != SCHEMA_VERSION:
        return 1, f"{kind}: unsupported schema_version {data.get('schema_version')!r}"
    if data.get("kind") != kind:
        return 1, f"{kind}: receipt kind {data.get('kind')!r} does not match"
    if data.get("status") not in {"complete", "partial", "blocked", "pending"}:
        return 1, f"{kind}: invalid overall status {data.get('status')!r}"
    if not _is_nonempty_identity(data.get("host")):
        return 1, f"{kind}: receipt host identity is missing"

    platforms = data["platforms"]
    if not isinstance(platforms, list) or not platforms:
        return 1, f"{kind}: platforms must be a nonempty list"
    for row in platforms:
        if not isinstance(row, dict):
            return 1, f"{kind}: platform row is not an object: {row!r}"
        if row.get("status") not in PLATFORM_STATUSES:
            return 1, f"{kind}: invalid platform status {row}"

    if (
        mode == "acceptance"
        and release_profile == "historical"
        and data.get("status") not in ACCEPTANCE_OVERALL
    ):
        return 1, (
            f"{kind}: overall status {data.get('status')!r} is incomplete; "
            "acceptance requires status 'complete' and every required profile executed"
        )

    structural: list[str] = []
    for row in platforms:
        if not isinstance(row, dict):
            structural.append(f"{kind}: platform row is not an object: {row!r}")
            continue
        if "id" not in row or not isinstance(row.get("id"), str) or not row["id"].strip():
            structural.append(f"{kind}: platform missing id: {row}")
        if row.get("status") not in PLATFORM_STATUSES:
            structural.append(f"{kind}: invalid platform status {row}")
        if row.get("status") == "executed":
            evidence_error = _evidence_error(base, row.get("evidence"))
            if evidence_error:
                structural.append(f"{kind}: {evidence_error} ({row.get('id')})")
            if not _is_nonempty_identity(row.get("identity")):
                structural.append(f"{kind}: executed platform missing identity: {row.get('id')}")
            forged = _forged_or_stale(row)
            if forged:
                structural.append(f"{kind}: {forged} ({row.get('id')})")

    coverage = _coverage(kind, platforms, base, release_profile)
    incomplete = [(name, reason) for name, reason in coverage if reason]
    inventory_lines = [
        f"{kind} inventory: {len(coverage) - len(incomplete)}/{len(coverage)} required profiles complete"
    ]
    for name, reason in coverage:
        if reason is None:
            inventory_lines.append(f"- {name}: complete")
        else:
            inventory_lines.append(f"- {name}: incomplete ({reason})")
    if structural:
        inventory_lines.append("structural issues:")
        inventory_lines.extend(f"- {item}" for item in structural)

    if mode == "inventory":
        return 0, "\n".join(inventory_lines)

    if structural:
        return 1, "\n".join(structural)
    if release_profile == "historical" and data.get("status") not in ACCEPTANCE_OVERALL:
        return 1, (
            f"{kind}: overall status {data.get('status')!r} is incomplete; "
            "acceptance requires status 'complete'"
        )
    if incomplete:
        details = "; ".join(f"{name} ({reason})" for name, reason in incomplete)
        return 1, f"{kind}: incomplete required coverage: {details}"
    return 0, ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        usage="check_manual_receipts.py <accessibility|compatibility|release> [--inventory]"
    )
    parser.add_argument("kind", choices=sorted(KIND_RELATIVE))
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="list incomplete required profiles without certifying acceptance",
    )
    parser.add_argument(
        "--release-profile",
        choices=("historical", "macos"),
        default="historical",
        help="historical keeps frozen Windows/Linux/Safari requirements; macos evaluates the 2026-09-13 Mac-only release",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return 2 if code is None else int(code)

    mode = "inventory" if args.inventory else "acceptance"
    code, message = check_kind(
        args.kind, root=ROOT, mode=mode, release_profile=args.release_profile
    )
    if args.inventory:
        print(message)
        return code
    if code == 0:
        path = _kind_path(args.kind, ROOT)
        data = json.loads(path.read_text(encoding="utf-8"))
        print(f"{args.kind}: ok ({len(data['platforms'])} platforms)")
        return 0
    print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
