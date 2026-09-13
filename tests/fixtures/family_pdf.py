"""Shared PDF object/content helpers for the fixture-family mechanism tests.

These helpers read the committed fixtures byte-for-byte. They deliberately use
the same stdlib-regex object parsing as tests/fixtures/test_fixtures.py (no new
dependency, no golden regeneration) and add only what the family tests need:
text matrices, per-run coordinates, page boxes, annotation objects, RLE image
decoding, and disposable-copy mutation that preserves every declared /Length.
"""
from __future__ import annotations

import re
from pathlib import Path

_OBJ = re.compile(rb"(\d+) 0 obj\n(.*?)\nendobj\n", re.S)
_STREAM = re.compile(rb"stream\n(.*?)\nendstream", re.S)
_TM = re.compile(rb"(-?[\d.]+) +(-?[\d.]+) +(-?[\d.]+) +(-?[\d.]+) +(-?[\d.]+) +(-?[\d.]+)\s+Tm")
_TJ = re.compile(rb"\(([^)]*)\) Tj")


def objects(data: bytes) -> dict[int, bytes]:
    return {int(m.group(1)): m.group(2) for m in _OBJ.finditer(data)}


def page_object(data: bytes) -> bytes:
    return next(o for o in objects(data).values() if b"/Type /Page" in o and b"/Pages" not in o)


def content_bytes(data: bytes) -> bytes:
    page = page_object(data)
    number = int(re.search(rb"/Contents (\d+) 0 R", page).group(1))
    raw = objects(data)[number]
    match = _STREAM.search(raw)
    if not match:
        raise AssertionError("page content object has no stream")
    return match.group(1)


def content_lines(data: bytes) -> list[bytes]:
    return [line for line in content_bytes(data).split(b"\n") if line.strip()]


def tm_matrices(content: bytes) -> list[list[float]]:
    return [[float(value) for value in match.groups()] for match in _TM.finditer(content)]


def painted_texts(content: bytes) -> list[str]:
    return [text.decode("latin-1") for text in _TJ.findall(content)]


def text_runs(content: bytes) -> list[tuple[float, float, str]]:
    """(x, y, text) for each text-showing run, in stream order."""
    return [(m[4], m[5], text) for m, text in _pairs(content)]


def _pairs(content: bytes):
    out = []
    cursor = 0
    for match in _TM.finditer(content):
        tail = content[match.end():match.end() + 200]
        shown = _TJ.search(tail)
        if not shown:
            continue
        out.append(([float(v) for v in match.groups()], shown.group(1).decode("latin-1")))
    return out


def text_order(content: bytes) -> list[str]:
    return [text for _m, text in _pairs(content)]


def box(page: bytes, name: bytes) -> list[float] | None:
    match = re.search(name + rb"\s*\[([^\]]+)\]", page)
    if not match:
        return None
    return [float(value) for value in match.group(1).split()]


def annot_refs(page: bytes) -> list[int]:
    match = re.search(rb"/Annots\s*\[([^\]]*)\]", page)
    if not match:
        return []
    return [int(value) for value in re.findall(rb"(\d+) 0 R", match.group(1))]


def annotations(data: bytes) -> list[dict]:
    """Every object the page lists in /Annots, as {'number', 'body', 'stream'}."""
    objs = objects(data)
    out = []
    for number in annot_refs(page_object(data)):
        body = objs.get(number)
        if body is None:
            continue
        stream = None
        match = _STREAM.search(body)
        if match:
            stream = match.group(1)
            body = body[:match.start()]
        out.append({"number": number, "body": body, "stream": stream})
    return out


def image_object(data: bytes) -> bytes:
    for body in objects(data).values():
        if b"/Subtype /Image" in body:
            return body
    raise AssertionError("no image XObject on the page")


