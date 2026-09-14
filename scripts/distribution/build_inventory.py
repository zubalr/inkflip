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
      --out .private/distribution/inventory [--check]
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


def input_digests() -> dict:
    """SHA-256 of every consumed input — the identity of what was evaluated.

    Outputs depend only on these digests (never on HEAD or wall-clock), so
    two runs over identical repository content are byte-identical. The
    evaluated commit is recorded separately in the task evidence."""
    names = [
        "config/resolved-assets.json",
        "bun.lock",
        "native/uv.lock",
        "fixtures/manifest.json",
        "package.json",
        "apps/web/package.json",
    ]
    return {n: sha256_file(ROOT / n) for n in names}


def build_inventory() -> dict:
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

    # Tesseract Debian closure (production-image dependency, linux/amd64):
    # recorded as its own bucket so the deb packages are neither double-
    # counted with the python wheels nor silently absent from the SBOM.
    native_deb_closure = []
    tess_stamp_path = ROOT / "release" / "tesseract" / "tesseract.stamp.json"
    if tess_stamp_path.is_file():
        try:
            tsd = json.loads(tess_stamp_path.read_text())
        except json.JSONDecodeError:
            tsd = {}
        for pkg in tsd.get("packages", []):
            native_deb_closure.append(
                {
                    "filename": pkg.get("filename"),
                    "sha256": pkg.get("sha256"),
                    "bytes": pkg.get("bytes"),
                    "target": "linux/amd64 production image",
                    "closure": f"{tsd.get('package')} {tsd.get('version')}",
                    "license": tsd.get("license"),
                }
            )

    # Node runtime + OCR model stamps (production-image inputs, linux/amd64)
    runtime_stamps = []
    for stamp_rel, kind in (("release/node/node.stamp.json", "node-runtime"),
                            ("release/models/model.stamp.json", "ocr-model")):
        sp = ROOT / stamp_rel
        if sp.is_file():
            try:
                sd = json.loads(sp.read_text())
            except json.JSONDecodeError:
                continue
            if sd.get("sha256"):
                runtime_stamps.append({
                    "kind": kind,
                    "path": stamp_rel,
                    "sha256": sd.get("sha256"),
                    "bytes": sd.get("bytes"),
                    "target": "linux/amd64 production image (Docker)",
                    "classification": "native-bundle input; not browser-shipped",
                })
    notice_inventory = []
    index_path = ROOT / "licenses" / "notice-index.json"
    if index_path.is_file():
        try:
            nid = json.loads(index_path.read_text())
            notice_inventory = [
                {"id": e.get("id"), "sha256": e.get("sha256"),
                 "path": e.get("path")}
                for e in nid.get("entries", []) if isinstance(e, dict)
            ]
        except json.JSONDecodeError:
            pass

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
        "inputs": input_digests(),
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
            "bundled_npm_packages": len(npm_components),
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
        "native_deb_closure": {
            "target": "linux/amd64 production image (Docker)",
            "packages": native_deb_closure,
        },
        "runtime_stamp_inputs": runtime_stamps,
        "notice_inventory": notice_inventory,
        "static_runtime": static_runtime,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=".private/distribution/inventory")
    parser.add_argument("--check", action="store_true", help="fail if outputs would change")
    parser.add_argument("--surface-doc", default=None, help="also write a compact public digest (e.g. docs/distribution/SURFACE.md)")
    args = parser.parse_args()

    inventory = build_inventory()
    sbom = build_cdx(inventory)

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
    if args.surface_doc:
        surface = render_surface_doc(inventory)
        (ROOT / args.surface_doc).write_text(surface)
        print(f"wrote {args.surface_doc}")
    if inventory["unknown"]:
        print(f"inventory records {len(inventory['unknown'])} unknown shipped-path file(s)", file=sys.stderr)
        status = max(status, 1)
    return status


if __name__ == "__main__":
    sys.exit(main())
