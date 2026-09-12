#!/usr/bin/env python3
"""Stage and verify Inkflip's same-origin browser assets (T02).

Three explicit operations, no implicit work:

  resolve  Enumerate the staged-asset set from the *installed* npm packages
           (pdfjs-dist, tesseract.js, tesseract.js-core) plus the pinned
           upstream OCR model entry, and write config/resolved-assets.json
           with real SHA-256 digests and byte counts.
  stage    Copy npm-sourced files and download upstream-sourced files into
           apps/web/public exactly as the manifest records. Every staged byte
           is hashed before it is accepted; a hash/size mismatch fails closed
           and leaves no partial file. Downloads happen only here, never at
           runtime.
  verify   Re-hash every staged file against the manifest. Missing files,
           wrong hashes, wrong sizes, schema violations and remote serve paths
           all fail closed. Used by scripts/check_dependencies.py --frozen.

Standard library only so the script runs under the pinned interpreter without
project dependencies installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/resolved-assets.json"
STAGING_ROOT = "apps/web/public"
ALLOWED_STAGED_PREFIXES = ("assets/", "models/", "notices/")

SCHEMA_VERSION = "1.0.0"
ASSET_KEYS = {"id", "kind", "version", "source", "source_url", "package",
              "license", "rights", "serve_prefix", "delivery", "files"}
PACKAGE_KEYS = {"name", "version", "integrity"}
FILE_KEYS = {"package_path", "staged_path", "sha256", "bytes", "source_url"}
REQUIRED_ASSET_KEYS = {"id", "kind", "version", "source", "license",
                       "serve_prefix", "files"}
REQUIRED_FILE_KEYS = {"staged_path", "sha256", "bytes"}
VALID_SOURCES = {"npm-package", "upstream-url"}

# The staged-asset set. Runtime-fetched directories of the exact pinned npm
# packages, the browser worker script, all feature-detected WASM core variants
# (scalar/SIMD/relaxed-SIMD, lstm and fast — the wrapper selects per browser
# capability), the explicit OCR model and every license/notice file shipped
# next to the binaries. T02 owns this list; changing it is a lock-owner change.
NPM_ASSET_SETS = [
    {
        "id": "pdfjs-cmaps",
        "kind": "reader-runtime",
        "package_name": "pdfjs-dist",
        "package_dir": "cmaps",
        "serve_prefix": "/assets/pdfjs/{version}/cmaps/",
        "license": "Apache-2.0",
        "rights": "Adobe-derived CMaps redistributed inside the Apache-2.0 pdfjs-dist package; complete package notices retained.",
        "delivery": "same-origin static; fetched by pdf.js only for documents that need external CMaps",
    },
    {
        "id": "pdfjs-standard-fonts",
        "kind": "reader-runtime",
        "package_name": "pdfjs-dist",
        "package_dir": "standard_fonts",
        "serve_prefix": "/assets/pdfjs/{version}/standard_fonts/",
        "license": "Apache-2.0",
        "rights": "Font metrics/glyph programs shipped with the Apache-2.0 pdfjs-dist package; notices retained.",
        "delivery": "same-origin static; fetched by pdf.js when a document references a non-embedded standard font",
    },
    {
        "id": "pdfjs-wasm",
        "kind": "reader-runtime-binary",
        "package_name": "pdfjs-dist",
        "package_dir": "wasm",
        "serve_prefix": "/assets/pdfjs/{version}/wasm/",
        "license": "Apache-2.0",
        "rights": "openjpeg (JPEG 2000), jbig2 and qcms WASM builds with their LICENSE_* notice files staged alongside the binaries.",
        "delivery": "same-origin static; fetched by pdf.js for image decode and ICC handling",
    },
    {
        "id": "pdfjs-iccs",
        "kind": "reader-runtime",
        "package_name": "pdfjs-dist",
        "package_dir": "iccs",
        "serve_prefix": "/assets/pdfjs/{version}/iccs/",
        "license": "Apache-2.0",
        "rights": "ICC profile and LICENSE shipped inside the Apache-2.0 pdfjs-dist package.",
        "delivery": "same-origin static; fetched by pdf.js for ICC-based color correction",
    },
    {
        "id": "pdfjs-license",
        "kind": "notice",
        "package_name": "pdfjs-dist",
        "package_files": ["LICENSE"],
        "serve_prefix": "/assets/pdfjs/{version}/",
        "license": "Apache-2.0",
        "rights": "Full license text of the distributed pdfjs-dist package.",
        "delivery": "same-origin static notice",
    },
    {
        "id": "tesseract-worker",
        "kind": "ocr-runtime",
        "package_name": "tesseract.js",
        "package_files": ["dist/worker.min.js", "dist/worker.min.js.LICENSE.txt", "LICENSE.md"],
        "serve_prefix": "/assets/tesseract/{version}/",
        "license": "Apache-2.0",
        "rights": "Browser worker script and bundled-license notice of the Apache-2.0 tesseract.js package.",
        "delivery": "same-origin static; loaded with workerBlobURL:false — never the jsdelivr CDN default",
    },
    {
        "id": "tesseract-core",
        "kind": "ocr-runtime-binary",
        "package_name": "tesseract.js-core",
        # Browser path: tesseract.js's getCore.js importScripts()s exactly one
        # feature-detected self-contained *.wasm.js shim (the wasm binary is
        # embedded in it). The split *.js + *.wasm pairs are Node-only builds
        # resolved from node_modules, so they are intentionally not staged.
        "package_files": [
            "tesseract-core.wasm.js",
            "tesseract-core-lstm.wasm.js",
            "tesseract-core-simd.wasm.js",
            "tesseract-core-simd-lstm.wasm.js",
            "tesseract-core-relaxedsimd.wasm.js",
            "tesseract-core-relaxedsimd-lstm.wasm.js",
            "LICENSE",
        ],
        "serve_prefix": "/assets/tesseract-core/{version}/",
        "license": "Apache-2.0",
        "rights": "Single-threaded scalar/SIMD/relaxed-SIMD WASM builds (no pthread/SharedArrayBuffer) plus the package LICENSE.",
        "delivery": "same-origin static; the worker imports exactly one feature-detected self-contained *.wasm.js shim",
    },
]

UPSTREAM_ASSETS = [
    {
        "id": "tessdata-fast-eng",
        "kind": "ocr-model",
        "version": "65727574dfcd264acbb0c3e07860e4e9e9b22185",
        "source": "upstream-url",
        "license": "Apache-2.0",
        "rights": "tessdata_fast eng.traineddata from the official tesseract-ocr/tessdata_fast repository at the pinned commit; Apache-2.0 per repository LICENSE.",
        "serve_prefix": "/models/tessdata-fast-eng/7d4322bd/",
        "delivery": "same-origin static, gzip:false, versioned path; downloaded only by explicit `prepare_assets.py stage`, never at runtime",
        "files": [
            {
                "staged_path": "models/tessdata-fast-eng/7d4322bd/eng.traineddata",
                "sha256": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
                "bytes": 4113088,
                "source_url": "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/65727574dfcd264acbb0c3e07860e4e9e9b22185/eng.traineddata",
            }
        ],
    },
]


class AssetError(Exception):
    """A manifest or staged-file violation; always fails closed."""


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package_root(name: str) -> Path:
    """Locate an installed package through the isolated linker's workspace link."""
    link = ROOT / "apps/web/node_modules" / name
    if not link.exists():
        # Fall back to the root store for build-only packages.
        matches = sorted((ROOT / "node_modules/.bun").glob(f"{name}@*/node_modules/{name}"))
        if matches:
            return matches[-1]
        raise AssetError(f"package not installed: {name} (run `bun install --frozen-lockfile`)")
    return link.resolve()


