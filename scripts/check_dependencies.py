#!/usr/bin/env python3
"""Verify the frozen supply-chain state of the Inkflip checkout (T02).

`--frozen` performs read-only, offline verification of every frozen surface:

  1. Toolchain pins — .node-version, .python-version, packageManager and the
     pyproject interpreter constraint agree exactly.
  2. bun.lock — every dependency spec in every workspace manifest resolves to
     an exact locked package carrying a content integrity hash; bunfig.toml
     still enforces the isolated linker, exact saves and the release-age gate.
  3. native/uv.lock — the pinned interpreter constraint matches .python-version,
     every declared dependency/dev pin resolves to a locked package, and every
     locked artifact carries a sha256.
  4. config/resolved-assets.json — strict schema plus a re-hash of every staged
     same-origin file (missing or substituted bytes fail closed).
  5. build/base-image.lock.json — OCI references are digest-pinned and every
     `uses:` action reference in .github/workflows is recorded at a full
     commit SHA.
  6. No-runtime-download policy — staged serve paths are same-origin and the
     web entry points contain no remote loader/CDN references.

It does not install or mutate anything; the twice-from-clean-checkout install
proof runs bun/uv themselves and is recorded in artifacts/tasks/T02/.

Exit 0 only when every check passes; each failure prints its cause.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_assets  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def ok(name: str, detail: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"ok   {name}: {detail}")


def fail(name: str, detail: str) -> None:
    global CHECKS
    CHECKS += 1
    FAILURES.append(f"{name}: {detail}")
    print(f"FAIL {name}: {detail}")


def require(condition: bool, name: str, detail: str, good: str) -> None:
    fail(name, detail) if not condition else ok(name, good)


def load_json(path: Path, name: str) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        fail(name, f"cannot parse {path.relative_to(ROOT)}: {error}")
        return None


# --- bun.lock is JSONC: strip comments and trailing commas safely ----------


def jsonc_to_json(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        out.append(ch)
        i += 1
    cleaned = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", cleaned)


def read_pin(path: Path) -> str | None:
    try:
        lines = [line.strip() for line in path.read_text().splitlines()
                 if line.strip() and not line.strip().startswith("#")]
    except OSError:
        return None
    return lines[0] if len(lines) == 1 else None


SEMVER = r"\d+\.\d+\.\d+"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


def check_toolchain() -> None:
    node_pin = read_pin(ROOT / ".node-version")
    require(node_pin is not None and re.fullmatch(SEMVER, node_pin or "") is not None,
            "toolchain.node", "missing or malformed .node-version",
            f".node-version={node_pin}")
    py_pin = read_pin(ROOT / ".python-version")
    require(py_pin is not None and re.fullmatch(SEMVER, py_pin or "") is not None,
            "toolchain.python", "missing or malformed .python-version",
            f".python-version={py_pin}")

    package = load_json(ROOT / "package.json", "toolchain.package") or {}
    manager = package.get("packageManager", "")
    require(isinstance(manager, str) and re.fullmatch(rf"bun@{SEMVER}", manager) is not None,
            "toolchain.bun", f"packageManager must pin an exact bun: {manager!r}",
            f"packageManager={manager}")

    pyproject_path = ROOT / "native/pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        fail("toolchain.pyproject", f"cannot parse native/pyproject.toml: {error}")
        pyproject = {}
    requires_python = pyproject.get("project", {}).get("requires-python", "")
    expected = f"=={py_pin}" if py_pin else ""
    require(requires_python == expected,
            "toolchain.python-agreement",
            f"native/pyproject.toml requires-python {requires_python!r} != pinned =={py_pin}",
            f"native interpreter pin =={py_pin} matches .python-version")


def workspace_manifests(package: dict) -> dict[str, dict]:
    manifests: dict[str, dict] = {}
    for pattern in package.get("workspaces", []):
        for candidate in sorted(glob.glob(str(ROOT / pattern))):
            manifest_path = Path(candidate) / "package.json"
            if manifest_path.is_file():
                rel = manifest_path.parent.relative_to(ROOT).as_posix()
                try:
                    manifests[rel] = json.loads(manifest_path.read_text())
                except json.JSONDecodeError:
                    pass
    manifests[""] = package
    return manifests


def check_bun_lock() -> None:
    lock_path = ROOT / "bun.lock"
    if not lock_path.is_file():
        fail("bun.lock", "bun.lock missing — run `bun install` and commit the lock")
        return
    try:
        lock = json.loads(jsonc_to_json(lock_path.read_text()))
    except json.JSONDecodeError as error:
        fail("bun.lock", f"bun.lock is not parseable JSONC: {error}")
        return
    packages = lock.get("packages", {})
    workspaces_lock = lock.get("workspaces", {})

    package = load_json(ROOT / "package.json", "bun.lock") or {}
    manifests = workspace_manifests(package)
    unresolved: list[str] = []
    checked_specs = 0
    for ws_rel, manifest in manifests.items():
        for section in ("dependencies", "devDependencies", "optionalDependencies",
                        "peerDependencies"):
            for dep_name, spec in (manifest.get(section) or {}).items():
                if str(spec).startswith(("workspace:", "link:", "file:")):
                    continue
                checked_specs += 1
                locked_spec = (workspaces_lock.get(ws_rel, {}).get(section) or {}).get(dep_name)
                if locked_spec != spec:
                    unresolved.append(f"{ws_rel or '.'}:{dep_name} spec {spec!r} "
                                      f"!= lock workspace spec {locked_spec!r}")
                    continue
                key = f"{dep_name}@{spec}"
                # bun.lock v2 keys the packages map by plain name; the entry's
                # first element is "name@version" and the last is integrity.
                entry = packages.get(dep_name)
                if isinstance(entry, list) and entry and entry[0] == key:
                    pass
                else:
                    entry = packages.get(key)
                if entry is None:
                    unresolved.append(f"{ws_rel or '.'}:{dep_name}@{spec} absent from lock packages")
                    continue
                if isinstance(entry, list) and len(entry) >= 2 and str(entry[1]).startswith("file:"):
                    continue  # local file/link resolution, integrity n/a
                record = json.dumps(entry)
                if not re.search(r"sha(256|384|512)-[A-Za-z0-9+/=]+", record):
                    unresolved.append(f"{key} has no content integrity hash")
    require(not unresolved and checked_specs > 0,
            "bun.lock.coverage",
            "; ".join(unresolved[:8]) or "no dependency specs found",
            f"all {checked_specs} manifest specs resolve to hashed lock entries")

    trusted = package.get("trustedDependencies")
    require(isinstance(trusted, list),
            "bun.lock.trusted-policy",
            "package.json must declare an explicit trustedDependencies list",
            f"trustedDependencies declared explicitly ({len(trusted)} entries)")

    bunfig = (ROOT / "bunfig.toml").read_text() if (ROOT / "bunfig.toml").is_file() else ""
    require('linker = "isolated"' in bunfig,
            "bun.lock.linker", "bunfig.toml must keep linker = \"isolated\"",
            "isolated linker enforced")
    require("exact = true" in bunfig and "minimumReleaseAge" in bunfig,
            "bun.lock.install-policy",
            "bunfig.toml must keep exact = true and minimumReleaseAge",
            "exact saves + release-age gate enforced")


def check_uv_lock() -> None:
    lock_path = ROOT / "native/uv.lock"
    if not lock_path.is_file():
        fail("uv.lock", "native/uv.lock missing — run `uv lock --project native` and commit it")
        return
    try:
        lock = tomllib.loads(lock_path.read_text())
    except tomllib.TOMLDecodeError as error:
        fail("uv.lock", f"native/uv.lock is not valid TOML: {error}")
        return
    py_pin = read_pin(ROOT / ".python-version")
    require(lock.get("requires-python") == f"=={py_pin}",
            "uv.lock.interpreter",
            f"uv.lock requires-python {lock.get('requires-python')!r} != =={py_pin}",
            f"uv.lock interpreter =={py_pin}")

    try:
        pyproject = tomllib.loads((ROOT / "native/pyproject.toml").read_text())
    except (OSError, tomllib.TOMLDecodeError):
        pyproject = {}
    declared: dict[str, str] = {}
    for dep in pyproject.get("project", {}).get("dependencies", []):
        match = re.match(r"^([A-Za-z0-9_.-]+?)\s*==\s*([0-9][^,; ]*)$", dep)
        if match:
            declared[match.group(1).lower().replace("_", "-")] = match.group(2)
        else:
            fail("uv.lock.manifest", f"dependency is not an exact pin: {dep!r}")
    for group, deps in (pyproject.get("dependency-groups") or {}).items():
        for dep in deps:
            match = re.match(r"^([A-Za-z0-9_.-]+?)\s*==\s*([0-9][^,; ]*)$", dep)
            if match:
                declared[match.group(1).lower().replace("_", "-")] = match.group(2)
            else:
                fail("uv.lock.manifest", f"{group} dependency is not an exact pin: {dep!r}")

    locked = {p["name"].lower().replace("_", "-"): p for p in lock.get("package", [])}
    missing = [f"{name}=={ver}" for name, ver in declared.items()
               if locked.get(name, {}).get("version") != ver]
    require(not missing and declared,
            "uv.lock.coverage",
            f"declared pins missing/different in uv.lock: {missing}" if missing
            else "no declared dependencies",
            f"all {len(declared)} declared pins locked exactly")

    unhashed = [p["name"] for p in lock.get("package", [])
                if "registry" in (p.get("source") or {})
                and not p.get("sdist", {}).get("hash")
                and not any("sha256:" in w.get("hash", "") for w in p.get("wheels", []))]
    require(not unhashed,
            "uv.lock.hashes",
            f"locked packages without artifact hashes: {unhashed}",
            f"every locked package carries sha256 artifact hashes ({len(lock.get('package', []))} packages)")


def check_assets() -> None:
    try:
        manifest = prepare_assets.load_manifest()
        checked = prepare_assets.verify(manifest)
        ok("assets", f"{checked} staged files hash-verified; "
                   f"{len(manifest['assets'])} assets all same-origin with license/source")
    except prepare_assets.AssetError as error:
        fail("assets", str(error))


def check_base_image_lock() -> None:
    data = load_json(ROOT / "build/base-image.lock.json", "base-image")
    if data is None:
        return
    images = data.get("oci_images")
    if not isinstance(images, list) or not images:
        fail("base-image.oci", "oci_images must be a nonempty list")
    else:
        for image in images:
            ref = image.get("ref", "?")
            index = image.get("index_digest", "")
            platforms = image.get("platform_digests", {})
            problems = []
            if not SHA256_RE.match(index):
                problems.append(f"index_digest {index!r} is not sha256:<64hex>")
            if not isinstance(platforms, dict) or not platforms:
                problems.append("no platform_digests recorded")
            else:
                for plat, digest in platforms.items():
                    if not SHA256_RE.match(str(digest)):
                        problems.append(f"{plat} digest {digest!r} is not sha256:<64hex>")
            tag = ref.rsplit(":", 1)[-1] if ":" in ref else ""
            if "@" not in ref and (not tag or tag in ("latest", "main", "edge")):
                problems.append(f"mutable or missing tag in ref {ref!r}")
            require(not problems, f"base-image.oci.{ref}",
                    "; ".join(problems) or "ok",
                    f"{ref} pinned at immutable digests")

    actions = data.get("github_actions")
    used: set[str] = set()
    workflow_dir = ROOT / ".github/workflows"
    for workflow in sorted(workflow_dir.glob("*.y*ml")) if workflow_dir.is_dir() else []:
        for match in re.finditer(r"uses:\s*([^\s'\"]+)", workflow.read_text()):
            used.add(match.group(1))
    recorded = {}
    if isinstance(actions, list):
        for entry in actions:
            uses = entry.get("uses", "")
            sha = entry.get("resolved_sha", "")
            recorded[uses] = entry
            if not SHA1_RE.match(str(sha)):
                fail("base-image.actions",
                     f"{uses}: resolved_sha {sha!r} is not a full commit SHA")
    for uses in sorted(used):
        entry = recorded.get(uses)
        if entry is None:
            fail("base-image.actions", f"workflow uses {uses} but no immutable revision is recorded")
        elif not SHA1_RE.match(str(entry.get("resolved_sha", ""))):
            fail("base-image.actions", f"{uses} recorded without a full SHA")
        else:
            ok("base-image.actions", f"{uses} recorded at immutable {entry['resolved_sha'][:12]}…")
    if not used:
        ok("base-image.actions", "no workflow `uses:` references present")


def strip_comments(text: str, suffix: str) -> str:
    """Strip comments while preserving string literals, regex literals, and line numbers."""
    if suffix in (".ts", ".tsx", ".js", ".mjs"):
        out: list[str] = []
        i = 0
        n = len(text)
        state = "NORMAL"
        last_token = ""
        control_paren_depth = 0
        in_control_stmt = False

        while i < n:
            c = text[i]
            c2 = text[i:i + 2]
            if state == "NORMAL":
                if c2 == "//":
                    state = "LINE_COMMENT"
                    out.append("  ")
                    i += 2
                    continue
                elif c2 == "/*":
                    state = "BLOCK_COMMENT"
                    out.append("  ")
                    i += 2
                    continue
                elif c == "'":
                    state = "STRING_SINGLE"
                    out.append(c)
                    i += 1
                    continue
                elif c == '"':
                    state = "STRING_DOUBLE"
                    out.append(c)
                    i += 1
                    continue
                elif c == "`":
                    state = "TEMPLATE"
                    out.append(c)
                    i += 1
                    continue
                elif c == "(":
                    if last_token in ("if", "while", "for", "with", "switch"):
                        in_control_stmt = True
                        control_paren_depth = 1
                    elif in_control_stmt:
                        control_paren_depth += 1
                    out.append(c)
                    last_token = "("
                    i += 1
                    continue
                elif c == ")":
                    if in_control_stmt:
                        control_paren_depth -= 1
                        if control_paren_depth == 0:
                            in_control_stmt = False
                            last_token = ")_ctrl"
                            out.append(c)
                            i += 1
                            continue
                    out.append(c)
                    last_token = ")"
                    i += 1
                    continue
                elif c == "/":
                    can_be_regex = (
                        (not last_token)
                        or (last_token in "=(:[{;,!&|?+-*^%~<>/")
                        or (last_token in (
                            "return", "case", "throw", "yield", "await",
                            "typeof", "delete", "void", "in", "of", ")_ctrl"
                        ))
                    )
                    if can_be_regex and c2 not in ("//", "/*"):
                        state = "REGEX"
                        out.append(c)
                        i += 1
                    else:
                        out.append(c)
                        last_token = c
                        i += 1
                else:
                    out.append(c)
                    if not c.isspace():
                        if c.isalnum() or c in "_$":
                            if last_token and (last_token[-1].isalnum() or last_token[-1] in "_$"):
                                last_token += c
                            else:
                                last_token = c
                        else:
                            last_token = c
                    i += 1
            elif state == "LINE_COMMENT":
                if c == "\n":
                    out.append("\n")
                    state = "NORMAL"
                    # Preserve preceding token across comments
                else:
                    out.append(" ")
                i += 1
            elif state == "BLOCK_COMMENT":
                if c2 == "*/":
                    out.append("  ")
                    i += 2
                    state = "NORMAL"
                    # Preserve preceding token across comments
                else:
                    out.append("\n" if c == "\n" else " ")
                i += 1
            elif state == "STRING_SINGLE":
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                elif c == "'":
                    state = "NORMAL"
                    last_token = "'"
                i += 1
            elif state == "STRING_DOUBLE":
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                elif c == '"':
                    state = "NORMAL"
                    last_token = '"'
                i += 1
            elif state == "TEMPLATE":
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                elif c == "`":
                    state = "NORMAL"
                    last_token = "`"
                i += 1
            elif state == "REGEX":
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                elif c == "[":
                    out.append(c)
                    i += 1
                    while i < n and text[i] != "]":
                        if text[i] == "\\" and i + 1 < n:
                            out.append(text[i:i + 2])
                            i += 2
                        else:
                            out.append(text[i])
                            i += 1
                    if i < n:
                        out.append(text[i])
                        i += 1
                    continue
                elif c == "/":
                    state = "NORMAL"
                    last_token = "/"
                i += 1
        return "".join(out)
    elif suffix == ".css":
        out = []
        i = 0
        n = len(text)
        state = "NORMAL"
        while i < n:
            c = text[i]
            c2 = text[i:i + 2]
            if state == "NORMAL":
                if c2 == "/*":
                    state = "COMMENT"
                    out.append("  ")
                    i += 2
                elif c == "'":
                    state = "STRING_SINGLE"
                    out.append(c)
                    i += 1
                elif c == '"':
                    state = "STRING_DOUBLE"
                    out.append(c)
                    i += 1
                else:
                    out.append(c)
                    i += 1
            elif state == "STRING_SINGLE":
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                elif c == "'":
                    state = "NORMAL"
                i += 1
            elif state == "STRING_DOUBLE":
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                elif c == '"':
                    state = "NORMAL"
                i += 1
            elif state == "COMMENT":
                if c2 == "*/":
                    out.append("  ")
                    i += 2
                    state = "NORMAL"
                else:
                    out.append("\n" if c == "\n" else " ")
                    i += 1
        return "".join(out)
    elif suffix == ".html":
        out = []
        i = 0
        n = len(text)
        state = "NORMAL"
        while i < n:
            c = text[i]
            c4 = text[i:i + 4]
            c3 = text[i:i + 3]
            if state == "NORMAL":
                if c4 == "<!--":
                    state = "COMMENT"
                    out.append("    ")
                    i += 4
                elif c == "<":
                    state = "TAG"
                    out.append(c)
                    i += 1
                else:
                    out.append(c)
                    i += 1
            elif state == "TAG":
                if c == ">":
                    state = "NORMAL"
                    out.append(c)
                    i += 1
                elif c == "'":
                    state = "TAG_STRING_SINGLE"
                    out.append(c)
                    i += 1
                elif c == '"':
                    state = "TAG_STRING_DOUBLE"
                    out.append(c)
                    i += 1
                else:
                    out.append(c)
                    i += 1
            elif state == "TAG_STRING_SINGLE":
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                elif c == "'":
                    state = "TAG"
                i += 1
            elif state == "TAG_STRING_DOUBLE":
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                elif c == '"':
                    state = "TAG"
                i += 1
            elif state == "COMMENT":
                if c3 == "-->":
                    out.append("   ")
                    i += 3
                    state = "NORMAL"
                else:
                    out.append("\n" if c == "\n" else " ")
                    i += 1
        return "".join(out)
    return text


EXECUTABLE_REMOTE_LOADER_RE = re.compile(
    r"(?:src|href)\s*=\s*[\"']https?://|"
    r"importScripts\s*\(\s*[\"']https?://|"
    r"new\s+(?:Shared)?Worker\s*\(\s*[\"']https?://|"
    r"fetch\s*\(\s*[\"']https?://|"
    r"import\s*\(\s*[\"']https?://|"
    r"import\s+[\"']https?://|"
    r"import\s+[\s\S]*?\s+from\s*[\"']https?://|"
    r"navigator\.sendBeacon\s*\(\s*[\"']https?://|"
    r"\.open\s*\(\s*[\"'](?:GET|POST|HEAD)[\"']\s*,\s*[\"']https?://|"
    r"@import\s+(?:url\s*\(\s*)?[\"']?https?://|"
    r"\burl\s*\(\s*[\"']?https?://",
    re.IGNORECASE
)

CDN_DOMAIN_RE = re.compile(
    r"(?:cdn\.jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com|esm\.sh|esm\.run)"
)


def check_no_runtime_download() -> None:
    try:
        manifest = prepare_assets.load_manifest()
        for asset in prepare_assets.validate_manifest(manifest):
            prepare_assets.check_serve_prefix(asset["serve_prefix"])
        ok("no-cdn.serve-paths", "all staged serve_prefixes are same-origin /-paths")
    except prepare_assets.AssetError as error:
        fail("no-cdn.serve-paths", str(error))

    offenders: list[str] = []
    # 1. Application web sources: no executable remote loaders and no CDN references
    app_scan_roots = [ROOT / "apps/web/src", ROOT / "apps/web/index.html",
                      ROOT / "apps/web/vite.config.ts"]
    for item in app_scan_roots:
        files = [item] if item.is_file() else sorted(item.rglob("*")) if item.is_dir() else []
        for file in files:
            if file.is_file() and file.suffix in (".ts", ".tsx", ".js", ".mjs", ".html", ".css"):
                text = strip_comments(file.read_text(errors="replace"), file.suffix)
                for match in EXECUTABLE_REMOTE_LOADER_RE.finditer(text):
                    line = text[:match.start()].count("\n") + 1
                    offenders.append(f"{file.relative_to(ROOT)}:{line}")
                for match in CDN_DOMAIN_RE.finditer(text):
                    line = text[:match.start()].count("\n") + 1
                    offenders.append(f"{file.relative_to(ROOT)}:{line}")

    # 2. Staged text assets in apps/web/public: no executable remote loaders
    staged_roots = [ROOT / "apps/web/public"]
    for item in staged_roots:
        files = [item] if item.is_file() else sorted(item.rglob("*")) if item.is_dir() else []
        for file in files:
            if file.is_file() and file.suffix in (".js", ".mjs", ".html", ".css"):
                text = strip_comments(file.read_text(errors="replace"), file.suffix)
                for match in EXECUTABLE_REMOTE_LOADER_RE.finditer(text):
                    line = text[:match.start()].count("\n") + 1
                    offenders.append(f"{file.relative_to(ROOT)}:{line}")

    require(not offenders, "no-cdn.sources",
            f"remote loader/CDN references in web sources or staged assets: {offenders[:6]}",
            "web sources and staged assets carry no remote script/worker/fetch or CDN reference")


def check_file_digest(path: Path, expected: str, name: str) -> None:
    try:
        actual, _ = prepare_assets.sha256_file(path)
    except OSError as error:
        fail(name, f"cannot read {path.name}: {error.strerror}")
        return
    require(actual == expected, name, f"SHA-256 mismatch for {path.name}",
            f"{path.name} SHA-256 matches recorded provenance")


def check_dependency_patch() -> None:
    """Bind the installed client constructor and Bun declarations to its patch."""
    record = load_json(ROOT / "config/dependency-patches.json", "patch.provenance") or {}
    entry = record.get("tesseract.js@7.0.0")
    if not isinstance(entry, dict):
        fail("patch.provenance", "missing pinned tesseract.js@7.0.0 patch record")
        return
    patch_path = "patches/tesseract.js@7.0.0.patch"
    expected = {"tesseract.js@7.0.0": patch_path}
    package = load_json(ROOT / "package.json", "patch.package") or {}
    try:
        lock = json.loads(jsonc_to_json((ROOT / "bun.lock").read_text()))
        installed = prepare_assets.package_root("tesseract.js")
        patch_text = (ROOT / patch_path).read_text()
    except (OSError, json.JSONDecodeError, prepare_assets.AssetError) as error:
        fail("patch.install", str(error))
        return
    for label, actual in [("manifest", package.get("patchedDependencies")),
                          ("lock", lock.get("patchedDependencies"))]:
        require(actual == expected, f"patch.{label}", "patch declaration missing or different",
                "exact pinned patch declaration matches")
    installed_meta = load_json(installed / "package.json", "patch.installed-package") or {}
    require((installed_meta.get("name"), installed_meta.get("version")) == ("tesseract.js", "7.0.0"),
            "patch.version", "installed package identity differs", "installed package is tesseract.js@7.0.0")
    require(entry.get("patch_path") == patch_path, "patch.path",
            "unexpected patch path", "patch path matches provenance")
    check_file_digest(ROOT / patch_path, entry.get("patch_sha256"), "patch.bytes")
    files = entry.get("files", {})
    required_files = {"src/createWorker.js", "src/index.d.ts"}
    headers = re.findall(r"^diff --git a/(\S+) b/(\S+)$", patch_text, re.M)
    expected_headers = {(relative, relative) for relative in required_files}
    require(set(headers) == expected_headers and len(headers) == len(expected_headers),
            "patch.targets", "patch contains missing, repeated or unexpected file targets",
            "patch modifies only its two recorded source files")
    require(set(files) == required_files, "patch.files", "unexpected patched file set",
            "constructor and public types are the complete patched file set")
    for relative in sorted(required_files):
        check_file_digest(installed / relative, files.get(relative, {}).get("patched_sha256"),
                          f"patch.installed.{relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frozen", action="store_true", required=True,
                        help="verify the committed frozen state (read-only, offline)")
    args = parser.parse_args()

    check_toolchain()
    check_bun_lock()
    check_dependency_patch()
    check_uv_lock()
    check_assets()
    check_base_image_lock()
    check_no_runtime_download()

    print(f"check_dependencies: {CHECKS - len(FAILURES)} passed, {len(FAILURES)} failed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
