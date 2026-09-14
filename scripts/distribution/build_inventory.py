#!/usr/bin/env python3
"""Build the deterministic distribution inventory and CycloneDX SBOM (T47 prep).

Answers, for this exact snapshot: *what would this repository distribute, and
what rights come with it?* Everything is classified:

  shipped           — bytes that leave the repository (staged browser assets,
                      the prepared public example) or that are compiled into
                      the shipped bundle (the prod dependency closure of
                      apps/web)
  runtime-tooling   — the frozen native Python environment (source + lock are
                      distributed; the built .venv is not)
  development-only  — build/test/lint tooling that never reaches a user
  unknown           — material found in a shipped directory that no manifest
                      accounts for (must be empty; check_distribution.py fails
                      on these)

Determinism: no wall-clock values anywhere. The SBOM timestamp is derived
from the evaluated commit; two runs over identical input are byte-identical.

Every consumed input is accounted for in `inputs` (repository-relative path
-> content digest): the tracked manifests and stamps, the notice index, and
the installed package.json of every bundled package. The recorded identity is
therefore the identity of what was actually evaluated.

Inputs (read-only, required): config/resolved-assets.json, bun.lock (tolerant
JSONC), native/uv.lock (TOML), fixtures/manifest.json,
licenses/notice-index.json, release/node/node.stamp.json,
release/models/model.stamp.json, release/tesseract/tesseract.stamp.json,
package manifests, the installed metadata of the locked npm closure, and the
docs/ATTRIBUTION.md-derived license map (validated against resolved-assets).

Honesty rules: a missing file, invalid JSON or invalid root/entry shape in a
required tracked input is a named config error; installed metadata that does
not match the locked name@version, or that declares no license expression, is
a named verification failure. Neither ever degrades into a silently empty (or
complete-looking) inventory, and a license expression is recorded verbatim.

Exit codes: 0 success, 1 verification failure, 2 config/usage error.

Usage:
  python3 scripts/distribution/build_inventory.py \
      --out .private/distribution/inventory [--check] \
      [--surface-doc docs/distribution/SURFACE.md]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Declared licenses for the frozen native (PyPI) pins. Source: the T02
# attribution ledger (docs/ATTRIBUTION.md), which re-verified every pin
# against PyPI at freeze time; uv.lock itself records no license fields.
PYPI_LICENSES = {
    "pypdfium2": "Apache-2.0 OR BSD-3-Clause",
    "pypdf": "BSD-3-Clause",
    "pillow": "MIT-CMU",
    "jsonschema": "MIT",
    "attrs": "MIT",
    "jsonschema-specifications": "MIT",
    "referencing": "Apache-2.0",
    "rpds-py": "MIT",
    "pytest": "MIT",
    "iniconfig": "MIT",
    "packaging": "Apache-2.0 OR BSD-2-Clause",
    "pluggy": "MIT",
    "pygments": "BSD-2-Clause",
    "colorama": "MIT",
}

# Required tracked inputs. These are the files whose bytes the inventory
# describes, so they are digested (and validated) as one set: a missing file
# is a config error, never a quietly smaller inventory.
TRACKED_INPUTS = (
    "config/resolved-assets.json",
    "bun.lock",
    "native/uv.lock",
    "fixtures/manifest.json",
    "package.json",
    "apps/web/package.json",
    "licenses/notice-index.json",
    "release/node/node.stamp.json",
    "release/models/model.stamp.json",
    "release/tesseract/tesseract.stamp.json",
)
NOTICE_INDEX = "licenses/notice-index.json"
TESSERACT_STAMP = "release/tesseract/tesseract.stamp.json"
STAMP_INPUTS = (
    ("release/node/node.stamp.json", "node-runtime"),
    ("release/models/model.stamp.json", "ocr-model"),
)
RESOLVED_ASSETS = "config/resolved-assets.json"
FIXTURES_MANIFEST = "fixtures/manifest.json"
UV_LOCK = "native/uv.lock"


class InventoryError(Exception):
    """A named, actionable failure carrying the exit code the CLI must use."""

    label = "error"
    exit_code = 2

    def __init__(self, *messages: str) -> None:
        self.messages = [f"{self.label}: {m}" for m in messages]
        super().__init__("; ".join(self.messages))


class ConfigError(InventoryError):
    """A required tracked input is missing, malformed or inconsistent (2)."""

    label = "config error"
    exit_code = 2


class VerificationError(InventoryError):
    """Installed/prepared material does not match the frozen lock (1)."""

    label = "verification failure"
    exit_code = 1


_ABSENT = object()


def is_sha256(value: object) -> bool:
    """True for a 64-hex digest string (never a bool or a short/exotic value)."""
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def repo_relative(path: Path) -> str:
    """Repository-relative POSIX key for a consumed input (never a host path)."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        raise ConfigError("a consumed input path resolves outside the repository root") from None


