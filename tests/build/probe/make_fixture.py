#!/usr/bin/env python3
"""Generate tests/build/probe/fixture.pdf — a fixed synthetic control.

One A4 page, two Helvetica text runs. The bytes are deterministic (no dates,
IDs or compressed streams), so the committed file and this generator cannot
drift apart: run with `--check` to assert the committed bytes are identical.
"""
from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "fixture.pdf"

OBJECTS = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
]


def build() -> bytes:
    stream = (b"BT /F1 60 Tf 72 660 Td (HELLO INKFLIP) Tj ET\n"
              b"BT /F1 28 Tf 72 600 Td (reading control) Tj ET\n")
    objects = list(OBJECTS)
    objects.append(b"<< /Length " + str(len(stream)).encode() +
                   b" >>\nstream\n" + stream + b"endstream")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


def main() -> int:
    data = build()
    if "--check" in sys.argv:
        if not OUT.is_file() or OUT.read_bytes() != data:
            print("fixture.pdf does not match the generator output")
            return 1
        print("fixture.pdf matches the generator output")
        return 0
    OUT.write_bytes(data)
    print(f"wrote {OUT} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
