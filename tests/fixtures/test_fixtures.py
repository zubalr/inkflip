"""TEST-05 fixture contract suite (T05).

Verifies the committed fixtures against the generator contract by parsing the
PDF bytes directly (stdlib only, no PDF library): determinism, mechanism
structure, control relations, rights and manifest integrity. Expectation
files describe generator intent for later reader comparisons; this suite
checks structure, not invented reader output.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
GENERATOR = ROOT / "scripts" / "make_fixtures.py"
REGISTRY = ROOT / "config" / "acceptance-commands.json"

CATALOG = json.loads((ROOT / "planning/quality/fixture-catalog.json").read_text())
EXPECTED_SPLITS = {e["id"]: e["split"].replace("public_demo", "public") for e in CATALOG}
EXPECTED_FAMILIES = {
    e["id"]: e["family"] for e in CATALOG
    if e["id"] in {"F01", "F02", "F03", "F07", "F08", "F04", "F05", "F06", "F10", "F11", "F17", "F18", "F19", "F20", "F21"}
}
PRIVATE_MARKERS = (
    b"begin private key",
    b"begin rsa private key",
    b"password",
    b"secret",
    b"flag{",
    b"ctf{",
)


def load_generator():
    spec = importlib.util.spec_from_file_location("inkflip_make_fixtures", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_generator(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *args],
        capture_output=True, text=True, cwd=ROOT, timeout=300,
    )


def pdf_objects(data: bytes) -> dict[int, bytes]:
    return {
        int(m.group(1)): m.group(2)
        for m in re.finditer(rb"(\d+) 0 obj\n(.*?)\nendobj\n", data, re.S)
    }


def stream_bytes(obj: bytes) -> bytes:
    declared = int(re.search(rb"/Length (\d+)", obj).group(1))
    body = re.search(rb"stream\n(.*?)\nendstream", obj, re.S).group(1)
    if len(body) != declared:
        raise AssertionError(f"/Length {declared} != actual stream length {len(body)}")
    return body


def page_of(data: bytes) -> tuple[dict[int, bytes], bytes]:
    objs = pdf_objects(data)
    page = next(o for o in objs.values() if b"/Type /Page" in o and b"/Pages" not in o)
    return objs, page


def content_of(data: bytes) -> bytes:
    objs, page = page_of(data)
    number = int(re.search(rb"/Contents (\d+) 0 R", page).group(1))
    return stream_bytes(objs[number])


def rle_decode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while True:
        n = data[i]
        i += 1
        if n == 128:
            break
        if n < 128:
            out.extend(data[i : i + n + 1])
            i += n + 1
        else:
            out.extend(bytes([data[i]]) * (257 - n))
            i += 1
    return bytes(out)


def manifest() -> dict:
    return json.loads((FIXTURES / "manifest.json").read_text())


def expectation(rel_path: str) -> dict:
    return json.loads((FIXTURES / rel_path).read_text())


def all_pdfs() -> list[Path]:
    return sorted(FIXTURES.rglob("*.pdf"))


def raster_of(data: bytes) -> tuple[bytes, int, int]:
    objs, page = page_of(data)
    number = int(re.search(rb"/Im0 (\d+) 0 R", page).group(1))
    img = objs[number]
    width = int(re.search(rb"/Width (\d+)", img).group(1))
    height = int(re.search(rb"/Height (\d+)", img).group(1))
    return rle_decode(stream_bytes(img)), width, height


def tm_words(content: bytes) -> list[tuple[float, float, str]]:
    found = re.findall(rb"1 0 0 1 ([\d.]+) ([\d.]+) Tm \(([^)]+)\) Tj", content)
    return [(float(x), float(y), text.decode("ascii")) for x, y, text in found]


class TestDeterminism(unittest.TestCase):
    """Criterion: repeated generation is byte-identical."""

    def test_two_regenerations_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a", Path(tmp) / "b"
            self.assertEqual(run_generator("--out", str(first)).returncode, 0)
            self.assertEqual(run_generator("--out", str(second)).returncode, 0)
            first_files = {p.relative_to(first).as_posix(): p.read_bytes() for p in first.rglob("*") if p.is_file()}
            second_files = {p.relative_to(second).as_posix(): p.read_bytes() for p in second.rglob("*") if p.is_file()}
            self.assertEqual(first_files, second_files)

    def test_check_mode_passes_on_committed_tree(self):
        result = run_generator("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_mode_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "fixtures"
            shutil.copytree(FIXTURES, copy)
            target = copy / "public" / "mapping-control.pdf"
            data = bytearray(target.read_bytes())
            data[-40] ^= 0x01
            target.write_bytes(bytes(data))
            result = run_generator("--check", "--out", str(copy))
            self.assertEqual(result.returncode, 1)
            self.assertIn("CHECK FAIL", result.stdout)

    def test_manifest_declares_determinism_without_seed_or_timestamp(self):
        data = manifest()
        self.assertIn("byte-identical", data["determinism"])
        self.assertIn("deterministic", data["seed"])


class TestMappingControl(unittest.TestCase):
    """F01: mapping/control render equal, actual extraction differs."""

    def test_paint_operators_are_identical(self):
        # Identical content streams plus identical non-CMap objects mean any
        # correct renderer in the same environment paints equal marks; the
        # pixel-level confirmation runs with the real readers (T26, G1).
        mapping = content_of((FIXTURES / "public/mapping-amount.pdf").read_bytes())
        control = content_of((FIXTURES / "public/mapping-control.pdf").read_bytes())
        self.assertEqual(mapping, control)
        self.assertIn(b"($100) Tj", mapping)

    def test_tounicode_differs_exactly_at_amount_glyph(self):
        def cmap_body(name: str) -> bytes:
            data = (FIXTURES / "public" / name).read_bytes()
            objs, _ = page_of(data)
            for obj in objs.values():
                if b"begincmap" in obj:
                    return stream_bytes(obj)
            raise AssertionError("no ToUnicode CMap stream")

        mapping, control = cmap_body("mapping-amount.pdf"), cmap_body("mapping-control.pdf")
        self.assertEqual(mapping.replace(b"<0031002C0030>", b"<0031>"), control)
        self.assertIn(b"<31> <0031002C0030>", mapping)
        self.assertIn(b"<31> <0031>", control)

    def test_extraction_intent_differs_while_painting_matches(self):
        mapping = expectation("public/mapping-amount.expect.json")
        control = expectation("public/mapping-control.expect.json")
        self.assertEqual(mapping["painted"], "$100")
        self.assertEqual(control["painted"], "$100")
        self.assertEqual(mapping["extraction_intent"], "$1,000")
        self.assertEqual(control["extraction_intent"], "$100")

    def test_observation_declares_text_raster_divergence(self):
        entry = next(e for e in manifest()["entries"] if e["path"] == "public/mapping-amount.pdf")
        self.assertIn("native text differs from identical raster", entry["observation"])


class TestCoveredText(unittest.TestCase):
    """F02: covered amount versus uncovered clean twin."""

    def test_cover_paint_order_is_text_cover_replacement(self):
        content = content_of((FIXTURES / "public/covered-amount.pdf").read_bytes())
        first = content.index(b"($1,000) Tj")
        cover = content.index(b"1 1 1 rg 44 208 220 62 re f")
        second = content.index(b"($100) Tj")
        self.assertLess(first, cover)
        self.assertLess(cover, second)

    def test_control_paints_final_amount_once(self):
        content = content_of((FIXTURES / "public/covered-control.pdf").read_bytes())
        self.assertEqual(content.count(b"Tj"), 4)  # header, notice, $100, footer
        self.assertIn(b"($100) Tj", content)
        self.assertNotIn(b"re f", content)
        self.assertNotIn(b"($1,000) Tj", content)

    def test_cover_is_opaque_white_fill(self):
        content = content_of((FIXTURES / "public/covered-amount.pdf").read_bytes())
        self.assertIn(b"1 1 1 rg", content)

    def test_known_reader_observations_are_labeled_not_invented(self):
        exp = expectation("public/covered-amount.expect.json")
        sources = [o["source"] for o in exp["known_reader_observations"]]
        self.assertTrue(sources)
        for source in sources:
            self.assertIn("planning/product/DEMO_AND_GALLERY.md", source)


class TestGeometryFamily(unittest.TestCase):
    """F07: nonzero/negative origins, all rotations, zero-origin control."""

    def test_all_rotations_present_with_negative_origin_and_userunit_two(self):
        for rotation in (0, 90, 180, 270):
            _, page = page_of((FIXTURES / f"public/geometry-{rotation}.pdf").read_bytes())
            self.assertIn(f"/Rotate {rotation}".encode(), page, f"rotation {rotation}")
            self.assertIn(b"/UserUnit 2", page)
            self.assertIn(b"/MediaBox [-20 -30 520 420]", page)
            self.assertIn(b"/CropBox [20 40 500 390]", page)

    def test_rotation_family_shares_identical_content(self):
        streams = {
            rotation: content_of((FIXTURES / f"public/geometry-{rotation}.pdf").read_bytes())
            for rotation in (0, 90, 180, 270)
        }
        self.assertEqual(len(set(streams.values())), 1)

    def test_control_is_zero_origin_rotation_zero_userunit_one(self):
        _, page = page_of((FIXTURES / "public/geometry-control.pdf").read_bytes())
        self.assertIn(b"/Rotate 0", page)
        self.assertIn(b"/UserUnit 1", page)
        self.assertIn(b"/MediaBox [0 0 520 400]", page)


class TestUserUnitFamily(unittest.TestCase):
    """F08: UserUnit 0.5/1/2/10 with a shared 100x100pt fiducial."""

    def test_all_units_declared_with_fiducial_square(self):
        for unit in ("0.5", "1", "2", "10"):
            data = (FIXTURES / f"development/userunit-{unit}.pdf").read_bytes()
            _, page = page_of(data)
            self.assertIn(f"/UserUnit {unit}".encode(), page, f"UserUnit {unit}")
            content = content_of(data)
            self.assertIn(b"372 250 100 100 re S", content, f"fiducial at {unit}")

    def test_family_shares_identical_fiducial_content(self):
        streams = tuple(
            content_of((FIXTURES / f"development/userunit-{unit}.pdf").read_bytes())
            for unit in ("0.5", "1", "2", "10")
        )
        self.assertEqual(len(set(streams)), 1)

    def test_unit_one_is_the_manifest_control(self):
        entries = {e["path"]: e for e in manifest()["entries"]}
        self.assertIsNone(entries["development/userunit-1.pdf"]["control"])
        for unit in ("0.5", "2", "10"):
            self.assertEqual(
                entries[f"development/userunit-{unit}.pdf"]["control"],
                "development/userunit-1.pdf",
            )


class TestSearchableScan(unittest.TestCase):
    """F03: legitimate scan, correct invisible layer, raster-only and shifted."""

    def test_raster_only_sibling_has_no_text_operators(self):
        content = content_of((FIXTURES / "development/scan-raster-only.pdf").read_bytes())
        self.assertIn(b"/Im0 Do", content)
        for operator in (b"Tj", b"TJ", b"Tm", b"Tr", b"BT"):
            self.assertNotIn(operator, content, f"unexpected text operator {operator}")

    def test_correct_layer_is_invisible_and_matches_expectation(self):
        data = (FIXTURES / "development/scan-correct.pdf").read_bytes()
        content = content_of(data)
        self.assertIn(b"3 Tr", content)
        emitted = tm_words(content)
        recorded = expectation("development/scan-correct.expect.json")["text_layer"]["words"]
        self.assertEqual(len(emitted), len(recorded))
        for (x, y, word), record in zip(emitted, recorded):
            self.assertEqual(word, record["word"])
            self.assertEqual(x, record["x_pt"])
            self.assertEqual(y, record["y_pt"])

    def test_layer_words_are_exactly_the_raster_words_in_order(self):
        exp = expectation("development/scan-correct.expect.json")
        lines = exp["raster"]["lines"]
        raster_words = [w for line in lines for w in line.split(" ")]
        layer_words = [w["word"] for w in exp["text_layer"]["words"]]
        self.assertEqual(layer_words, raster_words)

    def test_decoded_raster_equals_generator_drawing(self):
        gen = load_generator()
        data = (FIXTURES / "development/scan-correct.pdf").read_bytes()
        decoded, width, height = raster_of(data)
        self.assertEqual((width, height), (680, 880))
        self.assertEqual(decoded, bytes(gen._draw_raster()))

    def test_word_anchor_boxes_contain_matching_raster_ink(self):
        gen = load_generator()
        raster = bytes(gen._draw_raster())
        width = gen.SCAN_WIDTH
        for word in gen.scan_layout():
            x0, top = word["x_px"], word["top_px"]
            x1 = x0 + len(word["word"]) * gen.SCAN_CHAR_PITCH
            box = (
                raster[(top + dy) * width + x0 + dx]
                for dy in range(21)
                for dx in range(x1 - x0)
            )
            ink = sum(1 for v in box if v == 0)
            self.assertGreater(ink, 20, f"no ink under anchor of {word['word']}")

    def test_shifted_layer_is_displaced_by_declared_offset(self):
        exp = expectation("development/scan-shifted.expect.json")
        correct = expectation("development/scan-correct.expect.json")["text_layer"]["words"]
        dx, dy = exp["text_layer"]["displacement_pt"]
        self.assertEqual([dx, dy], [90.0, 72.0])
        shifted = tm_words(content_of((FIXTURES / "development/scan-shifted.pdf").read_bytes()))
        self.assertEqual(len(shifted), len(correct))
        for (x, y, word), base in zip(shifted, correct):
            self.assertEqual(word, base["word"])
            self.assertAlmostEqual(x, base["x_pt"] + dx)
            self.assertAlmostEqual(y, base["y_pt"] + dy)

    def test_correct_scan_records_no_alarm_intent(self):
        entry = next(e for e in manifest()["entries"] if e["path"] == "development/scan-correct.pdf")
        self.assertIn("no alarm solely because its OCR text is invisible", entry["observation"])

    def test_scan_siblings_share_one_split(self):
        entries = {e["path"]: e for e in manifest()["entries"]}
        splits = {
            entries[f"development/scan-{layer}.pdf"]["split"]
            for layer in ("correct", "raster-only", "shifted")
        }
        self.assertEqual(splits, {"development"})


class TestRightsAndPrivacy(unittest.TestCase):
    """I16: no embedded unlicensed font, no private or challenge-answer data."""

    def test_no_embedded_font_programs_anywhere(self):
        for path in all_pdfs():
            data = path.read_bytes()
            for marker in (b"/FontFile", b"/FontFile2", b"/FontFile3", b"/FontDescriptor"):
                self.assertNotIn(marker, data, f"{path.name} embeds font material")
            for base in re.findall(rb"/BaseFont /(\S+)", data):
                self.assertEqual(base, b"Helvetica", f"{path.name} uses {base!r}")

    def test_no_private_or_challenge_answer_data(self):
        for path in all_pdfs():
            data = path.read_bytes()
            objs = pdf_objects(data)
            decoded = bytes()
            for obj in objs.values():
                if b"stream" in obj:
                    body = re.search(rb"stream\n(.*?)\nendstream", obj, re.S)
                    if body:
                        decoded += body.group(1)
            for marker in PRIVATE_MARKERS:
                self.assertNotIn(marker, decoded.lower(), f"{path.name} contains {marker!r}")
            self.assertNotIn(b"@", decoded, f"{path.name} contains an address-like marker")

    def test_manifest_rights_cover_every_entry(self):
        data = manifest()
        for entry in data["entries"]:
            self.assertIn("MIT", entry["rights"])
            self.assertIn("no embedded font program", entry["rights"])


class TestManifestIntegrity(unittest.TestCase):
    """I13: source identity accompanies every fixture."""

    def test_manifest_hashes_and_lengths_match_disk(self):
        data = manifest()
        for entry in data["entries"]:
            pdf_path = FIXTURES / entry["path"]
            self.assertTrue(pdf_path.is_file(), entry["path"])
            payload = pdf_path.read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), entry["sha256"], entry["path"])
            self.assertEqual(len(payload), entry["bytes"], entry["path"])
            expect_path = FIXTURES / entry["expectations"]
            self.assertEqual(
                hashlib.sha256(expect_path.read_bytes()).hexdigest(),
                entry["expectations_sha256"],
                entry["expectations"],
            )

    def test_generator_hash_matches_source_file(self):
        data = manifest()
        self.assertEqual(
            hashlib.sha256(GENERATOR.read_bytes()).hexdigest(),
            data["generator_sha256"],
        )

    def test_required_fixture_ids_and_families_are_covered(self):
        entries = manifest()["entries"]
        seen = {e["fixture_id"]: e["family"] for e in entries}
        for fixture_id, family in EXPECTED_FAMILIES.items():
            self.assertIn(fixture_id, seen, fixture_id)
            self.assertEqual(seen[fixture_id], family, fixture_id)

    def test_splits_match_catalog(self):
        for entry in manifest()["entries"]:
            self.assertEqual(entry["split"], EXPECTED_SPLITS[entry["fixture_id"]], entry["path"])

    def test_every_mechanism_has_an_existing_control(self):
        entries = {e["path"]: e for e in manifest()["entries"]}
        for entry in entries.values():
            control = entry["control"]
            if control is not None:
                self.assertIn(control, entries, entry["path"])
                self.assertIsNone(entries[control]["control"], f"control {control} is not clean")
                self.assertEqual(entries[control]["split"], entry["split"], entry["path"])

    def test_expectation_files_bind_to_their_fixture(self):
        for entry in manifest()["entries"]:
            exp = expectation(entry["expectations"])
            self.assertEqual(exp["fixture_id"], entry["fixture_id"], entry["path"])
            self.assertEqual(exp["control"], entry["control"], entry["path"])


class TestNoFilenameConditioning(unittest.TestCase):
    """Criterion: no filename-conditioned app output is possible or encoded."""

    def test_filename_appears_nowhere_in_fixture_bytes(self):
        for path in all_pdfs():
            data = path.read_bytes()
            self.assertNotIn(path.stem.encode(), data, path.name)
            self.assertNotIn(path.name.encode(), data, path.name)

    def test_renamed_copy_is_byte_identical_and_content_addressed(self):
        source = FIXTURES / "public" / "mapping-amount.pdf"
        payload = source.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            renamed = Path(tmp) / "innocuous-research-doc.pdf"
            renamed.write_bytes(payload)
            self.assertEqual(renamed.read_bytes(), payload)
            digest = hashlib.sha256(payload).hexdigest()
        entry = next(e for e in manifest()["entries"] if e["path"] == "public/mapping-amount.pdf")
        self.assertEqual(digest, entry["sha256"], "identity must be content-addressed")


class TestRegistryRegistration(unittest.TestCase):
    """T05 owns the test:fixtures registration it promised to provide."""

    def test_test_fixtures_command_is_registered_and_active(self):
        registry = json.loads(REGISTRY.read_text())
        entry = registry["commands"]["test:fixtures"]
        self.assertEqual(entry["status"], "active")
        self.assertEqual(entry["owner_task"], "T05")
        self.assertEqual(entry["collection"], "harness-unittest")
        self.assertEqual(
            entry["argv"],
            ["uv", "run", "--frozen", "--project", "native", "python",
             "-m", "unittest", "discover", "-s", "tests/fixtures", "-v"],
        )


if __name__ == "__main__":
    unittest.main()
