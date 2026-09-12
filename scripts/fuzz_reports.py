#!/usr/bin/env python3
"""Bounded deterministic fuzzer for the T24 report-import boundary.

Drives ``tests/security/import/fuzz_driver.mjs`` (a thin JSON-lines wrapper
around ``packages/reports/validation``) with a seeded stream of hostile and
benign artifacts: malformed/truncated JSON, duplicate and prototype keys,
oversized strings and assets, archive/container bytes, HTML/SVG/PDF and
polyglot inputs, corrupted and weaponized PNGs, corpus-path traversal and
escaped hostile report text.

Every case is classified ``accept``/``reject``/``crash``/``egress`` and the
run emits a bounded receipt (counts, per-category breakdown, max case time)
plus a JSONL case log. A nonzero exit means an unexpected accept, an
unexpected reject, a crash or an egress attempt. No network access and no
external payload corpora are used; every payload is generated locally from
the delivered fixtures and seeded randomness.

Usage:
    python scripts/fuzz_reports.py --fixed-seed 8090 --cases 1000
    python scripts/fuzz_reports.py --cases 50 --out artifacts/tasks/T24
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import random
import select
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRIVER = ROOT / "tests" / "security" / "import" / "fuzz_driver.mjs"
VALID_DIR = ROOT / "planning" / "contracts" / "examples" / "valid"

# The fuzzer itself is bounded: at most this many cases and this much wall
# clock; any excess is a failure, not a hang.
MAX_CASES = 100_000
CASE_TIMEOUT_S = 60
RUN_TIMEOUT_S = 900

REPORT_FILES = [
    "cancelled.json",
    "empty-completed.json",
    "failed.json",
    "native-evidence.inkflip.json",
    "native-replay.inkflip.json",
    "repeated-occurrences.json",
]

# Non-report contract artifacts: valid through the artifact gate (mode
# "gate") but never through the report-only import (mode "validate").
ARTIFACT_FILES = [
    "acceptance-rules.json",
    "baseline.json",
    "comparison.json",
    "corpus.json",
    "reader-manifest.json",
    "worker-terminal.json",
]

HOSTILE_STRINGS = [
    "</title><script>alert(document.domain)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "javascript:alert(1)",
    '"><script>alert(1)</script><"',
    '<iframe src="https://evil.example"></iframe>',
    "<form action='https://evil.example'><input name=x></form>",
    "<base href='https://evil.example/'>",
    '<meta http-equiv="refresh" content="0;url=https://e.example">',
    'x" style="background:url(https://evil.example)" data-x="',
    "http://autolink.example/path and https://second.example",
    "\u202e RTL override content",
    "<a href='javascript:alert(1)'>click</a>",
    '<object data="data:text/html,<script>alert(1)</script>"></object>',
    "<!--[if IE]><script>alert(1)</script><![endif]-->",
    "vendor\\..\\..\\evil.exe",
    "C:\\Windows\\System32\\cmd.exe /c calc",
    "$(touch /tmp/pwned)`id`",
    "\x00</nulls>\x00",
]

TRAVERSAL_PATHS = [
    "../x.pdf",
    "a/../b.pdf",
    "/abs/x.pdf",
    "\\\\win\\x.pdf",
    "C:\\x.pdf",
    "x:drive.pdf",
    "..",
    "a/../../etc/passwd",
    "./../outside.pdf",
    "dir/../../../f.pdf",
]


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def make_png(
    width: int,
    height: int,
    *,
    color_type: int = 6,
    bit_depth: int = 8,
    bad_sig: bool = False,
    bad_crc: bool = False,
    truncate_idat: bool = False,
    extra_idat_data: bytes | None = None,
    ancillary: list[tuple[bytes, bytes]] | None = None,
    unknown_critical: bytes | None = None,
    trailing: bytes = b"",
    filter_byte: int = 0,
) -> bytes:
    """Procedural RGBA PNG for fuzz cases (zlib/struct only)."""
    bpp = 4 if color_type == 6 else (3 if color_type == 2 else 1)
    row = bytes([filter_byte]) + b"\x40" * (width * bpp)
    raw = row * height
    if extra_idat_data is not None:
        raw = extra_idat_data
    idat = zlib.compress(raw, 6)
    if truncate_idat:
        idat = idat[: max(2, len(idat) // 2)]
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    sig = b"\x89PNG\r\n\x1a\n" if not bad_sig else b"\x89PNF\r\n\x1a\n"
    chunks = [png_chunk(b"IHDR", ihdr)]
    for kind, data in ancillary or []:
        chunks.append(png_chunk(kind, data))
    if unknown_critical is not None:
        chunks.append(png_chunk(unknown_critical, b"\x00"))
    body = png_chunk(b"IDAT", idat)
    if bad_crc:
        body = body[:-4] + b"\xde\xad\xbe\xef"
    chunks.append(body)
    chunks.append(png_chunk(b"IEND", b""))
    return sig + b"".join(chunks) + trailing


class Driver:
    """Line-protocol wrapper for the node validation driver."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            ["node", str(DRIVER)],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert self.proc.stdin and self.proc.stdout
        self.stdin = self.proc.stdin
        self.stdout = self.proc.stdout

    def request(self, req: dict) -> dict:
        self.stdin.write(json.dumps(req) + "\n")
        self.stdin.flush()
        ready, _, _ = select.select(
            [self.stdout], [], [], CASE_TIMEOUT_S
        )
        if not ready:
            raise TimeoutError("case exceeded bound")
        line = self.stdout.readline()
        if line == "":
            raise RuntimeError("driver exited")
        return json.loads(line)

    def validate(self, payload: bytes, seq: int, mode: str = "validate") -> dict:
        return self.request(
            {
                "seq": seq,
                "mode": mode,
                "payload_b64": base64.b64encode(payload).decode("ascii"),
            }
        )

    def seal(self, report: dict, seq: int) -> str:
        res = self.request({"seq": seq, "mode": "seal", "report": report})
        if res.get("result") != "sealed":
            raise RuntimeError(f"seal failed: {res}")
        return res["json"]

    def stats(self) -> dict:
        return self.request({"seq": -1, "mode": "stats"})

    def close(self) -> str:
        try:
            self.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        try:
            return self.proc.stderr.read()[-2000:] if self.proc.stderr else ""
        except Exception:
            return ""


