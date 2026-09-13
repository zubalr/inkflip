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

Inputs (read-only): config/resolved-assets.json, bun.lock (tolerant JSONC),
native/uv.lock (TOML), fixtures/manifest.json, package manifests,
docs/ATTRIBUTION.md-derived license map (validated against resolved-assets).

Usage:
  python3 scripts/distribution/build_inventory.py \
      --out artifacts/sbom/zcode-preparation [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
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
    """bun.lock is JSONC (trailing commas); strip them tolerantly."""
    raw = (ROOT / "bun.lock").read_text()
    txt = re.sub(r",(\s*[}\]])", r"\1", raw)
    return json.loads(txt)


def npm_prod_closure(lock: dict, workspace: str = "apps/web") -> list[dict]:
    """Transitive closure of the workspace's production dependencies.

    bun.lock resolves one version per package name in this frozen lock, keyed
    by bare name; dependency entries may be ranges, so matching is by name and
    the resolved identity is taken from the lock entry itself."""
    packages = lock.get("packages", {})
    workspaces = lock.get("workspaces", {})
    wanted = dict(workspaces.get(workspace, {}).get("dependencies", {}))
    seen: dict[str, dict] = {}
    queue = list(wanted.items())
    while queue:
        name, spec = queue.pop(0)
        if name in seen:
            continue
        entry = packages.get(name)
        if not entry:
            raise SystemExit(f"bun.lock cannot resolve {name} (wanted {spec})")
        resolved = entry[0]
        if not resolved.startswith(f"{name}@"):
            raise SystemExit(f"bun.lock entry for {name} is malformed: {resolved!r}")
        version = resolved[len(name) + 1:]
        meta = entry[2] if len(entry) > 2 else {}
        seen[name] = {
            "name": name,
            "version": version,
            "requested_spec": spec,
            "integrity": f"sha512-{entry[3]}" if len(entry) > 3 and entry[3] else None,
            "dependencies": sorted((meta.get("dependencies") or {}).keys()),
        }
        for dep_name, dep_version in (meta.get("dependencies") or {}).items():
            if dep_name not in seen:
                queue.append((dep_name, dep_version))
    return [seen[k] for k in sorted(seen)]


def npm_declared_license(name: str) -> str | None:
    """Declared license from the installed distribution (bun isolated linker
    keeps every resolved package under node_modules/.bun/<name>@<ver>/)."""
    candidates = [
        ROOT / "node_modules" / name / "package.json",
        ROOT / "apps" / "web" / "node_modules" / name / "package.json",
    ]
    bun_store = ROOT / "node_modules" / ".bun"
    if bun_store.is_dir():
        for entry in sorted(bun_store.glob(f"{name}@*")):
            candidates.append(entry / "node_modules" / name / "package.json")
    for pkg_json in candidates:
        if pkg_json.is_file():
            try:
                return json.loads(pkg_json.read_text()).get("license")
            except json.JSONDecodeError:
                continue
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_inventory() -> dict:
    commit = git_commit()
    assets_cfg = json.loads((ROOT / "config" / "resolved-assets.json").read_text())
    lock = parse_bun_lock()
    uv_lock = tomllib.loads((ROOT / "native" / "uv.lock").read_text())
    fixtures = json.loads((ROOT / "fixtures" / "manifest.json").read_text())

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
    for path in sorted(public_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel_full = path.relative_to(ROOT).as_posix()
        rel_staged = path.relative_to(public_dir).as_posix()
        if rel_full in prepared_example_paths:
            continue
        if rel_staged not in staged_paths:
            unknown_assets.append({"path": rel_full, "bytes": path.stat().st_size})

    prepared_example = []
    examples_dir = ROOT / "apps" / "web" / "public" / "examples"
    if examples_dir.is_dir():
        for path in sorted(examples_dir.rglob("*")):
            if path.is_file() and not path.is_symlink():
                prepared_example.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                        "rights": "Prepared from this repository's own public fixtures by scripts/prepare_examples.py (project MIT terms; no third-party material).",
                    }
                )

    npm_components = []
    for pkg in npm_prod_closure(lock):
        npm_components.append(
            {
                "name": pkg["name"],
                "version": pkg["version"],
                "integrity": pkg["integrity"],
                "license": npm_declared_license(pkg["name"]),
                "license_source": "node_modules package.json (installed distribution)",
                "dependencies": pkg["dependencies"],
            }
        )

    native_packages = []
    dev_only_pypi = {"pytest", "iniconfig", "packaging", "pluggy", "pygments", "colorama"}
    for pkg in uv_lock.get("package", []):
        name = pkg.get("name")
        version = pkg.get("version")
        if not name or name == "inkflip":  # the native workspace root itself
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
    for entry in fixtures.get("entries", []):
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

    dev_npm = sorted((lock["workspaces"].get("", {}).get("devDependencies") or {}).keys())

    unknown = [u for u in unknown_assets]
    if unknown:
        sys.stderr.write(
            f"WARNING: {len(unknown)} unaccounted file(s) under the staged asset roots\n"
        )

    return {
        "schema_version": "1.0.0",
        "kind": "inkflip-distribution-inventory",
        "evaluated_commit": commit,
        "classification": {
            "shipped": "bytes that leave the repository or are compiled into the shipped bundle",
            "runtime-tooling": "frozen native environment distributed as source + lockfile",
            "development-only": "build/test/lint tooling, never distributed to users",
            "unknown": "material in shipped directories that no manifest accounts for (must be empty)",
        },
        "counts": {
            "shipped_asset_files": len(shipped_assets),
            "prepared_example_files": len(prepared_example),
            "bundled_npm_packages": len(npm_components),
            "native_lock_packages": len(native_packages),
            "fixture_entries": len(fixture_entries),
            "unknown": len(unknown),
        },
        "shipped_assets": shipped_assets,
        "prepared_example": prepared_example,
        "bundled_npm_packages": npm_components,
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


def build_cdx(inventory: dict, commit_time: str) -> dict:
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
        "serialNumber": f"urn:uuid:{hashlib.sha1(inventory['evaluated_commit'].encode()).hexdigest()[:8]}-0000-4000-8000-{hashlib.sha1(('sbom' + inventory['evaluated_commit']).encode()).hexdigest()[:12]}",
        "version": 1,
        "metadata": {
            "timestamp": commit_time,
            "tools": {"components": [{"type": "application", "name": "scripts/distribution/build_inventory.py", "version": "1.0.0"}]},
            "component": {
                "bom-ref": "pkg:generic/inkflip@0.0.0",
                "type": "application",
                "name": "inkflip",
                "version": "0.0.0",
                "comment": "local-first PDF reading inspector; static browser app + local native tooling. License/copyright finalization pending (T47).",
            },
            "properties": [
                {"name": "inkflip:evaluated-commit", "value": inventory["evaluated_commit"]},
                {"name": "inkflip:status", "value": "preparation (not the completed T47 gate)"},
            ],
        },
        "components": sorted(components, key=lambda c: c["bom-ref"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="artifacts/sbom/zcode-preparation")
    parser.add_argument("--check", action="store_true", help="fail if outputs would change")
    args = parser.parse_args()

    inventory = build_inventory()
    commit_time = git_commit_time(inventory["evaluated_commit"])
    sbom = build_cdx(inventory, commit_time)

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        "inventory.json": json.dumps(inventory, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        "sbom.cdx.json": json.dumps(sbom, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    }
    status = 0
    for name, content in targets.items():
        path = out_dir / name
        if args.check and path.is_file() and path.read_text() != content:
            print(f"CHANGED: {path}", file=sys.stderr)
            status = 1
        path.write_text(content)
        print(f"wrote {path}")
    if inventory["unknown"]:
        print(f"inventory records {len(inventory['unknown'])} unknown shipped-path file(s)", file=sys.stderr)
        status = max(status, 1)
    return status


if __name__ == "__main__":
    sys.exit(main())