def package_meta(name: str) -> dict:
    meta = json.loads((package_root(name) / "package.json").read_text())
    integrity = None
    lock = (ROOT / "bun.lock").read_text()
    # bun.lock records `"name": ["name@version", "", {meta}, "sha512-…"]`.
    match = re.search(rf'"{re.escape(name)}":\s*\[([^\]]*)\]', lock)
    if match:
        integrity_match = re.search(r'"(sha\d+-[A-Za-z0-9+/=]+)"', match.group(1))
        if integrity_match:
            integrity = integrity_match.group(1)
    return {"name": name, "version": meta["version"], "integrity": integrity}


def check_staged_path(staged_path: str) -> None:
    parsed = PurePosixPath(staged_path)
    if parsed.is_absolute() or ".." in parsed.parts or "\\" in staged_path:
        raise AssetError(f"staged path escapes the staging root: {staged_path!r}")
    if not staged_path.startswith(ALLOWED_STAGED_PREFIXES):
        raise AssetError(f"staged path outside allowed prefixes {ALLOWED_STAGED_PREFIXES}: {staged_path!r}")


def check_serve_prefix(prefix: str) -> None:
    if not prefix.startswith("/") or prefix.startswith("//") or "://" in prefix:
        raise AssetError(f"serve prefix is not a same-origin path: {prefix!r}")


