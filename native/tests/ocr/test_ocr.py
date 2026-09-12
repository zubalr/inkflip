"""T27 native rendered-region Tesseract reader tests (TEST-27).

Runs the real installed Tesseract over rasters rendered from the committed T05
fixtures with explicit UserUnit render compensation. Covers the T26/T27
contract discipline: no runtime fetch, distinct missing-binary / missing-model
/ unreadable-pixels / timeout failures, neutral filenames with validated
options, crop padding and inverse transforms, and verbatim raw OCR text with
all occurrences retained.
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"

sys.path.insert(0, str(NATIVE))

import jsonschema  # noqa: E402
from PIL import Image  # noqa: E402

from inkflip.readers import tesseract as tr  # noqa: E402

SCHEMA = json.loads((NATIVE / "inkflip/contracts/schema/inkflip.schema.json").read_text())


def schema_validator(def_name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{def_name}", "$defs": SCHEMA["$defs"]}
    )


def render_fixture(relative: str, scale: float, user_unit: float = 1.0):
    """Named-render a fixture page: scale is px per PHYSICAL point, so the
    PDFium render scale is scale * UserUnit (explicit compensation)."""
    from pypdfium2 import PdfDocument

    doc = PdfDocument((FIXTURES / relative).read_bytes())
    page = doc[0]
    image = page.render(scale=scale * user_unit).to_pil()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    doc.close()
    return buffer.getvalue(), image.size


def open_raster(png: bytes, scale: float):
    """render_fixture applies no rotation: the actual named render transform is
    Scale(scale)*R0, recorded as the canonical_to_raster matrix."""
    return tr.open_raster(
        png,
        None,
        1,
        render_meta={
            "raster_scale_px_per_pt": scale,
            "canonical_to_raster": [scale, 0.0, 0.0, scale, 0.0, 0.0],
        },
    )


def run_ocr(handle, crop=None, **kwargs):
    chunks: list[list[dict]] = []
    result = tr.extract(
        handle,
        {
            "id": kwargs.pop("plan_id", "check-ocr"),
            "page_index": 0,
            "reader_ids": [tr.READER_ID],
            "capability": "ocr",
            "region_id": None,
        },
        chunks.append,
        crop=crop,
        **kwargs,
    )
    occurrences = [o for chunk in chunks for o in chunk]
    return result, occurrences


def bare_plan(plan_id: str, page_index: int = 0) -> dict:
    return {
        "id": plan_id,
        "page_index": page_index,
        "reader_ids": [tr.READER_ID],
        "capability": "ocr",
        "region_id": None,
    }


_OVERSIZED_PNG: bytes | None = None


def oversized_png() -> bytes:
    """A valid PNG declaring 7000x7000 = 49 Mpx, above the 40 Mpx budget.
    Built once and cached; its pixel data never needs decoding."""
    global _OVERSIZED_PNG
    if _OVERSIZED_PNG is None:
        image = Image.new("1", (7000, 7000), 0)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", compress_level=1)
        _OVERSIZED_PNG = buffer.getvalue()
    return _OVERSIZED_PNG


class ReaderManifestTests(unittest.TestCase):
    def test_manifest_is_complete_and_schema_valid(self):
        manifest = tr.describe()
        schema_validator("ReaderManifest").validate(manifest)
        reader = manifest["reader"]
        self.assertEqual(reader["adapter_version"], "1.0.0")  # const pinned by the shared schema
        self.assertEqual(reader["method"], "ocr")
        self.assertEqual(reader["environment"], "native")
        self.assertIn("5.5.3", reader["build"])
        self.assertEqual(reader["settings"]["language"], "eng")
        self.assertEqual(reader["settings"]["render_reader_id"], "pdfium-native")
        # The manifest records the exact model identity the engine is pinned to.
        self.assertTrue(
            any("--tessdata-dir" in limit for limit in reader["capabilities"][0]["limits"]),
            reader["capabilities"][0]["limits"],
        )

    def test_model_hash_is_the_exact_local_traineddata(self):
        digest, path = tr.model_digest()
        self.assertIsNotNone(digest)
        self.assertIsNotNone(path)
        self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertIn("eng.traineddata", str(path))
        self.assertTrue(str(path).startswith("/"), "model resolves from the local install")


class TestFullPageOcr(unittest.TestCase):
    """F01/F03: verbatim raw text, all occurrences, punctuation retained."""

    @classmethod
    def setUpClass(cls):
        cls.png, cls.size = render_fixture("public/mapping-amount.pdf", scale=3, user_unit=1)

    def test_amount_line_is_recognized_with_canonical_geometry(self):
        handle = open_raster(self.png, 3.0)
        result, occurrences = run_ocr(handle)
        handle.close()
        self.assertEqual(result["status"], "completed")
        texts = [o["raw_text"] for o in occurrences]
        self.assertIn("$100", texts)
        for occurrence in occurrences:
            schema_validator("Occurrence").validate(occurrence)
            self.assertEqual(occurrence["geometry"]["precision"], "estimated")
            polygon = occurrence["geometry"]["polygon"]
            self.assertTrue(polygon)
            for x, y in polygon:
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x, 520)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(y, 400)
        amount = next(o for o in occurrences if o["raw_text"] == "$100")
        self.assertGreater(amount["engine_score"]["value"], 0.5)
        self.assertEqual(amount["engine_score"]["meaning"], "tesseract word confidence (engine diagnostic)")

    def test_raw_punctuation_and_case_are_retained_verbatim(self):
        handle = open_raster(self.png, 3.0)
        result, occurrences = run_ocr(handle)
        handle.close()
        texts = [o["raw_text"] for o in occurrences]
        self.assertIn("SYNTHETIC", texts)  # case preserved
        self.assertTrue(any(t.endswith(".") for t in texts), texts)  # punctuation preserved

    def test_f03_scan_ocr_reads_pixels_only_and_ignores_invisible_layer(self):
        """F03 minimum control: OCR sees the raster; the legitimate invisible
        text layer contributes nothing, so the correct scan and the raster-only
        sibling produce identical OCR output (no alarm from invisibility)."""
        correct_png, _ = render_fixture("development/scan-correct.pdf", scale=1)
        raster_only_png, _ = render_fixture("development/scan-raster-only.pdf", scale=1)
        handle_correct = open_raster(correct_png, 1.0)
        result_c, occurrences_c = run_ocr(handle_correct)
        handle_correct.close()
        handle_only = open_raster(raster_only_png, 1.0)
        result_r, occurrences_r = run_ocr(handle_only)
        handle_only.close()
        self.assertEqual(result_c["status"], "completed")
        self.assertEqual(result_r["status"], "completed")
        self.assertGreater(len(occurrences_c), 5)
        self.assertEqual(
            [o["raw_text"] for o in occurrences_c],
            [o["raw_text"] for o in occurrences_r],
        )
        # The layer's exact strings ('QUARTERLY SUMMARY') may OCR imperfectly
        # from the bitmap print; whatever the engine reports is retained
        # verbatim rather than corrected toward the invisible layer text.


class TestCropPaddingAndInverse(unittest.TestCase):
    """Criterion: crop padding/resize inverses correct."""

    @classmethod
    def setUpClass(cls):
        cls.png, _ = render_fixture("public/mapping-amount.pdf", scale=3, user_unit=1)

    def test_padding_is_max_of_8px_and_ten_percent_clipped(self):
        handle = open_raster(self.png, 3.0)
        # region height 190 -> pad = max(8, 19) = 19
        crop = tr.plan_crop(handle, (120, 400, 500, 590), psm=tr.SINGLE_LINE_PSM)
        self.assertEqual(crop.padding, (-19, -19))
        self.assertEqual(crop.padded, (101, 381, 519, 609))
        # clipping at the raster edge: no negative coordinates
        corner = tr.plan_crop(handle, (0, 0, 50, 40), psm=tr.SINGLE_LINE_PSM)
        self.assertEqual(corner.padded, (0, 0, 58, 48))
        handle.close()

    def test_single_line_psm7_reads_amount_through_inverse_transform(self):
        handle = open_raster(self.png, 3.0)
        crop = tr.plan_crop(handle, (120, 400, 500, 590), psm=tr.SINGLE_LINE_PSM)
        result, occurrences = run_ocr(handle, crop=crop)
        handle.close()
        self.assertEqual(result["status"], "completed")
        self.assertEqual([o["raw_text"] for o in occurrences], ["$100"])
        polygon = occurrences[0]["geometry"]["polygon"]
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        # The inverse chain (crop offset + raster scale) must land the word box
        # inside/near the original region's canonical footprint.
        self.assertTrue(all(120 / 3 - 5 <= x <= 500 / 3 + 5 for x in xs))
        self.assertTrue(all(400 / 3 - 5 <= y <= 590 / 3 + 5 for y in ys))

    def test_resize_inverse_halves_reported_boxes(self):
        handle = open_raster(self.png, 3.0)
        crop = tr.plan_crop(handle, (120, 400, 500, 590), psm=tr.SINGLE_LINE_PSM, resize=(2.0, 2.0))
        # A TSV box at crop pixel (200, 100) in the 2x-resized crop maps to
        # raster (200/2 + 101, 100/2 + 381) and then to canonical (/3).
        x, y = crop.crop_to_raster(200, 100)
        self.assertAlmostEqual(x, 201.0)
        self.assertAlmostEqual(y, 431.0)
        cx, cy = crop.raster_to_canonical(x, y)
        self.assertAlmostEqual(cx, 67.0, places=6)
        self.assertAlmostEqual(cy, 143.666667, places=5)
        handle.close()


class TestUserUnitRenderCompensation(unittest.TestCase):
    """F08: rasters must carry UserUnit-compensated physical dimensions once."""

    def test_userunit_two_render_is_twice_the_physical_pixels(self):
        # geometry-0 crop box is 480x350 user units; UserUnit 2 makes the
        # physical page 960x700 pt. At 3 px/pt the raster must be 2880x2100 —
        # which requires the render scale to carry UserUnit (3*2). A plain
        # scale-3 render would produce 1440x1050 and fail this assertion.
        png, size = render_fixture("public/geometry-0.pdf", scale=3, user_unit=2)
        self.assertEqual(size, (2880, 2100))
        handle = open_raster(png, 3.0)
        result, occurrences = run_ocr(handle)
        handle.close()
        self.assertEqual(result["status"], "completed")
        self.assertIn("$100", [o["raw_text"] for o in occurrences])
        for occurrence in occurrences:
            for x, y in occurrence["geometry"]["polygon"]:
                self.assertLessEqual(x, 960)
                self.assertLessEqual(y, 700)


class TestDistinctFailureModes(unittest.TestCase):
    """Criterion: missing model/binary/unreadable page differ; plus timeout."""

    @classmethod
    def setUpClass(cls):
        cls.png, _ = render_fixture("public/mapping-amount.pdf", scale=2)

    def test_missing_binary_is_unsupported(self):
        handle = open_raster(self.png, 2.0)
        result, _ = run_ocr(handle, binary=Path("/nonexistent/tesseract"))
        handle.close()
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("executable", result["reason"])

    def test_missing_model_is_distinct_from_missing_binary(self):
        handle = open_raster(self.png, 2.0)
        result, _ = run_ocr(handle, language="nonexistent_lang")
        handle.close()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("missing_model"), result["reason"])

    def test_unreadable_pixels_fails_at_open(self):
        with self.assertRaises(tr.AdapterError) as ctx:
            tr.open_raster(b"\x89PNG garbage not an image", None, 1)
        self.assertEqual(ctx.exception.reason, "unreadable_pixels")

    def test_blank_raster_completes_with_zero_occurrences(self):
        blank = Image.new("L", (600, 400), 255)
        buffer = io.BytesIO()
        blank.save(buffer, format="PNG")
        handle = open_raster(buffer.getvalue(), 1.0)
        result, occurrences = run_ocr(handle)
        handle.close()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(occurrences, [])
        self.assertEqual(result["produced_occurrence_count"], 0)

    def test_timeout_is_a_distinct_terminal(self):
        handle = open_raster(self.png, 2.0)
        result, _ = run_ocr(handle, timeout_s=0.001)
        handle.close()
        self.assertEqual(result["status"], "timeout")

    def test_digest_mismatch_fails_typed(self):
        with self.assertRaises(tr.AdapterError) as ctx:
            tr.open_raster(self.png, "0" * 64, 1)
        self.assertEqual(ctx.exception.reason, "parser_error")


class TestOptionInjectionDefense(unittest.TestCase):
    """Criterion: a malicious filename/identifier cannot become an option."""

    @classmethod
    def setUpClass(cls):
        cls.png, _ = render_fixture("public/mapping-amount.pdf", scale=2)

    def test_language_identifier_cannot_smuggle_flags(self):
        handle = open_raster(self.png, 2.0)
        result, _ = run_ocr(handle, language="eng --psm 8")
        handle.close()
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("invalid language", result["reason"])

    def test_invocation_uses_only_neutral_generated_names(self):
        recorded = {}
        handle = open_raster(self.png, 2.0)
        chunks: list[list[dict]] = []

        def capture(chunk):
            recorded["chunk"] = chunk

        real_run = __import__("subprocess").run

        def spy(argv, **kwargs):
            recorded["argv"] = argv
            self.assertFalse(kwargs.get("shell"), "shell=True is forbidden")
            return real_run(argv, **kwargs)

        import subprocess

        original = subprocess.run
        subprocess.run = spy
        try:
            tr.extract(
                handle,
                {"id": "argv-check", "page_index": 0, "reader_ids": [tr.READER_ID], "capability": "ocr", "region_id": None},
                capture,
            )
        finally:
            subprocess.run = original
            handle.close()
        argv = [str(a) for a in recorded["argv"]]
        self.assertEqual(len(argv), 10)
        self.assertEqual(argv[0].split("/")[-1], "tesseract")
        self.assertTrue(argv[1].startswith("/var/folders/") or "inkflip-ocr-" in argv[1])
        self.assertTrue(argv[1].endswith("input.png"))
        self.assertEqual(argv[2], "stdout")
        self.assertEqual(argv[3:5], ["--psm", "3"])
        self.assertEqual(argv[5:7], ["-l", "eng"])
        self.assertEqual(argv[7], "--tessdata-dir")
        tessdata = Path(argv[8])
        self.assertTrue(tessdata.is_dir(), argv[8])
        self.assertTrue((tessdata / "eng.traineddata").is_file(), argv[8])
        self.assertEqual(argv[9], "tsv")
        self.assertNotIn(";", " ".join(argv))


class TestCancellationAndSchema(unittest.TestCase):
    def test_immediate_cancellation_is_terminal(self):
        png, _ = render_fixture("public/mapping-amount.pdf", scale=2)
        handle = open_raster(png, 2.0)
        result, occurrences = run_ocr(handle, cancellation=lambda: True)
        handle.close()
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(occurrences, [])

    def test_closed_handle_fails(self):
        png, _ = render_fixture("public/mapping-amount.pdf", scale=2)
        handle = open_raster(png, 2.0)
        handle.close()
        handle.close()  # idempotent
        result, _ = run_ocr(handle)
        self.assertEqual(result["status"], "failed")

    def test_every_occurrence_and_score_validate(self):
        png, _ = render_fixture("public/mapping-amount.pdf", scale=3)
        handle = open_raster(png, 3.0)
        result, occurrences = run_ocr(handle)
        handle.close()
        self.assertTrue(occurrences)
        for occurrence in occurrences:
            schema_validator("Occurrence").validate(occurrence)
            schema_validator("EngineScore").validate(occurrence["engine_score"])


TSV_HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"


def tsv_row(ordinal: int, left: int, top: int, width: int, height: int, conf: str = "90.0", text: str = "w") -> str:
    return "\t".join(
        ["5", "1", "1", "1", "1", str(ordinal), str(left), str(top), str(width), str(height), conf, text]
    )


def make_stub_engine(root: Path, stdout_text: str) -> Path:
    """A stub tesseract printing canned TSV, with fake model bytes beside it."""
    bindir = root / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "tesseract"
    stub.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdout.write(" + repr(stdout_text) + ")\n")
    stub.chmod(0o755)
    tessdata = root / "share/tessdata"
    tessdata.mkdir(parents=True, exist_ok=True)
    (tessdata / "eng.traineddata").write_bytes(b"stub-model")
    return stub


def raster_png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (width, height), 255).save(buffer, format="PNG")
    return buffer.getvalue()


def run_stub_ocr(handle, stub, crop=None, **kwargs):
    chunks: list[list[dict]] = []
    result = tr.extract(handle, bare_plan("stub-check"), chunks.append, binary=stub, crop=crop, **kwargs)
    occurrences = [o for chunk in chunks for o in chunk]
    return result, occurrences


class TestWave2Resize(unittest.TestCase):
    """Wave-2: invert the resize actually performed; bound the output first."""

    # Reads the REAL saved PNG dimensions from its IHDR header and emits one
    # word whose box spans exactly those dimensions, with the dims as text.
    DIMS_STUB = (
        "#!/usr/bin/env python3\n"
        "import struct, sys\n"
        "with open(sys.argv[1], 'rb') as handle:\n"
        "    head = handle.read(24)\n"
        "    width, height = struct.unpack('>II', head[16:24])\n"
        "print(" + repr(TSV_HEADER) + ")\n"
        "print('\\t'.join(['5','1','1','1','1','1','0','0',str(width),str(height),'90.0',"
        "str(width) + 'x' + str(height)]))\n"
    )

    def _stub_layout(self, root: Path, script: str) -> Path:
        bindir = root / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        stub = bindir / "tesseract"
        stub.write_text(script)
        stub.chmod(0o755)
        tessdata = root / "share/tessdata"
        tessdata.mkdir(parents=True, exist_ok=True)
        (tessdata / "eng.traineddata").write_bytes(b"stub-model")
        return stub

    def test_odd_resize_inverse_uses_actual_destination(self):
        # 101x51 padded crop resized (0.5, 0.5): Pillow rounds to 50x26, so the
        # effective factors are 50/101 and 26/51, not the requested 0.5.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stub = self._stub_layout(root, self.DIMS_STUB)
            handle = tr.open_raster(
                raster_png(150, 80), None, 1,
                render_meta={"canonical_to_raster": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]},
            )
            crop = tr.plan_crop(handle, (10, 10, 95, 45), psm=tr.SINGLE_LINE_PSM, resize=(0.5, 0.5))
            self.assertEqual((crop.padded[2] - crop.padded[0], crop.padded[3] - crop.padded[1]), (101, 51))
            result, occurrences = run_stub_ocr(handle, stub, crop=crop)
            handle.close()
            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(occurrences), 1)
            # The word text is the REAL saved PNG size read by the stub engine.
            self.assertEqual(occurrences[0]["raw_text"], "50x26")
            # The box (0,0,50,26) inverted with the effective factors must
            # recover the full padded source extent (2,2)-(103,53), including
            # the crop offset; requested 0.5 factors would give (54,28).
            polygon = occurrences[0]["geometry"]["polygon"]
            self.assertAlmostEqual(polygon[0][0], 2.0, places=6)
            self.assertAlmostEqual(polygon[0][1], 2.0, places=6)
            self.assertAlmostEqual(polygon[2][0], 103.0, places=6)
            self.assertAlmostEqual(polygon[2][1], 53.0, places=6)
            self.assertEqual(occurrences[0]["geometry"]["precision"], "estimated")

    def test_resize_budget_returns_resource_limit_before_allocation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stub = self._stub_layout(root, "#!/usr/bin/env python3\n")
            handle = tr.open_raster(
                raster_png(150, 80), None, 1,
                render_meta={"canonical_to_raster": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]},
            )
            for factors in ((1000.0, 1000.0), (1e300, 1e300)):
                with self.subTest(factors=factors):
                    crop = tr.plan_crop(handle, (10, 10, 95, 45), psm=tr.SINGLE_LINE_PSM, resize=factors)
                    with mock.patch.object(
                        Image.Image, "resize", side_effect=AssertionError("resize was called")
                    ):
                        result, occurrences = run_stub_ocr(handle, stub, crop=crop)
                    self.assertEqual(result["status"], "failed")
                    self.assertTrue(result["reason"].startswith("resource_limit"), result["reason"])
                    self.assertEqual(occurrences, [])
            handle.close()


class TestWave2TsvBoundary(unittest.TestCase):
    """Wave-2: malformed engine rows fail typed while keeping emitted chunks."""

    def _typed_case(self, tsv: str):
        with tempfile.TemporaryDirectory() as folder:
            stub = make_stub_engine(Path(folder), tsv)
            handle = tr.open_raster(
                raster_png(150, 80), None, 1,
                render_meta={"canonical_to_raster": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]},
            )
            result, occurrences = run_stub_ocr(handle, stub)
            handle.close()
            return result, occurrences

    def test_valid_rows_before_malformed_row_are_retained(self):
        good = "\n".join([TSV_HEADER, tsv_row(1, 5, 5, 10, 8), tsv_row(2, 30, 5, 12, 8)])
        result, occurrences = self._typed_case(good + "\n" + tsv_row(3, "junk", 5, 10, 8) + "\n")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("parser_error"), result["reason"])
        self.assertEqual(result["produced_occurrence_count"], 2)
        self.assertEqual(len(occurrences), 2)

    def test_nonfinite_confidence_is_typed_not_clamped(self):
        tsv = "\n".join([TSV_HEADER, tsv_row(1, 5, 5, 10, 8, conf="nan")]) + "\n"
        result, occurrences = self._typed_case(tsv)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("parser_error"), result["reason"])
        self.assertEqual(occurrences, [])

    def test_nonnumeric_coordinate_is_typed_not_silently_dropped(self):
        tsv = "\n".join([TSV_HEADER, tsv_row(1, "inf", 5, 10, 8)]) + "\n"
        result, occurrences = self._typed_case(tsv)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("parser_error"), result["reason"])

    def test_huge_coordinate_is_typed_not_raw_overflow(self):
        tsv = "\n".join([TSV_HEADER, tsv_row(1, "9" * 309, 5, 10, 8)]) + "\n"
        result, occurrences = self._typed_case(tsv)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("parser_error"), result["reason"])

    def test_unexpected_header_is_typed_terminal(self):
        result, occurrences = self._typed_case("unexpected\theader\n")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("parser_error"), result["reason"])
        self.assertEqual(occurrences, [])

    def test_short_row_after_valid_chunk_is_typed(self):
        good = "\n".join([TSV_HEADER, tsv_row(1, 5, 5, 10, 8), tsv_row(2, 30, 5, 12, 8)])
        # 7-column header, truncated 6-field word row: skipping it would
        # silently lose coverage.
        result, occurrences = self._typed_case(good + "\n" + "5\t90\tlost\t0\t0\t1\n")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("parser_error"), result["reason"])
        self.assertEqual(result["produced_occurrence_count"], 2)
        self.assertEqual(len(occurrences), 2)

    def test_nonpositive_word_extents_fail_typed(self):
        for label, row in (
            ("zero_width", tsv_row(3, 0, 0, 0, 1)),
            ("zero_height", tsv_row(3, 0, 0, 1, 0)),
            ("negative_width", tsv_row(3, 5, 0, -1, 1)),
            ("negative_height", tsv_row(3, 0, 5, 1, -1)),
        ):
            with self.subTest(case=label):
                good = "\n".join([TSV_HEADER, tsv_row(1, 5, 5, 10, 8), tsv_row(2, 30, 5, 12, 8)])
                result, occurrences = self._typed_case(good + "\n" + row + "\n")
                self.assertEqual(result["status"], "failed")
                self.assertTrue(result["reason"].startswith("parser_error"), result["reason"])
                self.assertEqual(result["produced_occurrence_count"], 2)
                self.assertEqual(len(occurrences), 2)

    def test_257_valid_words_survive_later_malformed_row(self):
        # More than one full 256-word chunk: accumulated counts and ids must
        # survive a parser failure on a later row.
        good = "\n".join(
            [TSV_HEADER] + [tsv_row(i, i % 50, (i * 7) % 40, 10, 8, text=f"w{i}") for i in range(1, 258)]
        )
        result, occurrences = self._typed_case(good + "\n" + tsv_row(258, 5, 5, 10, 8, conf="nan") + "\n")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("parser_error"), result["reason"])
        self.assertEqual(result["produced_occurrence_count"], 257)
        self.assertEqual(len(occurrences), 257)
        self.assertEqual(len(result["retained_occurrence_ids"]), 257)
        self.assertEqual(len(set(result["retained_occurrence_ids"])), 257)


class TestReviewRevisionsWave1(unittest.TestCase):
    """Wave-1 independent source review findings, regression-tested at the
    real API seams: F2 region_id, F3 malformed region, F4 caller CropPlan,
    F5 page-scoped ids, F6 budget-before-decode, F7 exact word budget,
    F12 typed local I/O faults. F8/F9 (supervision) are T29 scope and F10
    (rotation) is a recorded limitation, deliberately not built here."""

    @classmethod
    def setUpClass(cls):
        cls.png, _ = render_fixture("public/mapping-amount.pdf", scale=2)

    def test_region_id_plan_without_crop_is_typed_unsupported(self):
        handle = open_raster(self.png, 2.0)
        chunks: list[list[dict]] = []
        plan = bare_plan("region-check")
        plan["region_id"] = "region-1"
        result = tr.extract(handle, plan, chunks.append)
        handle.close()
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("region", result["reason"])
        self.assertEqual(chunks, [])
        self.assertEqual(result["produced_occurrence_count"], 0)

    def test_non_schema_region_key_is_not_a_plan_channel(self):
        handle = open_raster(self.png, 2.0)
        chunks: list[list[dict]] = []
        plan = bare_plan("legacy-region")
        plan["region"] = [10, 10, 40, 40]  # not a CheckPlan schema property
        result = tr.extract(handle, plan, chunks.append)
        handle.close()
        self.assertEqual(result["status"], "completed")
        self.assertGreater(result["produced_occurrence_count"], 0)

    def test_malformed_regions_fail_typed_in_plan_crop(self):
        handle = open_raster(self.png, 2.0)
        try:
            for bad in ([1, 2, 3], (1, 2, 3, 4, 5), {"a": 1}, "abcd", 7, [1.5, 2, 3, 4]):
                with self.assertRaises(tr.AdapterError) as ctx:
                    tr.plan_crop(handle, bad)
                self.assertEqual(ctx.exception.reason, "geometry_unavailable", repr(bad))
        finally:
            handle.close()

    def test_caller_crop_plan_with_hostile_psm_is_rejected(self):
        handle = open_raster(self.png, 2.0)
        crop = tr.plan_crop(handle, (10, 10, 200, 60), psm=tr.SINGLE_LINE_PSM)
        hostile = dataclasses.replace(crop, psm="--tessdata-dir /etc")
        result, occurrences = run_ocr(handle, crop=hostile)
        handle.close()
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(occurrences, [])

    def test_caller_crop_plan_with_zero_resize_is_typed(self):
        handle = open_raster(self.png, 2.0)
        crop = tr.plan_crop(handle, (10, 10, 200, 60), psm=tr.SINGLE_LINE_PSM)
        zero = dataclasses.replace(crop, resize=(0.0, 0.0))
        result, _ = run_ocr(handle, crop=zero)
        handle.close()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("geometry_unavailable"), result["reason"])

    def test_caller_crop_plan_with_nan_resize_is_typed(self):
        handle = open_raster(self.png, 2.0)
        crop = tr.plan_crop(handle, (10, 10, 200, 60), psm=tr.SINGLE_LINE_PSM)
        nan = dataclasses.replace(crop, resize=(float("nan"), 1.0))
        result, _ = run_ocr(handle, crop=nan)
        handle.close()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("geometry_unavailable"), result["reason"])

    def test_caller_crop_plan_with_out_of_raster_padded_is_typed(self):
        handle = open_raster(self.png, 2.0)
        crop = tr.plan_crop(handle, (10, 10, 200, 60), psm=tr.SINGLE_LINE_PSM)
        outside = dataclasses.replace(crop, padded=(-10, -10, 300, 90))
        result, _ = run_ocr(handle, crop=outside)
        handle.close()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("geometry_unavailable"), result["reason"])

    def test_occurrence_id_includes_page_index(self):
        handle = open_raster(self.png, 2.0)
        chunks: list[list[dict]] = []
        result = tr.extract(handle, bare_plan("page3", page_index=3), chunks.append)
        handle.close()
        self.assertEqual(result["status"], "completed")
        occurrences = [o for chunk in chunks for o in chunk]
        self.assertTrue(occurrences)
        for occurrence in occurrences:
            self.assertIn("-p3-", occurrence["id"])
            self.assertEqual(occurrence["page_index"], 3)

    def test_pixel_budget_is_enforced_before_decode(self):
        data = oversized_png()  # built outside the patch: PIL save() calls load()
        with mock.patch.object(
            Image.Image, "load", side_effect=AssertionError("decode before budget check")
        ):
            with self.assertRaises(tr.AdapterError) as ctx:
                tr.open_raster(data, None, 1)
        self.assertEqual(ctx.exception.reason, "resource_limit")

    def test_workdir_failure_is_typed(self):
        handle = open_raster(self.png, 2.0)
        with mock.patch.object(
            tr.tempfile, "mkdtemp", side_effect=OSError(28, "No space left on device")
        ):
            result, _ = run_ocr(handle)
        handle.close()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("parser_error"), result["reason"])

    def test_crop_save_failure_is_typed(self):
        handle = open_raster(self.png, 2.0)
        with mock.patch.object(
            Image.Image, "save", side_effect=OSError(28, "No space left on device")
        ):
            result, _ = run_ocr(handle)
        handle.close()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("parser_error"), result["reason"])


class TestWordBudget(unittest.TestCase):
    """F7: the cap bounds emission exactly, via a canned-TSV stub engine."""

    @staticmethod
    def _stub_engine(root: Path, words: int) -> Path:
        header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
        lines = [
            "#!/usr/bin/env python3",
            "import sys",
            f"print({header!r})",
            "for i in range(%d):" % words,
            "    print('\\t'.join(['5', '1', '1', '1', '1', str(i + 1), '10', '10', "
            "'40', '12', '90.0', 'w' + str(i)]))",
            "",
        ]
        bindir = root / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        stub = bindir / "tesseract"
        stub.write_text("\n".join(lines))
        stub.chmod(0o755)
        return stub

    @classmethod
    def _run_with_stub(cls, words: int):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tessdata = root / "share/tessdata"
            tessdata.mkdir(parents=True)
            (tessdata / "eng.traineddata").write_bytes(b"stub-model")
            stub = cls._stub_engine(root, words)
            png, _ = render_fixture("public/mapping-amount.pdf", scale=2)
            handle = open_raster(png, 2.0)
            chunks: list[list[dict]] = []
            result = tr.extract(handle, bare_plan("budget"), chunks.append, binary=stub)
            handle.close()
            return result, chunks

    def test_one_word_over_budget_limits_emission_to_exactly_5000(self):
        result, chunks = self._run_with_stub(words=5001)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("resource_limit"), result["reason"])
        self.assertEqual(result["produced_occurrence_count"], 5000)
        self.assertEqual(len(result["retained_occurrence_ids"]), 5000)
        self.assertEqual(sum(len(chunk) for chunk in chunks), 5000)

    def test_exactly_at_budget_completes(self):
        result, chunks = self._run_with_stub(words=5000)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["produced_occurrence_count"], 5000)
        self.assertEqual(sum(len(chunk) for chunk in chunks), 5000)


class TestModelSelection(unittest.TestCase):
    """F11 + Cloud F1: the recorded model is exactly what the engine loads."""

    @classmethod
    def setUpClass(cls):
        cls.png, _ = render_fixture("public/mapping-amount.pdf", scale=2)

    def test_explicit_prefix_without_requested_model_rejects_without_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            prefix = Path(folder) / "prefix"
            prefix.mkdir()
            (prefix / "osd.traineddata").write_bytes(b"decoy")  # no eng here
            with mock.patch.dict(os.environ, {"TESSDATA_PREFIX": str(prefix)}):
                self.assertEqual(tr.model_digest(), (None, None))
                handle = open_raster(self.png, 2.0)
                result, _ = run_ocr(handle)
                handle.close()
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["reason"].startswith("missing_model"), result["reason"])

    def test_explicit_prefix_model_is_hashed_and_pinned_in_argv(self):
        with tempfile.TemporaryDirectory() as folder:
            prefix = Path(folder) / "prefix"
            prefix.mkdir()
            (prefix / "eng.traineddata").write_bytes(b"fake-eng-model-bytes")
            recorded: dict = {}
            real_run = subprocess.run

            def spy(argv, **kwargs):
                recorded["argv"] = [str(a) for a in argv]
                return real_run(argv, **kwargs)

            with mock.patch.dict(os.environ, {"TESSDATA_PREFIX": str(prefix)}):
                with mock.patch("subprocess.run", side_effect=spy):
                    digest, path = tr.model_digest()
                    self.assertEqual(digest, hashlib.sha256(b"fake-eng-model-bytes").hexdigest())
                    handle = open_raster(self.png, 2.0)
                    # The engine honestly rejects the fake model bytes; the
                    # point is that argv pinned exactly the prefixed directory.
                    result, _ = run_ocr(handle)
                    handle.close()
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["reason"].startswith("missing_model"), result["reason"])
            self.assertIn("--tessdata-dir", recorded["argv"])
            self.assertEqual(
                recorded["argv"][recorded["argv"].index("--tessdata-dir") + 1], str(prefix)
            )
            self.assertIn("-l", recorded["argv"])
            self.assertEqual(recorded["argv"][recorded["argv"].index("-l") + 1], "eng")

    def test_fallback_dir_is_probed_per_language(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # Corrected layout: binary at root/bin/tesseract, so the source
            # probes root/share/tessdata (first candidate) then root/bin/tessdata
            # (second candidate). The decoy directory exists but lacks eng.
            decoy = root / "share/tessdata"
            decoy.mkdir(parents=True)
            (decoy / "osd.traineddata").write_bytes(b"osd-only")
            target = root / "bin/tessdata"
            target.mkdir(parents=True)
            (target / "eng.traineddata").write_bytes(b"fallback-eng")
            binary = root / "bin/tesseract"
            binary.write_bytes(b"stub")
            binary.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if k != "TESSDATA_PREFIX"}
            with mock.patch.dict(os.environ, env, clear=True):
                digest, path = tr.model_digest(binary, "eng")
            self.assertIsNotNone(digest)
            self.assertEqual(digest, hashlib.sha256(b"fallback-eng").hexdigest())
            self.assertEqual(path.parent, target)


class TestWave2CanonicalGeometry(unittest.TestCase):
    """Wave-2 / F10 decision: canonical_to_raster affine authorizes geometry.

    The matrix is Scale(s)*R per COORDINATES.md; all four OCR box corners are
    mapped individually through the effective resize inverse, the crop offset
    and the recorded render inverse. Stub engines only; tiny real renders
    establish the actual rotation direction."""

    @staticmethod
    def _open(png: bytes, render_meta: dict) -> tr.RasterHandle:
        return tr.open_raster(png, None, 1, render_meta=render_meta)

    def _stub_ocr(self, handle, box, crop=None):
        with tempfile.TemporaryDirectory() as folder:
            stub = make_stub_engine(Path(folder), TSV_HEADER + "\n" + tsv_row(1, *box) + "\n")
            return run_stub_ocr(handle, stub, crop=crop)

    def test_contract_numeric_example_recovers_56_340(self):
        # COORDINATES.md numeric example: canonical (56,340) at 90 degrees,
        # scale 1.5 maps to raster (540,84); a crop at (500,60) resized 2x
        # puts it at OCR (80,48). Inversion must recover (56,340).
        png = raster_png(1050, 1440)
        handle = self._open(png, {"canonical_to_raster": [0.0, 1.5, -1.5, 0.0, 1050.0, 0.0]})
        crop = tr.plan_crop(handle, (500, 60, 1010, 700), psm=tr.SINGLE_LINE_PSM, resize=(2.0, 2.0))
        # Caller-built plan: pin the padded rect to the documented crop origin.
        crop = dataclasses.replace(crop, region=(500, 60, 1010, 700), padded=(500, 60, 1010, 700))
        result, occurrences = self._stub_ocr(handle, (80, 48, 10, 10), crop=crop)
        handle.close()
        self.assertEqual(result["status"], "completed")
        polygon = occurrences[0]["geometry"]["polygon"]
        # Independent analytic inverse of Scale(1.5)*R90: can_x = ry/1.5,
        # can_y = (1050 - rx)/1.5, applied to all four corners.
        expected = []
        for ox, oy in ((80, 48), (90, 48), (90, 58), (80, 58)):
            rx, ry = ox / 2.0 + 500.0, oy / 2.0 + 60.0
            expected.append([ry / 1.5, (1050.0 - rx) / 1.5])
        for got, want in zip(polygon, expected):
            self.assertAlmostEqual(got[0], want[0], places=6)
            self.assertAlmostEqual(got[1], want[1], places=6)
        self.assertAlmostEqual(polygon[0][0], 56.0, places=6)
        self.assertAlmostEqual(polygon[0][1], 340.0, places=6)

    def test_f08_fiducial_all_four_rotations(self):
        """F08 UserUnit-2 named render with independent closed-form fiducials:
        user 372,250..472,350 -> physical canonical (744,100)..(944,300); the
        recorded matrix maps them into the actual rendered ink, and every
        emitted corner must equal the expected canonical quad exactly. This
        kills displacement mutants (e.g. +10000 pt) and pins the recorded
        matrix to the actual named render instead of accepting either
        rotation direction."""
        configs = {
            0: ([0.5, 0.0, 0.0, 0.5, 0.0, 0.0], (372, 50, 100, 100),
                [[744.0, 100.0], [944.0, 100.0], [944.0, 300.0], [744.0, 300.0]]),
            90: ([0.0, 0.5, -0.5, 0.0, 400.0, 0.0], (250, 372, 100, 100),
                 [[744.0, 300.0], [744.0, 100.0], [944.0, 100.0], [944.0, 300.0]]),
            180: ([-0.5, 0.0, 0.0, -0.5, 520.0, 400.0], (48, 250, 100, 100),
                  [[944.0, 300.0], [744.0, 300.0], [744.0, 100.0], [944.0, 100.0]]),
            270: ([0.0, -0.5, 0.5, 0.0, 0.0, 520.0], (50, 48, 100, 100),
                  [[944.0, 100.0], [944.0, 300.0], [744.0, 300.0], [744.0, 100.0]]),
        }
        fixture = FIXTURES / "development/userunit-2.pdf"
        from pypdfium2 import PdfDocument

        for rotation, (matrix, box, expected) in configs.items():
            with self.subTest(rotation=rotation):
                doc = PdfDocument(fixture.read_bytes())
                page = doc[0]
                image = page.render(scale=1, rotation=rotation).to_pil().copy()
                bitmap_dims = image.size
                doc.close()
                if rotation in (90, 270):
                    self.assertEqual(bitmap_dims, (400, 520))
                else:
                    self.assertEqual(bitmap_dims, (520, 400))
                # The recorded matrix must agree with the actual rendered ink:
                # a small window just inside the box's lower edge carries the
                # fiducial mark (dark pixels), so the box sits on real ink at
                # the matrix-predicted raster location.
                gray = image.convert("L")
                x, y, w, h = box
                ink = min(
                    gray.getpixel((xx, yy))
                    for xx in range(x - 1, x + 3)
                    for yy in range(y + 48, y + 53)
                )
                self.assertLess(ink, 200, f"no fiducial ink at matrix-predicted location, rot {rotation}")
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                handle = self._open(buffer.getvalue(), {"canonical_to_raster": matrix})
                result, occurrences = self._stub_ocr(handle, box)
                handle.close()
                self.assertEqual(result["status"], "completed")
                self.assertEqual(len(occurrences), 1)
                # Exact corner equality: a displaced-geometry mutant
                # (+10000 pt on any emitted coordinate) fails here.
                self.assertEqual(occurrences[0]["geometry"]["polygon"], expected)
                self.assertEqual(occurrences[0]["geometry"]["precision"], "estimated")

    def test_huge_int_inputs_fail_typed_without_overflow(self):
        huge = 10**309  # exceeds sys.float_info.max; math.isfinite would raise
        with self.assertRaises(tr.AdapterError) as ctx:
            self._open(raster_png(150, 80), {"canonical_to_raster": [huge, 0, 0, 1, 0, 0]})
        self.assertEqual(ctx.exception.reason, "geometry_unavailable")
        with self.assertRaises(tr.AdapterError) as ctx:
            self._open(raster_png(150, 80), {"raster_scale_px_per_pt": huge})
        self.assertEqual(ctx.exception.reason, "geometry_unavailable")
        handle = self._open(
            raster_png(150, 80), {"canonical_to_raster": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]}
        )
        crop = tr.plan_crop(handle, (10, 10, 95, 45), psm=tr.SINGLE_LINE_PSM)
        with self.assertRaises(tr.AdapterError) as ctx:
            tr.plan_crop(handle, (10, 10, 95, 45), psm=tr.SINGLE_LINE_PSM, resize=(huge, 1))
        self.assertEqual(ctx.exception.reason, "geometry_unavailable")
        with tempfile.TemporaryDirectory() as folder:
            stub = make_stub_engine(Path(folder), TSV_HEADER + "\n" + tsv_row(1, 5, 5, 10, 8) + "\n")
            bad_scale = dataclasses.replace(crop, raster_scale=huge)
            result, _ = run_stub_ocr(handle, stub, crop=bad_scale)
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["reason"].startswith("geometry_unavailable"), result["reason"])
            bad_inverse = dataclasses.replace(crop, canonical_from_raster=[huge, 0, 0, 1, 0, 0])
            result, _ = run_stub_ocr(handle, stub, crop=bad_inverse)
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["reason"].startswith("geometry_unavailable"), result["reason"])
        handle.close()

    def test_caller_inverse_field_validated_before_conversion(self):
        handle = self._open(
            raster_png(150, 80), {"canonical_to_raster": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]}
        )
        crop = tr.plan_crop(handle, (10, 10, 95, 45), psm=tr.SINGLE_LINE_PSM)
        # A bare int is not a 6-component sequence: typed refusal, never a
        # raw TypeError from tuple conversion.
        not_a_sequence = dataclasses.replace(crop, canonical_from_raster=42)
        with tempfile.TemporaryDirectory() as folder:
            stub = make_stub_engine(Path(folder), TSV_HEADER + "\n" + tsv_row(1, 5, 5, 10, 8) + "\n")
            result, occurrences = run_stub_ocr(handle, stub, crop=not_a_sequence)
        handle.close()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("geometry_unavailable"), result["reason"])
        self.assertEqual(occurrences, [])

    def test_resize_io_and_memory_failures_are_typed(self):
        handle = self._open(
            raster_png(150, 80), {"canonical_to_raster": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]}
        )
        crop = tr.plan_crop(handle, (10, 10, 95, 45), psm=tr.SINGLE_LINE_PSM, resize=(2.0, 2.0))
        for label, effect, reason in (
            ("oserror", OSError("injected allocation failure"), "unreadable_pixels"),
            ("memoryerror", MemoryError("injected"), "resource_limit"),
        ):
            with self.subTest(case=label):
                with tempfile.TemporaryDirectory() as folder:
                    stub = make_stub_engine(Path(folder), TSV_HEADER + "\n" + tsv_row(1, 5, 5, 10, 8) + "\n")
                    with mock.patch.object(Image.Image, "resize", side_effect=effect):
                        result, occurrences = run_stub_ocr(handle, stub, crop=crop)
                self.assertEqual(result["status"], "failed")
                self.assertTrue(result["reason"].startswith(reason), result["reason"])
                self.assertEqual(occurrences, [])
        handle.close()

    def test_shear_quad_is_not_axis_aligned(self):
        png = raster_png(100, 100)
        handle = self._open(png, {"canonical_to_raster": [1.0, 0.15, 0.25, 1.0, 0.0, 0.0]})
        result, occurrences = self._stub_ocr(handle, (10, 10, 40, 20))
        handle.close()
        self.assertEqual(result["status"], "completed")
        polygon = occurrences[0]["geometry"]["polygon"]
        # A two-corner/axis-aligned reconstruction would keep equal y for the
        # top edge; the shear must tilt it.
        self.assertNotAlmostEqual(polygon[0][1], polygon[1][1])
        inverse = tr._contract_inverse([1.0, 0.15, 0.25, 1.0, 0.0, 0.0])
        for corner, point in zip(((10, 10), (50, 10), (50, 30), (10, 30)), polygon):
            expected = tr._contract_apply(inverse, corner)
            self.assertAlmostEqual(point[0], expected[0], places=6)
            self.assertAlmostEqual(point[1], expected[1], places=6)

    def test_missing_matrix_yields_unknown_geometry_despite_scalar(self):
        handle = tr.open_raster(raster_png(150, 80), None, 1, render_meta={"raster_scale_px_per_pt": 2.0})
        result, occurrences = self._stub_ocr(handle, (10, 10, 40, 20))
        handle.close()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(occurrences[0]["raw_text"], "w")
        self.assertIsNone(occurrences[0]["geometry"]["polygon"])
        self.assertEqual(occurrences[0]["geometry"]["precision"], "unknown")
        self.assertEqual(occurrences[0]["geometry"]["transform_ids"], [])

    def test_invalid_matrices_fail_typed_at_open(self):
        cases = {
            "singular": [1.0, 2.0, 2.0, 4.0, 0.0, 0.0],
            "nonfinite": [1.0, 0.0, 0.0, float("nan"), 0.0, 0.0],
            "string": [1.0, 0.0, 0.0, "x", 0.0, 0.0],
            "boolean": [True, 0.0, 0.0, 1.0, 0.0, 0.0],
            "short": [1.0, 0.0, 0.0, 1.0, 0.0],
            "notasequence": "nope",
        }
        for label, matrix in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(tr.AdapterError) as ctx:
                    self._open(raster_png(150, 80), {"canonical_to_raster": matrix})
                self.assertEqual(ctx.exception.reason, "geometry_unavailable")

    def test_unstable_inverse_extent_fails_typed(self):
        # det = 2e-12 passes the singular check, but the inverse maps the
        # raster corner to canonical coordinates far beyond any page extent.
        with self.assertRaises(tr.AdapterError) as ctx:
            self._open(raster_png(100, 100), {"canonical_to_raster": [1.0, 0.0, 0.0, 2e-12, 0.0, 0.0]})
        self.assertEqual(ctx.exception.reason, "geometry_unavailable")

    def test_caller_provenance_mismatch_is_refused(self):
        handle = self._open(
            raster_png(150, 80), {"canonical_to_raster": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]}
        )
        crop = tr.plan_crop(handle, (10, 10, 95, 45), psm=tr.SINGLE_LINE_PSM)
        stale = dataclasses.replace(crop, canonical_from_raster=(9.0, 9.0, 9.0, 9.0, 9.0, 9.0))
        with tempfile.TemporaryDirectory() as folder:
            stub = make_stub_engine(Path(folder), TSV_HEADER + "\n" + tsv_row(1, 5, 5, 10, 8) + "\n")
            result, occurrences = run_stub_ocr(handle, stub, crop=stale)
        handle.close()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("geometry_unavailable"), result["reason"])
        self.assertEqual(occurrences, [])

    def test_caller_crop_plan_malformed_field_shapes_are_typed(self):
        handle = self._open(
            raster_png(150, 80), {"canonical_to_raster": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]}
        )
        crop = tr.plan_crop(handle, (10, 10, 95, 45), psm=tr.SINGLE_LINE_PSM)
        with tempfile.TemporaryDirectory() as folder:
            stub = make_stub_engine(Path(folder), TSV_HEADER + "\n" + tsv_row(1, 5, 5, 10, 8) + "\n")
            for label, mutated in (
                ("psm_list", dataclasses.replace(crop, psm=[])),
                ("resize_short", dataclasses.replace(crop, resize=(1.0,))),
            ):
                with self.subTest(case=label):
                    result, occurrences = run_stub_ocr(handle, stub, crop=mutated)
                    self.assertIn(result["status"], ("failed", "unsupported"))
                    self.assertEqual(occurrences, [])
            with self.assertRaises(tr.AdapterError):
                tr.plan_crop(handle, (10, 10, 95, 45), psm=[], resize=(1.0,))
        handle.close()

    def test_model_read_failure_is_sanitized_model_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            prefix = Path(folder) / "prefix"
            prefix.mkdir()
            trained = prefix / "eng.traineddata"
            trained.write_bytes(b"unreachable-model")
            real_read = Path.read_bytes

            def deny(self):
                if self == trained:
                    raise PermissionError(13, "denied")
                return real_read(self)

            with mock.patch.dict(os.environ, {"TESSDATA_PREFIX": str(prefix)}):
                with mock.patch.object(Path, "read_bytes", deny):
                    with self.assertRaises(tr.AdapterError) as ctx:
                        tr.model_digest(None, "eng")
                    self.assertEqual(ctx.exception.reason, "model_integrity")
                    self.assertNotIn(str(prefix), ctx.exception.detail)
                    self.assertNotIn("/", ctx.exception.detail)
                    handle = tr.open_raster(
                        raster_png(150, 80), None, 1,
                        render_meta={"canonical_to_raster": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]},
                    )
                    result, _ = run_stub_ocr(handle, make_stub_engine(Path(folder) / "engine", ""))
                    handle.close()
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["reason"].startswith("model_integrity"), result["reason"])


if __name__ == "__main__":
    unittest.main()
