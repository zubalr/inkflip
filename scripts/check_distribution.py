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


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_declared_entry(gid: str, path, sha256, nbytes) -> list[str]:
    """Strict per-entry integrity validation. Integrity fields are required:
    a declared file without a byte count and a well-formed SHA-256 digest is
    a config error (the recovery-review gap: absent fields were accepted)."""
    errors: list[str] = []
    label = f"{gid}: entry {path!r}"
    if not isinstance(path, str) or not path:
        return [f"{gid}: entry with missing or non-string path"]
    if sha256 is None:
        errors.append(f"{label}: missing required sha256 digest (a filename is not integrity)")
    elif not isinstance(sha256, str):
        errors.append(f"{label}: sha256 must be a string, got {type(sha256).__name__}")
    elif not SHA256_RE.match(sha256):
        errors.append(f"{label}: malformed sha256 digest {sha256!r} (expected 64 lowercase hex chars)")
    if nbytes is None:
        errors.append(f"{label}: missing required byte count")
    elif isinstance(nbytes, bool):
        errors.append(f"{label}: bytes must be an integer, got boolean")
    elif not isinstance(nbytes, int):
        errors.append(f"{label}: bytes must be an integer, got {type(nbytes).__name__}")
    elif nbytes < 0:
        errors.append(f"{label}: negative byte count {nbytes}")
    return [e for e in errors if e]


