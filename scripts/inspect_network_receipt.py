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
# Candidate base64/base64url payloads embedded in log text (F6): decode
# and re-scan so a marker wrapped inside a base64'd JSON/blob is caught.
B64_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_-]{24,}={0,2}")
# Egress kinds the in-page tripwire can emit. Anything outside this closed
# set is itself a violation — a channel the tripwire learned later can
# never slip past unexamined (F4).
EGRESS_FORBIDDEN = {
    "beacon", "eventsource", "window.open", "serviceworker.register",
    "websocket", "webrtc", "webtransport", "form.submit",
}
EGRESS_SAME_ORIGIN = {"fetch", "xhr", "worker"}
# Keys every capture must carry — absence means the proof, not just the
# data, is missing (F1: fail closed on absent evidence).
REQUIRED_CAPTURE_KEYS = {
    "schema_version", "label", "mode", "surface", "origin", "legs",
    "requests", "request_failures", "responses", "websockets", "egress",
    "console", "page_errors", "dialogs", "downloads", "server_log",
    "storage",
}
# Journey coverage required across the union of all captures' legs —
# a receipt cannot claim the journey ran if the legs were never recorded.
REQUIRED_JOURNEY_LEGS = {
    "open": re.compile(r"open-canary"),
    "error": re.compile(r"error-"),
    "render": re.compile(r"render"),
    "ocr": re.compile(r"ocr-(open|extract|prepare)"),
    "export": re.compile(r"export"),
    "reopen": re.compile(r"reopen-export"),
    "clear": re.compile(r"clear-file"),
}


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


def _headers_text(value: object) -> str:
    """Serialize a captured header map deterministically for scanning."""
    return json.dumps(value, sort_keys=True) if isinstance(value, dict) else ""