def validate_manifest(data: dict) -> list[dict]:
    """Strict manifest validation (fixture family F22: reject unknown keys)."""
    allowed_top = {"schema_version", "recorded_by", "recorded_at",
                   "staging_root", "public_base", "assets"}
    unknown = set(data) - allowed_top
    if unknown:
        raise AssetError(f"manifest has unknown keys: {sorted(unknown)}")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise AssetError(f"unsupported manifest schema_version: {data.get('schema_version')!r}")
    if data.get("staging_root") != STAGING_ROOT:
        raise AssetError(f"unexpected staging_root: {data.get('staging_root')!r}")
    assets = data.get("assets")
    if not isinstance(assets, list) or not assets:
        raise AssetError("manifest must list at least one asset")
    seen_ids: set[str] = set()
    for asset in assets:
        unknown = set(asset) - ASSET_KEYS
        if unknown:
            raise AssetError(f"asset {asset.get('id')!r} has unknown keys: {sorted(unknown)}")
        missing = REQUIRED_ASSET_KEYS - set(asset)
        if missing:
            raise AssetError(f"asset {asset.get('id')!r} missing keys: {sorted(missing)}")
        if asset["id"] in seen_ids:
            raise AssetError(f"duplicate asset id: {asset['id']}")
        seen_ids.add(asset["id"])
        if asset["source"] not in VALID_SOURCES:
            raise AssetError(f"asset {asset['id']}: unknown source {asset['source']!r}")
        if asset["source"] == "npm-package":
            package = asset.get("package")
            if not isinstance(package, dict) or set(package) - PACKAGE_KEYS \
                    or not package.get("name") or not package.get("version"):
                raise AssetError(f"asset {asset['id']}: npm-package assets need package name/version")
        check_serve_prefix(asset["serve_prefix"])
        files = asset["files"]
        if not isinstance(files, list) or not files:
            raise AssetError(f"asset {asset['id']} has no files")
        seen_paths: set[str] = set()
        for entry in files:
            unknown = set(entry) - FILE_KEYS
            if unknown:
                raise AssetError(f"asset {asset['id']} file has unknown keys: {sorted(unknown)}")
            missing = REQUIRED_FILE_KEYS - set(entry)
            if missing:
                raise AssetError(f"asset {asset['id']} file missing keys: {sorted(missing)}")
            check_staged_path(entry["staged_path"])
            if entry["staged_path"] in seen_paths:
                raise AssetError(f"asset {asset['id']}: duplicate staged path {entry['staged_path']}")
            seen_paths.add(entry["staged_path"])
            sha = entry["sha256"]
            if not isinstance(sha, str) or len(sha) != 64 or \
                    any(c not in "0123456789abcdef" for c in sha):
                raise AssetError(f"asset {asset['id']}: malformed sha256 for {entry['staged_path']}")
            if not isinstance(entry["bytes"], int) or entry["bytes"] <= 0:
                raise AssetError(f"asset {asset['id']}: malformed byte count for {entry['staged_path']}")
            if asset["source"] == "upstream-url" and not entry.get("source_url"):
                raise AssetError(f"asset {asset['id']}: upstream file needs source_url")
    return assets


def load_manifest() -> dict:
    try:
        data = json.loads(MANIFEST.read_text())
    except FileNotFoundError as error:
        raise AssetError(f"manifest missing: {MANIFEST.relative_to(ROOT)}") from error
    except json.JSONDecodeError as error:
        raise AssetError(f"manifest is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise AssetError("manifest root must be an object")
    return data


def resolve() -> dict:
    """Enumerate the staged set from installed packages; record real hashes."""
    assets: list[dict] = []
    for spec in NPM_ASSET_SETS:
        root = package_root(spec["package_name"])
        meta = package_meta(spec["package_name"])
        version = meta["version"]
        serve_prefix = spec["serve_prefix"].format(version=version)
        staged_base = serve_prefix.lstrip("/")
        package = {"name": spec["package_name"], "version": version}
        if meta.get("integrity"):
            package["integrity"] = meta["integrity"]
        asset = {
            "id": spec["id"],
            "kind": spec["kind"],
            "version": version,
            "source": "npm-package",
            "package": package,
            "license": spec["license"],
            "rights": spec["rights"],
            "serve_prefix": serve_prefix,
            "delivery": spec["delivery"],
            "files": [],
        }
        if "package_dir" in spec:
            candidates = sorted(p for p in (root / spec["package_dir"]).iterdir() if p.is_file())
            package_paths = [f"{spec['package_dir']}/{p.name}" for p in candidates]
        else:
            package_paths = list(spec["package_files"])
        for package_path in package_paths:
            source_file = root / package_path
            if not source_file.is_file():
                raise AssetError(f"{spec['package_name']}@{version}: expected file missing: {package_path}")
            digest, size = sha256_file(source_file)
            asset["files"].append({
                "package_path": package_path,
                "staged_path": f"{staged_base}{Path(package_path).name}",
                "sha256": digest,
                "bytes": size,
            })
        assets.append(asset)
    for upstream in UPSTREAM_ASSETS:
        asset = {k: v for k, v in upstream.items() if k != "files"}
        asset["files"] = [dict(entry) for entry in upstream["files"]]
        assets.append(asset)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "recorded_by": "T02",
        "recorded_at": "2026-09-12",
        "staging_root": STAGING_ROOT,
        "public_base": "/",
        "assets": assets,
    }
    validate_manifest(manifest)
    return manifest