def expand_groups(root: Path, manifest: dict) -> tuple[list[dict], list[str]]:
    """Expand groups into declared files. Returns (files, config_errors)."""
    declared: dict[str, dict] = {}
    errors: list[str] = []
    groups = manifest.get("groups")
    if not isinstance(groups, list):
        return [], ["manifest: 'groups' must be a list of group objects"]
    for idx, group in enumerate(groups):
        if not isinstance(group, dict):
            errors.append(f"manifest: groups[{idx}] is not an object")
            continue
        gid = group.get("id")
        if not isinstance(gid, str) or not gid:
            errors.append(f"manifest: groups[{idx}] missing a non-empty string 'id'")
            continue
        if gid in {g.get("id") for g in groups[:idx] if isinstance(g, dict)}:
            errors.append(f"manifest: duplicate group id {gid!r}")
        explicit = group.get("explicit_files", [])
        if not isinstance(explicit, list):
            errors.append(f"{gid}: explicit_files must be a list")
            continue
        for position, f in enumerate(explicit):
            if not isinstance(f, dict):
                errors.append(f"{gid}: explicit_files entry is not an object")
                continue
            rel = f.get("path")
            key = rel if isinstance(rel, str) else f"<non-string path at position {position}>"
            if key in declared:
                errors.append(f"{gid}: duplicate declared path {key}")
                continue
            errors.extend(validate_declared_entry(gid, rel, f.get("sha256"), f.get("bytes")))
            declared[key] = {
                "path": rel,
                "sha256": f.get("sha256"),
                "bytes": f.get("bytes"),
                "group": gid,
                "invalid": bool([e for e in errors if e.startswith(f"{gid}: entry {rel!r}")]),
            }
        source = group.get("digest_source")
        if source is not None:
            if not isinstance(source, dict):
                errors.append(f"{gid}: digest_source must be an object")
                continue
            required_source_keys = ("path", "group", "file_list", "path_field", "digest_field", "bytes_field")
            missing_keys = [k for k in required_source_keys if k not in source]
            if missing_keys:
                # An explicitly incomplete selector must not silently shrink
                # the expected set: it is a config error, not a skip.
                errors.append(f"{gid}: digest_source missing required key(s): {missing_keys}")
                continue
            doc_path = root / source["path"]
            if not contained(root, source["path"]):
                errors.append(f"{gid}: digest source path escapes the repository root: {source['path']}")
                continue
            if not doc_path.is_file():
                errors.append(f"{gid}: digest source is not a file: {source['path']}")
                continue
            try:
                doc = json.loads(doc_path.read_text())
            except json.JSONDecodeError as exc:
                errors.append(f"{gid}: malformed JSON in digest source {source['path']}: {exc}")
                continue
            except (OSError) as exc:
                errors.append(f"{gid}: unreadable digest source {source['path']}: {exc}")
                continue
            entries, err = resolve_file_list(doc, source)
            if err:
                errors.append(f"{gid}: {err}")
                continue
            prefix = source.get("path_prefix", "")
            for entry in entries:
                if not isinstance(entry, dict):
                    errors.append(f"{gid}: digest-source entry is not an object")
                    continue
                try:
                    rel = prefix + entry[source["path_field"]]
                except (KeyError, TypeError):
                    errors.append(f"{gid}: digest-source entry missing path field {source['path_field']!r}")
                    continue
                if rel in declared:
                    errors.append(f"{gid}: duplicate declared path {rel}")
                    continue
                sha = entry.get(source["digest_field"])
                nbytes = entry.get(source["bytes_field"])
                errors.extend(validate_declared_entry(gid, rel, sha, nbytes))
                declared[rel] = {
                    "path": rel,
                    "sha256": sha,
                    "bytes": nbytes,
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


def run_checks(root: Path, manifest: dict, dist_manifest_rel: str | None = None) -> tuple[list[str], list[str], int]:
    failures: list[str] = []
    errors: list[str] = []
    scope_notes: list[str] = []

    for field in ("groups", "distribution", "notice"):
        if field not in manifest:
            errors.append(f"manifest missing required field {field!r}")
    if errors:
        return errors + failures, [], 2

    shipped_roots = manifest["distribution"].get("shipped_roots", [])
    has_surface = bool(shipped_roots) or bool(manifest.get("native_bundle")) or bool(dist_manifest_rel)
    if not has_surface:
        errors.append("manifest declares no verification surface (shipped_roots/native_bundle/dist_manifest)")

    for rel in shipped_roots:
        if not contained(root, rel):
            errors.append(f"shipped root escapes repository root: {rel}")
        elif not (root / rel).is_dir():
            errors.append(f"shipped root does not exist: {rel}")

    declared_files, expand_errors = expand_groups(root, manifest)
    errors.extend(expand_errors)

    for f in declared_files:
        if not isinstance(f["path"], str):
            continue  # already reported via validate_declared_entry
        if not contained(root, f["path"]):
            errors.append(f"declared path escapes repository root: {f['path']}")

    if errors:
        return errors + failures, [], 2

    # 2. declared files must match actual bytes
    declared_set = {f["path"] for f in declared_files}
    for f in sorted(declared_files, key=lambda x: x["path"]):
        if f.get("invalid"):
            continue  # integrity declaration already reported as a config error
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

    # 6. native bundle surface (declared third-party dependency inputs)
    nb = manifest.get("native_bundle")
    if nb:
        failures.extend(check_native_bundle(root, nb, scope_notes))

    # 7. generated static dist surface (optional --dist-manifest)
    if dist_manifest_rel:
        failures.extend(check_dist(root, dist_manifest_rel))

    if errors:
        return errors + failures, [], 2
    return sorted(failures), scope_notes, (0 if not failures else 1)


def scope_report(root: Path, manifest: dict, dist_manifest_rel: str | None) -> list[str]:
    """Named scope summary + explicit incomplete items: a pass on one scope
    must never read as full release completion."""
    lines = []
    nb = manifest.get("native_bundle")
    if nb:
        wheel = nb.get("application_wheel") or {}
        declared = wheel.get("declared") if isinstance(wheel, dict) else bool(wheel)
        if declared:
            wpath = wheel.get("path") if isinstance(wheel, dict) else None
            if wpath and not (root / wpath).exists():
                lines.append(
                    f"scope note: the declared application wheel ({wpath}) is absent — "
                    "native release remains incomplete"
                )
        else:
            lines.append(
                "scope note: no application wheel is declared — the native bundle covers "
                "third-party dependency inputs only, not a complete shipped application image"
            )
    if not dist_manifest_rel:
        lines.append("scope note: built static dist was not verified (no --dist-manifest given)")
    return lines


WHEEL_TAG_RE = re.compile(
    r"^(?P<dist>[A-Za-z0-9_.]+)-(?P<version>[^-]+)-"
    r"(?P<py>cp313|py3)-(?P<abi>cp313|abi3|none)-"
    r"(?P<plat>any|manylinux(?:_\d+_\d+|2014|1)_x86_64\.manylinux\d*_x86_64|manylinux(?:_\d+_\d+|2014|1)_x86_64)"
)


def check_native_bundle(root: Path, nb: dict, scope_notes: list | None = None) -> list[str]:
    """Verify the declared native third-party bundle against its manifest and
    (when prepared locally) its actual artifacts."""
    failures: list[str] = []
    scope_notes = scope_notes if scope_notes is not None else []
    for field in ("requirements_lock", "wheels_manifest", "expected_runtime_packages", "context_dir"):
        if field not in nb:
            return [f"native_bundle: missing required field {field!r}"]

    lock_path = root / nb["requirements_lock"]
    manifest_path = root / nb["wheels_manifest"]
    for label, path in (("requirements lock", lock_path), ("wheels manifest", manifest_path)):
        if not path.is_file() or path.stat().st_size == 0:
            failures.append(f"native bundle: {label} missing or empty: {nb['requirements_lock'] if label.startswith('requirements') else nb['wheels_manifest']}")
    if not lock_path.is_file() or not manifest_path.is_file():
        return failures
    try:
        wm = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        return failures + [f"native bundle: wheels manifest unreadable: {exc}"]

    entries = wm.get("wheels", [])
    by_name: dict[str, list[dict]] = {}
    for e in entries:
        by_name.setdefault(e.get("name", ""), []).append(e)
    for name in nb["expected_runtime_packages"]:
        count = len(by_name.get(name, []))
        if count == 0:
            failures.append(f"native bundle: required component absent: {name}")
        elif count > 1:
            failures.append(f"native bundle: duplicate entries for {name}: {count}")
    for name in by_name:
        if name not in nb["expected_runtime_packages"]:
            failures.append(f"native bundle: unexpected package in wheels manifest: {name}")

    context = root / nb["context_dir"]
    context_ready = context.is_dir()
    if not context_ready:
        failures.append(
            "native bundle: build context not prepared locally "
            f"({nb['context_dir']}; run scripts/distribution/prepare_native_bundle.py)"
        )
    for e in entries:
        filename = e.get("filename", "")
        if not filename or not WHEEL_TAG_RE.match(filename):
            failures.append(f"native bundle: wheel filename fails platform/ABI tag check: {filename}")
        if not e.get("sha256") or not e.get("url"):
            failures.append(f"native bundle: wheel entry lacks hash or source URL: {filename}")
        if not e.get("license_evidence"):
            failures.append(f"native bundle: wheel entry lacks license evidence: {filename}")
        else:
            ev = root / e["license_evidence"]
            has_content = (ev.is_file() and ev.stat().st_size > 0) or (
                ev.is_dir() and any(f.stat().st_size > 0 for f in ev.rglob("*") if f.is_file())
            )
            if not has_content:
                failures.append(f"native bundle: license evidence missing or empty: {e['license_evidence']}")
        if context_ready and e.get("path_in_context"):
            artifact = root / nb["context_dir"] / e["path_in_context"]
            if not artifact.is_file():
                failures.append(f"native bundle: prepared wheel missing from context: {e['path_in_context']}")
            elif e.get("sha256") and sha256_file(artifact) != e["sha256"]:
                failures.append(f"native bundle: prepared wheel hash mismatch: {e['path_in_context']}")

    # Tesseract Debian closure stamp (production OCR dependency, linux/amd64)
    ts = nb.get("tesseract_stamp") or {}
    stamp_rel = ts.get("path")
    if stamp_rel:
        if not contained(root, stamp_rel):
            errors.append(f"native bundle: tesseract stamp path escapes root: {stamp_rel}")
        else:
            tpath = root / stamp_rel
            if not tpath.is_file():
                failures.append(f"native bundle: tesseract stamp missing: {stamp_rel}")
            else:
                try:
                    tsd = json.loads(tpath.read_text())
                except json.JSONDecodeError as exc:
                    failures.append(f"native bundle: tesseract stamp unreadable: {exc}")
                    tsd = {}
                if tsd:
                    if tsd.get("kind") != "inkflip-native-tesseract-debs":
                        failures.append("native bundle: tesseract stamp has wrong kind")
                    for field, expected in (("package", ts.get("expected_package")),
                                            ("version", ts.get("expected_version")),
                                            ("arch", ts.get("expected_arch"))):
                        if expected and tsd.get(field) != expected:
                            failures.append(
                                f"native bundle: tesseract stamp {field} is {tsd.get(field)!r}, expected {expected!r}"
                            )
                    if not tsd.get("license"):
                        failures.append("native bundle: tesseract stamp lacks license")
                    pkgs = tsd.get("packages") or []
                    if not pkgs:
                        failures.append("native bundle: tesseract stamp records no packages")
                    for pkg in pkgs:
                        if not isinstance(pkg, dict) or not pkg.get("filename"):
                            failures.append("native bundle: tesseract stamp has a malformed package entry")
                            continue
                        if not pkg.get("sha256") or pkg.get("bytes") is None:
                            failures.append(f"native bundle: deb entry lacks hash/bytes: {pkg.get('filename')}")
                    debs_dir = ts.get("debs_dir")
                    if debs_dir:
                        debs_path = root / debs_dir
                        if debs_path.is_dir():
                            actual = {p.name for p in debs_path.glob("*.deb")}
                            expected_names = {p["filename"] for p in pkgs if isinstance(p, dict)}
                            for name in sorted(expected_names - actual):
                                failures.append(f"native bundle: deb closure missing prepared file: {name}")
                            for name in sorted(actual - expected_names):
                                failures.append(f"native bundle: undeclared deb in prepared closure: {name}")

    # application wheel / complete-image audit interface
    wheel = nb.get("application_wheel") or {}
    if wheel.get("declared"):
        wpath, wsha = wheel.get("path"), wheel.get("sha256")
        if not wpath or not wsha:
            failures.append("native bundle: application_wheel declared without path+sha256")
        else:
            wp = root / wpath
            if not wp.is_file():
                failures.append(f"native bundle: declared application wheel missing: {wpath}")
            elif sha256_file(wp) != wsha:
                failures.append(f"native bundle: application wheel digest mismatch: {wpath}")
    image = nb.get("application_image") or {}
    lock_rel = image.get("image_lock")
    if lock_rel:
        lock_path = root / lock_rel
        if not lock_path.is_file() and not image.get("declared"):
            # The lock ships with the packaging lane's merge; until then it is a
            # visible scope note, not a gate failure (the image itself is absent too).
            scope_notes.append(f"image lock not present yet in this tree: {lock_rel} (arrives with the packaging merge)")
            lock_path = None
        if lock_path is not None and lock_path.is_file():
            try:
                lock = json.loads(lock_path.read_text())
            except json.JSONDecodeError as exc:
                failures.append(f"native bundle: image lock unreadable: {exc}")
                lock = {}
            if not (lock.get("base_image") or {}).get("index_digest"):
                failures.append("native bundle: image lock lacks base_image.index_digest pin")
    if image.get("declared"):
        digest = image.get("expected_image_digest")
        if not digest:
            failures.append("native bundle: application_image declared without expected_image_digest")
        # the wheel must be declared for any complete-image claim
        if not wheel.get("declared"):
            failures.append(
                "native bundle: application_image declared but application_wheel is not — "
                "a third-party bundle alone is not a complete shipped application image"
            )

    # Assembled-context stamp audit (Cursor's interface, read-only): when the
    # packaging lane has assembled native/dist, verify the app-wheel stamp
    # against the actual wheel bytes and the build-context identity fields.
    stamp_rel = nb.get("application_wheel_stamp")
    if stamp_rel:
        spath = root / stamp_rel
        if not spath.is_file():
            scope_notes.append(f"application wheel stamp not present yet: {stamp_rel} (arrives with assembled native/dist)")
        else:
            try:
                stamp = json.loads(spath.read_text())
            except json.JSONDecodeError as exc:
                failures.append(f"native bundle: application wheel stamp unreadable: {exc}")
                stamp = {}
            for field in ("filename", "sha256", "bytes", "assembled_path", "wheel_tag"):
                if not stamp.get(field):
                    failures.append(f"native bundle: application wheel stamp lacks {field!r}")
            assembled = stamp.get("assembled_path")
            if assembled and stamp.get("sha256"):
                ap = root / assembled
                if not ap.is_file():
                    failures.append(f"native bundle: stamped application wheel missing: {assembled}")
                elif sha256_file(ap) != stamp["sha256"]:
                    failures.append(f"native bundle: application wheel digest mismatch: {assembled}")
            tag = stamp.get("wheel_tag", "")
            if tag and not re.fullmatch(r"[a-z0-9]+-[^-]+-[^-]+", tag):
                failures.append(f"native bundle: implausible wheel tag in stamp: {tag!r}")
    build_context_rel = nb.get("build_context_identity")
    if build_context_rel:
        bcpath = root / build_context_rel
        if not bcpath.is_file():
            scope_notes.append(f"build-context identity record not present yet: {build_context_rel}")
        else:
            try:
                bc = json.loads(bcpath.read_text())
            except json.JSONDecodeError as exc:
                failures.append(f"native bundle: build-context identity unreadable: {exc}")
                bc = {}
            for field in ("kind", "docker_platform", "dockerfile"):
                if not bc.get(field):
                    failures.append(f"native bundle: build-context identity lacks {field!r}")

    for stamp_field, required in (("node_stamp", ("version", "sha256", "url", "shasums256_source")),
                                  ("model_stamp", ("name", "sha256", "license", "source"))):
        stamp_rel = nb.get(stamp_field)
        if not stamp_rel:
            failures.append(f"native bundle: {stamp_field} not declared")
            continue
        stamp_path = root / stamp_rel
        if not stamp_path.is_file():
            failures.append(f"native bundle: {stamp_field} missing: {stamp_rel}")
            continue
        try:
            stamp = json.loads(stamp_path.read_text())
        except json.JSONDecodeError as exc:
            failures.append(f"native bundle: {stamp_field} unreadable: {exc}")
            continue
        for field in required:
            if not stamp.get(field):
                failures.append(f"native bundle: {stamp_field} lacks {field!r}")
    return failures


def check_dist(root: Path, dist_manifest_rel: str) -> list[str]:
    """Verify the generated static dist against a recorded dist manifest
    (same fail-closed contract as check_static_dist.py)."""
    failures: list[str] = []
    path = root / dist_manifest_rel
    if not path.is_file():
        return [f"dist manifest missing: {dist_manifest_rel} (record it after building, see scripts/distribution/record_dist.py)"]
    try:
        dm = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return [f"dist manifest unreadable: {exc}"]
    dist_root = root / dm.get("dist_root", "apps/web/dist")
    if not dist_root.is_dir():
        return [f"dist root missing: {dm.get('dist_root', 'apps/web/dist')} (build first)"]
    declared: dict[str, dict] = {}
    for f in dm.get("files", []):
        rel = f.get("path") if isinstance(f, dict) else None
        if not rel:
            failures.append("dist manifest: malformed entry (missing path)")
            continue
        if rel in declared:
            failures.append(f"dist manifest: duplicate entry for {rel}")
            continue
        if rel.startswith("/") or ".." in Path(rel).parts:
            failures.append(f"dist manifest: entry escapes root (traversal/absolute): {rel}")
            continue
        if f.get("sha256") is None or f.get("bytes") is None:
            failures.append(f"dist manifest: entry lacks required bytes/sha256: {rel}")
        declared[rel] = f
    reject = dm.get("reject_patterns") or dm.get("reject_source_maps") and [r"\.map$"] or []
    import re as _re
    patterns = [_re.compile(pat) for pat in reject]
    for rel in sorted(declared):
        for pat in patterns:
            if pat.search(rel):
                failures.append(f"dist: prohibited development material declared: {rel} (pattern {pat.pattern!r})")
                break
    for actual in sorted(dist_root.rglob("*")):
        if actual.is_file():
            rel = actual.relative_to(root).as_posix()
            for pat in patterns:
                if pat.search(rel):
                    failures.append(f"dist: prohibited development material present: {rel} (pattern {pat.pattern!r})")
                    break
    for rel, f in sorted(declared.items()):
        actual = root / rel
        if not actual.is_file():
            failures.append(f"dist: missing declared file: {rel}")
            continue
        if f.get("sha256") and sha256_file(actual) != f["sha256"]:
            failures.append(f"dist: hash mismatch: {rel}")
    for actual in sorted(dist_root.rglob("*")):
        if actual.is_file() and not actual.is_symlink():
            rel = actual.relative_to(root).as_posix()
            if rel not in declared:
                failures.append(f"dist: undeclared file: {rel}")
    return failures


# ------------------------------------------------- production image (Docker)

def verify_production_image(root: Path, image: dict, docker_cmd: str) -> list[str]:
    """Read-only verification of the declared production image via Docker:
    identity/architecture by `docker inspect`; wheel/model digests, the
    tesseract binary and the notice inventory by a read-only container run.
    The image ref alone is not proof — actual bytes are checked."""
    import subprocess
    failures: list[str] = []
    ref = image.get("image_ref")
    expected_digest = image.get("expected_image_digest")
    if not ref or not expected_digest:
        return ["production image: image_ref and expected_image_digest are required for --docker verification"]

    def docker(*args: str) -> tuple[int, str]:
        proc = subprocess.run([docker_cmd, *args], capture_output=True, text=True, timeout=300)
        return proc.returncode, (proc.stdout or proc.stderr)

    rc, out = docker("inspect", "--format", "{{.Id}}\n{{.Architecture}}\n{{.Os}}", ref)
    if rc != 0:
        return [f"production image: docker inspect failed for {ref}: {out.strip()[:200]}"]
    lines = out.strip().splitlines()
    image_id, arch, os_name = (lines + ["", "", ""])[:3]
    if image_id != expected_digest:
        failures.append(f"production image: identity mismatch (inspect {image_id}, declared {expected_digest})")
    if arch != image.get("architecture"):
        failures.append(f"production image: architecture is {arch!r}, declared {image.get('architecture')!r}")
    if os_name != image.get("os", "linux"):
        failures.append(f"production image: os is {os_name!r}, declared {image.get('os', 'linux')!r}")

    rc, out = docker("run", "--rm", "--network", "none", "--user", "0",
                     "--entrypoint", "sh", ref,
                     "-c",
                     "sha256sum /app/wheels/inkflip-*.whl /wheels/inkflip-*.whl 2>/dev/null; "
                     "sha256sum /app/models/tessdata/eng.traineddata 2>/dev/null; "
                     "/usr/bin/tesseract --version 2>&1 | head -1")
    if rc != 0:
        return failures + [f"production image: read-only container check failed: {out.strip()[:200]}"]
    hashes = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            hashes[parts[1].rsplit("/", 1)[-1]] = parts[0]

    wheel_sha = image.get("expected_wheel_sha256")
    wheel_found = [v for k, v in hashes.items() if k.endswith(".whl")]
    if wheel_sha and wheel_sha not in wheel_found:
        failures.append(
            f"production image: application wheel digest mismatch (expected {wheel_sha[:12]}…, found {wheel_found or 'none'})"
        )
    model_sha = image.get("expected_model_sha256")
    if model_sha and hashes.get("eng.traineddata") != model_sha:
        failures.append("production image: model digest mismatch")
    tver = image.get("expected_tesseract_version")
    if tver and f"tesseract {tver}" not in out:
        failures.append(f"production image: tesseract version line missing/mismatched (expected {tver!r})")
    # notice inventory: parse INDEX.json (id -> path/sha256) and hash-check
    # each required entry's actual bytes inside the image — labels are not proof.
    index_entries: dict[str, dict] = {}
    rc_idx, index_json = docker("run", "--rm", "--network", "none", "--user", "0",
                                "--entrypoint", "cat", ref, "/app/notices/INDEX.json")
    if rc_idx != 0 or not index_json.strip():
        failures.append("production image: notice INDEX.json absent from image notice directory")
    else:
        try:
            parsed = json.loads(index_json)
            for e in parsed.get("entries", []):
                if isinstance(e, dict) and e.get("id"):
                    index_entries[e["id"]] = e
        except json.JSONDecodeError:
            failures.append("production image: notice INDEX.json is not valid JSON")
    for notice_id in image.get("required_notice_ids", []):
        entry = index_entries.get(notice_id)
        if entry is None:
            failures.append(f"production image: required notice id absent from image notice inventory: {notice_id}")
            continue
        entry_path, entry_sha = entry.get("path"), entry.get("sha256")
        if entry_path and entry_sha:
            rc2, hash_out = docker("run", "--rm", "--network", "none", "--user", "0",
                                   "--entrypoint", "sh", ref,
                                   "-c", f"sha256sum /app/{entry_path} 2>/dev/null")
            actual = hash_out.split()[0] if rc2 == 0 and hash_out.split() else None
            if actual != entry_sha:
                failures.append(
                    f"production image: notice {notice_id!r} bytes do not match INDEX (expected {entry_sha[:12]}…, got {str(actual)[:12]}…)"
                )
    return failures


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
    parser.add_argument("--dist-manifest", default=None, help="verify apps/web/dist against this recorded dist manifest (see scripts/distribution/record_dist.py)")
    parser.add_argument("--docker", metavar="IMAGE", default=None, help="read-only production-image verification via docker (inspect + container checks)")
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

    problems, gate_scope_notes, code = run_checks(root, manifest, args.dist_manifest)
    if args.docker and not problems:
        nb = manifest.get("native_bundle") or {}
        image = nb.get("production_image") or {}
        if image.get("declared"):
            import shutil as _shutil
            docker_cmd = _shutil.which("docker")
            if not docker_cmd:
                problems.append("production image: docker CLI not found; --docker verification could not run")
            else:
                image = dict(image)
                image["image_ref"] = args.docker
                problems.extend(verify_production_image(root, image, docker_cmd))
                gate_scope_notes.append(f"production image verified via docker: {args.docker}")
                code = (2 if any(e in problems for e in []) else 1) if problems else 0
    scope_notes = gate_scope_notes + scope_report(root, manifest, args.dist_manifest)
    if args.json:
        print(json.dumps({"ok": code == 0, "exit_code": code, "problems": problems,
                          "scope_notes": scope_notes}, indent=2))
    else:
        if not problems:
            scopes = ["browser static surface"]
            if manifest.get("native_bundle"):
                scopes.append("native third-party dependency inputs")
            if args.dist_manifest:
                scopes.append("built static dist")
            print(f"distribution check PASSED for: {', '.join(scopes)}")
            for note in scope_notes:
                print(f"  note: {note}")
            for note in scope_report(root, manifest, args.dist_manifest):
                print(f"  note: {note}")
            print(f"  groups: {len(manifest.get('groups', []))}, shipped roots: {len(manifest['distribution'].get('shipped_roots', []))}")
        else:
            print(f"distribution check: {len(problems)} problem(s)")
            for p in problems:
                print(f"  - {p}")
    return code


if __name__ == "__main__":
    sys.exit(main())
