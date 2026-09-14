#!/usr/bin/env python3
"""Static deployment preflight (T48) — validate the built static bundle and
the Workers Static Assets configuration BEFORE any deployment.

Fail-closed contract (repairs from the 2026-09-13 recovery review):

  * The registered invocation REQUIRES a recorded, source-bound dist
    manifest (--dist-manifest). A missing manifest is a failure, never a
    skipped check. Generate it through the normal recorder
    (scripts/distribution/record_dist.py) after building — validation
    never regenerates or repairs it. Inventory/record generation is a
    separate command; this acceptance gate only verifies.
  * The manifest must describe EXACTLY the supplied dist root: every built
    file declared (extra or missing -> failure), every entry with byte
    count and SHA-256 (missing digest -> failure), hashes/sizes matching
    the actual bytes, no empty required assets, no traversal/absolute/
    out-of-root entries (config error), no duplicate entries (config
    error), no symlink escapes, and a matching build identity (the
    manifest's file_set_sha256 must equal the recomputed file-set digest).
  * Configuration is validated against an explicit allowlist. Any Worker
    script, binding or application-compute feature (R2, D1, KV, queues,
    services, durable objects, containers, AI, triggers, cron, ...) is
    rejected — including per-environment overrides. assets.directory must
    resolve to a real in-root path and to the same directory as the
    supplied dist argument (string normalization is not containment).
    Malformed configuration yields a deterministic error, never a
    traceback or a pass.
  * _headers is parsed into rules and directives: CSP source lists are
    validated per directive (external/wildcard/protocol-relative script,
    worker or connect sources fail; JS unsafe-inline/unsafe-eval fail; the
    contract's 'wasm-unsafe-eval' and style-src-attr 'unsafe-inline'
    allowances are the only exceptions), cache policies are bound to the
    paths they claim (an immutable word in an unrelated rule satisfies
    nothing), repeated directives in one rule fail, and index.html, sw.js
    and release.json freshness rules must exist.
  * Same-origin loading audit covers built JS, HTML, CSS (url()/@import)
    and the prepared examples too: protocol-relative URLs (//host) are
    external, not local.

Static scanning has documented limits; browser-level no-egress and CSP
behavior is verified separately by the canary suites against the real
build under these headers. Local preflight is not proof of a deployed
hostname.

Exit codes: 0 pass, 1 verification failures, 2 config/usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MAX_BYTES = 24 * 1024 * 1024

CONFIG_ALLOWED_TOP = {"name", "compatibility_date", "workers_dev", "preview_urls", "assets", "env"}
CONFIG_ALLOWED_ASSETS = {"directory", "html_handling", "not_found_handling"}
CONFIG_ALLOWED_ENV = {"compatibility_date", "workers_dev", "preview_urls"}
COMPUTE_KEYS = {
    "main", "bindings", "r2_buckets", "d1_databases", "kv_namespaces",
    "queues", "services", "durable_objects", "containers", "ai", "triggers",
    "crons", "analytics_engine_datasets", "browser", "assets_with_bindings",
    "functions", "mtls_certificates", "logpush", "workflows", "send_email",
    "hyperdrive", "vectorize", "version_metadata",
}
REQUIRED_CSP = {
    "default-src": {"'none'"},
    "script-src": {"'self'", "'wasm-unsafe-eval'"},
    "worker-src": {"'self'"},
    "connect-src": {"'self'"},
    "img-src": {"'self'", "blob:", "data:"},
    "font-src": {"'self'", "blob:"},
    "style-src": {"'self'"},
    "style-src-attr": {"'unsafe-inline'"},
    "object-src": {"'none'"},
    "frame-src": {"'none'"},
    "base-uri": {"'none'"},
    "form-action": {"'none'"},
    "frame-ancestors": {"'none'"},
    "manifest-src": {"'self'"},
}
STRICT_SOURCE_DIRECTIVES = {"script-src", "worker-src", "connect-src", "default-src",
                            "img-src", "font-src", "style-src", "manifest-src",
                            "object-src", "frame-src", "base-uri", "form-action",
                            "frame-ancestors"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def contained(root: Path, rel: str) -> bool:
    if rel.startswith(("/", "~")) or (len(rel) > 1 and rel[1] == ":"):
        return False
    if ".." in Path(rel).parts:
        return False
    try:
        (root / rel).resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


# ---------------------------------------------------------------- configuration

def check_config(root: Path, config_path: Path, dist_arg: str):
    """Returns (problems, errors, resolved_dist_or_None)."""
    problems: list[str] = []
    errors: list[str] = []
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        return problems, [f"config: malformed JSON in {config_path.name}: {exc}"], None
    if not isinstance(config, dict):
        return problems, ["config: top level must be a JSON object"], None

    def reject_compute(where: str, obj: dict) -> None:
        for key in obj:
            if key in COMPUTE_KEYS:
                errors.append(
                    f"config: {where} declares compute/binding feature {key!r} — rejected (T48: no application compute)"
                )

    reject_compute("top level", config)
    for key in config:
        if key not in CONFIG_ALLOWED_TOP and key not in COMPUTE_KEYS:
            errors.append(f"config: unknown top-level key {key!r} (allowlist: {sorted(CONFIG_ALLOWED_TOP)})")

    env = config.get("env")
    if env is not None:
        if not isinstance(env, dict):
            errors.append("config: 'env' must be an object of per-environment overrides")
        else:
            for env_name, section in env.items():
                if not isinstance(section, dict):
                    errors.append(f"config: env.{env_name} must be an object")
                    continue
                reject_compute(f"env.{env_name}", section)
                for key in section:
                    if key in COMPUTE_KEYS:
                        continue
                    if key not in CONFIG_ALLOWED_ENV:
                        errors.append(
                            f"config: env.{env_name} key {key!r} is not part of the static allowlist "
                            "(environment overrides cannot add surface)"
                        )

    assets = config.get("assets")
    if not isinstance(assets, dict):
        errors.append("config: 'assets' section missing (Workers Static Assets required)")
        return problems, errors, None
    reject_compute("assets", assets)
    for key in assets:
        if key not in CONFIG_ALLOWED_ASSETS:
            errors.append(f"config: assets.{key} is not part of the static assets allowlist")
    if assets.get("html_handling") != "auto-trailing-slash":
        problems.append(
            "config: html_handling must be 'auto-trailing-slash' ('/' serves index.html; "
            "verified live — 'none' leaves the site root a 404)"
        )
    if assets.get("not_found_handling") != "none":
        problems.append("config: not_found_handling must be 'none' (unknown paths 404, never a catch-all)")

    directory = assets.get("directory")
    if not isinstance(directory, str) or not directory:
        errors.append("config: assets.directory must be a path string")
        return problems, errors, None
    if directory.startswith("/"):
        errors.append(f"config: assets.directory is absolute ({directory!r}) — must be relative to the repository root")
        return problems, errors, None
    if ".." in Path(directory).parts:
        errors.append(
            f"config: assets.directory {directory!r} contains '..' segments — "
            "traversal is rejected by construction (real path resolution, not string normalization)"
        )
        return problems, errors, None
    resolved = (config_path.parent / directory).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        errors.append(
            f"config: assets.directory {directory!r} resolves to {resolved}, outside the repository root "
            "(real path resolution, not string normalization)"
        )
        return problems, errors, None
    expected = (root / dist_arg).resolve()
    if resolved != expected:
        problems.append(
            f"config: assets.directory {directory!r} resolves to {resolved} but the supplied dist root is {expected}"
        )
    if not resolved.is_dir():
        problems.append(f"dist: configured directory does not exist (build first): {directory}")
    if (root / "functions").is_dir():
        problems.append("config: functions/ directory exists — Pages Functions are not part of the static design")
    return problems, errors, resolved


# ------------------------------------------------------------------- dist manifest

def file_set_digest(entries: list) -> str:
    h = hashlib.sha256()
    for e in sorted((e for e in entries if isinstance(e, dict) and isinstance(e.get("path"), str)),
                    key=lambda x: x["path"]):
        h.update(e["path"].encode())
        h.update(str(e.get("bytes", "")).encode())
        h.update((e.get("sha256") or "").encode())
    return h.hexdigest()


def check_dist_manifest(root: Path, dist: Path, manifest_rel: str):
    """Exact source-bound manifest verification. Returns (problems, errors)."""
    problems: list[str] = []
    errors: list[str] = []
    mpath = root / manifest_rel
    if not mpath.is_file():
        return [
            f"manifest: required dist manifest not found: {manifest_rel} — build and record it "
            "via scripts/distribution/record_dist.py (fail closed; acceptance never runs "
            "without a recorded build identity)"
        ], errors
    try:
        dm = json.loads(mpath.read_text())
    except json.JSONDecodeError as exc:
        return problems, [f"manifest: malformed JSON: {exc}"]
    if not isinstance(dm, dict) or dm.get("kind") != "inkflip-dist-manifest":
        return problems, ["manifest: not an inkflip-dist-manifest document"]

    dist_prefix = ""
    if dist.is_relative_to(root):
        dist_prefix = f"{dist.relative_to(root).as_posix()}/"
    if dm.get("dist_root") not in (dist_prefix.rstrip("/"), str(dist), f"./{dist_prefix.rstrip('/')}"):
        errors.append(
            f"manifest: dist_root {dm.get('dist_root')!r} does not bind the supplied dist root "
            f"({dist_prefix.rstrip('/') or str(dist)})"
        )

    entries = dm.get("files")
    if not isinstance(entries, list) or not entries:
        return problems, errors + ["manifest: no files recorded (an empty manifest is not acceptance evidence)"]

    declared: dict[str, dict] = {}
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("path"), str) or not e["path"]:
            errors.append("manifest: malformed entry (missing path)")
            continue
        rel = e["path"]
        key = rel[len(dist_prefix):]
        if key in declared:
            errors.append(f"manifest: duplicate entry for {rel}")
            continue
        if not contained(root, rel):
            errors.append(f"manifest: entry escapes the repository root (traversal/absolute): {rel}")
            continue
        if not rel.startswith(dist_prefix):
            problems.append(f"manifest: entry outside the dist root: {rel}")
            continue
        declared[key] = e
    if errors:
        return problems, errors
    for rel, e in declared.items():
        if e.get("sha256") is None or e.get("bytes") is None:
            problems.append(f"manifest: entry lacks required bytes/sha256: {rel}")

    actual: dict[str, Path] = {}
    for path in sorted(dist.rglob("*")):
        rel = path.relative_to(dist).as_posix()
        if path.is_symlink():
            target = path.resolve()
            try:
                target.relative_to(dist.resolve())
                problems.append(f"symlink in dist (not shipped content): {rel}")
            except ValueError:
                problems.append(f"symlink escape in dist: {rel} -> {target}")
            continue
        if path.is_file():
            actual[rel] = path

    for rel in sorted(set(declared) - set(actual)):
        problems.append(f"manifest: declared file missing from build: {rel}")
    for rel in sorted(set(actual) - set(declared)):
        problems.append(f"manifest: undeclared built file: {rel}")

    empty_required = []
    for rel in sorted(set(declared) & set(actual)):
        e = declared[rel]
        actual_path = dist / rel
        size = actual_path.stat().st_size
        if size != e.get("bytes"):
            problems.append(f"manifest: size mismatch: {rel} (recorded {e.get('bytes')}, actual {size})")
        if e.get("sha256") is not None and sha256_file(actual_path) != e["sha256"]:
            problems.append(f"manifest: hash mismatch (stale build or tampering): {rel}")
        if size == 0 and rel in ("index.html", "sw.js", "_headers"):
            empty_required.append(rel)
    for rel in empty_required:
        problems.append(f"manifest: required asset is empty: {rel}")

    recorded_set = dm.get("file_set_sha256")
    if recorded_set is None:
        problems.append("manifest: missing build identity (file_set_sha256)")
    else:
        recomputed = file_set_digest(entries)
        if recorded_set != recomputed:
            problems.append("manifest: build identity stale (file_set_sha256 does not match recorded entries)")
    return problems, errors


# ------------------------------------------------------------------- completeness

def check_sizes(dist: Path) -> list[str]:
    problems = []
    for path in sorted(dist.rglob("*")):
        if path.is_file() and not path.is_symlink():
            size = path.stat().st_size
            if size >= MAX_BYTES:
                problems.append(f"size: {path.relative_to(dist)} is {size} bytes (>= 24 MiB ceiling)")
            if size == 0 and path.suffix in (".js", ".mjs", ".css", ".wasm"):
                problems.append(f"empty built asset: {path.relative_to(dist)}")
    return problems


def check_completeness(dist: Path) -> list[str]:
    problems = []
    for required in ("index.html", "sw.js", "_headers"):
        p = dist / required
        if not p.is_file():
            problems.append(f"completeness: dist/{required} missing")
        elif p.stat().st_size == 0:
            problems.append(f"completeness: dist/{required} is empty")
    if not (dist / "assets").is_dir() or not any((dist / "assets").iterdir()):
        problems.append("completeness: dist/assets missing or empty (reader runtimes)")
    if not (dist / "models").is_dir() or not any((dist / "models").rglob("*.traineddata")):
        problems.append("completeness: dist/models missing or has no OCR model")
    if not (dist / "examples").is_dir() or not (dist / "examples" / "index.json").is_file():
        problems.append("completeness: dist/examples missing or has no catalog")
    for notice in ("assets/pdfjs", "assets/tesseract", "assets/tesseract-core"):
        d = dist / notice
        if d.is_dir() and not any(f.name.startswith("LICENSE") for f in d.rglob("*")):
            problems.append(f"notices: no LICENSE file found under dist/{notice}")
    return problems


# ------------------------------------------------------------------- same-origin

LOAD_CONTEXT_RE = re.compile(
    r"""(?:fetch\s*\(\s*|new\s+Worker\s*\(\s*|importScripts\s*\(\s*|import\s*\(\s*|
        XMLHttpRequest\.open\s*\(\s*[^,]*,\s*|new\s+EventSource\s*\(\s*|
        WebSocket\s*\(\s*|navigator\.sendBeacon\s*\(\s*)["'`]([^"'`]+)["'`]""",
    re.VERBOSE,
)
HTML_ATTR_RE = re.compile(
    r"""<(?:script|img|image|use|iframe|embed|source|track|audio|video|link)\b[^>]*?
        (?:src|href|poster)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE | re.VERBOSE,
)
CSS_EXT_RE = re.compile(
    r"""@import\s+(?:url\s*\(\s*)?["']?([^"')\s;]+)|url\s*\(\s*["']?\s*([^"')\s]+)""",
    re.IGNORECASE | re.VERBOSE,
)

# Canonical metadata names the public page without fetching it. Exempt only
# this exact element, never its URL in scripts or assets.
CANONICAL_ELEMENT = '<link rel="canonical" href="https://inkflip-rose.vercel.app/" />'


def is_external(url: str) -> bool:
    """External = any non-same-origin target. Protocol-relative (//host)
    resolves against the page scheme on a different host: external."""
    u = url.strip()
    if u.startswith("//"):
        return True
    if u.startswith(("#", "data:", "blob:", "about:")):
        return False
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", u):
        return True
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", u):
        return False
    if "\\" in u:
        return True
    return False


def check_same_origin(dist: Path) -> list[str]:
    problems = []
    scan = [
        p for p in sorted(dist.rglob("*"))
        if p.is_file() and not p.is_symlink()
        and (p.suffix in (".js", ".mjs", ".html", ".css") or p.name == "sw.js")
    ]
    for path in scan:
        rel = path.relative_to(dist)
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        contexts = [(m.group(1), "fetch/worker/import context") for m in LOAD_CONTEXT_RE.finditer(text)]
        if path.suffix == ".html":
            contexts += [(m.group(1), "HTML loading attribute")
                         for m in HTML_ATTR_RE.finditer(text.replace(CANONICAL_ELEMENT, ""))]
        if path.suffix == ".css":
            contexts += [(m.group(1) or m.group(2), "CSS url/import") for m in CSS_EXT_RE.finditer(text)]
        for url, kind in contexts:
            if not url or url.startswith(("data:", "blob:", "#")):
                continue
            if url.startswith("/") and not url.startswith("//"):
                continue
            if is_external(url):
                problems.append(f"same-origin: {rel} loads external URL {url!r} ({kind})")
    return problems


# ------------------------------------------------------------------- headers

def parse_headers(text: str):
    rules: list[tuple[str, list[tuple[str, str]]]] = []
    errors: list[str] = []
    current: tuple[str, list[tuple[str, str]]] | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            if current:
                rules.append(current)
            current = (line.strip(), [])
            continue
        if current is None:
            errors.append(f"headers line {lineno}: header line before any path rule")
            continue
        stripped = line.strip()
        if ":" not in stripped:
            errors.append(f"headers line {lineno}: malformed header (no colon): {stripped!r}")
            continue
        name, _, value = stripped.partition(":")
        current[1].append((name.strip(), value.strip()))
    if current:
        rules.append(current)
    return rules, errors


def parse_csp(value: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for part in value.split(";"):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        directives.setdefault(tokens[0], []).extend(tokens[1:])
    return directives


def csp_problems(directives: dict[str, list[str]], where: str) -> list[str]:
    problems = []
    for name, sources in directives.items():
        if len(sources) != len(set(sources)) and name in REQUIRED_CSP:
            problems.append(f"headers: {where}: repeated directive {name}")
    for name, required in REQUIRED_CSP.items():
        actual = set(directives.get(name, []))
        if not actual:
            problems.append(f"headers: {where}: CSP missing required directive {name}")
            continue
        if name == "style-src-attr":
            if actual != required:
                problems.append(
                    f"headers: {where}: style-src-attr must be exactly {sorted(required)} "
                    "(the geometric inline-style concession — nothing more)"
                )
            continue
        for src in actual - required:
            if name in STRICT_SOURCE_DIRECTIVES and (
                EXTERNAL_LIKE.match(src) or src in ("'unsafe-inline'", "'unsafe-eval'")
            ):
                problems.append(f"headers: {where}: {name} forbids {src!r}")
    for name in set(directives) - set(REQUIRED_CSP):
        problems.append(f"headers: {where}: unexpected CSP directive {name!r} (policy drift)")
    return problems


EXTERNAL_LIKE = re.compile(
    r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:)?//"   # absolute or protocol-relative URL
    r"|^[a-zA-Z][a-zA-Z0-9+.-]*:"
    r"|^\*"
    r"|^\*\."
)


def rule_matches(path_pattern: str, target: str) -> bool:
    """Cloudflare _headers splat: '*' matches any characters including '/'.
    A rule's path applies to itself and everything below it."""
    if path_pattern in ("/*", "/"):
        return True
    pattern = re.escape(path_pattern).replace(r"\*", ".*")
    return re.fullmatch(pattern, target) is not None or target.startswith(path_pattern.replace("*", ""))



def rules_matching(rules, target: str):
    return [r for r in rules if rule_matches(r[0], target)]


def header_values(rule, name: str):
    return [v for n, v in rule[1] if n.lower() == name.lower()]


def check_headers(dist: Path) -> list[str]:
    problems = []
    hp = dist / "_headers"
    if not hp.is_file():
        return ["headers: dist/_headers missing (copy apps/web/public/_headers into the static root)"]
    rules, parse_errors = parse_headers(hp.read_text())
    problems.extend(parse_errors)
    if not rules:
        return problems + ["headers: no rules parsed"]

    csp_count = 0
    for pattern, headers in rules:
        values = header_values((pattern, headers), "Content-Security-Policy")
        if len(values) > 1:
            problems.append(f"headers: rule {pattern!r}: Content-Security-Policy declared more than once")
        for v in values:
            csp_count += 1
            problems.extend(csp_problems(parse_csp(v), f"rule {pattern!r}"))
    if csp_count == 0:
        problems.append("headers: no Content-Security-Policy in any rule")

    top = [r for r in rules if r[0] in ("/*", "/")]
    if not top:
        problems.append("headers: no top-level (/*) rule carrying the baseline policy")
    else:
        directives = parse_csp(header_values(top[0], "Content-Security-Policy")[0] if header_values(top[0], "Content-Security-Policy") else "")
        for name in REQUIRED_CSP:
            if name not in directives:
                problems.append(f"headers: top rule missing required CSP directive {name}")

    def cache_values_for(target: str) -> list[str]:
        found = []
        for rule in rules_matching(rules, target):
            found.extend(header_values(rule, "Cache-Control"))
        return found

    for target, label in (("/index.html", "index.html"), ("/sw.js", "sw.js"), ("/release.json", "release.json")):
        values = cache_values_for(target)
        if not values:
            problems.append(f"headers: no Cache-Control rule for {label} (freshness required)")
        elif not any("no-cache" in v for v in values):
            problems.append(f"headers: {label} cache rule must be no-cache (found {values})")
    for target in ("/assets/x", "/models/x/y"):
        values = cache_values_for(target)
        if not values:
            problems.append(f"headers: no Cache-Control rule covering {target} (immutable required)")
        elif not any("immutable" in v and "max-age" in v for v in values):
            problems.append(f"headers: cache rule covering {target} must be public max-age immutable (found {values})")

    for pattern, headers in rules:
        for n, _ in headers:
            if n.lower() in ("cross-origin-opener-policy", "cross-origin-embedder-policy"):
                problems.append(
                    f"headers: rule {pattern!r} sets {n} — the selected WASM route requires no default COOP/COEP isolation"
                )
    return problems


# ------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 pass, 1 verification failures, 2 config error. "
        "The acceptance invocation REQUIRES --dist-manifest (fail closed); "
        "inventory generation is a separate command (scripts/distribution/record_dist.py).",
    )
    parser.add_argument("dist", help="built static root (e.g. apps/web/dist)")
    parser.add_argument("--config", default="wrangler.json", help="wrangler.json path")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument(
        "--dist-manifest", required=True,
        help="recorded dist manifest (required; created by scripts/distribution/record_dist.py after a real build)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    dist_arg = args.dist
    dist = (root / dist_arg).resolve()
    config_path = root / args.config
    if not config_path.is_file():
        print(f"config error: config not found: {args.config}", file=sys.stderr)
        return 2

    problems: list[str] = []
    errors: list[str] = []
    cfg_problems, cfg_errors, _resolved = check_config(root, config_path, dist_arg)
    problems += cfg_problems
    errors += cfg_errors
    if not dist.is_dir():
        errors.append(f"dist root not found: {dist_arg} (build first)")
    else:
        problems += check_sizes(dist)
        problems += check_completeness(dist)
        problems += check_same_origin(dist)
        problems += check_headers(dist)
        m_problems, m_errors = check_dist_manifest(root, dist, args.dist_manifest)
        problems += m_problems
        errors += m_errors

    all_problems = errors + problems
    if args.json:
        print(json.dumps({"ok": not all_problems, "problems": all_problems,
                          "scope_notes": ["local preflight only; not proof of a deployed hostname"]}, indent=2))
    elif all_problems:
        print(f"static deployment preflight: {len(all_problems)} problem(s)")
        for p in all_problems:
            print(f"  - {p}")
    else:
        print("static deployment preflight: PASS (local configuration/bundle checks; not proof of a deployed hostname)")
    if errors:
        return 2  # malformed/duplicate/traversal/unknown-key: deterministic config errors
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
