#!/usr/bin/env python3
"""Deterministic original Inkflip fixture generator (T05).

Fixed, harmless sample recipes only; this is not a payload tool and cannot
build arbitrary documents. Stdlib only. No font programs are embedded: text
pages use PDF base-14 Helvetica and the searchable-scan raster is printed by
a generated 5x7 bitmap glyph table (no font resource at all). Repeated
generation is byte-identical on every platform: fixed object order, fixed
stream bytes, no creation timestamp, no random document ID and no
compression-codec dependence (the raster uses PDF RunLength filtering, which
this file encodes itself).

Families (planning/quality/fixture-catalog.json), with clean twins:

  F01 mapping-amount   ToUnicode one-to-many mapping; control paints the same
                       operators with the identity mapping. (public)
  F02 covered-text     earlier amount covered by an opaque rectangle and
                       replaced; control paints the final amount once.
                       (public)
  F07 origins-rotation nonzero/negative MediaBox origin and /Rotate
                       90/180/270 at UserUnit 2; control is zero-origin
                       rotation 0 UserUnit 1. (public)
  F08 userunit         UserUnit 0.5/1/2/10 with a 100x100pt fiducial square;
                       UserUnit 1 is the control. (development)
  F03 searchable-scan  owned raster of an original printed page plus a
                       correctly positioned invisible (Tr 3) text layer;
                       raster-only and displaced-layer siblings.
                       (development)

The g78.1 catalog follow-up adds F04/F05/F06/F10/F11/F17/F18/F19/F21
PDF controls and F20 JSON process scenarios. The original recipe version and
all original PDF/expectation bytes remain frozen.

Every written PDF gains a sibling machine-expectation JSON recording
generator intent, control relation and (for the scan family) exact text-layer
anchors. fixtures/manifest.json records the generator source hash, recipe,
rights, split and SHA-256 for every file. Expectations describe intended
structure for later reader comparisons; they are never application input and
no reader output is invented here.

Usage:
  python3 scripts/make_fixtures.py              # (re)generate fixtures/
  python3 scripts/make_fixtures.py --check      # verify tree == regeneration
  python3 scripts/make_fixtures.py --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

GENERATOR_VERSION = "1.0.0"
MANIFEST_SCHEMA = "1.0.0"
RIGHTS = (
    "Original synthetic sample of the Inkflip project, approved under the "
    "project's MIT terms; no embedded font program; no third-party material; "
    "no private or challenge-answer data."
)
# RunLength-encoded raster bytes depend only on this file, so every emitted
# byte is reproducible; nothing here is pinned to one machine or codec build.
BYTE_STABILITY = "byte-identical"

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Minimal deterministic PDF writing (port of planning/probes/make_fixtures.py)
# ---------------------------------------------------------------------------

def pdf(objects: list[bytes], trailer: str = "") -> bytes:
    b = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for n, obj in enumerate(objects, 1):
        offsets.append(len(b))
        b.extend(f"{n} 0 obj\n".encode() + obj + b"\nendobj\n")
    pos = len(b)
    b.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]:
        b.extend(f"{off:010d} 00000 n \n".encode())
    b.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R{trailer} >>\nstartxref\n{pos}\n%%EOF\n".encode()
    )
    return bytes(b)


def stream(data: bytes) -> bytes:
    return f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"


# ---------------------------------------------------------------------------
# Text-page recipe (F01, F02, F07, F08)
# ---------------------------------------------------------------------------

def make(
    amount_map: bool = False,
    covered: bool = False,
    covered_control: bool = False,
    rotation: int = 0,
    unit: float = 1,
    origin: bool = False,
    fiducial: bool = False,
) -> bytes:
    head = (
        b"BT /F0 16 Tf 48 352 Td (SYNTHETIC EXAMPLE) Tj ET\n"
        b"BT /F0 12 Tf 48 320 Td (No real transaction. Reader behavior only.) Tj ET\n"
    )
    body = head + b"BT /F1 48 Tf 48 220 Td ($100) Tj ET\n"
    if covered:
        body = (
            head
            + b"BT /F0 48 Tf 48 220 Td ($1,000) Tj ET\n"
            + b"1 1 1 rg 44 208 220 62 re f\n"
            + b"0 0 0 rg BT /F0 48 Tf 48 220 Td ($100) Tj ET\n"
        )
    elif covered_control:
        body = head + b"BT /F0 48 Tf 48 220 Td ($100) Tj ET\n"
    if fiducial:
        body += b"0.5 w 372 250 100 100 re S\n"
    body += b"BT /F0 12 Tf 48 130 Td (Rendered marks and extracted text are separate.) Tj ET\n"
    cmap = (
        b"/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        b"/CMapName /InkflipExample def\n/CMapType 2 def\n1 begincodespacerange\n"
        b"<00> <FF>\nendcodespacerange\n3 beginbfchar\n<24> <0024>\n<30> <0030>\n<31> "
        + (b"<0031002C0030>" if amount_map else b"<0031>")
        + b"\nendbfchar\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    )
    boxes = (
        "/MediaBox [0 0 520 400] /CropBox [0 0 520 400]"
        if not origin
        else "/MediaBox [-20 -30 520 420] /CropBox [20 40 500 390]"
    )
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R {boxes} /Rotate {rotation} /UserUnit {unit} "
            "/Resources << /Font << /F0 4 0 R /F1 6 0 R >> >> /Contents 5 0 R >>".encode()
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        stream(body),
        (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding /ToUnicode 7 0 R >>"
        ),
        stream(cmap),
    ]
    return pdf(objs)


# ---------------------------------------------------------------------------
# Searchable-scan recipe (F03): owned bitmap print + invisible text layer
# ---------------------------------------------------------------------------

# Original 5x7 bitmap glyph table drawn for this generator (rows top to
# bottom, bit 4 = leftmost column). No font resource is embedded in any PDF.
BITMAP_FONT = {
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "B": (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    "C": (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E),
    "D": (0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "F": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    "G": (0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F),
    "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "I": (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "J": (0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C),
    "K": (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11),
    "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11),
    "N": (0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11),
    "O": (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "P": (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    "Q": (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D),
    "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "S": (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "U": (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "V": (0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A),
    "X": (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    "Y": (0x11, 0x11, 0x11, 0x0A, 0x04, 0x04, 0x04),
    "Z": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    "3": (0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    "5": (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    "6": (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    "$": (0x04, 0x0F, 0x14, 0x0E, 0x05, 0x1E, 0x04),
    ".": (0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C),
    "-": (0x00, 0x00, 0x00, 0x0E, 0x00, 0x00, 0x00),
    " ": (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
}

SCAN_WIDTH = 680
SCAN_HEIGHT = 880
SCAN_SCALE = 3  # glyph cell is 15x21 px; one char advances 18 px, a line 30 px
SCAN_CHAR_PITCH = 6 * SCAN_SCALE
SCAN_LINE_PITCH = 10 * SCAN_SCALE
SCAN_MARGIN_X = 60
SCAN_FIRST_TOP = 100
SCAN_PAGE_W = 612.0  # US Letter; 612/680 == 792/880 == 0.9 exactly
SCAN_PAGE_H = 792.0
SCAN_PT_PER_PX = SCAN_PAGE_W / SCAN_WIDTH  # 0.9
SCAN_FONT_SIZE = 26  # 21 px cap band * 0.9 pt/px ~ Helvetica cap height at 26 pt
SCAN_SHIFT = (90.0, 72.0)  # displaced-layer sibling offset in points

SCAN_LINES = [
    "QUARTERLY SUMMARY",
    "INVOICE 2026-0417",
    "AMOUNT DUE $100.00",
    "ISSUED 2026-09-01",
    "PAGE 1 OF 1",
]


def scan_layout() -> list[dict]:
    """Word anchors shared by the bitmap print and the invisible text layer.

    Coordinates are derived once so the raster and the layer are correct by
    construction: (x_px, top_px) locate each word's first glyph column/row in
    the raster; x_pt/y_pt are the PDF text-layer anchor of the same word's
    left/baseline in page points.
    """
    words = []
    for line_index, line in enumerate(SCAN_LINES):
        top_px = SCAN_FIRST_TOP + line_index * SCAN_LINE_PITCH
        for run_index, word in enumerate(line.split(" ")):
            char_index = sum(len(w) + 1 for w in line.split(" ")[:run_index])
            x_px = SCAN_MARGIN_X + char_index * SCAN_CHAR_PITCH
            baseline_px = top_px + 7 * SCAN_SCALE  # bottom ink row of the glyphs
            words.append(
                {
                    "line": line_index,
                    "word": word,
                    "x_px": x_px,
                    "top_px": top_px,
                    "x_pt": round(x_px * SCAN_PT_PER_PX, 2),
                    "y_pt": round(
                        (SCAN_HEIGHT - baseline_px - 3) * (SCAN_PAGE_H / SCAN_HEIGHT), 2
                    ),
                }
            )
    return words


def _draw_raster() -> bytearray:
    buf = bytearray(b"\xff" * (SCAN_WIDTH * SCAN_HEIGHT))
    for word in scan_layout():
        cursor_px = word["x_px"]
        for ch in word["word"]:
            glyph = BITMAP_FONT[ch]
            for row in range(7):
                bits = glyph[row]
                for col in range(5):
                    if bits & (0x10 >> col):
                        x0 = cursor_px + col * SCAN_SCALE
                        y0 = word["top_px"] + row * SCAN_SCALE
                        for dy in range(SCAN_SCALE):
                            offset = (y0 + dy) * SCAN_WIDTH + x0
                            for dx in range(SCAN_SCALE):
                                buf[offset + dx] = 0
            cursor_px += SCAN_CHAR_PITCH
    return buf


def runlength_encode(data: bytes) -> bytes:
    """PDF RunLength filter encoding (deterministic, decoder-free)."""
    out = bytearray()
    i, n = 0, len(data)
    literals = bytearray()

    def flush() -> None:
        for start in range(0, len(literals), 128):
            chunk = literals[start : start + 128]
            out.append(len(chunk) - 1)
            out.extend(chunk)
        literals.clear()

    while i < n:
        run = 1
        while i + run < n and data[i + run] == data[i] and run < 127:
            run += 1
        if run >= 3:
            flush()
            out.append(257 - run)
            out.append(data[i])
            i += run
        else:
            literals.extend(data[i : i + run])
            i += run
    flush()
    out.append(128)
    return bytes(out)


def layer_words(layer: str) -> list[dict]:
    """Emitted text-layer anchors for one F03 sibling ('correct', 'raster-only'
    or 'shifted'). Each word is placed with an absolute text matrix, so the
    recorded x_pt/y_pt are exactly the positions a reader reports."""
    if layer == "correct":
        return scan_layout()
    if layer == "shifted":
        return [
            {
                **w,
                "x_pt": round(w["x_pt"] + SCAN_SHIFT[0], 2),
                "y_pt": round(w["y_pt"] + SCAN_SHIFT[1], 2),
            }
            for w in scan_layout()
        ]
    return []


def scan_pdf(layer: str) -> bytes:
    """Build one F03 sibling: layer is 'correct', 'raster-only' or 'shifted'."""
    raster = runlength_encode(bytes(_draw_raster()))
    layout = layer_words(layer)
    image = (
        f"<< /Type /XObject /Subtype /Image /Width {SCAN_WIDTH} /Height {SCAN_HEIGHT} "
        "/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /RunLengthDecode /Length "
        f"{len(raster)} >>\nstream\n".encode()
        + raster
        + b"\nendstream"
    )
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    content = f"q {SCAN_PAGE_W:g} 0 0 {SCAN_PAGE_H:g} 0 0 cm /Im0 Do Q\n".encode()
    if layout:
        content += b"BT /F0 26 Tf 3 Tr\n"
        for w in layout:
            content += f"1 0 0 1 {w['x_pt']:g} {w['y_pt']:g} Tm ({w['word']}) Tj\n".encode()
        content += b"ET\n"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject "
            "<< /Im0 4 0 R >> /Font << /F0 5 0 R >> >> /Contents 6 0 R >>".encode()
        ),
        image,
        font,
        stream(content),
    ]
    return pdf(objs)


# ---------------------------------------------------------------------------
# Recipes, expectations and manifest
# ---------------------------------------------------------------------------

def recipes() -> list[dict]:
    """One entry per emitted PDF, in fixed emission order."""

    def entry(name: str, split: str, fixture_id: str, family: str, control: str | None,
              recipe: dict, observation: str, extra: dict | None = None) -> dict:
        base = {
            "name": name,
            "split": split,
            "fixture_id": fixture_id,
            "family": family,
            "control": control,
            "recipe": recipe,
            "observation": observation,
        }
        if extra:
            base.update(extra)
        return base

    geometry = {"rotation": None, "unit": 2, "origin": True}
    entries = [
        entry("public/mapping-amount.pdf", "public", "F01", "mapping-amount",
              "public/mapping-control.pdf", {"amount_map": True},
              "native text differs from identical raster",
              {"painted": "$100", "extraction_intent": "$1,000"}),
        entry("public/mapping-control.pdf", "public", "F01", "mapping-amount", None,
              {"amount_map": False},
              "identity mapping control; renders and extracts $100",
              {"painted": "$100", "extraction_intent": "$100"}),
        entry("public/covered-amount.pdf", "public", "F02", "covered-text",
              "public/covered-control.pdf", {"covered": True},
              "actual extraction kept, mechanism limited; reader-dependent "
              "concatenation is retained as observed behavior",
              {"paint_order": ["$1,000", "white cover rect", "$100"],
               "known_reader_observations": [
                   {"reader": "PDFium", "output": "$1,00000",
                    "source": "planning/product/DEMO_AND_GALLERY.md (planning environment, 2026-09)"},
                   {"reader": "pypdf", "output": "$1,000$100",
                    "source": "planning/product/DEMO_AND_GALLERY.md (planning environment, 2026-09)"},
               ]}),
        entry("public/covered-control.pdf", "public", "F02", "covered-text", None,
              {"covered_control": True},
              "clean twin: final visible amount painted once, never covered",
              {"painted": "$100", "extraction_intent": "$100"}),
    ]
    for rotation in (0, 90, 180, 270):
        entries.append(
            entry(f"public/geometry-{rotation}.pdf", "public", "F07", "origins-rotation",
                  "public/geometry-control.pdf", {**geometry, "rotation": rotation},
                  "transforms and actual pixel anchors through nonzero/negative origins, "
                  "rotation and UserUnit 2")
        )
    entries.append(
        entry("public/geometry-control.pdf", "public", "F07", "origins-rotation", None,
              {"rotation": 0, "unit": 1, "origin": False},
              "zero-origin rotation 0 UserUnit 1 control")
    )
    for unit in (0.5, 1, 2, 10):
        entries.append(
            entry(f"development/userunit-{unit:g}.pdf", "development", "F08", "userunit",
                  None if unit == 1 else "development/userunit-1.pdf",
                  {"unit": unit, "fiducial": "100x100pt stroke square at 372 250"},
                  "no double scaling; physical-size equivalents with known fiducials")
        )
    for layer in ("correct", "raster-only", "shifted"):
        observation = {
            "correct": "legitimate searchable scan: invisible layer matches the raster "
                       "words and anchors; no alarm solely because its OCR text is invisible",
            "raster-only": "clean sibling with no text layer at all",
            "shifted": "deliberately displaced layer; layer words do not match raster "
                       "word anchors",
        }[layer]
        entries.append(
            entry(f"development/scan-{layer}.pdf", "development", "F03", "searchable-scan",
                  "development/scan-raster-only.pdf" if layer == "correct" else None,
                  {"layer": layer, "raster": "owned 5x7 bitmap print, 680x880 gray",
                   "shift_pt": list(SCAN_SHIFT) if layer == "shifted" else None},
                  observation)
        )
    return entries


def expectation_for(entry: dict) -> dict:
    exp = {
        "fixture_id": entry["fixture_id"],
        "family": entry["family"],
        "mechanism": entry["recipe"],
        "observation": entry["observation"],
        "control": entry["control"],
        "split": entry["split"],
        "byte_stability": BYTE_STABILITY,
        "rights": RIGHTS,
        "generator": "scripts/make_fixtures.py",
        "generator_version": GENERATOR_VERSION,
    }
    for key in ("painted", "extraction_intent", "paint_order", "known_reader_observations"):
        if key in entry:
            exp[key] = entry[key]
    if entry["family"] == "searchable-scan":
        layer = entry["recipe"]["layer"]
        exp["raster"] = {
            "width_px": SCAN_WIDTH,
            "height_px": SCAN_HEIGHT,
            "colorspace": "DeviceGray",
            "bits_per_component": 8,
            "filter": "RunLengthDecode",
            "lines": SCAN_LINES,
            "font": "generated 5x7 bitmap table; no PDF font resource",
        }
        exp["text_layer"] = {
            "mode": "invisible Tr 3" if layer != "raster-only" else "absent",
            "font": "Helvetica base-14 (no program embedded)",
            "font_size_pt": SCAN_FONT_SIZE,
            "words": [
                {k: w[k] for k in ("word", "line", "x_pt", "y_pt")}
                for w in layer_words(layer)
            ],
            "displacement_pt": list(SCAN_SHIFT) if layer == "shifted" else None,
        }
    return exp


# Catalog follow-up recipes are independent of the frozen original five families.
# Payloads may be PDF or JSON: F20 is a process/event fixture, not a fake PDF.
def fixed_page(body: bytes, box: str = "0 0 320 240") -> list[bytes]:
    return [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [{box}] "
         "/Resources << /Font << /F0 4 0 R >> >> /Contents 5 0 R >>").encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        stream(body),
    ]


def fixed_text(value: str = "$100", matrix: str = "1 0 0 1 48 120") -> bytes:
    return f"BT /F0 24 Tf {matrix} Tm ({value}) Tj ET\n".encode("ascii")


def rc4(key: bytes, data: bytes) -> bytes:
    """Original bounded R2 fixture cipher; never used for application security."""
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) % 256
        state[i], state[j] = state[j], state[i]
    out = bytearray()
    i = j = 0
    for value in data:
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        out.append(value ^ state[(state[i] + state[j]) % 256])
    return bytes(out)


def encrypted_page() -> bytes:
    """PDF 1.7 algorithms 3.1–3.5, revision 2; fixed harmless unlock 'fixture'."""
    pad = bytes.fromhex("28bf4e5e4e758a4164004e56fffa01082e2e00b6d0683e802f0ca9fe6453697a")
    user = (b"fixture" + pad)[:32]
    owner_key = hashlib.md5((b"fixture-owner" + pad)[:32]).digest()[:5]
    owner = rc4(owner_key, user)
    ident = hashlib.md5(b"Inkflip original bounded encryption fixture").digest()
    permissions = (-4).to_bytes(4, "little", signed=True)
    key = hashlib.md5(user + owner + permissions + ident).digest()[:5]
    obj_key = hashlib.md5(key + b"\x05\x00\x00\x00\x00").digest()[:10]
    objects = fixed_page(fixed_text())
    objects[4] = stream(rc4(obj_key, fixed_text()))
    objects.append(("<< /Filter /Standard /V 1 /R 2 /Length 40 /P -4 "
                    f"/O <{owner.hex()}> /U <{rc4(key, pad).hex()}> >>").encode())
    return pdf(objects, f" /Encrypt 6 0 R /ID [<{ident.hex()}> <{ident.hex()}>]")


def raster_page(pixels: bytes, width: int, height: int) -> bytes:
    encoded = runlength_encode(pixels)
    objects = fixed_page(b"q 272 0 0 160 24 40 cm /Im0 Do Q\n")
    objects[2] = objects[2].replace(b"/Font <<", b"/XObject << /Im0 6 0 R >> /Font <<")
    objects.append((f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                    "/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /RunLengthDecode "
                    f"/Length {len(encoded)} >>\nstream\n").encode() + encoded + b"\nendstream")
    return pdf(objects)


def catalog_entry(fid: str, variant: str, payload: bytes, intent: dict,
                  extension: str = "pdf") -> dict:
    catalog = json.loads((ROOT / "planning/quality/fixture-catalog.json").read_text())
    family = next(item for item in catalog if item["id"] == fid)
    split = {"public_demo": "public", "development": "development"}[family["split"]]
    stem = f"{split}/{family['family']}"
    return {
        "name": f"{stem}-{variant}.{extension}", "fixture_id": fid,
        "family": family["family"], "split": split,
        "control": None if variant == "control" else f"{stem}-control.{extension}",
        "recipe": {"version": "g78.1", "group_id": fid, "variant": variant, "intent": intent},
        "observation": family["expected_invariant"], "payload": payload,
    }


def json_payload(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def structural_entries() -> list[dict]:
    text = fixed_text()
    white = b"1 1 1 rg\n" + text
    dark = b"0 0 0 rg 24 96 200 60 re f\n"
    cover = b"1 1 1 rg 24 96 200 60 re f\n"
    triangle = b"q 48 110 m 108 150 l 168 110 l h W n\n" + text + b"Q\n"
    definitions = [
        ("F04", "control", dark + white, {"visible": "$100", "contrast": "white on black"}),
        ("F04", "white", white, {"visible": "", "contrast": "white on white", "native_intent": "$100"}),
        ("F05", "control", cover + b"0 0 0 rg\n" + text, {"order": ["fill", "text"]}),
        ("F05", "after", text + cover, {"order": ["text", "fill"]}),
        ("F06", "control", text, {"visibility": "full"}),
        ("F06", "partial", text + b"1 1 1 rg 78 110 24 36 re f\n", {"visibility": "partial cover", "cover": [78, 110, 24, 36]}),
        ("F06", "triangle", triangle, {"visibility": "nonrectangular clip; bounding-box approximation insufficient"}),
        ("F11", "control", text, {"occurrences": [[48, 120]], "text": "$100"}),
        ("F11", "four", b"".join(fixed_text(matrix=f"1 0 0 1 {x} {y}") for x, y in [(48, 180), (200, 180), (48, 60), (200, 60)]),
         {"occurrences": [[48, 180], [200, 180], [48, 60], [200, 60]], "text": "$100"}),
    ]
    return [catalog_entry(fid, variant, pdf(fixed_page(body)), intent)
            for fid, variant, body, intent in definitions]


def missing_map_entries() -> list[dict]:
    # Keep all painted glyphs identical; only the Unicode map changes.
    cmap = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            b"/CMapName /Owned def /CMapType 2 def\n"
            b"1 begincodespacerange <00> <FF> endcodespacerange\n"
            b"3 beginbfchar <24> <0024> <31> <0031> <30> <0030> endbfchar\n"
            b"endcmap CMapName currentdict /CMap defineresource pop end end\n")
    result = []
    for variant, mapping in [("control", cmap), ("absent", None), ("malformed", b"begincmap 1 beginbfchar <31> <ZZZZ> endbfchar endcmap\n")]:
        objects = fixed_page(fixed_text())
        if mapping is not None:
            objects[3] = objects[3].replace(b" >>", b" /ToUnicode 6 0 R >>")
            objects.append(stream(mapping))
        result.append(catalog_entry("F10", variant, pdf(objects),
                      {"painted": "$100", "mapping": variant,
                       "raw_output": "record reader API verbatim, including fallback or failure"}))
    return result


def failure_entries() -> list[dict]:
    valid = pdf(fixed_page(fixed_text()))
    noise = bytes(0 if ((i * 73 + i // 128 * 19) % 17) < 8 else 255 for i in range(128 * 64))
    return [
        catalog_entry("F17", "control", scan_pdf("raster-only"), {"raster_text": SCAN_LINES}),
        catalog_entry("F17", "blank", raster_page(bytes([255]) * 8192, 128, 64), {"raster_text": None, "region": "blank; no default value"}),
        catalog_entry("F17", "noise", raster_page(noise, 128, 64), {"raster_text": None, "region": "unreadable deterministic pattern"}),
        catalog_entry("F18", "control", valid, {"load": "valid"}),
        catalog_entry("F18", "encrypted", encrypted_page(), {"load": "locked without credential", "test_credential": "fixture", "encryption": "Standard R2 RC4-40; synthetic only"}),
        catalog_entry("F18", "truncated", valid[:80], {"load": "incomplete header/page tree; failure"}),
        catalog_entry("F18", "malformed", pdf([b"<< /Type /Catalog /Pages 2 0 R >>", b"null"]), {"load": "invalid page tree; reader-specific failure, never all-clear"}),
        catalog_entry("F19", "control", valid, {"box": [0, 0, 320, 240], "render_max_edge": 512}),
        catalog_entry("F19", "extreme", pdf(fixed_page(fixed_text(), "0 0 1000000000 1000000000")),
                      {"box": [0, 0, 1000000000, 1000000000], "render_max_edge": 512,
                       "unbounded_render_forbidden": True, "requested_pixels_at_72dpi": 1000000000000000000}),
    ]


def fault_entries() -> list[dict]:
    result = []
    # Consumers drive these fake process scenarios under their own supervisor.
    # No engine/model initializes; the reusable executable double lives in tests.
    for variant in ("control", "model-failure", "crash", "hang", "cancel", "stale"):
        scenario = {"scenario": variant, "max_wall_ms": 1000, "generation": 2,
                    "preserved_result": {"job": "completed-first", "text": "$100"},
                    "events": [{"generation": 2, "job": "completed-first", "state": "completed"}]}
        terminal = {"control": "completed", "model-failure": "failed", "crash": "failed",
                    "hang": "timed_out", "cancel": "cancelled", "stale": "completed"}[variant]
        scenario["expected_terminal"] = terminal
        result.append(catalog_entry("F20", variant, json_payload(scenario),
                                    {"kind": "bounded fake process/event input", "terminal": terminal}, "json"))
    return result


def canary_entries() -> list[dict]:
    # Marker channels are distinct; source digest is derived after PDF generation.
    body = fixed_text("INKFLIP-CANARY-TEXT-7B2").replace(b"24 Tf", b"12 Tf")
    objects = fixed_page(body)
    objects[0] = objects[0].replace(b" >>", b" /Metadata 6 0 R >>")
    objects[2] = objects[2].replace(b" /Contents", b" /Annots [7 0 R] /Contents")
    metadata = b'<canary>INKFLIP-CANARY-METADATA-8C3</canary>'
    objects.append(stream(metadata).replace(b"<< /Length", b"<< /Type /Metadata /Subtype /XML /Length"))
    objects.append(b"<< /Type /Annot /Subtype /Text /Rect [20 20 40 40] /Contents (INKFLIP-CANARY-ANNOTATION-9D4) >>")
    payload = pdf(objects)
    return [
        catalog_entry("F21", "control", pdf(fixed_page(b"")), {"actions": "same local actions with no document content", "egress": "none"}),
        catalog_entry("F21", "channels", payload,
                      {"egress": "none", "storage": "no document-derived persistence",
                       "channels": {"text": "INKFLIP-CANARY-TEXT-7B2", "metadata": "INKFLIP-CANARY-METADATA-8C3",
                                    "annotation": "INKFLIP-CANARY-ANNOTATION-9D4", "filename": "network-canary-channels.pdf",
                                    "hash": hashlib.sha256(payload).hexdigest(),
                                    "crop": "rendered text marker pixels", "report": "actual report containing text marker"}}),
    ]


def followup_entries() -> list[dict]:
    return structural_entries() + missing_map_entries() + failure_entries() + fault_entries() + canary_entries()


def entry_payload(entry: dict) -> bytes:
    if "payload" in entry:
        return entry["payload"]
    recipe = dict(entry["recipe"])
    wants_fiducial = "fiducial" in recipe
    recipe.pop("fiducial", None)
    if entry["family"] == "searchable-scan":
        return scan_pdf(recipe["layer"])
    return make(fiducial=wants_fiducial, **recipe)


def build_tree() -> dict[str, bytes]:
    """Return every generated file keyed by its path under fixtures/."""
    files: dict[str, bytes] = {}
    entries = []
    generator_sha = hashlib.sha256((ROOT / "scripts/make_fixtures.py").read_bytes()).hexdigest()
    for entry in recipes() + followup_entries():
        data = entry_payload(entry)
        name = entry["name"]
        files[name] = data
        expect_name = str(Path(name).with_suffix(".expect.json"))
        expect = expectation_for(entry)
        files[expect_name] = (json.dumps(expect, indent=2, sort_keys=True) + "\n").encode()
        manifest_entry = {
            "path": name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "expectations": expect_name,
            "expectations_sha256": hashlib.sha256(files[expect_name]).hexdigest(),
            "fixture_id": entry["fixture_id"],
            "family": entry["family"],
            "split": entry["split"],
            "control": entry["control"],
            "recipe": entry["recipe"],
            "rights": RIGHTS,
            "byte_stability": BYTE_STABILITY,
            "observation": entry["observation"],
        }
        entries.append(manifest_entry)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "generator": "scripts/make_fixtures.py",
        "generator_version": GENERATOR_VERSION,
        "generator_sha256": generator_sha,
        "catalog_sha256": hashlib.sha256((ROOT / "planning/quality/fixture-catalog.json").read_bytes()).hexdigest(),
        "seed": "none; recipes are fully deterministic",
        "determinism": "byte-identical on every platform; no timestamps or random IDs",
        "rights": RIGHTS,
        "entries": entries,
    }
    files["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    return files


def write_tree(out: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def check(out: Path) -> int:
    """Verify the on-disk tree equals a fresh deterministic regeneration."""
    files = build_tree()
    problems = []
    for name, data in sorted(files.items()):
        target = out / name
        if not target.is_file():
            problems.append(f"missing: {name}")
        elif target.read_bytes() != data:
            problems.append(f"differs from regeneration: {name}")
    for path in sorted(out.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(out).as_posix()
        if "__pycache__" in rel.split("/") or rel.endswith((".DS_Store", ".pyc")):
            continue
        if rel not in files:
            problems.append(f"unexpected file not produced by this generator: {rel}")
    if problems:
        for problem in problems:
            print(f"CHECK FAIL: {problem}")
        return 1
    print(f"check ok: {len(files)} files in {out} match deterministic regeneration")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "fixtures",
                        help="output directory (default: fixtures/)")
    parser.add_argument("--check", action="store_true",
                        help="verify the existing tree equals a fresh regeneration")
    args = parser.parse_args()
    if args.check:
        return check(args.out)
    files = build_tree()
    write_tree(args.out, files)
    print(f"generated {len(files)} files under {args.out}")
    return 0


if __name__ == "__main__":
    sys_exit_code = main()
    raise SystemExit(sys_exit_code)