def rle_decode(data: bytes) -> bytes:
    out = bytearray()
    index = 0
    while index < len(data):
        length = data[index]
        index += 1
        if length == 128:
            break
        if length < 128:
            out.extend(data[index:index + length + 1])
            index += length + 1
        else:
            out.extend(bytes([data[index]]) * (257 - length))
            index += 1
    return bytes(out)


def image_stream(data: bytes) -> bytes:
    raw = image_object(data)
    match = _STREAM.search(raw)
    if not match:
        raise AssertionError("image object has no stream")
    return match.group(1)


def raster(data: bytes) -> bytes:
    raw = image_object(data)
    match = _STREAM.search(raw)
    if not match:
        raise AssertionError("image object has no stream")
    return rle_decode(match.group(1))


def image_header(data: bytes) -> dict:
    raw = image_object(data)
    head = raw.split(b"stream")[0]
    return {
        "width": int(re.search(rb"/Width (\d+)", head).group(1)),
        "height": int(re.search(rb"/Height (\d+)", head).group(1)),
        "bits": int(re.search(rb"/BitsPerComponent (\d+)", head).group(1)),
        "filter": re.search(rb"/Filter /(\w+)", head).group(1).decode(),
        "colour_space": re.search(rb"/ColorSpace /(\w+)", head).group(1).decode(),
    }


def speckle_score(pixels: bytes, width: int, height: int) -> int:
    """Count pixels whose grey value differs from all four orthogonal neighbours.

    A deterministic, resolution-independent proxy for the declared 'fixed-seed
    speckle': isolated single-pixel deviations cannot come from the printed
    line itself, which is made of connected glyph strokes.
    """
    score = 0
    for y in range(1, height - 1):
        row = y * width
        for x in range(1, width - 1):
            value = pixels[row + x]
            if (
                pixels[row + x - 1] != value
                and pixels[row + x + 1] != value
                and pixels[row - width + x] != value
                and pixels[row + width + x] != value
            ):
                score += 1
    return score


def same_length(old: bytes, text: str) -> bytes:
    """Encode ``text`` padded with spaces to exactly ``len(old)`` bytes.

    PDF content streams treat trailing whitespace as insignificant, so this
    keeps every declared /Length (and therefore the xref) valid.
    """
    encoded = text.encode("latin-1")
    if len(encoded) > len(old):
        raise AssertionError("replacement longer than the pattern")
    return encoded + b" " * (len(old) - len(encoded))


def object_stream(data: bytes, number: int) -> bytes | None:
    """The stream bytes of one indirect object, or None when it has none."""
    body = objects(data).get(number)
    if body is None:
        return None
    match = _STREAM.search(body)
    return match.group(1) if match else None


def patched_copy(source: Path, destination: Path, replacements: list[tuple[bytes, bytes]]) -> Path:
    """Copy a fixture and apply equal-length byte replacements.

    Equal length keeps every declared /Length and xref offset valid, so the
    mutated copy stays a well-formed fixture. This is the counterfactual
    instrument: a mutation that must make a mechanism assertion fail.
    """
    data = source.read_bytes()
    for old, new in replacements:
        if len(old) != len(new):
            raise AssertionError("patched_copy requires equal-length replacements")
        count = data.count(old)
        if count == 0:
            raise AssertionError(f"pattern not present: {old!r}")
        data = data.replace(old, new)
    destination.write_bytes(data)
    return destination


def permuted_content_copy(source: Path, destination: Path) -> Path:
    """Copy a fixture with its content-stream lines reversed.

    Reversing whole lines preserves the total stream length exactly (so
    /Length stays valid) while changing the order text is emitted in.
    """
    data = source.read_bytes()
    content = content_bytes(data)
    lines = [line for line in content.split(b"\n") if line.strip()]
    flipped = b"\n".join(reversed(lines)) + b"\n"
    if len(flipped) != len(content):
        raise AssertionError("line permutation must preserve stream length")
    destination.write_bytes(data.replace(content, flipped))
    return destination