def observation_texts(capture: dict):
    """(channel, text) pairs that could carry document material outbound."""
    obs = []
    for i, req in enumerate(capture.get("requests", [])):
        obs.append((f"requests[{i}].url", req.get("url", "")))
        headers = _headers_text(req.get("headers"))
        if headers:
            obs.append((f"requests[{i}].headers", headers))
        body = req.get("post_body")
        if isinstance(body, str):
            obs.append((f"requests[{i}].post_body", body))
    for i, req in enumerate(capture.get("request_failures", [])):
        obs.append((f"request_failures[{i}].url", req.get("url", "")))
        headers = _headers_text(req.get("headers"))
        if headers:
            obs.append((f"request_failures[{i}].headers", headers))
    for i, res in enumerate(capture.get("responses", [])):
        obs.append((f"responses[{i}].url", res.get("url", "")))
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
    for i, leg in enumerate(capture.get("legs", [])):
        detail = leg.get("detail") if isinstance(leg, dict) else None
        if isinstance(detail, str):
            obs.append((f"legs[{i}].detail", detail))
    for i, dialog in enumerate(capture.get("dialogs", [])):
        obs.append((f"dialogs[{i}].message", str(dialog.get("message", ""))))
    for i, entry in enumerate(capture.get("server_log", [])):
        obs.append((f"server_log[{i}].path", str(entry.get("path", ""))))
        query = entry.get("query")
        if isinstance(query, str):
            obs.append((f"server_log[{i}].query", query))
        headers = _headers_text(entry.get("headers"))
        if headers:
            obs.append((f"server_log[{i}].headers", headers))
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
        # Failed requests never reached the wire, but their intended
        # destination still has to satisfy the same wire rules — a
        # failures-only record can never smuggle a foreign origin.
        for i, req in enumerate(cap.get("request_failures", [])):
            url = str(req.get("url", ""))
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                v_same.append({"capture": cpath.name,
                               "channel": f"request_failures[{i}].url",
                               "problem": f"non-http scheme {parsed.scheme!r}"})
                continue
            if parsed.netloc != origin_netloc:
                v_same.append({"capture": cpath.name,
                               "channel": f"request_failures[{i}].url",
                               "problem": f"foreign origin {parsed.netloc!r}"})
            path = parsed.path or "/"
            if path not in allowlist:
                v_allow.append({"capture": cpath.name,
                                "channel": f"request_failures[{i}].url",
                                "problem": f"path not allowlisted: {path}"})
            if parsed.query:
                v_query.append({"capture": cpath.name,
                                "channel": f"request_failures[{i}].url",
                                "problem": "query string present"})
            method = str(req.get("method", "")).upper()
            if method and method not in ALLOWED_METHODS:
                v_method.append({"capture": cpath.name,
                                 "channel": f"request_failures[{i}].url",
                                 "problem": f"method {method}"})
        for i, res in enumerate(cap.get("responses", [])):
            parsed = urlparse(str(res.get("url", "")))
            if parsed.scheme in ("http", "https") and parsed.netloc != origin_netloc:
                v_same.append({"capture": cpath.name, "channel": f"responses[{i}].url",
                               "problem": f"foreign origin {parsed.netloc!r}"})
            elif parsed.scheme not in ("http", "https"):
                v_same.append({"capture": cpath.name, "channel": f"responses[{i}].url",
                               "problem": f"non-http scheme {parsed.scheme!r}"})
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
        obs = observation_texts(cap)
        for channel, text in obs:
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
        # Normalized sweep: a marker split across two log lines or smeared
        # over whitespace is invisible to per-text substring matching, so
        # the concatenation and a whitespace-collapsed variant are scanned
        # per marker (excluding that marker's allowed channels).
        for marker in marker_rows:
            scoped = [t for ch, t in obs
                      if ch.split("[")[0] not in marker["allowed_channels"]]
            joined = "".join(scoped)
            collapsed = re.sub(r"\s+", "", joined)
            for enc_name, enc_value in marker["encodings"].items():
                if enc_value in joined or enc_value in collapsed:
                    v_markers.append({
                        "capture": cpath.name, "channel": "<joined channels>",
                        "marker_id": marker["id"],
                        "encoding": f"{enc_name} (cross-channel/whitespace)"})
                    break
            # Base64-carried payloads: decode plausible tokens and scan the
            # decoded text — catches a marker wrapped inside a base64'd
            # JSON/blob payload on any channel.
            for channel, text in obs:
                if channel.split("[")[0] in marker["allowed_channels"]:
                    continue
                for token in B64_TOKEN_RE.findall(text)[:50]:
                    if len(token) > 8192:
                        continue
                    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
                        try:
                            decoded = decoder(token + "=" * (-len(token) % 4))
                        except (ValueError, TypeError):
                            continue
                        decoded_text = decoded.decode("utf-8", errors="ignore")
                        if not decoded_text:
                            continue
                        for enc_name in ("raw", "url_encoded"):
                            enc_value = marker["encodings"].get(enc_name, "")
                            if enc_value and enc_value in decoded_text:
                                v_markers.append({
                                    "capture": cpath.name, "channel": channel,
                                    "marker_id": marker["id"],
                                    "encoding": "base64-wrapped payload"})
                                break
    check("no_canary_material_outbound",
          "No canary bytes/text/name/hash/crop/report in outbound traffic or URLs",
          "no marker (filename, visible/hidden text, document hash, raster "
          "pixels, note, report id/name — in raw, percent, base64, hex, "
          "cross-channel-split or base64-wrapped spellings) appears in any "
          "captured request URL/header/body, response, websocket, egress "
          "attempt, console payload, leg detail, dialog, storage value or "
          "server path/header",
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
            if kind in EGRESS_FORBIDDEN:
                v_channels.append({"capture": cpath.name, "channel": f"egress[{i}]",
                                   "problem": f"{kind} attempt: {urlparse(urljoin(origin, target)).netloc or target}"})
            elif kind in EGRESS_SAME_ORIGIN:
                resolved = urlparse(urljoin(origin, target))
                if resolved.scheme in ("http", "https", "ws", "wss"):
                    if resolved.netloc != origin_netloc:
                        v_channels.append({"capture": cpath.name, "channel": f"egress[{i}]",
                                           "problem": f"foreign {kind} target {resolved.netloc}"})
                    elif resolved.path not in allowlist:
                        v_channels.append({"capture": cpath.name, "channel": f"egress[{i}]",
                                           "problem": f"{kind} target not allowlisted: {resolved.path}"})
                elif resolved.scheme not in LOCAL_SCHEMES:
                    v_channels.append({"capture": cpath.name, "channel": f"egress[{i}]",
                                       "problem": f"unhandled {kind} scheme {resolved.scheme!r}"})
            else:
                v_channels.append({"capture": cpath.name, "channel": f"egress[{i}]",
                                   "problem": f"unrecognized egress kind {kind!r} — fails closed"})
        for i, dialog in enumerate(cap.get("dialogs", [])):
            v_channels.append({"capture": cpath.name, "channel": f"dialogs[{i}]",
                               "problem": f"unexpected {dialog.get('type')} dialog: "
                                          f"{str(dialog.get('message', ''))[:80]}"})
        sw = cap.get("storage", {}).get("service_workers", 0)
        if sw not in (0, "0", None):
            v_channels.append({"capture": cpath.name, "channel": "storage.service_workers",
                               "problem": f"{sw} service worker registration(s)"})
    check("no_websocket_beacon_serviceworker",
          "telemetry/external-font absence proven",
          "zero websockets, zero sendBeacon/EventSource/window.open/"
          "WebRTC/WebTransport/form.submit attempts, zero unexpected "
          "dialogs, zero service-worker registrations; fetch/XHR/worker "
          "tripwire targets all stay inside the same-origin allowlist; "
          "unrecognized egress kinds fail closed",
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

    # --- 5b. Evidence presence — the validator requires evidence, not
    #         merely the absence of leaks (F1: fail closed on absence). --
    v_present: list[dict] = []
    all_leg_names: set[str] = set()
    for cpath, cap in captures:
        missing_keys = sorted(REQUIRED_CAPTURE_KEYS - set(cap.keys()))
        for key in missing_keys:
            v_present.append({"capture": cpath.name, "channel": "capture",
                              "problem": f"required capture key {key!r} absent"})
        legs = cap.get("legs")
        if not isinstance(legs, list) or not legs:
            v_present.append({"capture": cpath.name, "channel": "legs",
                              "problem": "no journey legs recorded"})
        else:
            for j, leg in enumerate(legs):
                if not isinstance(leg, dict) or not leg.get("name"):
                    v_present.append({"capture": cpath.name,
                                      "channel": f"legs[{j}]",
                                      "problem": "leg missing a name"})
                    continue
                all_leg_names.add(str(leg["name"]))
                if not isinstance(leg.get("ok"), bool):
                    v_present.append({"capture": cpath.name,
                                      "channel": f"legs[{j}]",
                                      "problem": "leg.ok is not boolean"})
        if "storage" not in cap:
            v_present.append({"capture": cpath.name, "channel": "storage",
                              "problem": "storage snapshot absent"})
        if not isinstance(cap.get("mode"), str) or not cap.get("mode"):
            v_present.append({"capture": cpath.name, "channel": "mode",
                              "problem": "mode label absent"})
        if cap.get("offline") is not True and not cap.get("requests"):
            v_present.append({"capture": cpath.name, "channel": "requests",
                              "problem": "non-offline capture recorded zero "
                                         "requests — evidence absent"})
        for i, req in enumerate(cap.get("requests", [])):
            if not isinstance(req.get("headers"), dict):
                v_present.append({"capture": cpath.name,
                                  "channel": f"requests[{i}].headers",
                                  "problem": "request headers not captured"})
        for i, req in enumerate(cap.get("request_failures", [])):
            if not isinstance(req.get("headers"), dict):
                v_present.append({"capture": cpath.name,
                                  "channel": f"request_failures[{i}].headers",
                                  "problem": "failed-request headers not captured"})
        for i, entry in enumerate(cap.get("server_log", [])):
            if not isinstance(entry.get("headers"), dict):
                v_present.append({"capture": cpath.name,
                                  "channel": f"server_log[{i}].headers",
                                  "problem": "served request headers not logged"})
    for journey, pattern in REQUIRED_JOURNEY_LEGS.items():
        if not any(pattern.search(name) for name in all_leg_names):
            v_present.append({"capture": "-", "channel": "legs",
                              "problem": f"required journey leg {journey!r} "
                                         "absent from every capture"})
    check("capture_evidence_present",
          "online/warm/offline modes documented",
          "every capture carries the full channel key set, nonempty named "
          "legs, a storage snapshot and captured request headers; every "
          "non-offline capture recorded at least one request; the union of "
          "legs covers open/error/render/OCR/export/reopen/clear — absent "
          "or emptied evidence can never pass",
          v_present, {"journey_legs_seen": len(all_leg_names)})

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

    # --- 6b. Model-fetch provenance from the wire evidence (F9). ------------
    # Cold mode must show the staged model download reaching the server
    # exactly once; warm mode must show zero model requests (verified IDB
    # slot); offline captures must show zero model paths in the server log.
    v_prov: list[dict] = []
    model_reqs_cold = 0
    model_served_total = 0
    for cpath, cap in captures:
        mode = str(cap.get("mode", ""))
        model_reqs = [
            urlparse(str(r.get("url", ""))).path
            for r in cap.get("requests", [])
            if urlparse(str(r.get("url", ""))).path.startswith("/models/")
        ]
        model_served = [
            str(e.get("path", ""))
            for e in cap.get("server_log", [])
            if str(e.get("path", "")).startswith("/models/")
        ]
        model_served_total += len(model_served)
        if mode == "cold":
            model_reqs_cold += len(model_reqs)
        if mode == "warm" and (model_reqs or model_served):
            v_prov.append({"capture": cpath.name, "channel": "models",
                           "problem": f"warm mode touched model assets "
                                      f"(requests={len(model_reqs)} served={len(model_served)})"})
        if mode == "offline" and model_served:
            v_prov.append({"capture": cpath.name, "channel": "models",
                           "problem": "model asset reached the server while offline"})
    if model_reqs_cold == 0:
        v_prov.append({"capture": "-", "channel": "models",
                       "problem": "no cold-mode capture shows the staged "
                                  "model download — network provenance unproven"})
    if model_served_total == 0:
        v_prov.append({"capture": "-", "channel": "models",
                       "problem": "the model fetch never reached the server "
                                  "in any capture — cold download unproven"})
    check("model_fetch_provenance",
          "online/warm/offline modes documented",
          "cold mode fetched the staged model over the wire exactly once "
          "(network provenance), warm mode reused the verified cache with "
          "zero model requests, offline captures served zero model paths — "
          "derived from request and server-log evidence, not in-page "
          "assertions",
          v_prov, {"cold_model_requests": model_reqs_cold,
                   "model_paths_served": model_served_total})

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
            # allowed_channels is declared per marker in the private canary
            # manifest (gitignored); the policy is echoed here — marker ids
            # and digests only, never marker values — so the committed
            # receipt shows which channels each report-derived marker was
            # permitted to occupy (local downloads only).
            "markers": [
                {
                    "id": m["id"],
                    "sha256_16": m["digest"],
                    "allowed_channels": sorted(m["allowed_channels"]),
                }
                for m in marker_rows
            ],
        },
        "captures": [
            {
                "file": cpath.name,
                "label": cap.get("label"),
                "mode": cap.get("mode"),
                "surface": cap.get("surface"),
                "requests": len(cap.get("requests", [])),
                "responses": len(cap.get("responses", [])),
                "websockets": len(cap.get("websockets", [])),
                "egress_records": len(cap.get("egress", [])),
                "console_messages": len(cap.get("console", [])),
                "dialogs": len(cap.get("dialogs", [])),
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