def read_json_input(rel: str, problems: list[str]) -> object:
    """Read one required tracked JSON input, recording named problems.

    Returns the parsed document, or `_ABSENT` when the file is missing,
    unreadable or not JSON — a JSON `null` root is returned as None so the
    caller's root-shape check names it."""
    path = ROOT / rel
    if not path.is_file():
        problems.append(f"{rel}: required input file is missing")
        return _ABSENT
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        problems.append(f"{rel}: invalid JSON ({exc})")
    except OSError as exc:
        problems.append(f"{rel}: unreadable ({exc})")
    return _ABSENT


def load_assets_config() -> dict:
    """Validated config/resolved-assets.json (staged asset groups).

    Validated before any field is read: a malformed manifest is a named
    config error listing every violation, not a KeyError traceback."""
    problems: list[str] = []
    data = read_json_input(RESOLVED_ASSETS, problems)
    if data is _ABSENT:
        raise ConfigError(*problems)
    if not isinstance(data, dict):
        raise ConfigError(f"{RESOLVED_ASSETS}: root must be a JSON object")
    staging_root = data.get("staging_root")
    if not isinstance(staging_root, str) or not staging_root.strip():
        problems.append(f"{RESOLVED_ASSETS}: missing a non-empty string 'staging_root'")
    groups = data.get("assets")
    if not isinstance(groups, list):
        problems.append(f"{RESOLVED_ASSETS}: 'assets' must be a list")
        raise ConfigError(*problems)
    for i, group in enumerate(groups):
        if not isinstance(group, dict):
            problems.append(f"{RESOLVED_ASSETS}: assets[{i}] is malformed (not a JSON object)")
            continue
        for field in ("id", "kind", "source", "license", "rights", "serve_prefix"):
            value = group.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{RESOLVED_ASSETS}: assets[{i}] is missing a non-empty string {field!r}")
        if "package" in group and not isinstance(group["package"], dict):
            problems.append(f"{RESOLVED_ASSETS}: assets[{i}].package must be a JSON object")
        files = group.get("files")
        if not isinstance(files, list):
            problems.append(f"{RESOLVED_ASSETS}: assets[{i}].files must be a list")
            continue
        for j, entry in enumerate(files):
            where = f"assets[{i}].files[{j}]"
            if not isinstance(entry, dict):
                problems.append(f"{RESOLVED_ASSETS}: {where} is malformed (not a JSON object)")
                continue
            staged = entry.get("staged_path")
            if not isinstance(staged, str) or not staged.strip():
                problems.append(f"{RESOLVED_ASSETS}: {where} is missing a non-empty string 'staged_path'")
            if not is_sha256(entry.get("sha256")):
                problems.append(f"{RESOLVED_ASSETS}: {where} is missing a 64-hex 'sha256' digest")
            if not isinstance(entry.get("bytes"), int) or isinstance(entry.get("bytes"), bool):
                problems.append(f"{RESOLVED_ASSETS}: {where} is missing an integer 'bytes' count")
    if problems:
        raise ConfigError(*problems)
    return data