# --------------------------------------------------------------------------
# Case generators. Each returns (category, expected, mode, payload_bytes).
# expected is "accept" or "reject".
# --------------------------------------------------------------------------


def load_reports() -> dict[str, bytes]:
    return {
        name: (VALID_DIR / name).read_bytes()
        for name in REPORT_FILES + ARTIFACT_FILES
        if (VALID_DIR / name).is_file()
    }


def load_json(name: str) -> dict:
    return json.loads((VALID_DIR / name).read_text())


def gen_cases(seed: int, count: int, drv: Driver) -> list[dict]:
    """Deterministic case stream for (seed, count)."""
    rng = random.Random(seed)
    all_files = load_reports()
    reports = {
        n: all_files[n] for n in REPORT_FILES if n in all_files
    }
    artifacts = {
        n: all_files[n] for n in ARTIFACT_FILES if n in all_files
    }
    evidence = load_json("native-evidence.inkflip.json")
    corpus_raw = (VALID_DIR / "corpus.json").read_bytes()
    corpus = load_json("corpus.json")
    cases: list[dict] = []

    seq = 0

    def sealed_bytes(mutate) -> bytes:
        r = json.loads(json.dumps(evidence))
        mutate(r)
        return drv.seal(r, seq).encode("utf-8")

    # --- category bodies ---------------------------------------------------
    def cat_baseline():
        name = rng.choice(sorted(reports))
        return reports[name], "accept", "validate"

    def cat_whitespace():
        doc = rng.choice(list(reports.values())).decode("utf-8")
        variant = "  \n" + doc + "\n\n \t"
        return variant.encode(), "accept", "validate"

    def cat_artifact_gate():
        # non-report artifacts validate through the artifact gate…
        name = rng.choice(sorted(artifacts))
        return artifacts[name], "accept", "gate"

    def cat_artifact_not_report():
        # …but the report-only import still refuses them
        name = rng.choice(sorted(artifacts))
        return artifacts[name], "reject", "validate"

    def cat_truncate():
        doc = rng.choice(list(reports.values()))
        cut = rng.randrange(1, len(doc) - 1)
        return doc[:cut], "reject", "validate"

    def cat_bitflip():
        doc = bytearray(rng.choice(list(reports.values())))
        # Only mutate non-whitespace positions and never to the same byte:
        # any surviving parse then differs semantically and fails the hash.
        ws = b" \t\n\r"
        pos = [i for i, b in enumerate(doc) if b not in ws]
        for _ in range(rng.randrange(1, 5)):
            i = rng.choice(pos)
            b = rng.randrange(0x21, 0x7F)
            if b == doc[i]:
                b = (b + 1) % 0x7E + 0x21
            doc[i] = b
        return bytes(doc), "reject", "validate"

    def cat_dupkey():
        doc = rng.choice(list(reports.values())).decode("utf-8")
        splices = [
            ('"kind": "report"', '"kind": "report","kind": "report"'),
            ('"kind": "report"', '"kind": "report","kind": "other"'),
        ]
        old, new = rng.choice(splices)
        if old not in doc:
            # fixture layout drifted — still guarantee a rejection
            return (doc + " trailing-garbage").encode(), "reject", "validate"
        return doc.replace(old, new, 1).encode(), "reject", "validate"

    def cat_prototype():
        doc = rng.choice(list(reports.values())).decode("utf-8")
        key, val = rng.choice(
            [
                ('"__proto__"', '{"isAdmin":true}'),
                ('"constructor"', '"x"'),
                ('"prototype"', '["polluted"]'),
                ('"__proto__"', "null"),
            ]
        )
        if '"kind": "report"' not in doc:
            return (doc + " trailing-garbage").encode(), "reject", "validate"
        return doc.replace(
            '"kind": "report"', f"{key}:{val},\"kind\": \"report\"", 1
        ).encode(), "reject", "validate"

    def cat_structure():
        doc = rng.choice(list(reports.values())).decode("utf-8")
        r = json.loads(doc)
        choice = rng.randrange(6)
        if choice == 0:
            key = rng.choice(list(r.keys()))
            r.pop(key, None)
        elif choice == 1:
            r[rng.choice(["execute", "plugin", "command", "reader_path"])] = (
                "x"
            )
        elif choice == 2:
            r["schema_version"] = "9.9.9"
        elif choice == 3:
            r["readers"] = "not-an-array"
        elif choice == 4:
            r["document"]["sha256"] = "0" * 64
        else:
            r.setdefault("execution", {})["argv"] = ["rm", "-rf", "/"]
        return json.dumps(r).encode(), "reject", "validate"

    def cat_deepnest():
        d = rng.choice([25, 30, 64, 200, 5000])
        return ("[" * d + "1" + "]" * d).encode(), "reject", "validate"

    def cat_numbers():
        body = rng.choice(
            [
                '{"a":1e999}',
                '{"a":-1e999}',
                '{"a":NaN}',
                '{"a":Infinity}',
                '{"a":9007199254740993}',
                '{"a":' + "9" * rng.randrange(30, 500) + "}",
                '{"a":01}',
                '{"a":.5}',
            ]
        )
        return body.encode(), "reject", "validate"

    def cat_bigstring():
        over = 2_000_000 + rng.randrange(1, 4096)
        field = rng.choice(["title", "explanation"])

        def m(r):
            r["findings"][0][field] = "x" * over

        return sealed_bytes(m), "reject", "validate"

    def cat_bigjson():
        pad = 33 * 1024 * 1024
        return b"{" + b" " * (pad - 2) + b"}", "reject", "validate"

    def cat_archive():
        magics = [
            b"PK\x03\x04",
            b"PK\x05\x06",
            b"PK\x07\x08",
            b"\x1f\x8b\x08",
            b"7z\xbc\xaf\x27\x1c",
            b"Rar!\x1a\x07\x00",
            b"\xfd7zXZ\x00",
            b"BZh9",
            b"\x28\xb5\x2f\xfd",
            b"MSCF",
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        ]
        magic = rng.choice(magics)
        tail = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 512)))
        if rng.random() < 0.3:
            tail += (VALID_DIR / "empty-completed.json").read_bytes()[:256]
        return magic + tail, "reject", "validate"

    def cat_tar():
        block = bytearray(1024)
        block[257:262] = b"ustar"
        for i in range(rng.randrange(0, 40)):
            block[rng.randrange(0, 250)] = rng.randrange(256)
        return bytes(block), "reject", "validate"

    def cat_markup():
        body = rng.choice(
            [
                "<!doctype html><html><body>x</body></html>",
                "<svg xmlns='http://www.w3.org/2000/svg'><rect/></svg>",
                "<?xml version='1.0'?><report/>",
                "<html><script>alert(1)</script></html>",
                "  \n <p>report</p>",
            ]
        )
        return body.encode(), "reject", "validate"

    def cat_pdf():
        return b"%PDF-1." + str(rng.randrange(4, 8)).encode() + b"\n" + bytes(
            rng.randrange(256) for _ in range(200)
        ), "reject", "validate"

    def cat_utf16():
        doc = rng.choice(list(reports.values()))
        bom = rng.choice([b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00"])
        return bom + doc, "reject", "validate"

    def cat_polyglot():
        doc = rng.choice(list(reports.values()))
        kind = rng.randrange(4)
        if kind == 0:
            out = doc + b"\nPK\x03\x04" + b"\x00" * 16
        elif kind == 1:
            out = b"PK\x03\x04" + b"\x00" * 8 + doc
        elif kind == 2:
            out = doc + b'   {"kind":"report"}'
        else:
            out = b"\x89PNG\r\n\x1a\n" + doc
        return out, "reject", "validate"

    def cat_garbage():
        n = rng.randrange(0, 4096)
        if rng.random() < 0.5:
            data = bytes(rng.randrange(256) for _ in range(n))
        else:
            data = "".join(
                chr(rng.randrange(0x20, 0xD7FF)) for _ in range(n)
            ).encode("utf-8", "surrogatepass")
        return data, "reject", "validate"

    def cat_surrogates():
        body = rng.choice(
            [
                '{"a":"\\ud800"}',
                '{"a":"\\udc00x"}',
                '{"a":"\\udfff\\ud800"}',
            ]
        )
        return body.encode(), "reject", "validate"

    def cat_png_corrupt():
        w, h = rng.choice([(1, 1), (4, 4), (13, 7), (64, 64)])
        variant = rng.randrange(8)
        kw = {}
        if variant == 0:
            kw["bad_sig"] = True
        elif variant == 1:
            kw["bad_crc"] = True
        elif variant == 2:
            kw["truncate_idat"] = True
        elif variant == 3:
            kw["filter_byte"] = rng.randrange(5, 256)
        elif variant == 4:
            # uppercase first byte = critical chunk type the decoder must
            # refuse (lowercase-first would be ignorable ancillary)
            kw["unknown_critical"] = rng.choice([b"ABCD", b"WXYZ"])
        elif variant == 5:
            kw["trailing"] = b"PK\x03\x04" + b"\x00" * 8
        elif variant == 6:
            # inflate output far beyond declared raster
            kw["extra_idat_data"] = b"\x00" * (w * h * 4 + h + 4096)
            png = make_png(w, h, **kw)
        else:
            # variant 7: two concatenated PNGs — trailing document fails
            png = make_png(w, h) + make_png(w, h)
        if variant != 7 and variant != 6:
            png = make_png(w, h, **kw)

        def m(r):
            a = r["assets"][0]
            a["data_base64"] = base64.b64encode(png).decode()
            a["byte_length"] = len(png)
            a["sha256"] = hashlib.sha256(png).hexdigest()
            a["pixel_size"] = [w, h]
            a["media_type"] = "image/png"
            a["purpose"] = "crop"

        return sealed_bytes(m), "reject", "validate"

    def cat_png_bomb():
        # Declared raster is inside the pixel cap, but the IDAT inflates to
        # many times the needed bytes (decompression abuse).
        w = rng.choice([512, 1000, 1999])
        raw = b"\x00" * (w * w * 4 + w + 8 * 1024 * 1024)
        png = make_png(w, w, extra_idat_data=raw)

        def m(r):
            a = r["assets"][0]
            a["data_base64"] = base64.b64encode(png).decode()
            a["byte_length"] = len(png)
            a["sha256"] = hashlib.sha256(png).hexdigest()
            a["pixel_size"] = [w, w]
            a["media_type"] = "image/png"
            a["purpose"] = "crop"

        return sealed_bytes(m), "reject", "validate"

    def cat_png_ancillary():
        w, h = rng.choice([(2, 2), (9, 5)])
        anc = rng.choice(
            [
                [(b"acTL", struct.pack(">II", 1, 0))],
                [(b"tEXt", b"evil\x00<script>alert(1)</script>")],
                [(b"iCCP", b"fake profile\x00\x00" + zlib.compress(b"x"))],
                [(b"eXIf", b"II*\x00" + b"\x00" * 16)],
            ]
        )
        png = make_png(w, h, ancillary=anc)

        def m(r):
            a = r["assets"][0]
            a["data_base64"] = base64.b64encode(png).decode()
            a["byte_length"] = len(png)
            a["sha256"] = hashlib.sha256(png).hexdigest()
            a["pixel_size"] = [w, h]
            a["media_type"] = "image/png"
            a["purpose"] = "crop"

        # ancillary/vector chunks are sanitized away: import must succeed
        return sealed_bytes(m), "accept", "validate"

    def cat_asset_meta():
        r = json.loads(json.dumps(evidence))
        a = r["assets"][0]
        choice = rng.randrange(6)
        if choice == 0:
            a["sha256"] = "0" * 64
        elif choice == 1:
            a["byte_length"] = a["byte_length"] + rng.choice([1, -1, 1000])
        elif choice == 2:
            a["media_type"] = rng.choice(
                ["image/svg+xml", "text/html", "application/zip", "image/png;evil"]
            )
        elif choice == 3:
            a["purpose"] = rng.choice(["executable", "plugin", "payload"])
        elif choice == 4:
            b64 = list(a["data_base64"])
            b64[rng.randrange(len(b64))] = rng.choice(["!", " ", "\n", "="])
            a["data_base64"] = "".join(b64)
        else:
            a["id"] = rng.choice(["../evil", "UPPER", "a b", "a;b"])
        return drv.seal(r, seq).encode(), "reject", "validate"

    def cat_asset_fake():
        # non-PNG bytes claiming to be a PNG crop
        body = rng.choice(
            [
                b"<svg xmlns='http://www.w3.org/2000/svg' onload='x'/>",
                b"GIF89a" + b"\x00" * 32,
                b"BM" + b"\x00" * 64,
                b"\xff\xd8\xff\xe0" + b"\x00" * 64,
                b"%PDF-1.7\n",
                b"PK\x03\x04" + b"\x00" * 32,
            ]
        )

        def m(r):
            a = r["assets"][0]
            a["data_base64"] = base64.b64encode(body).decode()
            a["byte_length"] = len(body)
            a["sha256"] = hashlib.sha256(body).hexdigest()
            a["media_type"] = "image/png"
            a["purpose"] = "crop"
            a["pixel_size"] = [4, 4]

        return sealed_bytes(m), "reject", "validate"

    def cat_corpus_path():
        bad = rng.random() < 0.8
        if not bad:
            # the delivered manifest itself is a clean accept
            return corpus_raw, "accept", "gate"
        m = json.loads(json.dumps(corpus))
        m["entries"][0]["source_path"] = rng.choice(TRAVERSAL_PATHS)
        return json.dumps(m).encode(), "reject", "gate"

    def cat_hostile_string():
        payload = rng.choice(HOSTILE_STRINGS)
        slot = rng.randrange(4)

        def m(r):
            if slot == 0:
                r["findings"][0]["title"] = payload[:200]
            elif slot == 1:
                r["findings"][0]["explanation"] = payload[:4000]
            elif slot == 2:
                r["readers"][0]["name"] = payload[:100]
            else:
                r["limitations"] = [payload[:2000]]

        return sealed_bytes(m), "accept", "validate"

    CATEGORIES = [
        (cat_baseline, 60),
        (cat_whitespace, 20),
        (cat_artifact_gate, 20),
        (cat_artifact_not_report, 20),
        (cat_truncate, 90),
        (cat_bitflip, 100),
        (cat_dupkey, 40),
        (cat_prototype, 60),
        (cat_structure, 80),
        (cat_deepnest, 40),
        (cat_numbers, 30),
        (cat_bigstring, 25),
        (cat_bigjson, 2),
        (cat_archive, 80),
        (cat_tar, 20),
        (cat_markup, 40),
        (cat_pdf, 20),
        (cat_utf16, 15),
        (cat_polyglot, 50),
        (cat_garbage, 60),
        (cat_surrogates, 15),
        (cat_png_corrupt, 90),
        (cat_png_bomb, 15),
        (cat_png_ancillary, 25),
        (cat_asset_meta, 60),
        (cat_asset_fake, 40),
        (cat_corpus_path, 40),
        (cat_hostile_string, 60),
    ]
    total_w = sum(w for _, w in CATEGORIES)

    # Guarantee coverage: one of each category first, then weighted random.
    order = [fn for fn, _ in CATEGORIES]
    while len(order) < count:
        r = rng.randrange(total_w)
        acc = 0
        for fn, w in CATEGORIES:
            acc += w
            if r < acc:
                order.append(fn)
                break
    rng.shuffle(order)
    order = order[:count]

    for fn in order:
        seq += 1
        t0 = time.monotonic()
        payload, expected, mode = fn()
        cases.append(
            {
                "seq": seq,
                "category": fn.__name__[4:],
                "expected": expected,
                "mode": mode,
                "payload": payload,
                "size": len(payload),
                "gen_ms": round((time.monotonic() - t0) * 1000, 2),
            }
        )
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixed-seed", type=int, default=8090)
    ap.add_argument("--cases", type=int, default=1000)
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "artifacts" / "tasks" / "T24" / "fuzz",
        help="directory for fuzz-receipt.json / fuzz-cases.jsonl",
    )
    args = ap.parse_args()
    if not 1 <= args.cases <= MAX_CASES:
        ap.error(f"--cases must be within 1..{MAX_CASES}")

    drv = Driver()
    started = time.monotonic()
    counts = {
        "accepted": 0,
        "rejected": 0,
        "crashes": 0,
        "unexpected_accepts": 0,
        "unexpected_rejects": 0,
        "egress": 0,
    }
    by_category: dict[str, dict[str, int]] = {}
    codes: dict[str, int] = {}
    max_ms = 0.0
    failures: list[dict] = []
    args.out.mkdir(parents=True, exist_ok=True)
    case_log = open(args.out / "fuzz-cases.jsonl", "w", encoding="utf-8")

    stream = hashlib.sha256()

    try:
        cases = gen_cases(args.fixed_seed, args.cases, drv)
        for case in cases:
            row = {
                "seq": case["seq"],
                "category": case["category"],
                "expected": case["expected"],
                "size": case["size"],
                "gen_ms": case["gen_ms"],
            }
            stream.update(
                json.dumps(
                    [
                        case["seq"],
                        case["category"],
                        case["expected"],
                        case["mode"],
                        case["size"],
                        hashlib.sha256(case["payload"]).hexdigest(),
                    ],
                    separators=(",", ":"),
                ).encode()
            )
            try:
                res = drv.validate(
                    case["payload"], case["seq"], mode=case["mode"]
                )
            except (RuntimeError, TimeoutError, BrokenPipeError) as exc:
                res = {"result": "crash", "detail": str(exc)[:200]}
            result = res.get("result", "error")
            row["result"] = result
            row["code"] = res.get("code") or res.get("detail")
            row["ms"] = res.get("ms")
            if isinstance(res.get("ms"), (int, float)):
                max_ms = max(max_ms, float(res["ms"]))
            cat = by_category.setdefault(
                case["category"],
                {"accept": 0, "reject": 0, "crash": 0, "egress": 0},
            )
            cat[result if result in cat else "crash"] += 1
            if row["code"]:
                codes[str(row["code"])] = codes.get(str(row["code"]), 0) + 1

            if result == "accept":
                counts["accepted"] += 1
                if case["expected"] == "reject":
                    counts["unexpected_accepts"] += 1
                    failures.append(row)
            elif result == "reject":
                counts["rejected"] += 1
                if case["expected"] == "accept":
                    counts["unexpected_rejects"] += 1
                    failures.append(row)
            elif result == "egress":
                counts["egress"] += 1
                failures.append(row)
            else:
                counts["crashes"] += 1
                failures.append(row)
            case_log.write(json.dumps(row, ensure_ascii=False) + "\n")
            if time.monotonic() - started > RUN_TIMEOUT_S:
                failures.append({"error": "run timeout", "seq": case["seq"]})
                break
    finally:
        try:
            stats = drv.stats()
        except Exception:
            stats = {"egress_attempts": ["<driver unreachable>"]}
        stderr_tail = drv.close()
        case_log.close()

    egress_attempts = stats.get("egress_attempts", [])
    if egress_attempts:
        counts["egress"] += len(egress_attempts)

    receipt = {
        "tool": "scripts/fuzz_reports.py",
        "task": "T24",
        "seed": args.fixed_seed,
        "cases_requested": args.cases,
        "stream_sha256": stream.hexdigest(),
        "counts": counts,
        "by_category": by_category,
        "reject_codes": codes,
        "max_case_ms": round(max_ms, 2),
        "wall_s": round(time.monotonic() - started, 2),
        "egress_attempts": egress_attempts,
        "driver_stderr_tail": stderr_tail[-500:] if stderr_tail else "",
        "unexpected": failures[:100],
    }
    ok = (
        counts["crashes"] == 0
        and counts["egress"] == 0
        and counts["unexpected_accepts"] == 0
        and counts["unexpected_rejects"] == 0
        and not egress_attempts
    )
    receipt["verdict"] = "pass" if ok else "fail"
    (args.out / "fuzz-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt["counts"], sort_keys=True))
    print(
        f"verdict={receipt['verdict']} cases={args.cases} "
        f"seed={args.fixed_seed} max_case_ms={receipt['max_case_ms']} "
        f"wall_s={receipt['wall_s']} out={args.out}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
