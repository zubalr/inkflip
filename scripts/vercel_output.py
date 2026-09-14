#!/usr/bin/env python3
"""Vercel static adapter for the already-built Inkflip dist.

This is not a second product and not a remote npm/Next.js build. The
browser app is the Vite tree at apps/web/dist/. Cloudflare's wrangler.json
preflight remains the T48 gate for that provider. This adapter only:

  * copies the production dist into Build Output API v3 `.vercel/output`
  * translates apps/web/public/_headers (copied into dist) into effective
    Vercel routes — a deployed `_headers` text file is not equivalent
  * refuses Vercel Functions, Image Optimization, crons, and SPA HTML
    fallbacks so a missing worker/model stays a real 404

Intended publication path (local frozen build, prebuilt upload):

  bun run build
  python3 scripts/distribution/record_dist.py --skip-build
  python3 scripts/check_static_dist.py apps/web/dist \\
    --config wrangler.json \\
    --dist-manifest .private/distribution/dist-manifest.json
  python3 scripts/vercel_output.py prepare
  python3 scripts/vercel_output.py check
  bunx --bun vercel@59.16.0 deploy --prebuilt --prod --skip-domain --yes

Exit codes: 0 pass, 1 verification failures, 2 config/usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_static_dist as csd  # noqa: E402

DEFAULT_DIST = "apps/web/dist"
DEFAULT_OUTPUT = ".vercel/output"
DEFAULT_VERCEL_JSON = "vercel.json"
SKIP_NAMES = {".DS_Store", "Thumbs.db"}
SKIP_SUFFIXES = {".map"}
REQUIRED_SECURITY_HEADERS = {
    "content-security-policy",
    "referrer-policy",
    "x-content-type-options",
    "permissions-policy",
    "cross-origin-resource-policy",
}
VERCEL_JSON_ALLOWED = {
    "$schema",
    "framework",
    "buildCommand",
    "installCommand",
    "outputDirectory",
    "cleanUrls",
    "trailingSlash",
    "headers",
}
VERCEL_JSON_FORBIDDEN = {
    "functions",
    "crons",
    "rewrites",
    "redirects",
    "images",
    "fluid",
    "proxy",
    "builds",
    "routes",
    "bunVersion",
    "regions",
    "bulkRedirectsPath",
}
OUTPUT_CONFIG_ALLOWED = {"version", "routes", "overrides", "framework"}
OUTPUT_CONFIG_FORBIDDEN = {
    "images",
    "crons",
    "wildcard",
    "services",
    "cache",
}
INDEX_DESTS = {"/index.html", "index.html", "/"}


def skip_static(path: Path) -> bool:
    if path.name in SKIP_NAMES:
        return True
    if path.suffix in SKIP_SUFFIXES or path.name.endswith(".map"):
        return True
    return False


def cf_pattern_to_src(pattern: str) -> str:
    """Cloudflare `_headers` path → Build Output API PCRE `src`."""
    if not pattern.startswith("/"):
        raise ValueError(f"header path must start with '/': {pattern!r}")
    if pattern == "/*":
        return "/(.*)"
    if pattern.endswith("/*"):
        return re.escape(pattern[:-2]) + "/(.*)"
    return re.escape(pattern)


def cf_pattern_to_vercel_source(pattern: str) -> str:
    """Cloudflare `_headers` path → vercel.json `headers[].source` (path-to-regexp)."""
    if not pattern.startswith("/"):
        raise ValueError(f"header path must start with '/': {pattern!r}")
    if pattern == "/*":
        return "/(.*)"
    if pattern.endswith("/*"):
        return pattern[:-1] + "(.*)"
    return pattern


def load_header_rules(headers_path: Path):
    if not headers_path.is_file():
        raise FileNotFoundError(headers_path)
    rules, parse_errors = csd.parse_headers(headers_path.read_text())
    if parse_errors:
        raise ValueError("; ".join(parse_errors))
    if not rules:
        raise ValueError(f"no header rules in {headers_path}")
    return rules


def routes_from_rules(rules) -> list[dict]:
    """Header-only continue routes. No dest, so the filesystem 404s misses."""
    routes: list[dict] = []
    for pattern, headers in rules:
        header_map: dict[str, str] = {}
        for name, value in headers:
            header_map[name] = value
        route = {"src": cf_pattern_to_src(pattern), "headers": header_map, "continue": True}
        routes.append(route)
        if pattern == "/index.html":
            routes.append({"src": "/", "headers": dict(header_map), "continue": True})
    return routes


def vercel_json_headers_from_rules(rules) -> list[dict]:
    entries: list[dict] = []
    for pattern, headers in rules:
        item = {
            "source": cf_pattern_to_vercel_source(pattern),
            "headers": [{"key": name, "value": value} for name, value in headers],
        }
        entries.append(item)
        if pattern == "/index.html":
            entries.append(
                {
                    "source": "/",
                    "headers": [{"key": name, "value": value} for name, value in headers],
                }
            )
    return entries


def expected_vercel_json(rules) -> dict:
    return {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "framework": None,
        "installCommand": None,
        "buildCommand": None,
        "outputDirectory": DEFAULT_DIST,
        "cleanUrls": False,
        "trailingSlash": False,
        "headers": vercel_json_headers_from_rules(rules),
    }


def copy_dist_to_static(dist: Path, static_root: Path) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    errors: list[str] = []
    copied = 0
    for path in sorted(dist.rglob("*")):
        rel = path.relative_to(dist).as_posix()
        if path.is_symlink():
            try:
                target = path.resolve()
                target.relative_to(dist.resolve())
            except (ValueError, OSError):
                errors.append(f"symlink escape in dist: {rel}")
                continue
            if skip_static(path) or not target.is_file():
                continue
            dest = static_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, dest)
            copied += 1
            continue
        if not path.is_file():
            continue
        if skip_static(path):
            continue
        dest = static_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        copied += 1
    if copied == 0:
        problems.append("prepare: no static files copied from dist")
    return problems, errors


def prepare(root: Path, dist_rel: str, output_rel: str) -> tuple[list[str], list[str], Path]:
    problems: list[str] = []
    errors: list[str] = []
    dist = (root / dist_rel).resolve()
    if not dist.is_dir():
        return problems, [f"dist root not found: {dist_rel} (build first)"], root / output_rel
    headers_path = dist / "_headers"
    if not headers_path.is_file():
        return problems, ["dist/_headers missing; the production build must copy apps/web/public/_headers"], root / output_rel
    try:
        rules = load_header_rules(headers_path)
    except (OSError, ValueError) as exc:
        return problems, [f"headers: {exc}"], root / output_rel

    output = (root / output_rel).resolve()
    try:
        output.relative_to(root)
    except ValueError:
        return problems, [f"output {output_rel!r} escapes the repository root"], output
    if output.exists():
        shutil.rmtree(output)
    static_root = output / "static"
    static_root.mkdir(parents=True)
    copy_problems, copy_errors = copy_dist_to_static(dist, static_root)
    problems += copy_problems
    errors += copy_errors
    config = {"version": 3, "routes": routes_from_rules(rules)}
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    return problems, errors, output


def listed_functions(output: Path) -> list[str]:
    func = output / "functions"
    if not func.exists():
        return []
    found = []
    if func.is_dir():
        found.append("functions/")
        for path in func.rglob("*"):
            found.append(path.relative_to(output).as_posix())
    else:
        found.append("functions")
    return found


def route_dest(route: dict) -> str | None:
    dest = route.get("dest") or route.get("destination")
    return dest if isinstance(dest, str) and dest else None


def is_html_fallback(route: dict) -> bool:
    dest = route_dest(route)
    if dest is None:
        return False
    path = dest.split("?")[0]
    return path in INDEX_DESTS or path.endswith(".html")


def headers_from_route(route: dict) -> dict[str, str]:
    raw = route.get("headers")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def route_src(route: dict) -> str:
    src = route.get("src") or route.get("source")
    return src if isinstance(src, str) else ""


def src_matches(src: str, target: str) -> bool:
    try:
        return re.fullmatch(src, target) is not None
    except re.error:
        return False


def cache_values_for(routes: list[dict], target: str) -> list[str]:
    found = []
    for route in routes:
        if not isinstance(route, dict) or "handle" in route:
            continue
        if src_matches(route_src(route), target):
            headers = headers_from_route(route)
            for name, value in headers.items():
                if name.lower() == "cache-control":
                    found.append(value)
    return found


def security_headers_for(routes: list[dict], target: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    for route in routes:
        if not isinstance(route, dict) or "handle" in route:
            continue
        if src_matches(route_src(route), target):
            for name, value in headers_from_route(route).items():
                merged[name.lower()] = value
    return merged


def check_output_config(config: dict, rules) -> list[str]:
    problems: list[str] = []
    if config.get("version") != 3:
        problems.append("config.json: version must be 3 (Build Output API)")
    for key in config:
        if key in OUTPUT_CONFIG_FORBIDDEN:
            problems.append(f"config.json: {key} is not part of this static upload")
        elif key not in OUTPUT_CONFIG_ALLOWED:
            problems.append(f"config.json: unknown key {key!r}")
    routes = config.get("routes")
    if not isinstance(routes, list) or not routes:
        return problems + ["config.json: routes missing — _headers was not translated"]
    for i, route in enumerate(routes):
        if not isinstance(route, dict):
            problems.append(f"config.json: routes[{i}] is not an object")
            continue
        if "handle" in route:
            problems.append(f"config.json: routes[{i}] uses handle {route.get('handle')!r}")
        if "middlewarePath" in route:
            problems.append(f"config.json: routes[{i}] declares middleware")
        dest = route_dest(route)
        if dest:
            problems.append(
                f"config.json: routes[{i}] dest {dest!r} — static files must be served from "
                "output/static without rewrites"
            )
        if is_html_fallback(route):
            problems.append(
                f"config.json: routes[{i}] would return HTML for a miss (SPA fallback forbidden)"
            )
        if route.get("headers") and route.get("continue") is not True:
            problems.append(
                f"config.json: routes[{i}] attaches headers without continue=true "
                "(would intercept the static file)"
            )
    expected = routes_from_rules(rules)
    if routes != expected:
        problems.append(
            "config.json: routes do not match the translation of dist/_headers "
            "(deployed _headers text is not equivalent)"
        )
    for target, label in (("/index.html", "index.html"), ("/sw.js", "sw.js"),
                          ("/release.json", "release.json"), ("/", "document root")):
        values = cache_values_for(routes, target)
        if not values:
            problems.append(f"routes: no Cache-Control for {label} ({target})")
        elif not any("no-cache" in v for v in values):
            problems.append(f"routes: {label} must be no-cache (found {values})")
    for target in ("/assets/x", "/models/x/y"):
        values = cache_values_for(routes, target)
        if not values:
            problems.append(f"routes: no Cache-Control covering {target}")
        elif not any("immutable" in v and "max-age" in v for v in values):
            problems.append(f"routes: {target} must be public max-age immutable (found {values})")
    sec = security_headers_for(routes, "/index.html")
    missing = sorted(REQUIRED_SECURITY_HEADERS - set(sec))
    if missing:
        problems.append(f"routes: missing security headers on documents: {missing}")
    else:
        if sec.get("referrer-policy") != "no-referrer":
            problems.append("routes: Referrer-Policy must be no-referrer")
        if sec.get("x-content-type-options") != "nosniff":
            problems.append("routes: X-Content-Type-Options must be nosniff")
        if sec.get("cross-origin-resource-policy") != "same-origin":
            problems.append("routes: Cross-Origin-Resource-Policy must be same-origin")
        csp = sec.get("content-security-policy", "")
        problems.extend(csd.csp_problems(csd.parse_csp(csp), "translated /* route"))
    for name in sec:
        if name in ("cross-origin-opener-policy", "cross-origin-embedder-policy"):
            problems.append("routes: COOP/COEP is not part of the selected WASM route")
    return problems


def check_vercel_json(path: Path, rules) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    errors: list[str] = []
    if not path.is_file():
        return [f"vercel.json missing at {path}"], errors
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return problems, [f"vercel.json: malformed JSON: {exc}"]
    if not isinstance(data, dict):
        return problems, ["vercel.json: top level must be an object"]
    for key in data:
        if key in VERCEL_JSON_FORBIDDEN:
            errors.append(f"vercel.json: {key} is not part of the static Hobby upload")
        elif key not in VERCEL_JSON_ALLOWED:
            errors.append(f"vercel.json: unknown key {key!r} (allowlist: {sorted(VERCEL_JSON_ALLOWED)})")
    if data.get("framework") is not None:
        problems.append("vercel.json: framework must be null (Other — not Next.js/Vite remote build)")
    if data.get("buildCommand") is not None:
        problems.append("vercel.json: buildCommand must be null (local frozen build + --prebuilt)")
    if data.get("installCommand") is not None:
        problems.append("vercel.json: installCommand must be null")
    if data.get("outputDirectory") != DEFAULT_DIST:
        problems.append(f"vercel.json: outputDirectory must be {DEFAULT_DIST!r}")
    if data.get("cleanUrls") is not False:
        problems.append("vercel.json: cleanUrls must be false (keep /index.html and hashed assets)")
    if data.get("trailingSlash") is not False:
        problems.append("vercel.json: trailingSlash must be false")
    expected = expected_vercel_json(rules)
    if data.get("headers") != expected["headers"]:
        problems.append("vercel.json: headers do not match the translation of _headers")
    return problems, errors


def check_static_identity(dist: Path, static_root: Path) -> list[str]:
    problems: list[str] = []
    dist_files: dict[str, Path] = {}
    for path in dist.rglob("*"):
        if path.is_symlink() or not path.is_file() or skip_static(path):
            continue
        dist_files[path.relative_to(dist).as_posix()] = path
    static_files: dict[str, Path] = {}
    for path in static_root.rglob("*"):
        rel = path.relative_to(static_root).as_posix()
        if path.is_symlink():
            problems.append(f"output/static contains a symlink: {rel}")
            continue
        if not path.is_file():
            continue
        if skip_static(path):
            problems.append(f"output/static includes excluded file: {rel}")
            continue
        static_files[rel] = path
    for rel in sorted(set(dist_files) - set(static_files)):
        problems.append(f"output/static missing dist file: {rel}")
    for rel in sorted(set(static_files) - set(dist_files)):
        problems.append(f"output/static has undeclared file: {rel}")
    for rel in sorted(set(dist_files) & set(static_files)):
        if csd.sha256_file(dist_files[rel]) != csd.sha256_file(static_files[rel]):
            problems.append(f"output/static hash mismatch vs dist: {rel}")
        if dist_files[rel].stat().st_size != static_files[rel].stat().st_size:
            problems.append(f"output/static size mismatch vs dist: {rel}")
    return problems


def check(root: Path, dist_rel: str, output_rel: str, vercel_json_rel: str) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    errors: list[str] = []
    dist = (root / dist_rel).resolve()
    output = (root / output_rel).resolve()
    if not dist.is_dir():
        errors.append(f"dist root not found: {dist_rel} (build first)")
        return problems, errors
    if not output.is_dir():
        errors.append(f"Vercel output not found: {output_rel} (run prepare first)")
        return problems, errors
    headers_path = dist / "_headers"
    if not headers_path.is_file():
        errors.append("dist/_headers missing")
        return problems, errors
    try:
        rules = load_header_rules(headers_path)
    except (OSError, ValueError) as exc:
        return problems, [f"headers: {exc}"]

    config_path = output / "config.json"
    if not config_path.is_file():
        errors.append("output/config.json missing")
        return problems, errors
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        return problems, [f"config.json: malformed JSON: {exc}"]
    if not isinstance(config, dict):
        return problems, ["config.json: top level must be an object"]

    functions = listed_functions(output)
    if functions:
        errors.append(
            "output/functions present — this upload is static files only "
            f"({', '.join(functions[:8])})"
        )

    static_root = output / "static"
    if not static_root.is_dir():
        errors.append("output/static missing")
        return problems, errors

    problems += check_output_config(config, rules)
    problems += csd.check_sizes(static_root)
    problems += csd.check_completeness(static_root)
    problems += csd.check_same_origin(static_root)
    problems += check_static_identity(dist, static_root)
    v_problems, v_errors = check_vercel_json(root / vercel_json_rel, rules)
    problems += v_problems
    errors += v_errors
    return problems, errors


def _print_report(label: str, problems: list[str], errors: list[str], as_json: bool) -> int:
    all_problems = errors + problems
    if as_json:
        print(json.dumps({"ok": not all_problems, "problems": all_problems}, indent=2))
    elif all_problems:
        print(f"{label}: {len(all_problems)} problem(s)")
        for item in all_problems:
            print(f"  - {item}")
    else:
        print(f"{label}: PASS")
    if errors:
        return 2
    return 1 if problems else 0


def _take_option(argv: list[str], name: str, default: str) -> tuple[str, list[str]]:
    """Allow a global option before or after the subcommand."""
    value = default
    out: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == name:
            if i + 1 >= len(argv):
                raise SystemExit(f"error: {name} requires a value")
            value = argv[i + 1]
            i += 2
            continue
        if arg.startswith(name + "="):
            value = arg.split("=", 1)[1]
            i += 1
            continue
        out.append(arg)
        i += 1
    return value, out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root_s, argv = _take_option(argv, "--root", ".")
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Global option --root DIR may appear before or after the subcommand.",
    )
    parser.add_argument("--root", default=".", help="repository root")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare", help="write .vercel/output from apps/web/dist")
    p_prep.add_argument("--dist", default=DEFAULT_DIST)
    p_prep.add_argument("--output", default=DEFAULT_OUTPUT)
    p_prep.add_argument("--json", action="store_true")

    p_check = sub.add_parser("check", help="validate Vercel output against dist/_headers")
    p_check.add_argument("--dist", default=DEFAULT_DIST)
    p_check.add_argument("--output", default=DEFAULT_OUTPUT)
    p_check.add_argument("--vercel-json", default=DEFAULT_VERCEL_JSON)
    p_check.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    root = Path(root_s).resolve()
    if args.cmd == "prepare":
        problems, errors, output = prepare(root, args.dist, args.output)
        if not errors and not problems:
            print(f"vercel output prepared at {output}")
            return 0
        return _print_report("vercel prepare", problems, errors, args.json)
    problems, errors = check(root, args.dist, args.output, args.vercel_json)
    return _print_report(
        "vercel output preflight (local configuration/bundle checks; not proof of a deployed hostname)",
        problems,
        errors,
        args.json,
    )


if __name__ == "__main__":
    sys.exit(main())
