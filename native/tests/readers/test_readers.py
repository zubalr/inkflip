"""T26 native reader adapter tests (TEST-26).

Covers the T26 acceptance criteria against the committed T05 fixtures with the
frozen pypdfium2 5.8.0 / pypdf 6.18.0 stack: mapping/control/covered outputs
preserved, shared glyph boxes coalesced without guessed widths, pypdf text
page-only, rotations/origins/UserUnit mapped through the canonical transform,
malformed/encrypted failures isolated, and complete build/version manifests.
Emitted occurrences and results are validated against the authoritative JSON
Schema delivered by T03.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"

sys.path.insert(0, str(NATIVE))

import jsonschema  # noqa: E402  (frozen product dependency via native)

from inkflip.readers import pdfium as pdfium_reader  # noqa: E402
from inkflip.readers import pypdf as pypdf_reader  # noqa: E402

SCHEMA = json.loads((NATIVE / "inkflip/contracts/schema/inkflip.schema.json").read_text())


def schema_validator(def_name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{def_name}", "$defs": SCHEMA["$defs"]}
    )


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "t26_make_fixtures", ROOT / "scripts" / "make_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_bytes(relative: str) -> bytes:
    return (FIXTURES / relative).read_bytes()


def run_pdfium(data: bytes, page_index: int = 0, cancellation=None):
    handle = pdfium_reader.open_document(data, None, 1)
    try:
        chunks: list[list[dict]] = []
        result = pdfium_reader.extract(
            handle,
            {
                "id": "check-pdfium",
                "page_index": page_index,
                "reader_ids": [pdfium_reader.READER_ID],
                "capability": "native_text",
                "region_id": None,
            },
            chunks.append,
            cancellation,
        )
        occurrences = [o for chunk in chunks for o in chunk]
        return result, occurrences
    finally:
        handle.close()


def run_pypdf(data: bytes, page_index: int = 0):
    handle = pypdf_reader.open_document(data, None, 1)
    try:
        chunks: list[list[dict]] = []
        result = pypdf_reader.extract(
            handle,
            {
                "id": "check-pypdf",
                "page_index": page_index,
                "reader_ids": [pypdf_reader.READER_ID],
                "capability": "native_text",
                "region_id": None,
            },
            chunks.append,
        )
        occurrences = [o for chunk in chunks for o in chunk]
        return result, occurrences
    finally:
        handle.close()


def joined_text(occurrences) -> str:
    return "".join(o["raw_text"] for o in occurrences)


class ReaderManifestTests(unittest.TestCase):
    """Criterion: build/version manifest complete (I13)."""

    def test_pdfium_manifest_is_complete_and_schema_valid(self):
        manifest = pdfium_reader.describe()
        schema_validator("ReaderManifest").validate(manifest)
        reader = manifest["reader"]
        self.assertEqual(reader["adapter_version"], "1.0.0")
        self.assertEqual(reader["method"], "native_text")
        self.assertEqual(reader["environment"], "native")
        self.assertIn("pypdfium2 5.8.0", reader["build"])
        self.assertIn("PDFium", reader["build"])
        self.assertEqual(len(reader["model_hashes"]), 1)
        self.assertRegex(reader["model_hashes"][0], r"^[a-f0-9]{64}$")
        self.assertEqual(manifest["asset_hashes"], reader["model_hashes"])
        native_text = next(
            c for c in reader["capabilities"] if c["name"] == "native_text"
        )
        self.assertEqual(native_text["support"], "supported")

    def test_pypdf_manifest_is_complete_and_schema_valid(self):
        manifest = pypdf_reader.describe()
        schema_validator("ReaderManifest").validate(manifest)
        reader = manifest["reader"]
        self.assertEqual(reader["adapter_version"], "1.0.0")
        self.assertIn("pypdf 6.18.0", reader["build"])
        self.assertEqual(manifest["execution_policy"], "installed_allowlist_no_report_commands")


class TestPdfiumMappingControlCovered(unittest.TestCase):
    """Criterion: mapping/control/covered actual outputs preserved (F01, F02)."""

    def test_mapping_expands_glyph_without_splitting_shared_box(self):
        _, occurrences = run_pdfium(fixture_bytes("public/mapping-amount.pdf"))
        texts = [o["raw_text"] for o in occurrences]
        self.assertIn("$", texts)
        self.assertIn("1,0", texts)
        self.assertNotIn(",", texts)  # expansion is never split into bare scalars
        shared = [o for o in occurrences if o["raw_text"] == "1,0"]
        self.assertEqual(len(shared), 1)
        # The dollar glyph keeps its own reported box; no width was invented
        # between '$' and the expanded '1,0' glyph box.
        dollar = next(o for o in occurrences if o["raw_text"] == "$")
        self.assertNotEqual(dollar["geometry"]["polygon"], shared[0]["geometry"]["polygon"])
        self.assertIn("coalesced", shared[0]["geometry"]["basis"])

    def test_mapping_output_differs_from_control_with_equal_painting(self):
        _, mapping = run_pdfium(fixture_bytes("public/mapping-amount.pdf"))
        _, control = run_pdfium(fixture_bytes("public/mapping-control.pdf"))
        self.assertIn("1,0", joined_text(mapping))
        self.assertNotIn("1,0", joined_text(control))
        self.assertIn("$100", joined_text(control).replace(" ", ""))
        mapping_dollar = next(o for o in mapping if o["raw_text"] == "$")
        control_dollar = next(o for o in control if o["raw_text"] == "$")
        self.assertEqual(
            mapping_dollar["geometry"]["polygon"],
            control_dollar["geometry"]["polygon"],
            "mapping and control paint identical operators, so boxes must match",
        )

    def test_covered_actual_output_is_preserved_verbatim(self):
        _, occurrences = run_pdfium(fixture_bytes("public/covered-amount.pdf"))
        text = joined_text(occurrences)
        # PDFium 149.0.7825.0 merges the covered '$1,000' and replacement '$100'
        # into '$1,00000'; the raw observation is preserved, never corrected.
        self.assertIn("$1,00000", text.replace(" ", ""))
        self.assertNotIn("$1,000$100", text)

    def test_joined_raw_text_matches_engine_output(self):
        data = fixture_bytes("public/mapping-amount.pdf")
        _, occurrences = run_pdfium(data)
        from pypdfium2 import PdfDocument

        doc = PdfDocument(data)
        textpage = doc[0].get_textpage()
        engine_text = textpage.get_text_range(0, textpage.count_chars())
        textpage.close()
        doc.close()
        expected = engine_text.replace("\r", "").replace("\n", "")
        self.assertEqual(joined_text(occurrences), expected)


class TestPdfiumGeometry(unittest.TestCase):
    """Criterion: all rotations/origins map correctly; UserUnit once (F07, F08)."""

    def test_rotations_store_identical_canonical_anchors(self):
        anchors = []
        for rotation in (0, 90, 180, 270):
            _, occurrences = run_pdfium(fixture_bytes(f"public/geometry-{rotation}.pdf"))
            dollar = next(o for o in occurrences if o["raw_text"] == "$")
            anchors.append(dollar["geometry"]["polygon"])
        for polygon in anchors[1:]:
            for point, base in zip(polygon, anchors[0]):
                self.assertAlmostEqual(point[0], base[0], delta=1e-3)
                self.assertAlmostEqual(point[1], base[1], delta=1e-3)
        # Analytic anchor: '$' paints at (48, 209.87..263.44) in user space with
        # crop [20,40,500,390] and UserUnit 2 -> top-left (56, 2*(390-263.44)).
        # PDFium reports float32 boxes, so expectations carry that quantization.
        self.assertAlmostEqual(anchors[0][0][0], 56.0, delta=1e-3)
        self.assertAlmostEqual(anchors[0][0][1], 2 * (390 - 263.44), delta=1e-3)

    def test_userunit_scales_exactly_once(self):
        for unit in ("0.5", "1", "2", "10"):
            with self.subTest(userunit=unit):
                data = fixture_bytes(f"development/userunit-{unit}.pdf")
                handle = pdfium_reader.open_document(data, None, 1)
                meta = pdfium_reader.pages(handle)[0]
                self.assertAlmostEqual(meta["physical_width_pt"], 520 * float(unit))
                self.assertAlmostEqual(meta["physical_height_pt"], 400 * float(unit))
                handle.close()
                _, occurrences = run_pdfium(data)
                dollar = next(o for o in occurrences if o["raw_text"] == "$")
                top_left = dollar["geometry"]["polygon"][0]
                self.assertAlmostEqual(top_left[0], 48 * float(unit), delta=1e-2 * float(unit))
                self.assertAlmostEqual(
                    top_left[1], (400 - 263.44) * float(unit), delta=1e-2 * float(unit)
                )

    def test_missing_mapping_output_passes_through_unchanged(self):
        """F10 mechanism: with no ToUnicode CMap the engine's raw output is
        passed through verbatim; the adapter never substitutes a fallback."""
        gen = load_generator()
        body = b"BT /F0 16 Tf 48 352 Td (SYNTHETIC EXAMPLE) Tj ET\n"
        objs = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 520 400] "
            b"/Resources << /Font << /F0 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            gen.stream(body),
        ]
        data = gen.pdf(objs)
        _, occurrences = run_pdfium(data)
        from pypdfium2 import PdfDocument

        doc = PdfDocument(data)
        textpage = doc[0].get_textpage()
        engine_text = textpage.get_text_range(0, textpage.count_chars())
        textpage.close()
        doc.close()
        self.assertTrue(occurrences)
        self.assertEqual(joined_text(occurrences), engine_text.replace("\r", "").replace("\n", ""))

    def test_duplicate_occurrences_keep_distinct_boxes_and_ordinals(self):
        gen = load_generator()
        body = (
            b"BT /F0 16 Tf 48 352 Td (SYNTHETIC EXAMPLE) Tj ET\n"
            + b"".join(
                f"BT /F0 12 Tf 48 {300 - step * 60} Td ($100) Tj ET\n".encode()
                for step in range(4)
            )
        )
        # A clean minimal PDF built with the generator's deterministic writer;
        # same glyph, four distinct painted positions (F11 mechanism).
        objs = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 520 400] "
            b"/Resources << /Font << /F0 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            gen.stream(body),
        ]
        data = gen.pdf(objs)
        _, occurrences = run_pdfium(data)
        dollars = [o for o in occurrences if o["raw_text"] == "$"]
        self.assertEqual(len(dollars), 4)
        polygons = {tuple(map(tuple, o["geometry"]["polygon"])) for o in dollars}
        self.assertEqual(len(polygons), 4, "each occurrence keeps its own position")
        ordinals = sorted(o["ordinal"] for o in dollars)
        self.assertEqual(ordinals, sorted(set(ordinals)))
        for occurrence in occurrences:
            schema_validator("Occurrence").validate(occurrence)


class TestPdfiumFailureIsolation(unittest.TestCase):
    """Criterion: malformed/encrypted failures isolated (I17)."""

    def test_empty_and_malformed_and_digest_mismatch_fail_typed(self):
        for data, digest in ((b"", None), (b"%PDF-1.7 garbage", None), (fixture_bytes("public/mapping-amount.pdf"), "0" * 64)):
            with self.subTest(data=data[:12], digest=digest):
                with self.assertRaises(pdfium_reader.AdapterError) as ctx:
                    pdfium_reader.open_document(data, digest, 1)
                self.assertEqual(ctx.exception.reason, "parser_error")

    def test_encrypted_document_fails_with_password_reason(self):
        import pypdf

        writer = pypdf.PdfWriter()
        writer.append(io.BytesIO(fixture_bytes("public/mapping-amount.pdf")))
        writer.encrypt("secret")
        buffer = io.BytesIO()
        writer.write(buffer)
        encrypted = buffer.getvalue()
        with self.assertRaises(pdfium_reader.AdapterError) as ctx:
            pdfium_reader.open_document(encrypted, None, 1)
        self.assertEqual(ctx.exception.reason, "parser_error")
        self.assertIn("password", ctx.exception.detail)

    def test_closed_handle_and_bad_plans_stay_terminal(self):
        handle = pdfium_reader.open_document(fixture_bytes("public/mapping-amount.pdf"), None, 1)
        handle.close()
        handle.close()  # idempotent
        plan = {
            "id": "check-closed",
            "page_index": 0,
            "reader_ids": [pdfium_reader.READER_ID],
            "capability": "native_text",
            "region_id": None,
        }
        result = pdfium_reader.extract(handle, plan, lambda chunk: None)
        self.assertEqual(result["status"], "failed")

        with pdfium_reader.open_document(fixture_bytes("public/mapping-amount.pdf"), None, 1) as handle:
            base = {"reader_ids": [pdfium_reader.READER_ID], "capability": "native_text", "region_id": None}
            self.assertEqual(
                pdfium_reader.extract(handle, {**base, "id": "r1", "page_index": 9}, lambda c: None)["status"],
                "unsupported",
            )
            self.assertEqual(
                pdfium_reader.extract(handle, {**base, "id": "r2", "page_index": 0, "capability": "ocr"}, lambda c: None)["status"],
                "unsupported",
            )
            self.assertEqual(
                pdfium_reader.extract(handle, {**base, "id": "r3", "page_index": 0, "region_id": "reg-1"}, lambda c: None)["status"],
                "unsupported",
            )

    def test_cancellation_is_terminal_and_chunked_emission_is_bounded(self):
        data = fixture_bytes("public/mapping-amount.pdf")
        result, occurrences = run_pdfium(data, cancellation=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["produced_occurrence_count"], len(occurrences))

        chunks: list[list[dict]] = []
        handle = pdfium_reader.open_document(data, None, 1)
        try:
            pdfium_reader.extract(
                handle,
                {"id": "c", "page_index": 0, "reader_ids": [pdfium_reader.READER_ID], "capability": "native_text", "region_id": None},
                chunks.append,
            )
        finally:
            handle.close()
        self.assertTrue(all(len(chunk) <= pdfium_reader.MAX_OCCURRENCES_PER_CHUNK for chunk in chunks))


class TestPdfiumSchemaConformance(unittest.TestCase):
    """I02: every occurrence binds reader, page, ordinal and geometry precision."""

    def test_all_emitted_occurrences_validate_against_schema(self):
        for relative in ("public/mapping-amount.pdf", "public/covered-amount.pdf", "public/geometry-90.pdf"):
            with self.subTest(fixture=relative):
                _, occurrences = run_pdfium(fixture_bytes(relative))
                self.assertTrue(occurrences)
                for occurrence in occurrences:
                    schema_validator("Occurrence").validate(occurrence)
                for occurrence in occurrences[:1]:
                    schema_validator("CheckResult").validate(
                        {
                            "id": "check-x",
                            "status": "completed",
                            "reason": None,
                            "produced_occurrence_count": len(occurrences),
                            "retained_occurrence_ids": [o["id"] for o in occurrences],
                        }
                    )
        handle = pdfium_reader.open_document(fixture_bytes("public/mapping-amount.pdf"), None, 1)
        try:
            for page in pdfium_reader.pages(handle):
                self.assertTrue(page["geometry_supported"])
        finally:
            handle.close()


class TestPypdfReader(unittest.TestCase):
    """Criterion: pypdf text stays page-only (F01, F02)."""

    def test_mapping_text_is_page_level_without_geometry(self):
        result, occurrences = run_pypdf(fixture_bytes("public/mapping-amount.pdf"))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(occurrences), 1)
        occurrence = occurrences[0]
        self.assertIn("$1,000", occurrence["raw_text"])
        self.assertEqual(occurrence["geometry"]["precision"], "page_only")
        self.assertIsNone(occurrence["geometry"]["polygon"])
        self.assertEqual(occurrence["geometry"]["transform_ids"], [])
        schema_validator("Occurrence").validate(occurrence)

    def test_covered_concatenation_is_preserved(self):
        _, occurrences = run_pypdf(fixture_bytes("public/covered-amount.pdf"))
        self.assertIn("$1,000$100", occurrences[0]["raw_text"])

    def test_control_outputs_identity_mapping(self):
        _, occurrences = run_pypdf(fixture_bytes("public/mapping-control.pdf"))
        self.assertIn("$100", occurrences[0]["raw_text"])
        self.assertNotIn("1,0", occurrences[0]["raw_text"])

    def test_encrypted_is_a_terminal_failure_not_a_raise(self):
        import pypdf

        writer = pypdf.PdfWriter()
        writer.append(io.BytesIO(fixture_bytes("public/mapping-amount.pdf")))
        writer.encrypt("secret")
        buffer = io.BytesIO()
        writer.write(buffer)
        result, occurrences = run_pypdf(buffer.getvalue())
        self.assertEqual(result["status"], "failed")
        self.assertIn("password", result["reason"])
        self.assertEqual(occurrences, [])

    def test_malformed_open_fails_typed(self):
        with self.assertRaises(pypdf_reader.AdapterError) as ctx:
            pypdf_reader.open_document(b"not a pdf at all", None, 1)
        self.assertEqual(ctx.exception.reason, "parser_error")

    def test_page_metadata_supports_other_adapters(self):
        handle = pypdf_reader.open_document(fixture_bytes("public/geometry-90.pdf"), None, 1)
        try:
            meta = pypdf_reader.pages(handle)[0]
            self.assertEqual(meta["rotation"], 90)
            self.assertEqual(meta["user_unit"], 2)
            self.assertEqual(meta["effective_view"], [20.0, 40.0, 500.0, 390.0])
        finally:
            handle.close()

    def test_closed_handle_and_out_of_range(self):
        handle = pypdf_reader.open_document(fixture_bytes("public/mapping-amount.pdf"), None, 1)
        handle.close()
        result = pypdf_reader.extract(
            handle,
            {"id": "x", "page_index": 0, "reader_ids": [pypdf_reader.READER_ID], "capability": "native_text", "region_id": None},
            lambda chunk: None,
        )
        self.assertEqual(result["status"], "failed")
        with pypdf_reader.open_document(fixture_bytes("public/mapping-amount.pdf"), None, 1) as handle:
            result = pypdf_reader.extract(
                handle,
                {"id": "x", "page_index": 5, "reader_ids": [pypdf_reader.READER_ID], "capability": "native_text", "region_id": None},
                lambda chunk: None,
            )
            self.assertEqual(result["status"], "unsupported")


if __name__ == "__main__":
    unittest.main()
