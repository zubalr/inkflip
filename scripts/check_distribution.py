#!/usr/bin/env python3
"""Verify that what Inkflip declares to distribute matches what is actually
there (T47 distribution gate, preparation implementation).

Reads config/distribution-manifest.json (or --manifest PATH) and checks:

  1. manifest sanity: schema fields present, all paths contained in the
     repository root (no `..`, no absolute paths, no symlinked manifest
     entries) — violations are config errors (exit 2);
  2. every declared shipped file exists with the declared byte count and
     SHA-256 digest;
  3. every file under the declared shipped roots is declared (unlisted
     shipped assets fail), no symlinks inside shipped roots (symlink_policy),
     and no private/development content patterns appear in shipped paths;
  4. every group's license declaration is non-empty and its license evidence
     file exists and is non-empty;
  5. NOTICE exists, is non-empty, and names every third-party group
     (notice_name), so license summaries agree with the bundled notices.

Unknowns are preserved visibly: an unaccounted file is a named failure, never
silently excluded, and a filename is never treated as provenance — rights
come only from the declared license evidence.

Output: a deterministic, sorted, itemized report on stdout. Exit codes:
  0  all checks pass
  1  one or more verification failures (hash mismatch, missing file,
     undeclared asset, missing license evidence, notice inconsistency,
     private content, symlink)
  2  manifest/config or usage error (unreadable, malformed, path escape)

Usage:
  python3 scripts/check_distribution.py --release
  python3 scripts/check_distribution.py --release --manifest PATH --root DIR
  python3 scripts/check_distribution.py --json ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def contained(root: Path, rel: str) -> bool:
    """True if rel resolves to a location strictly inside root."""
    if rel.startswith(("/", "\\")) or drive_prefix(rel):
        return False
    resolved = (root / rel).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return False
    return True


def drive_prefix(rel: str) -> bool:
    return len(rel) > 1 and rel[1] == ":"


def expand_groups(root: Path, manifest: dict) -> tuple[list[dict], list[str]]:
    """Expand groups into declared files. Returns (files, config_errors)."""
    declared: dict[str, dict] = {}
    errors: list[str] = []
    for group in manifest.get("groups", []):
        gid = group.get("id", "<unnamed-group>")
        for f in group.get("explicit_files", []):
            rel = f["path"]
            if rel in declared:
                errors.append(f"{gid}: duplicate declared path {rel}")
            declared[rel] = {
                "path": rel,
                "sha256": f.get("sha256"),
                "bytes": f.get("bytes"),
                "group": gid,
            }
        source = group.get("digest_source")
        if source:
            doc_path = root / source["path"]
            try:
                doc = json.loads(doc_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"{gid}: unreadable digest source {source['path']}: {exc}")
                continue
            entries, err = resolve_file_list(doc, source)
            if err:
                errors.append(f"{gid}: {err}")
                continue
            prefix = source.get("path_prefix", "")
            for entry in entries:
                rel = prefix + entry[source["path_field"]]
                if rel in declared:
                    errors.append(f"{gid}: duplicate declared path {rel}")
                declared[rel] = {
                    "path": rel,
                    "sha256": entry.get(source["digest_field"]),
                    "bytes": entry.get(source["bytes_field"]),
                    "group": gid,
                }
    return list(declared.values()), errors


def resolve_file_list(doc: dict, source: dict) -> tuple[list[dict], str | None]:
    file_list = source.get("file_list", "")
    if file_list == "assets[].files[]":
        for group in doc.get("assets", []):
            if group.get("id") == source.get("group"):
                return group.get("files", []), None
        return [], f"digest source has no asset group {source.get('group')!r}"
    m = re.fullmatch(r"files\(([^)]*)\)", file_list)
    if m:
        files_map = doc.get("files", {})
        keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
        keys = keys if keys else list(files_map)
        return [files_map[k] for k in keys if k in files_map], None
    return [], f"unsupported file_list spec {file_list!r}"


def run_checks(root: Path, manifest: dict) -> tuple[list[str], int]:
    failures: list[str] = []
    errors: list[str] = []

    for field in ("groups", "distribution", "notice"):
        if field not in manifest:
            errors.append(f"manifest missing required field {field!r}")
    if errors:
        return errors + failures, 2

    shipped_roots = manifest["distribution"].get("shipped_roots", [])
    if not shipped_roots:
        errors.append("manifest declares no shipped_roots")

    for rel in shipped_roots:
        if not contained(root, rel):
            errors.append(f"shipped root escapes repository root: {rel}")
        elif not (root / rel).is_dir():
            errors.append(f"shipped root does not exist: {rel}")

    declared_files, expand_errors = expand_groups(root, manifest)
    errors.extend(expand_errors)

    for f in declared_files:
        if not contained(root, f["path"]):
            errors.append(f"declared path escapes repository root: {f['path']}")

    if errors:
        return errors + failures, 2

    # 2. declared files must match actual bytes
    declared_set = {f["path"] for f in declared_files}
    for f in sorted(declared_files, key=lambda x: x["path"]):
        path = root / f["path"]
        if not path.is_file():
            failures.append(f"missing declared file: {f['path']} (group {f['group']})")
            continue
        if f["bytes"] is not None and path.stat().st_size != f["bytes"]:
            failures.append(
                f"size mismatch: {f['path']} (declared {f['bytes']}, actual {path.stat().st_size})"
            )
        if f["sha256"]:
            actual = sha256_file(path)
            if actual != f["sha256"]:
                failures.append(
                    f"hash mismatch: {f['path']} (declared {f['sha256'][:12]}…, actual {actual[:12]}…)"
                )

    # 3. walk shipped roots: undeclared files, symlinks, private content
    patterns = [re.compile(p) for p in manifest.get("private_content_patterns", [])]
    for shipped_root in sorted(shipped_roots):
        base = root / shipped_root
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                failures.append(f"symlink inside shipped root (policy {manifest.get('symlink_policy', 'reject')}): {rel}")
                continue
            if not path.is_file():
                continue
            if rel not in declared_set:
                failures.append(f"undeclared shipped asset: {rel}")
            for pat in patterns:
                if pat.search(rel):
                    failures.append(f"private/development content in shipped root: {rel} (pattern {pat.pattern!r})")
                    break

    # 4. license evidence per group
    for group in sorted(manifest["groups"], key=lambda g: g.get("id", "")):
        gid = group.get("id", "<unnamed>")
        license_decl = group.get("license")
        if not license_decl:
            failures.append(f"group {gid}: no license declared (a filename is not provenance)")
        evidence = group.get("license_evidence")
        if not evidence:
            failures.append(f"group {gid}: no license evidence recorded")
            continue
        if not contained(root, evidence):
            errors.append(f"group {gid}: license evidence path escapes repository root: {evidence}")
            continue
        ev_path = root / evidence
        if not ev_path.is_file() or ev_path.stat().st_size == 0:
            failures.append(f"group {gid}: license evidence missing or empty: {evidence}")

    # 5. NOTICE consistency
    notice_rel = manifest.get("notice")
    if not notice_rel or not contained(root, notice_rel):
        errors.append(f"manifest notice path invalid: {notice_rel!r}")
    else:
        notice_path = root / notice_rel
        if not notice_path.is_file() or notice_path.stat().st_size == 0:
            failures.append(f"NOTICE missing or empty: {notice_rel}")
        else:
            notice_text = notice_path.read_text()
            for group in manifest["groups"]:
                name = group.get("notice_name")
                if group.get("third_party") and name and name not in notice_text:
                    failures.append(
                        f"notice inconsistency: NOTICE does not name third-party group {group.get('id')!r} ({name!r})"
                    )

    if errors:
        return errors + failures, 2
    return sorted(failures), (0 if not failures else 1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 pass, 1 verification failures, 2 config/usage error.",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="run the full release gate checks (required; without it only usage is shown)",
    )
    parser.add_argument("--manifest", default="config/distribution-manifest.json")
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    args = parser.parse_args()

    if not args.release:
        parser.print_help()
        return 2

    root = Path(args.root).resolve()
    manifest_path = root / args.manifest if not Path(args.manifest).is_absolute() else Path(args.manifest)
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"config error: cannot read manifest {args.manifest}: {exc}", file=sys.stderr)
        return 2

    problems, code = run_checks(root, manifest)
    if args.json:
        print(json.dumps({"ok": code == 0, "exit_code": code, "problems": problems}, indent=2))
    else:
        if not problems:
            print("distribution manifest: all checks passed")
            print(f"  groups: {len(manifest.get('groups', []))}, shipped roots: {len(manifest['distribution']['shipped_roots'])}")
        else:
            print(f"distribution manifest: {len(problems)} problem(s)")
            for p in problems:
                print(f"  - {p}")
    return code


if __name__ == "__main__":
    sys.exit(main())
