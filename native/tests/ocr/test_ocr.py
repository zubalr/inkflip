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
            first = root / "share/tessdata"
            first.mkdir(parents=True)
            (first / "osd.traineddata").write_bytes(b"osd-only")
            second = root / "tessdata"
            second.mkdir()
            (second / "eng.traineddata").write_bytes(b"fallback-eng")
            # Binary directly at the root: its sibling candidates are
            # root/share/tessdata (no eng) and root/tessdata (has eng).
            binary = root / "tesseract"
            binary.write_bytes(b"stub")
            binary.chmod(0o755)
            digest, path = tr.model_digest(binary, "eng")
            self.assertIsNotNone(digest)
            self.assertEqual(digest, hashlib.sha256(b"fallback-eng").hexdigest())
            self.assertEqual(path.parent, second)


if __name__ == "__main__":
    unittest.main()