def load_fixtures_manifest() -> list[dict]:
    """Validated fixtures/manifest.json entries (the shipped public fixtures)."""
    problems: list[str] = []
    data = read_json_input(FIXTURES_MANIFEST, problems)
    if data is _ABSENT:
        raise ConfigError(*problems)
    if not isinstance(data, dict):
        raise ConfigError(f"{FIXTURES_MANIFEST}: root must be a JSON object")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ConfigError(f"{FIXTURES_MANIFEST}: 'entries' must be a list")
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append(f"{FIXTURES_MANIFEST}: entries[{i}] is malformed (not a JSON object)")
            continue
        for field in ("fixture_id", "family", "split", "rights"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{FIXTURES_MANIFEST}: entries[{i}] is missing a non-empty string {field!r}")
        if not isinstance(entry.get("path"), str) or not entry["path"].strip():
            problems.append(f"{FIXTURES_MANIFEST}: entries[{i}] is missing a non-empty string 'path'")
        if not is_sha256(entry.get("sha256")):
            problems.append(f"{FIXTURES_MANIFEST}: entries[{i}] is missing a 64-hex 'sha256' digest")
        if not isinstance(entry.get("bytes"), int) or isinstance(entry.get("bytes"), bool):
            problems.append(f"{FIXTURES_MANIFEST}: entries[{i}] is missing an integer 'bytes' count")
    if problems:
        raise ConfigError(*problems)
    return entries


def load_uv_lock() -> dict:
    """Validated native/uv.lock (TOML) — the frozen native package set."""
    path = ROOT / UV_LOCK
    if not path.is_file():
        raise ConfigError(f"{UV_LOCK}: required input file is missing")
    try:
        data = tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ConfigError(f"{UV_LOCK}: invalid TOML ({exc})") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{UV_LOCK}: root must be a TOML table")
    packages = data.get("package")
    if not isinstance(packages, list):
        raise ConfigError(f"{UV_LOCK}: 'package' must be a list of tables")
    problems = []
    for i, pkg in enumerate(packages):
        if not isinstance(pkg, dict) or not isinstance(pkg.get("name"), str) or not pkg["name"].strip():
            problems.append(f"{UV_LOCK}: package[{i}] is missing a non-empty string 'name'")
        elif not isinstance(pkg.get("version"), str) or not pkg["version"].strip():
            problems.append(f"{UV_LOCK}: package[{i}] ({pkg['name']}) is missing a non-empty string 'version'")
    if problems:
        raise ConfigError(*problems)
    return data


def load_required_inputs() -> tuple[list[dict], list[dict], dict]:
    """Validated notice index, node/model stamps and tesseract closure.

    All four are tracked, required inputs: a missing file, invalid JSON or an
    invalid root/entry shape is a named config error (every violation named
    separately), never a silently empty notice inventory, a silently absent
    runtime stamp or an empty deb closure."""
    problems: list[str] = []

    index = read_json_input(NOTICE_INDEX, problems)
    notice_inventory = _notice_entries(index, problems)
    stamps = [
        _stamp_entry(rel, read_json_input(rel, problems), problems)
        for rel, _ in STAMP_INPUTS
    ]
    tesseract = _tesseract_closure(read_json_input(TESSERACT_STAMP, problems), problems)
    if problems:
        raise ConfigError(*problems)
    return notice_inventory, stamps, tesseract


def _notice_entries(data: object, problems: list[str]) -> list[dict]:
    if data is _ABSENT:
        return []
    found: list[str] = []
    if not isinstance(data, dict):
        found.append(f"{NOTICE_INDEX}: root must be a JSON object")
    else:
        entries = data.get("entries")
        if not isinstance(entries, list):
            found.append(f"{NOTICE_INDEX}: 'entries' must be a list")
        else:
            for i, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    found.append(f"{NOTICE_INDEX}: entries[{i}] is malformed (not a JSON object)")
                    continue
                for field in ("id", "path"):
                    value = entry.get(field)
                    if not isinstance(value, str) or not value.strip():
                        found.append(f"{NOTICE_INDEX}: entries[{i}] is missing a non-empty string {field!r}")
                if not is_sha256(entry.get("sha256")):
                    found.append(f"{NOTICE_INDEX}: entries[{i}] is missing a 64-hex 'sha256' digest")
    problems.extend(found)
    if found:
        return []
    return [{"id": e["id"], "sha256": e["sha256"], "path": e["path"]} for e in data["entries"]]


def _stamp_entry(rel: str, data: object, problems: list[str]) -> dict:
    if data is _ABSENT:
        return {}
    if not isinstance(data, dict):
        problems.append(f"{rel}: root must be a JSON object")
        return {}
    if not is_sha256(data.get("sha256")):
        problems.append(f"{rel}: missing a 64-hex 'sha256' digest")
        return {}
    return data


def _tesseract_closure(data: object, problems: list[str]) -> dict:
    if data is _ABSENT:
        return {}
    found: list[str] = []
    if not isinstance(data, dict):
        found.append(f"{TESSERACT_STAMP}: root must be a JSON object")
    else:
        packages = data.get("packages")
        if not isinstance(packages, list):
            found.append(f"{TESSERACT_STAMP}: 'packages' must be a list")
        else:
            for i, pkg in enumerate(packages):
                if not isinstance(pkg, dict):
                    found.append(f"{TESSERACT_STAMP}: packages[{i}] is malformed (not a JSON object)")
                    continue
                filename = pkg.get("filename")
                if not isinstance(filename, str) or not filename.strip():
                    found.append(f"{TESSERACT_STAMP}: packages[{i}] is missing a non-empty string 'filename'")
                if not is_sha256(pkg.get("sha256")):
                    found.append(f"{TESSERACT_STAMP}: packages[{i}] is missing a 64-hex 'sha256' digest")
    problems.extend(found)
    return {} if found else data


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def git_commit_time(commit: str) -> str:
    """Committer timestamp (ISO, UTC) — deterministic per commit."""
    ts = subprocess.run(
        ["git", "show", "-s", "--format=%ct", commit],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    from datetime import datetime, timezone

    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_bun_lock() -> dict:
    """bun.lock is JSONC (trailing commas); strip them tolerantly.

    A missing, unreadable or malformed lock, or one whose consumed top-level
    tables have the wrong shape, is a named config error."""
    rel = "bun.lock"
    path = ROOT / rel
    if not path.is_file():
        raise ConfigError(f"{rel}: required input file is missing")
    try:
        raw = path.read_text()
    except OSError as exc:
        raise ConfigError(f"{rel}: unreadable ({exc})") from None
    txt = re.sub(r",(\s*[}\]])", r"\1", raw)
    try:
        data = json.loads(txt)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{rel}: invalid JSON ({exc})") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{rel}: root must be a JSON object")
    for table in ("packages", "workspaces"):
        if not isinstance(data.get(table), dict):
            raise ConfigError(f"{rel}: {table!r} must be a JSON object")
    return data


def workspace_table(lock: dict, workspace: str, field: str) -> dict:
    """Validated {field} table of one bun.lock workspace entry.

    An absent entry means "no workspace entry" -> empty, and an absent or null
    table means "no table" -> empty. The entry and the table must be JSON
    objects when present: an explicit null entry, or a list, string or number
    in either place is a named config error, never an AttributeError."""
    entry = lock["workspaces"].get(workspace, _ABSENT)
    if entry is _ABSENT:
        return {}
    if not isinstance(entry, dict):
        raise ConfigError(f'bun.lock: workspaces["{workspace}"] must be a JSON object')
    table = entry.get(field)
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise ConfigError(f'bun.lock: workspaces["{workspace}"].{field} must be a JSON object')
    return table


def npm_prod_closure(lock: dict, workspace: str = "apps/web") -> list[dict]:
    """Transitive closure of the workspace's production dependencies.

    bun.lock resolves one version per package name in this frozen lock, keyed
    by bare name; dependency entries may be ranges, so matching is by name and
    the resolved identity is taken from the lock entry itself."""
    packages = lock.get("packages", {})
    wanted = dict(workspace_table(lock, workspace, "dependencies"))
    seen: dict[str, dict] = {}
    queue = list(wanted.items())
    while queue:
        name, spec = queue.pop(0)
        if name in seen:
            continue
        entry = packages.get(name)
        if not entry:
            raise ConfigError(f"bun.lock cannot resolve {name} (wanted {spec})")
        if not isinstance(entry, list) or not isinstance(entry[0], str):
            raise ConfigError(f"bun.lock entry for {name} is malformed: {entry!r}")
        resolved = entry[0]
        if not resolved.startswith(f"{name}@"):
            raise ConfigError(f"bun.lock entry for {name} is malformed: {resolved!r}")
        version = resolved[len(name) + 1:]
        if not version:
            raise ConfigError(f"bun.lock entry for {name} records no resolved version: {resolved!r}")
        meta = entry[2] if len(entry) > 2 else {}
        if not isinstance(meta, dict):
            raise ConfigError(f"bun.lock metadata for {name} is malformed: {meta!r}")
        dependencies = meta.get("dependencies") or {}
        if not isinstance(dependencies, dict):
            raise ConfigError(f"bun.lock dependencies for {name} are malformed: {dependencies!r}")
        seen[name] = {
            "name": name,
            "version": version,
            "requested_spec": spec,
            "integrity": f"sha512-{entry[3]}" if len(entry) > 3 and entry[3] else None,
            "dependencies": sorted(dependencies.keys()),
        }
        for dep_name, dep_version in dependencies.items():
            if dep_name not in seen:
                queue.append((dep_name, dep_version))
    return [seen[k] for k in sorted(seen)]


def installed_package_candidates(name: str) -> list[Path]:
    """Deterministic candidate paths for an installed distribution.

    The bun isolated linker keeps every resolved package under
    node_modules/.bun/<flat-name>@<version>[/<peer-hash>]/, where scoped names
    use '+' instead of '/' in the directory name; a hoisted layout would place
    it under node_modules/<name>/ instead. Candidates are ordered by path so
    the resolved evidence never depends on directory-listing order."""
    candidates = [
        ROOT / "node_modules" / name / "package.json",
        ROOT / "apps" / "web" / "node_modules" / name / "package.json",
    ]
    bun_store = ROOT / "node_modules" / ".bun"
    if bun_store.is_dir():
        flat = name.replace("/", "+")
        candidates += sorted(
            entry / "node_modules" / name / "package.json"
            for entry in bun_store.glob(f"{flat}@*")
        )
    return candidates


def _resolve_installed(name: str, version: str, problems: list[str]) -> tuple[str, Path] | None:
    """License expression of the installed package that IS <name>@<version>.

    The lock decides the identity: a candidate whose `name` matches but whose
    `version` differs is not evidence for the locked package. Records a named
    verification problem — never a null license — when nothing matches."""
    observed: list[str] = []
    for pkg_json in installed_package_candidates(name):
        if not pkg_json.is_file():
            continue
        rel = repo_relative(pkg_json)
        try:
            data = json.loads(pkg_json.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            observed.append(f"{rel} is not valid JSON ({exc})")
            continue
        except OSError as exc:
            observed.append(f"{rel} is unreadable ({exc})")
            continue
        if not isinstance(data, dict):
            observed.append(f"{rel} is not a JSON object")
            continue
        observed.append(f"{rel} declares {data.get('name')}@{data.get('version')}")
        if data.get("name") != name or str(data.get("version")) != version:
            continue
        license_value = data.get("license")
        if isinstance(license_value, str) and license_value.strip():
            return license_value, pkg_json
        if isinstance(license_value, dict):
            legacy = license_value.get("type")
            if isinstance(legacy, str) and legacy.strip():
                return legacy, pkg_json
        problems.append(
            f"installed package metadata for {name}@{version} declares no license "
            f"expression (license: {license_value!r}) at {rel}"
        )
        return None
    detail = "; ".join(observed) if observed else "no candidate package.json exists"
    problems.append(
        f"installed package metadata does not match the locked identity {name}@{version}: {detail}"
    )
    return None


def npm_declared_license(name: str, version: str) -> tuple[str, Path]:
    """(declared license expression verbatim, installed package.json) for the
    locked name@version. Raises a named verification failure otherwise."""
    problems: list[str] = []
    resolved = _resolve_installed(name, version, problems)
    if resolved is None:
        raise VerificationError(*problems)
    return resolved


def resolve_npm_components(lock: dict) -> tuple[list[dict], list[Path]]:
    """Production npm closure, each package licensed by its locked identity.

    Returns the inventory's components and the installed package.json paths
    actually consumed (for the input digest map). Every unresolved package is
    reported: a partial closure is never presented as a complete inventory."""
    components: list[dict] = []
    installed: list[Path] = []
    problems: list[str] = []
    for pkg in npm_prod_closure(lock):
        resolved = _resolve_installed(pkg["name"], pkg["version"], problems)
        if resolved is None:
            continue
        expression, pkg_json = resolved
        installed.append(pkg_json)
        components.append(
            {
                "name": pkg["name"],
                "version": pkg["version"],
                "integrity": pkg["integrity"],
                "license": expression,
                "license_source": "node_modules package.json (installed distribution)",
                "dependencies": pkg["dependencies"],
            }
        )
    if problems:
        raise VerificationError(*problems)
    return components, installed


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def input_digests(installed: Iterable[Path] = ()) -> dict[str, str]:
    """SHA-256 of every consumed input — the identity of what was evaluated.

    Covers the tracked manifests and stamps, the notice index, and the
    installed package.json of each bundled package (`installed`). Keys are
    repository-relative and the map is sorted, so the recorded identity is
    stable and never embeds a host path. A missing required file is a named
    config error. Outputs depend only on these digests (never on HEAD or
    wall-clock), so two runs over identical repository content are
    byte-identical; the evaluated commit is recorded separately in the task
    evidence."""
    digests: dict[str, str] = {}
    missing: list[str] = []
    for path in list(ROOT / rel for rel in TRACKED_INPUTS) + list(installed):
        rel = repo_relative(path)
        if not path.is_file():
            missing.append(rel)
            continue
        digests[rel] = sha256_file(path)
    if missing:
        raise ConfigError(*[f"{rel}: required input file is missing" for rel in sorted(missing)])
    return dict(sorted(digests.items()))


def build_inventory() -> dict:
    assets_cfg = load_assets_config()
    lock = parse_bun_lock()
    uv_lock = load_uv_lock()
    fixtures = load_fixtures_manifest()
    notice_inventory, stamp_data, tess_stamp = load_required_inputs()
    npm_packages, installed_metadata = resolve_npm_components(lock)

    shipped_assets = []
    staged_paths = set()
    for group in assets_cfg["assets"]:
        for f in group["files"]:
            staged_paths.add(f["staged_path"])
            shipped_assets.append(
                {
                    "id": group["id"],
                    "kind": group["kind"],
                    "source": group["source"],
                    "package": group.get("package", {}).get("name"),
                    "package_version": group.get("package", {}).get("version"),
                    "package_integrity": group.get("package", {}).get("integrity"),
                    "license": group["license"],
                    "rights": group["rights"],
                    "path": f["staged_path"],
                    "serve_prefix": group["serve_prefix"],
                    "bytes": f["bytes"],
                    "sha256": f["sha256"],
                }
            )
    shipped_assets.sort(key=lambda a: a["path"])

    # Unaccounted files under the staged root (all of apps/web/public) are
    # unknowns, never silently dropped — except files this inventory itself
    # accounts for elsewhere (the prepared example directory).
    staged_root_prefix = assets_cfg["staging_root"].rstrip("/") + "/"
    prepared_example_paths = set()
    examples_dir = ROOT / "apps" / "web" / "public" / "examples"
    if examples_dir.is_dir():
        for path in sorted(examples_dir.rglob("*")):
            if path.is_file() and not path.is_symlink():
                prepared_example_paths.add(path.relative_to(ROOT).as_posix())
    unknown_assets = []
    public_dir = ROOT / "apps" / "web" / "public"
    static_runtime_paths = {"apps/web/public/sw.js", "apps/web/public/examples/index.json", "apps/web/public/_headers"}
    for path in sorted(public_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel_full = path.relative_to(ROOT).as_posix()
        if rel_full in prepared_example_paths or rel_full in static_runtime_paths:
            continue
        rel_staged = path.relative_to(public_dir).as_posix()
        if rel_staged not in staged_paths:
            unknown_assets.append({"path": rel_full, "bytes": path.stat().st_size})

    prepared_example = []
    offline_example_paths: set[str] = set()
    manifest_ts = ROOT / "apps" / "web" / "src" / "offline" / "manifest.ts"
    if manifest_ts.is_file():
        import re as _re

        offline_example_paths = {
            m.group(1).lstrip("/")
            for m in _re.finditer(r'path:\s*"/(examples/[^"]+)"', manifest_ts.read_text())
        }
    examples_dir = ROOT / "apps" / "web" / "public" / "examples"
    if examples_dir.is_dir():
        for path in sorted(examples_dir.rglob("*")):
            if path.is_file() and not path.is_symlink():
                rel = path.relative_to(ROOT).as_posix()
                staged_rel = rel[len("apps/web/public/"):]
                prepared_example.append(
                    {
                        "path": rel,
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                        "in_offline_manifest": staged_rel in offline_example_paths,
                        "rights": "Prepared from this repository's own public fixtures by scripts/prepare_examples.py (project MIT terms; no third-party material).",
                    }
                )

    native_packages = []
    dev_only_pypi = {"pytest", "iniconfig", "packaging", "pluggy", "pygments", "colorama"}
    for pkg in uv_lock["package"]:
        name = pkg["name"]
        version = pkg["version"]
        if name == "inkflip":  # the native workspace root itself
            continue
        native_packages.append(
            {
                "name": name,
                "version": version,
                "license": PYPI_LICENSES.get(name),
                "license_source": "docs/ATTRIBUTION.md ledger (T02 freeze; PyPI metadata re-verified there)",
                "dev_group": name in dev_only_pypi,
            }
        )
    native_packages.sort(key=lambda p: p["name"])

    fixture_entries = []
    for entry in fixtures:
        fixture_entries.append(
            {
                "fixture_id": entry["fixture_id"],
                "family": entry["family"],
                "split": entry["split"],
                "path": f"fixtures/{entry['path']}",
                "bytes": entry["bytes"],
                "sha256": entry["sha256"],
                "rights": entry["rights"],
            }
        )

    dev_npm = sorted(workspace_table(lock, "", "devDependencies").keys())

    # Tesseract Debian closure (production-image dependency, linux/amd64):
    # recorded as its own bucket so the deb packages are neither double-
    # counted with the python wheels nor silently absent from the SBOM.
    native_deb_closure = []
    for pkg in tess_stamp["packages"]:
        native_deb_closure.append(
            {
                "filename": pkg.get("filename"),
                "sha256": pkg.get("sha256"),
                "bytes": pkg.get("bytes"),
                "target": "linux/amd64 production image",
                "closure": f"{tess_stamp.get('package')} {tess_stamp.get('version')}",
                "license": tess_stamp.get("license"),
            }
        )

    # Node runtime + OCR model stamps (production-image inputs, linux/amd64)
    runtime_stamps = []
    for (stamp_rel, kind), stamp in zip(STAMP_INPUTS, stamp_data):
        runtime_stamps.append({
            "kind": kind,
            "path": stamp_rel,
            "sha256": stamp["sha256"],
            "bytes": stamp.get("bytes"),
            "target": "linux/amd64 production image (Docker)",
            "classification": "native-bundle input; not browser-shipped",
        })

    static_runtime = []
    sw = ROOT / "apps" / "web" / "public" / "sw.js"
    if sw.is_file():
        static_runtime.append(
            {
                "path": "apps/web/public/sw.js",
                "bytes": sw.stat().st_size,
                "sha256": sha256_file(sw),
                "kind": "service-worker",
                "rights": "Original project code (MIT). Manifest-bound explicit caching only; no precache at install.",
            }
        )
    index_json = ROOT / "apps" / "web" / "public" / "examples" / "index.json"
    if index_json.is_file():
        static_runtime.append(
            {
                "path": "apps/web/public/examples/index.json",
                "bytes": index_json.stat().st_size,
                "sha256": sha256_file(index_json),
                "kind": "example-catalog",
                "rights": "Generated catalog of the prepared public examples (project MIT terms).",
            }
        )

    unknown = [u for u in unknown_assets]
    if unknown:
        sys.stderr.write(
            f"WARNING: {len(unknown)} unaccounted file(s) under the staged asset roots\n"
        )

    return {
        "schema_version": "1.0.0",
        "kind": "inkflip-distribution-inventory",
        "inputs": input_digests(installed_metadata),
        "classification": {
            "shipped": "bytes that leave the repository or are compiled into the shipped bundle",
            "runtime-tooling": "frozen native environment distributed as source + lockfile",
            "development-only": "build/test/lint tooling, never distributed to users",
            "unknown": "material in shipped directories that no manifest accounts for (must be empty)",
        },
        "counts": {
            "shipped_asset_files": len(shipped_assets),
            "prepared_example_files": len(prepared_example),
            "prepared_example_in_offline_manifest": sum(1 for e in prepared_example if e["in_offline_manifest"]),
            "offline_manifest_example_entries": len(offline_example_paths),
            "bundled_npm_packages": len(npm_packages),
            "native_lock_packages": len(native_packages),
            "fixture_entries": len(fixture_entries),
            "native_deb_packages": len(native_deb_closure),
            "runtime_stamp_inputs": len(runtime_stamps),
            "notice_inventory_entries": len(notice_inventory),
            "unknown": len(unknown),
        },
        "native_deb_closure": {
            "target": "linux/amd64 production image (Docker)",
            "packages": native_deb_closure,
        },
        "runtime_stamp_inputs": runtime_stamps,
        "notice_inventory": notice_inventory,
        "static_runtime": static_runtime,
        "shipped_assets": shipped_assets,
        "prepared_example": prepared_example,
        "bundled_npm_packages": npm_packages,
        "native_lock_packages": native_packages,
        "fixtures": fixture_entries,
        "development_only_npm": dev_npm,
        "unknown": unknown,
        "excluded": {
            "private_or_generated": [
                "apps/web/dist (generated; rebuilt every build)",
                "native/.venv (built locally from the frozen lock; never shipped)",
                "tests/privacy/.private (live canary material; git-ignored)",
                "artifacts/tasks/** captures and receipts (task evidence, not distributed)",
                "evaluation/ held-out labels (custodian-owned; never distributed)",
            ]
        },
    }


def cdx_purl_ecosystem(name: str, version: str, ecosystem: str) -> str:
    return f"pkg:{ecosystem}/{name}@{version}"


def build_cdx(inventory: dict) -> dict:
    # Deterministic identity: serial derives from the input digests, and the
    # timestamp is the manifest's recorded "as of" date — never wall-clock.
    identity = hashlib.sha256(
        json.dumps(inventory["inputs"], sort_keys=True).encode()
    ).hexdigest()
    components = []
    for pkg in inventory["bundled_npm_packages"]:
        comp = {
            "type": "library",
            "bom-ref": cdx_purl_ecosystem(pkg["name"], pkg["version"], "npm"),
            "name": pkg["name"],
            "version": pkg["version"],
            "purl": cdx_purl_ecosystem(pkg["name"], pkg["version"], "npm"),
            "scope": "required",
        }
        if pkg.get("license"):
            comp["licenses"] = [{"license": {"id": pkg["license"]}}]
        if pkg.get("integrity"):
            comp["hashes"] = [{"alg": "SHA-512", "content": pkg["integrity"].split("-", 1)[1]}]
        components.append(comp)
    for pkg in inventory["native_lock_packages"]:
        comp = {
            "type": "library",
            "bom-ref": cdx_purl_ecosystem(pkg["name"], pkg["version"], "pypi"),
            "name": pkg["name"],
            "version": pkg["version"],
            "purl": cdx_purl_ecosystem(pkg["name"], pkg["version"], "pypi"),
            "scope": "required" if not pkg.get("dev_group") else "excluded",
            "comment": "runtime-tooling: frozen native environment (source+lock distribution)",
        }
        if pkg.get("license"):
            comp["licenses"] = [{"expression": pkg["license"]}]
        components.append(comp)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{identity[:8]}-0000-4000-8000-{identity[8:20]}",
        "version": 1,
        "metadata": {
            "timestamp": "2026-09-13T00:00:00Z",  # as-of date of the recorded distribution manifest
            "tools": {"components": [{"type": "application", "name": "scripts/distribution/build_inventory.py", "version": "1.0.0"}]},
            "component": {
                "bom-ref": "pkg:generic/inkflip@0.0.0",
                "type": "application",
                "name": "inkflip",
                "version": "0.0.0",
                "comment": "local-first PDF reading inspector; static browser app + local native tooling. License/copyright finalization pending (T47).",
            },
            "properties": [
                {"name": "inkflip:input-digests-sha256", "value": identity},
                {"name": "inkflip:status", "value": "preparation (not the completed T47 gate)"},
            ],
        },
        "components": sorted(components, key=lambda c: c["bom-ref"]),
    }


def render_surface_doc(inventory: dict) -> str:
    """Compact deterministic public digest of the current distribution surface."""
    lines = [
        "# Distribution surface digest",
        "",
        "Generated by `scripts/distribution/build_inventory.py` from the frozen",
        "inputs recorded in `inventory.json` (deterministic: identical inputs",
        "produce this exact document). Current as of the recorded toolchain",
        "freeze; re-generate after any dependency or asset change.",
        "",
        "## Counts",
        "",
        "| Bucket | Count |",
        "| --- | --- |",
    ]
    for key, value in sorted(inventory["counts"].items()):
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## Bundled production packages (browser bundle)",
        "",
        "| Package | Version | Declared license |",
        "| --- | --- | --- |",
    ]
    for pkg in inventory["bundled_npm_packages"]:
        lines.append(f"| {pkg['name']} | {pkg['version']} | {pkg['license']} |")
    lines += [
        "",
        "## Native runtime-tooling packages (frozen lock)",
        "",
        "| Package | Version | Declared license | Dev group |",
        "| --- | --- | --- | --- |",
    ]
    for pkg in inventory["native_lock_packages"]:
        lines.append(f"| {pkg['name']} | {pkg['version']} | {pkg['license']} | {'yes' if pkg['dev_group'] else 'no'} |")
    lines += [
        "",
        "## Staged browser asset groups",
        "",
        "| Group | Files | License |",
        "| --- | --- | --- |",
    ]
    seen = {}
    for a in inventory["shipped_assets"]:
        seen[a["id"]] = (a["license"], seen.get(a["id"], (None, 0))[1] + 1)
    for gid, (lic, count) in sorted(seen.items()):
        lines.append(f"| {gid} | {count} | {lic} |")
    lines.append("")
    return "\n".join(lines)


def check_output(path: Path, content: str) -> int:
    """Compare one output file against the derived bytes — never writing.

    Returns 0 when the file matches, 1 for a named failure (missing, not a
    regular file, unreadable, or differing bytes). The file is left untouched
    and no directory is created, so a successful check cannot manufacture its
    own evidence."""
    if not path.exists():
        print(f"MISSING: {path}", file=sys.stderr)
        return 1
    if not path.is_file():
        print(f"NOT-A-FILE: {path}", file=sys.stderr)
        return 1
    try:
        existing = path.read_bytes()
    except OSError as exc:
        print(f"UNREADABLE: {path} ({exc})", file=sys.stderr)
        return 1
    if existing != content.encode():
        print(f"CHANGED: {path}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 success, 1 verification failure, 2 config/usage error.",
    )
    parser.add_argument("--out", default=".private/distribution/inventory")
    parser.add_argument("--check", action="store_true", help="fail if outputs would change")
    parser.add_argument("--surface-doc", default=None, help="also write a compact public digest (e.g. docs/distribution/SURFACE.md)")
    args = parser.parse_args()

    try:
        inventory = build_inventory()
        sbom = build_cdx(inventory)
    except InventoryError as exc:
        # Named, actionable failures only — never a traceback, and no output
        # is written from a run that could not establish its inputs.
        for line in exc.messages:
            print(line, file=sys.stderr)
        return exc.exit_code

    out_dir = ROOT / args.out
    targets = [
        (out_dir / "inventory.json", str(out_dir / "inventory.json"),
         json.dumps(inventory, indent=2, sort_keys=True, ensure_ascii=False) + "\n"),
        (out_dir / "sbom.cdx.json", str(out_dir / "sbom.cdx.json"),
         json.dumps(sbom, indent=2, sort_keys=True, ensure_ascii=False) + "\n"),
    ]
    if args.surface_doc:
        targets.append((ROOT / args.surface_doc, args.surface_doc, render_surface_doc(inventory)))

    status = 0
    written: list[str] = []
    for path, label, content in targets:
        if args.check:
            # Check mode is strictly read-only: every target is compared and
            # left untouched, and nothing (not even the parent directory) is
            # created. Each kind of failure is named on stderr.
            status = max(status, check_output(path, content))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        written.append(label)
    if inventory["unknown"]:
        print(f"inventory records {len(inventory['unknown'])} unknown shipped-path file(s)", file=sys.stderr)
        status = max(status, 1)
    # A success line is only truthful when nothing was recorded as failing.
    if status == 0:
        for label in written:
            print(f"wrote {label}")
    return status


if __name__ == "__main__":
    sys.exit(main())