def stage(manifest: dict) -> int:
    assets = validate_manifest(manifest)
    staged = 0
    for asset in assets:
        for entry in asset["files"]:
            target = ROOT / STAGING_ROOT / entry["staged_path"]
            if asset["source"] == "npm-package":
                source = package_root(asset["package"]["name"]) / entry["package_path"]
                if not source.is_file():
                    raise AssetError(f"missing source file: {entry['package_path']} in {asset['package']['name']}")
                digest, size = sha256_file(source)
                if digest != entry["sha256"] or size != entry["bytes"]:
                    raise AssetError(
                        f"installed source drifted for {entry['staged_path']}: "
                        "refusing to stage bytes the manifest does not record")
                data = source.read_bytes()
            else:
                request = urllib.request.Request(
                    entry["source_url"], headers={"User-Agent": "inkflip-asset-prepare/1.0"})
                try:
                    with urllib.request.urlopen(request, timeout=60) as response:
                        data = response.read()
                except OSError as error:
                    raise AssetError(f"download failed for {entry['staged_path']}: {error}") from error
                # Fail closed: never write bytes the manifest does not describe.
                if len(data) != entry["bytes"] or sha256_bytes(data) != entry["sha256"]:
                    raise AssetError(
                        f"downloaded bytes fail checksum for {entry['staged_path']}; nothing staged")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and sha256_file(target) == (entry["sha256"], entry["bytes"]):
                continue
            target.write_bytes(data)
            staged += 1
    return staged


def verify(manifest: dict) -> int:
    """Re-hash staged files; every deviation fails closed."""
    assets = validate_manifest(manifest)
    checked = 0
    failures: list[str] = []
    for asset in assets:
        for entry in asset["files"]:
            target = ROOT / STAGING_ROOT / entry["staged_path"]
            if not target.is_file():
                failures.append(f"missing staged file: {entry['staged_path']} (asset {asset['id']})")
                continue
            digest, size = sha256_file(target)
            if digest != entry["sha256"] or size != entry["bytes"]:
                failures.append(
                    f"checksum/size mismatch: {entry['staged_path']} "
                    f"(expected sha256 {entry['sha256'][:12]}…/{entry['bytes']}B, "
                    f"got {digest[:12]}…/{size}B)")
                continue
            checked += 1
    if failures:
        raise AssetError("staged asset verification failed:\n  " + "\n  ".join(failures))
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("resolve", "stage", "verify"))
    parser.add_argument("--write", action="store_true",
                        help="resolve: write config/resolved-assets.json instead of printing")
    args = parser.parse_args()
    try:
        if args.action == "resolve":
            manifest = resolve()
            if args.write:
                MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
                print(f"wrote {MANIFEST.relative_to(ROOT)} "
                      f"({sum(len(a['files']) for a in manifest['assets'])} files, "
                      f"{len(manifest['assets'])} assets)")
            else:
                print(json.dumps(manifest, indent=2))
            return 0
        manifest = load_manifest()
        if args.action == "stage":
            staged = stage(manifest)
            total = sum(len(a["files"]) for a in manifest["assets"])
            print(f"staged {staged} new/changed files ({total} recorded)")
        else:
            checked = verify(manifest)
            print(f"verified {checked} staged files against {MANIFEST.relative_to(ROOT)}")
        return 0
    except AssetError as error:
        print(f"prepare_assets: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
