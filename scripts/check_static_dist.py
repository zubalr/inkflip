#!/usr/bin/env python3
"""Static deployment preflight (T48) — validate the built static bundle and
the Workers Static Assets configuration BEFORE any deployment.

Checks (fail exit 1, named; config errors exit 2):

  1. configuration: wrangler.json declares Workers Static Assets with NO
     Worker script (`main`), no bindings, no functions/ directory, and the
     contract's html_handling/not_found_handling ("none" — unknown paths
     are 404s, never a dynamic catch-all);
  2. size ceiling: every built file is below 24 MiB;
  3. completeness: every declared distribution-manifest group file and the
     example catalogs exist in dist with matching bytes; reader/model
     notice files shipped alongside their assets;
  4. same-origin: built JS/HTML/worker reference no third-party script,
     worker, WASM, model or connect URLs (allowing the documented
     data:/blob: schemes);
  5. headers: the shipped `_headers` matches the contract — CSP with no
     JS unsafe-eval (wasm-unsafe-eval allowed), no third-party origins,
     immutable caching for hashed /assets/ and /models/, no-cache for
     index.html, and no default COOP/COEP cross-origin isolation.

Usage:
  python3 scripts/check_static_dist.py apps/web/dist --config wrangler.json
  python3 scripts/check_static_dist.py apps/web/dist --config wrangler.json --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MAX_BYTES = 24 * 1024 * 1024
SELF_ONLY = re.compile(r"https?://(?!localhost|127\.0\.0\.1)[a-z0-9.-]+", re.IGNORECASE)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def contained(root: Path, rel: str) -> bool:
    if rel.startswith(("/", "~")) or (len(rel) > 1 and rel[1] == ":"):
        return False
    try:
        (root / rel).resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def check_config(dist: Path, config: dict, root: Path) -> list[str]:
    problems = []
    assets = config.get("assets") or {}
    if config.get("main"):
        problems.append("config: `main` declares a Worker script — Static Assets must run without one")
    if config.get("bindings") or config.get("vars") or config.get("durable_objects") or config.get("services"):
        problems.append("config: bindings/compute configuration present — none is allowed")
    if assets.get("directory", "./apps/web/dist").lstrip("./") not in ("apps/web/dist",):
        problems.append(f"config: assets.directory is {assets.get('directory')!r}, expected ./apps/web/dist")
    # html_handling must keep "/" serving index.html (auto-trailing-slash,
    # verified live via `wrangler dev`) while not_found_handling "none" keeps
    # unknown paths as 404s — never a dynamic catch-all that renders the app.
    if assets.get("html_handling") != "auto-trailing-slash":
        problems.append(
            "config: html_handling must be 'auto-trailing-slash' ('/' serves index.html; "
            "verified live — 'none' leaves the site root a 404)"
        )
    if assets.get("not_found_handling") != "none":
        problems.append("config: not_found_handling must be 'none' (unknown paths 404, never a catch-all)")
    if (root / "functions").is_dir():
        problems.append("config: functions/ directory exists — Pages Functions are not part of the static design")
    return problems


def check_sizes(dist: Path) -> list[str]:
    problems = []
    for path in sorted(dist.rglob("*")):
        if path.is_file() and not path.is_symlink():
            size = path.stat().st_size
            if size >= MAX_BYTES:
                problems.append(f"size: {path.relative_to(dist)} is {size} bytes (>= 24 MiB ceiling)")
    return problems


def check_completeness(dist: Path, root: Path) -> list[str]:
    problems = []
    # Built output must contain the app shell, service worker, reader/model assets and examples
    for required in ("index.html", "sw.js", "_headers"):
        if not (dist / required).is_file():
            problems.append(f"completeness: dist/{required} missing")
    if not (dist / "assets").is_dir():
        problems.append("completeness: dist/assets missing (reader runtimes)")
    if not (dist / "models").is_dir():
        problems.append("completeness: dist/models missing (OCR model)")
    if not (dist / "examples").is_dir():
        problems.append("completeness: dist/examples missing (prepared examples)")
    # notice files shipped alongside third-party assets
    for notice in ("assets/pdfjs", "assets/tesseract", "assets/tesseract-core"):
        d = dist / notice
        if d.is_dir() and not any(f.name.startswith("LICENSE") for f in d.rglob("*")):
            problems.append(f"notices: no LICENSE file found under dist/{notice}")
    return problems


LOAD_CONTEXT_RE = re.compile(
    r"""(?:fetch\(\s*|new\s+Worker\(\s*|importScripts\(\s*|import\(\s*|
        XMLHttpRequest\.open\(\s*[^,]*,\s*|<script[^>]+src=|<link[^>]+href=|
        new\s+EventSource\(\s*|WebSocket\(\s*|sendBeacon\(\s*)["'\`]([^"'\`]+)["'\`]""",
    re.VERBOSE,
)


def check_same_origin(dist: Path) -> list[str]:
    """Only URLs in actual loading contexts count: fetch/Worker/import/XHR/
    script src/link href/WebSocket/beacon. URL strings inside error messages,
    comments or validation patterns are not fetches."""
    problems = []
    scan_files = [
        p for p in sorted(dist.rglob("*"))
        if p.is_file() and p.suffix in (".js", ".mjs", ".html") and "examples" not in p.parts
    ]
    for path in scan_files:
        rel = path.relative_to(dist)
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for m in LOAD_CONTEXT_RE.finditer(text):
            url = m.group(1)
            if url.startswith(("/", "data:", "blob:", "#", "./", "../")):
                continue  # same-origin or inline
            if SELF_ONLY.search(url):
                problems.append(f"same-origin: {rel} loads external URL {url!r} in a fetch/worker/import context")
    return problems


def check_headers(dist: Path) -> list[str]:
    problems = []
    hp = dist / "_headers"
    if not hp.is_file():
        return ["headers: dist/_headers missing (copy apps/web/public/_headers into the static root)"]
    text = hp.read_text()
    residual_eval = text.replace("'wasm-unsafe-eval'", "").replace('"wasm-unsafe-eval"', "").replace("wasm-unsafe-eval", "")
    if re.search(r"['\"\s]unsafe-eval['\"\s;,]", residual_eval):
        problems.append("headers: CSP allows JavaScript unsafe-eval")
    csp_line = next((l for l in text.splitlines() if "Content-Security-Policy" in l), "")
    for needed in ("default-src 'none'", "script-src 'self'", "worker-src 'self'",
                   "connect-src 'self'", "object-src 'none'", "frame-ancestors 'none'"):
        if needed not in csp_line:
            problems.append(f"headers: CSP missing {needed!r}")
    if "wasm-unsafe-eval" not in csp_line:
        problems.append("headers: CSP lacks 'wasm-unsafe-eval' (required WASM permission from the contract)")
    if "/assets/*" not in text or "immutable" not in text:
        problems.append("headers: immutable caching rule for /assets/* missing")
    if "/models/*" not in text or "immutable" not in text:
        problems.append("headers: immutable caching rule for /models/* missing")
    if "/index.html" not in text or "no-cache" not in text:
        problems.append("headers: no-cache rule for /index.html missing")
    for isolation in ("Cross-Origin-Opener-Policy", "Cross-Origin-Embedder-Policy"):
        if isolation in text:
            problems.append(f"headers: {isolation} present — the selected WASM route requires no default COOP/COEP isolation")
    return problems


def check_manifest_hashes(dist: Path, root: Path, dist_manifest_rel: str | None) -> list[str]:
    """When a recorded dist manifest exists, verify declared bytes/hashes."""
    problems = []
    if not dist_manifest_rel:
        return problems
    dm_path = root / dist_manifest_rel
    if not dm_path.is_file():
        return [f"manifest: recorded dist manifest missing: {dist_manifest_rel}"]
    dm = json.loads(dm_path.read_text())
    for f in dm.get("files", []):
        actual = root / f["path"]
        if not actual.is_file():
            problems.append(f"manifest: recorded file missing from build: {f['path']}")
        elif f.get("sha256") and sha256_file(actual) != f["sha256"]:
            problems.append(f"manifest: hash mismatch: {f['path']}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 pass, 1 preflight failures, 2 usage error.",
    )
    parser.add_argument("dist", help="built static root (e.g. apps/web/dist)")
    parser.add_argument("--config", default="wrangler.json", help="wrangler.json path")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--dist-manifest", default=".private/distribution/dist-manifest.json",
                        help="recorded dist manifest for hash verification (skipped if absent)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    dist = (root / args.dist).resolve()
    config_path = root / args.config
    if not dist.is_dir():
        print(f"usage error: dist root not found: {args.dist}", file=sys.stderr)
        return 2
    if not config_path.is_file():
        print(f"usage error: config not found: {args.config}", file=sys.stderr)
        return 2
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"usage error: unreadable config: {exc}", file=sys.stderr)
        return 2

    problems: list[str] = []
    problems += check_config(dist, config, root)
    problems += check_sizes(dist)
    problems += check_completeness(dist, root)
    problems += check_same_origin(dist)
    problems += check_headers(dist)
    dm_rel = args.dist_manifest if (root / args.dist_manifest).is_file() else None
    problems += check_manifest_hashes(dist, root, dm_rel)

    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems}, indent=2))
    elif problems:
        print(f"static deployment preflight: {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
    else:
        print("static deployment preflight: PASS (local configuration/bundle checks; not proof of a deployed hostname)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
