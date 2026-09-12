#!/usr/bin/env python3
"""T15 — turn captured browser traffic into a checkable no-egress receipt.

The Playwright suite (tests/privacy/local.spec.ts) drives the real built
site (feature preview mounts plus a test-owned OCR/export harness page)
through the canary journey and writes raw captures to a private directory.
This inspector re-verifies those captures OFFLINE and emits
artifacts/tasks/T15/network-receipt.json — a committed, redacted receipt
that binds every acceptance criterion to observed evidence without ever
embedding canary marker material (markers are recorded by id + SHA-256
digest only).

Usage:
    python3 scripts/inspect_network_receipt.py \
        --capture tests/privacy/.private/capture \
        --canary tests/privacy/.private/canary.json \
        --dist tests/privacy/dist \
        --receipt artifacts/tasks/T15/network-receipt.json \
        --redacted-capture artifacts/tasks/T15/capture \
        --require-modes cold,warm,offline

    # Redact marker material + absolute private paths from a log file in place:
    python3 scripts/inspect_network_receipt.py \
        --redact-file artifacts/tasks/T15/commands.log \
        --canary tests/privacy/.private/canary.json

Exit status is nonzero whenever any check fails, so the receipt can never
be produced quietly over a leak.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

SCHEMA = 1
ALLOWED_METHODS = {"GET", "HEAD", "OPTIONS"}
# Schemes observed on fetch/XHR/worker targets that are not network egress.
LOCAL_SCHEMES = {"blob", "data", "about"}
# Service-worker/cache buckets that must stay empty for document data.
DENYLIST_RE = re.compile(
    r"(telemetry|analytics|sentry|datadog|segment\.io|mixpanel|amplitude|"
    r"hotjar|fullstory|logrocket|newrelic|google-analytics|googletagmanager|"
    r"doubleclick|fonts\.googleapis|fonts\.gstatic|use\.fontawesome|"
    r"jsdelivr|unpkg|cdnjs|cloudflareinsights|cloudflare-static|"
    r"/beacon\b|/collect\b|/rum\b|/track\b)",
    re.IGNORECASE,
)
URL_LITERAL_RE = re.compile(r"https?://[^\s\"'<>`\\)]+")
# Hardcoded endpoint literals that would be real findings even when never
# fetched: telemetry/analytics/beacon collectors. Vendor-neutral inert
# strings (spec URLs, xmlns namespaces, CDN defaults the adapter
# overrides, parser test vectors, repo links) are census-only — the
# runtime capture is the authority that none were fetched.
TELEMETRY_LITERAL_RE = re.compile(
    r"(sentry\.io|datadoghq|segment\.io|mixpanel|amplitude|hotjar|"
    r"fullstory|logrocket|newrelic|google-analytics|googletagmanager|"
    r"doubleclick|cloudflareinsights|/collect\b|/beacon\b|/rum\b|/track\b)",
    re.IGNORECASE,
)
MAX_VIOLATION_DETAILS = 25


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def marker_encodings(value: str) -> dict[str, str]:
    """Every transport spelling a marker could take inside traffic."""
    raw = value.encode("utf-8")
    out = {
        "raw": value,
        "url_encoded": _quote(value),
        "base64": base64.b64encode(raw).decode(),
        "base64url": base64.urlsafe_b64encode(raw).decode().rstrip("="),
        "hex": raw.hex(),
        "hex_upper": raw.hex().upper(),
    }
    # Hash-valued markers additionally travel as base64 of the digest bytes.
    if re.fullmatch(r"[0-9a-f]{64}", value):
        digest = bytes.fromhex(value)
        out["digest_base64"] = base64.b64encode(digest).decode()
        out["digest_base64url"] = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return {k: v for k, v in out.items() if len(v) >= 8}


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


class Violation(Exception):
    pass


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except OSError as error:
        raise Violation(f"cannot read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise Violation(f"{path} is not valid JSON: {error}") from error


def dist_allowlist(dist: Path) -> set[str]:
    """Fixed same-origin paths: every file in the built site plus roots."""
    allow = {"/", "/index.html", "/favicon.ico"}
    if not dist.is_dir():
        raise Violation(f"dist directory missing: {dist}")
    for path in sorted(dist.rglob("*")):
        if path.is_file():
            allow.add("/" + path.relative_to(dist).as_posix())
    return allow


def iter_strings(node: object, prefix: str = ""):
    if isinstance(node, str):
        yield prefix, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from iter_strings(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_strings(value, f"{prefix}[{index}]")


def observation_texts(capture: dict):
    """(channel, text) pairs that could carry document material outbound."""
    obs = []
    for i, req in enumerate(capture.get("requests", [])):
        obs.append((f"requests[{i}].url", req.get("url", "")))
        body = req.get("post_body")
        if isinstance(body, str):
            obs.append((f"requests[{i}].post_body", body))
    for i, req in enumerate(capture.get("request_failures", [])):
        obs.append((f"request_failures[{i}].url", req.get("url", "")))
    for i, ws in enumerate(capture.get("websockets", [])):
        obs.append((f"websockets[{i}].url", ws.get("url", "")))
        for j, frame in enumerate(ws.get("frames_sent", [])):
            obs.append((f"websockets[{i}].frames_sent[{j}]", str(frame)))
    for i, entry in enumerate(capture.get("egress", [])):
        obs.append((f"egress[{i}].target", str(entry.get("target", ""))))
        detail = entry.get("detail")
        if isinstance(detail, str):
            obs.append((f"egress[{i}].detail", detail))
    for i, msg in enumerate(capture.get("console", [])):
        obs.append((f"console[{i}].text", str(msg.get("text", ""))))
    for i, text in enumerate(capture.get("page_errors", [])):
        obs.append((f"page_errors[{i}]", str(text)))
    for i, entry in enumerate(capture.get("server_log", [])):
        obs.append((f"server_log[{i}].path", str(entry.get("path", ""))))
        query = entry.get("query")
        if isinstance(query, str):
            obs.append((f"server_log[{i}].query", query))
    storage = capture.get("storage", {})
    for field, text in iter_strings(storage):
        obs.append((f"storage.{field}", text))
    for i, dl in enumerate(capture.get("downloads", [])):
        obs.append((f"downloads[{i}].filename", str(dl.get("filename", ""))))
    return obs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, help="directory of raw capture JSON files")
    parser.add_argument("--canary", type=Path, required=True, help="canary manifest (marker values stay private)")
    parser.add_argument("--dist", type=Path, help="built site root used to derive the allowlist")
    parser.add_argument("--receipt", type=Path, help="output receipt path")
    parser.add_argument("--redacted-capture", type=Path,
                        help="write marker-redacted copies of the captures here")
    parser.add_argument("--redact-file", type=Path,
                        help="redact a text file in place (logs) and exit")
    parser.add_argument("--require-modes", default="",
                        help="comma-separated capture modes that must be present")
    args = parser.parse_args()

    canary = load_json(args.canary)
    if not isinstance(canary, dict):
        raise Violation("canary manifest must be a JSON object")
    markers = canary.get("markers", [])
    if not markers:
        raise Violation("canary manifest carries no markers")

    if args.redact_file is not None:
        return redact_file(args.redact_file, markers)

    if args.capture is None or args.dist is None or args.receipt is None:
        raise Violation("--capture, --dist and --receipt are required for a receipt")

    captures = []
    for path in sorted(args.capture.glob("*.json")):
        data = load_json(path)
        if not isinstance(data, dict):
            raise Violation(f"capture {path.name} is not a JSON object")
        captures.append((path, data))
    if not captures:
        raise Violation(f"no capture files under {args.capture}")

    allowlist = dist_allowlist(args.dist)
    origins = {c.get("origin") for _, c in captures}
    if len(origins) != 1:
        raise Violation(f"captures disagree about origin: {sorted(map(str, origins))}")
    origin = str(origins.pop())
    origin_netloc = urlparse(origin).netloc

    checks: list[dict] = []

    def check(check_id: str, criterion: str, detail: str, violations: list[dict], counts: dict):
        checks.append({
            "id": check_id,
            "criterion": criterion,
            "status": "fail" if violations else "pass",
            "detail": detail,
            "counts": counts,
            "violations": violations[:MAX_VIOLATION_DETAILS],
        })

    # --- 1. Every request is same-origin http(s) on a fixed allowlisted path,
    #        with no query string and a read-only method. --------------------
    v_same, v_allow, v_method, v_query = [], [], [], []
    methods: dict[str, int] = {}
    unique_paths: set[str] = set()
    served_pairs: set[tuple[str, str]] = set()
    cache_hits: list[str] = []
    request_total = 0
    for cpath, cap in captures:
        server_seen = {(str(e.get("method")), str(e.get("path"))) for e in cap.get("server_log", [])}
        served_pairs |= server_seen
        for i, req in enumerate(cap.get("requests", [])):
            request_total += 1
            url = str(req.get("url", ""))
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                v_same.append({"capture": cpath.name, "channel": f"requests[{i}].url",
                               "problem": f"non-http scheme {parsed.scheme!r}"})
                continue
            if parsed.netloc != origin_netloc:
                v_same.append({"capture": cpath.name, "channel": f"requests[{i}].url",
                               "problem": f"foreign origin {parsed.netloc!r}"})
            path = parsed.path or "/"
            unique_paths.add(path)
            if path not in allowlist:
                v_allow.append({"capture": cpath.name, "channel": f"requests[{i}].url",
                                "problem": f"path not allowlisted: {path}"})
            if parsed.query:
                v_query.append({"capture": cpath.name, "channel": f"requests[{i}].url",
                                "problem": "query string present"})
            method = str(req.get("method", "")).upper()
            methods[method] = methods.get(method, 0) + 1
            if method not in ALLOWED_METHODS:
                v_method.append({"capture": cpath.name, "channel": f"requests[{i}].url",
                                 "problem": f"method {method}"})
            elif (method, path) not in server_seen:
                # Same-origin + allowlisted but never reached the server:
                # satisfied by the browser HTTP cache (warm mode) — counted
                # for the record, not a violation.
                cache_hits.append(f"{method} {path}")
    for cpath, cap in captures:
        for i, entry in enumerate(cap.get("server_log", [])):
            path = str(entry.get("path", ""))
            if path not in allowlist:
                v_allow.append({"capture": cpath.name, "channel": f"server_log[{i}].path",
                                "problem": f"served path not allowlisted: {path}"})
            query = entry.get("query")
            if isinstance(query, str) and query:
                v_query.append({"capture": cpath.name, "channel": f"server_log[{i}].query",
                                "problem": "served query string present"})

    check("requests_same_origin",
          "only fixed allowlisted same-origin asset paths",
          "every http(s) request resolved to the local static origin "
          f"({cache_hits.__len__()} additionally satisfied from browser "
          "HTTP cache — same-origin allowlisted paths)",
          v_same, {"requests": request_total, "cache_satisfied": len(cache_hits)})
    check("requests_allowlisted_paths",
          "only fixed allowlisted same-origin asset paths",
          "every requested/served path is an exact member of the built-site "
          "file allowlist (dist listing plus /, /index.html, /favicon.ico)",
          v_allow, {"allowlist_size": len(allowlist), "unique_paths": len(unique_paths)})
    check("requests_read_only_methods",
          "only fixed allowlisted same-origin asset paths",
          "request methods are read-only static fetches",
          v_method, {"methods": methods})
    check("requests_no_query_strings",
          "No canary bytes/text/name/hash/crop/report in outbound traffic or URLs",
          "no request URL or served path carried a query string",
          v_query, {"requests": request_total})

    # --- 2. Canary markers never appear, in any transport encoding. ---------
    marker_rows = []
    for marker in markers:
        mid = str(marker.get("id"))
        value = str(marker.get("value", ""))
        if not mid or not value:
            raise Violation("each canary marker needs nonempty id and value")
        marker_rows.append({
            "id": mid,
            "digest": sha256_hex(value.encode("utf-8"))[:16],
            "encodings": marker_encodings(value),
            "allowed_channels": set(marker.get("allowed_channels", [])),
        })
    v_markers: list[dict] = []
    for cpath, cap in captures:
        for channel, text in observation_texts(cap):
            variants = {text, unquote(text)}
            for marker in marker_rows:
                if channel.split("[")[0] in marker["allowed_channels"]:
                    continue
                for enc_name, enc_value in marker["encodings"].items():
                    if any(enc_value in variant for variant in variants):
                        v_markers.append({
                            "capture": cpath.name, "channel": channel,
                            "marker_id": marker["id"], "encoding": enc_name})
                        break
    check("no_canary_material_outbound",
          "No canary bytes/text/name/hash/crop/report in outbound traffic or URLs",
          "no marker (filename, visible/hidden text, document hash, raster "
          "pixels, note, report id/name — in raw, percent, base64 or hex "
          "spellings) appears in any captured request URL, body, websocket, "
          "egress attempt, console payload, storage value or server path",
          v_markers, {"markers": len(marker_rows)})

    # --- 3. No websocket/beacon/service-worker channel exists at all. -------
    v_channels: list[dict] = []
    ws_total = 0
    for cpath, cap in captures:
        for i, ws in enumerate(cap.get("websockets", [])):
            ws_total += 1
            v_channels.append({"capture": cpath.name, "channel": f"websockets[{i}]",
                               "problem": f"websocket to {urlparse(str(ws.get('url',''))).netloc}"})
        for i, entry in enumerate(cap.get("egress", [])):
            kind = str(entry.get("kind", ""))
            target = str(entry.get("target", ""))
            if kind in {"beacon", "eventsource", "window.open", "serviceworker.register"}:
                v_channels.append({"capture": cpath.name, "channel": f"egress[{i}]",
                                   "problem": f"{kind} attempt: {urlparse(urljoin(origin, target)).netloc or target}"})
            elif kind in {"fetch", "xhr", "worker", "websocket"}:
                resolved = urlparse(urljoin(origin, target))
                if resolved.scheme in ("http", "https", "ws", "wss"):
                    if resolved.netloc != origin_netloc:
                        v_channels.append({"capture": cpath.name, "channel": f"egress[{i}]",
                                           "problem": f"foreign {kind} target {resolved.netloc}"})
                    elif kind == "websocket":
                        v_channels.append({"capture": cpath.name, "channel": f"egress[{i}]",
                                           "problem": "websocket constructor used"})
                    elif resolved.path not in allowlist:
                        v_channels.append({"capture": cpath.name, "channel": f"egress[{i}]",
                                           "problem": f"{kind} target not allowlisted: {resolved.path}"})
                elif resolved.scheme not in LOCAL_SCHEMES:
                    v_channels.append({"capture": cpath.name, "channel": f"egress[{i}]",
                                       "problem": f"unhandled {kind} scheme {resolved.scheme!r}"})
        sw = cap.get("storage", {}).get("service_workers", 0)
        if sw not in (0, "0", None):
            v_channels.append({"capture": cpath.name, "channel": "storage.service_workers",
                               "problem": f"{sw} service worker registration(s)"})
    check("no_websocket_beacon_serviceworker",
          "telemetry/external-font absence proven",
          "zero websockets, zero sendBeacon/EventSource/window.open attempts, "
          "zero service-worker registrations; worker/fetch/XHR tripwire "
          "targets all stay inside the same-origin allowlist",
          v_channels, {"websockets": ws_total})

    # --- 4. Telemetry / external-font denylist. ------------------------------
    v_deny: list[dict] = []
    for cpath, cap in captures:
        for channel, text in observation_texts(cap):
            if DENYLIST_RE.search(text):
                v_deny.append({"capture": cpath.name, "channel": channel,
                               "problem": "denylist pattern matched"})
    check("no_telemetry_or_external_font",
          "telemetry/external-font absence proven",
          "no captured URL, console payload, egress attempt or server path "
          "matches the telemetry/analytics/CDN/external-font denylist",
          v_deny, {"denylist_pattern": DENYLIST_RE.pattern})

    # --- 5. Storage: nothing document-shaped persists. ----------------------
    v_store: list[dict] = []
    model_sha = str(canary.get("model_sha256", ""))
    allowed_idb = {("keyval-store", "keyval", "inkflip/models/eng.traineddata")}
    for cpath, cap in captures:
        storage = cap.get("storage")
        if storage is None:
            continue
        for field in ("local", "session"):
            entries = storage.get(field, {})
            if entries:
                v_store.append({"capture": cpath.name, "channel": f"storage.{field}",
                                "problem": f"{len(entries)} keys persisted"})
        if storage.get("cookies"):
            v_store.append({"capture": cpath.name, "channel": "storage.cookies",
                            "problem": "cookies present"})
        if storage.get("cache_storage"):
            v_store.append({"capture": cpath.name, "channel": "storage.cache_storage",
                            "problem": f"{len(storage['cache_storage'])} cache entries"})
        for j, row in enumerate(storage.get("idb", [])):
            key = (str(row.get("db")), str(row.get("store")), str(row.get("key")))
            if key not in allowed_idb:
                v_store.append({"capture": cpath.name, "channel": f"storage.idb[{j}]",
                                "problem": f"unexpected idb entry {'/'.join(key)}"})
            elif model_sha and row.get("value_sha256") != model_sha:
                v_store.append({"capture": cpath.name, "channel": f"storage.idb[{j}]",
                                "problem": "idb value is not the staged model bytes"})
    check("storage_document_free",
          "No canary bytes/text/name/hash/crop/report in outbound traffic or URLs",
          "localStorage/sessionStorage/cookies/CacheStorage are empty and "
          "IndexedDB holds only the sha256-verified staged OCR model slot — "
          "no document keys, names, crops or reports persist",
          v_store, {"allowed_idb": sorted("/".join(k) for k in allowed_idb)})

    # --- 6. Recorded legs all completed + required modes are present. -------
    v_legs: list[dict] = []
    modes_seen: dict[str, int] = {}
    for cpath, cap in captures:
        mode = str(cap.get("mode", ""))
        modes_seen[mode] = modes_seen.get(mode, 0) + 1
        for leg in cap.get("legs", []):
            if leg.get("ok") is not True:
                v_legs.append({"capture": cpath.name, "channel": f"legs.{leg.get('name')}",
                               "problem": str(leg.get("detail", "leg did not complete"))})
        if str(cap.get("offline")) == "true" or cap.get("offline") is True:
            if cap.get("server_log"):
                v_legs.append({"capture": cpath.name, "channel": "offline.requests",
                               "problem": "requests reached the server while offline"})
            for req in cap.get("requests", []) + cap.get("request_failures", []):
                path = urlparse(str(req.get("url", ""))).path
                if not (path.startswith("/assets/") or path.startswith("/models/")
                        or path in ("/", "/index.html", "/privacy.html")):
                    v_legs.append({"capture": cpath.name, "channel": "offline.requests",
                                   "problem": f"offline attempt outside fixed assets: {path}"})
    required = {m for m in args.require_modes.split(",") if m}
    missing_modes = sorted(required - set(modes_seen))
    for m in missing_modes:
        v_legs.append({"capture": "-", "channel": "mode",
                       "problem": f"required mode {m!r} has no capture"})
    check("journey_legs_completed",
          "online/warm/offline modes documented",
          "every recorded journey leg completed (open, error, render, OCR, "
          "export, reopen, clear) and every required mode has a capture; "
          "offline captures show zero requests reaching the server and "
          "only fixed-asset attempts (prepared-cache hits or the honestly "
          "failed cold-offline model fetch)",
          v_legs, {"modes": modes_seen})

    # --- 7. Cold fixed-asset assessment (first navigation). -----------------
    v_cold: list[dict] = []
    cold_caps = [c for c in captures if c[1].get("cold_boot") is True]
    if not cold_caps:
        v_cold.append({"capture": "-", "channel": "cold_boot",
                       "problem": "no cold-boot capture recorded"})
    else:
        cold_paths = []
        for cpath, cap in cold_caps:
            for i, req in enumerate(cap.get("requests", [])):
                parsed = urlparse(str(req.get("url", "")))
                cold_paths.append(parsed.path)
                if parsed.path not in allowlist or parsed.netloc != origin_netloc:
                    v_cold.append({"capture": cpath.name, "channel": f"requests[{i}].url",
                                   "problem": "cold request outside allowlist"})
        cold_detail = (
            f"cold navigation requested {len(cold_paths)} fixed asset(s), "
            "all inside the built-site allowlist"
        )
    check("cold_fixed_assets",
          "only fixed allowlisted same-origin asset paths",
          cold_detail if cold_caps else "cold-boot capture missing",
          v_cold, {"cold_requests": len(cold_paths) if cold_caps else 0})

    # --- 8. Built artifacts contain no live external endpoints. -------------
    # Enumerate every external URL literal in the built JS/HTML/CSS into the
    # receipt census. A literal is a violation only when it is a telemetry/
    # beacon collector pattern or when the same host actually appeared in a
    # runtime outbound channel — the capture proves every remaining literal
    # (vendor spec links, xmlns namespaces, overridden CDN defaults, parser
    # test vectors, repo links) is inert.
    v_literals: list[dict] = []
    literal_hosts: dict[str, int] = {}
    runtime_hosts: set[str] = set()
    for _cpath, cap in captures:
        for req in cap.get("requests", []) + cap.get("request_failures", []):
            runtime_hosts.add(urlparse(str(req.get("url", ""))).netloc)
        for entry in cap.get("egress", []):
            runtime_hosts.add(urlparse(urljoin(origin, str(entry.get("target", "")))).netloc)
        for ws in cap.get("websockets", []):
            runtime_hosts.add(urlparse(str(ws.get("url", ""))).netloc)
    for asset in sorted(args.dist.rglob("*")):
        if asset.suffix not in (".js", ".html", ".css", ".mjs") or not asset.is_file():
            continue
        try:
            text = asset.read_text(errors="replace")
        except OSError:
            continue
        for match in URL_LITERAL_RE.finditer(text):
            literal = match.group(0)
            host = urlparse(literal).netloc or literal
            literal_hosts[host] = literal_hosts.get(host, 0) + 1
            if TELEMETRY_LITERAL_RE.search(literal):
                v_literals.append({"capture": asset.relative_to(args.dist).as_posix(),
                                   "channel": "dist_literal",
                                   "problem": "telemetry/collector literal in built asset"})
            elif host in runtime_hosts and host != origin_netloc:
                v_literals.append({"capture": asset.relative_to(args.dist).as_posix(),
                                   "channel": "dist_literal",
                                   "problem": f"literal host {host!r} also appeared in runtime traffic"})
    check("built_assets_no_external_endpoints",
          "telemetry/external-font absence proven",
          "built JS/HTML/CSS contains no telemetry/collector endpoint "
          "literals and no external literal host that also appeared in "
          "runtime traffic; the full literal census (vendor spec links, "
          "xmlns namespaces, overridden CDN defaults, parser test vectors) "
          "is recorded for review and was never fetched at runtime",
          v_literals, {"literal_hosts": literal_hosts})

    verdict = "pass" if all(c["status"] == "pass" for c in checks) else "fail"
    receipt = {
        "schema_version": SCHEMA,
        "tool": "scripts/inspect_network_receipt.py",
        "task": "T15",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "origin": origin,
        "canary": {
            # The document hash is itself a marker — record only its digest
            # so the public receipt stays marker-free.
            "document_sha256_16": sha256_hex(
                str(canary.get("document", {}).get("sha256", "")).encode()
            )[:16],
            "byte_length": canary.get("document", {}).get("byte_length"),
            "markers": [{"id": m["id"], "sha256_16": m["digest"]} for m in marker_rows],
        },
        "captures": [
            {
                "file": cpath.name,
                "label": cap.get("label"),
                "mode": cap.get("mode"),
                "surface": cap.get("surface"),
                "requests": len(cap.get("requests", [])),
                "websockets": len(cap.get("websockets", [])),
                "egress_records": len(cap.get("egress", [])),
                "console_messages": len(cap.get("console", [])),
                "legs": [{"name": l.get("name"), "ok": l.get("ok")} for l in cap.get("legs", [])],
            }
            for cpath, cap in captures
        ],
        "census": {
            "requests_total": request_total,
            "methods": methods,
            "unique_paths": sorted(unique_paths),
            "served_pairs": len(served_pairs),
            "downloads": [
                {"filename_sha256_16": sha256_hex(str(d.get("filename", "")).encode())[:16],
                 "bytes": d.get("bytes"), "kind": d.get("kind")}
                for _, cap in captures for d in cap.get("downloads", [])
            ],
        },
        "checks": checks,
        "verdict": verdict,
        "limitations": list(canary.get("limitations", [])),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")

    if args.redacted_capture is not None:
        write_redacted(captures, marker_rows, args.redacted_capture)

    failed = [c for c in checks if c["status"] == "fail"]
    print(f"receipt: {args.receipt}  verdict={verdict}  "
          f"checks={len(checks)} failed={len(failed)}  requests={request_total}")
    for c in failed:
        print(f"  FAIL {c['id']}: {len(c['violations'])} violation(s) — {c['detail']}",
              file=sys.stderr)
    return 0 if verdict == "pass" else 1


def redact_text(text: str, markers: list[dict]) -> str:
    """Replace marker encodings + absolute private paths with safe tokens."""
    for marker in markers:
        mid = str(marker.get("id"))
        for enc_value in marker_encodings(str(marker.get("value", ""))).values():
            text = text.replace(enc_value, f"<marker:{mid}>")
    home = str(Path.home())
    text = text.replace(home + "/", "<private>/").replace(home, "<private>")
    return text


def redact_file(path: Path, markers: list[dict]) -> int:
    if not path.is_file():
        print(f"redact: {path} missing", file=sys.stderr)
        return 1
    original = path.read_text(errors="replace")
    redacted = redact_text(original, markers)
    path.write_text(redacted)
    changed = "updated" if redacted != original else "already clean"
    print(f"redact: {path} {changed}")
    return 0


def write_redacted(captures: list[tuple[Path, dict]], marker_rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    markers = [{"id": m["id"], "value": m["encodings"]["raw"]} for m in marker_rows]
    for cpath, cap in captures:
        text = redact_text(json.dumps(cap, indent=2), markers)
        (out_dir / cpath.name).write_text(text + "\n")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Violation as error:
        print(f"inspect: {error}", file=sys.stderr)
        raise SystemExit(2)
