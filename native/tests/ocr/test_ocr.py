"""T27 native rendered-region Tesseract reader tests (TEST-27).

Runs the real installed Tesseract over rasters rendered from the committed T05
fixtures with explicit UserUnit render compensation. Covers the T26/T27
contract discipline: no runtime fetch, distinct missing-binary / missing-model
/ unreadable-pixels / timeout failures, neutral filenames with validated
options, crop padding and inverse transforms, and verbatim raw OCR text with
all occurrences retained.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import unittest
from pathlib import Path

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
    return tr.open_raster(png, None, 1, render_meta={"raster_scale_px_per_pt": scale})


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


class ReaderManifestTests(unittest.TestCase):
    def test_manifest_is_complete_and_schema_valid(self):
        manifest = tr.describe()
        schema_validator("ReaderManifest").validate(manifest)
        reader = manifest["reader"]
        self.assertEqual(reader["adapter_version"], "1.0.0")
        self.assertEqual(reader["method"], "ocr")
        self.assertEqual(reader["environment"], "native")
        self.assertIn("5.5.3", reader["build"])
        self.assertEqual(reader["settings"]["language"], "eng")
        self.assertEqual(reader["settings"]["render_reader_id"], "pdfium-native")

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
        self.assertEqual(len(argv), 6)
        self.assertEqual(argv[0].split("/")[-1], "tesseract")
        self.assertTrue(argv[1].startswith("/var/folders/") or "inkflip-ocr-" in argv[1])
        self.assertTrue(argv[1].endswith("input.png"))
        self.assertEqual(argv[2], "stdout")
        self.assertEqual(argv[3:5], ["--psm", "3"])
        self.assertEqual(argv[5], "tsv")
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


if __name__ == "__main__":
    unittest.main()
