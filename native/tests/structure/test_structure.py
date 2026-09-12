"""T28 bounded native structural observation tests (TEST-28).

Covers the committed fixtures that exist for the assigned families (F03
searchable scan, F02 covered-text paint order as the overlap control, F07
geometry/user-unit families) plus hand-assembled minimal PDFs for the
controlled scenarios the fixture lane has not generated yet (F04
white-contrast controls, F05-style paint-order sweep, F06 partial-clip
controls, the render-mode Tr sweep, off-crop geometry, alpha compositing and
nested Form XObjects). The builder emits real one-page PDFs with a
standard-14 font; nothing writes to the fixtures directory or weakens a
shared contract.

Acceptance criteria under test:

* Invisible-over-border and white-on-dark controls cannot produce a
  universal hidden/visible verdict (the module emits no verdict at all).
* No false "all checked": unsupported compositing, nested forms, absent
  properties and budget exhaustion are recorded as limitations or typed
  terminals.
* Off-crop observation keeps raw/native geometry while page display remains
  the crop.
* Unsupported compositing is explicitly recorded.
"""
from __future__ import annotations

import io
import json
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
FIXTURES = ROOT / "fixtures"

sys.path.insert(0, str(NATIVE))

import jsonschema  # noqa: E402

from inkflip.checks import structure  # noqa: E402
from inkflip.readers import pdfium  # noqa: E402

SCHEMA = json.loads((NATIVE / "inkflip/contracts/schema/inkflip.schema.json").read_text())


def schema_validator(def_name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{def_name}", "$defs": SCHEMA["$defs"]}
    )


def fixture_bytes(relative: str) -> bytes:
    return (FIXTURES / relative).read_bytes()


def build_pdf(
    content: str,
    *,
    media_box: str = "[0 0 520 400]",
    crop_box: str | None = None,
    extra_resources: str = "",
    extra_objects: dict[int, str] | None = None,
) -> bytes:
    """Hand-assemble a real one-page PDF (standard-14 Helvetica, no font
    embedding) with the given content stream and optional page boxes."""
    page_dict = (
        f"<< /Type /Page /Parent 2 0 R /MediaBox {media_box} "
        + (f"/CropBox {crop_box} " if crop_box else "")
        + f"/Resources << /Font << /F0 5 0 R >>{extra_resources} >> /Contents 4 0 R >>"
    )
    objects: dict[int, str] = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: page_dict,
        4: "<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        5: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    if extra_objects:
        objects.update(extra_objects)
    out = io.BytesIO()
    out.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = out.tell()
        body = objects[number]
        out.write(f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref_at = out.tell()
    count = max(objects) + 1
    out.write(f"xref\n0 {count}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for number in range(1, count):
        out.write(f"{offsets[number]:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    )
    return out.getvalue()


def plan(capability: str, page_index: int = 0, plan_id: str = "check-structure") -> dict:
    return {
        "id": plan_id,
        "page_index": page_index,
        "reader_ids": [structure.READER_ID],
        "capability": capability,
        "region_id": None,
    }


def run_extract(data: bytes, capability: str, page_index: int = 0, cancel=None):
    handle = pdfium.open_document(data, None, 1)
    chunks: list[list[dict]] = []
    result = structure.extract(
        handle, plan(capability, page_index), chunks.append, cancellation=cancel
    )
    handle.close()
    occurrences = [o for chunk in chunks for o in chunk]
    return result, occurrences


NO_VERDICT_STRINGS = ('"verdict"', '"hidden"', '"visible"', '"suspicious"', '"safe"')


class ManifestTests(unittest.TestCase):
    def test_manifest_is_complete_and_schema_valid(self):
        manifest = structure.describe()
        schema_validator("ReaderManifest").validate(manifest)
        reader = manifest["reader"]
        self.assertEqual(reader["adapter_version"], "1.0.0")
        self.assertEqual(reader["method"], "structure")
        self.assertEqual(reader["environment"], "native")
        capabilities = {c["name"]: c["support"] for c in reader["capabilities"]}
        self.assertEqual(capabilities["object_render_mode"], "supported")
        self.assertEqual(capabilities["crop_metadata"], "supported")
        self.assertEqual(capabilities["paint_overlap"], "approximate")
        # Explicit unsupported-compositing record lives in the manifest.
        joined = " ".join(reader["limitations"])
        self.assertIn("not inspected", joined)
        self.assertIn("no universal hidden/visible verdict", joined)

    def test_no_verdict_fields_anywhere_in_the_module_output(self):
        data = fixture_bytes("development/scan-correct.pdf")
        for capability in structure.SUPPORTED_CAPABILITIES:
            with self.subTest(capability=capability):
                result, occurrences = run_extract(data, capability)
                self.assertEqual(result["status"], "completed")
                blob = json.dumps([result] + occurrences).lower()
                for verdict in NO_VERDICT_STRINGS:
                    self.assertNotIn(verdict, blob)


class RenderModeTests(unittest.TestCase):
    """Criterion: render mode is a property; invisible stays un-alerted."""

    def test_f03_invisible_layer_recorded_without_alert(self):
        data = fixture_bytes("development/scan-correct.pdf")
        result, occurrences = run_extract(data, "object_render_mode")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["produced_occurrence_count"], 13)
        for occurrence in occurrences:
            schema_validator("Occurrence").validate(occurrence)
        invisible = [o for o in occurrences if ":tr3:invisible" in o["raw_source_locator"]]
        # The layer's `3 Tr` text is recorded with raw 3 + PDF semantics name.
        self.assertGreaterEqual(len(invisible), 13)
        for occurrence in invisible:
            self.assertIn("render_mode_raw=3", occurrence["geometry"]["basis"])
            self.assertIn(
                "not a hidden or visible verdict", " ".join(occurrence["limitations"])
            )
        # The raster-only control has no text objects at all: neither page
        # triggers an alert; the module has no alert concept.
        control_result, control_occurrences = run_extract(
            fixture_bytes("development/scan-raster-only.pdf"), "object_render_mode"
        )
        self.assertEqual(control_result["status"], "completed")
        self.assertEqual(control_occurrences, [])

    def test_render_mode_tr_sweep_uses_pdf_semantics(self):
        """Every Tr value reads back as the RAW content-stream integer and is
        interpreted with PDF Tr semantics — not PDFium's enum names (whose
        value 3 is named FILL_STROKE). Kills an enum-name-mapping mutant."""
        for tr, expected_name in {
            0: "fill", 1: "stroke", 2: "fill_stroke", 3: "invisible",
            4: "fill_clip", 5: "stroke_clip", 6: "fill_stroke_clip", 7: "clip",
        }.items():
            with self.subTest(tr=tr):
                data = build_pdf(f"BT /F0 12 Tf {tr} Tr 1 0 0 1 60 300 Tm (T) Tj ET\n")
                result, occurrences = run_extract(data, "object_render_mode")
                self.assertEqual(result["status"], "completed", tr)
                matches = [
                    o for o in occurrences
                    if o["raw_source_locator"]
                    == f"pdfium:pageobj[0]:tr{tr}:{expected_name}"
                ]
                self.assertEqual(len(matches), 1, f"tr{tr} -> {expected_name}")
                self.assertIn(f"render_mode_raw={tr}", matches[0]["geometry"]["basis"])

    def test_absent_or_default_properties_are_honest(self):
        # A Tr-7 (clip) text object carries no painted fill on this build, but
        # the graphics state still has a default fill color: the record shows
        # the current state without any visibility claim, and the font name is
        # clean (this build counts the terminating NUL in the returned length).
        data = build_pdf("BT /F0 12 Tf 7 Tr 1 0 0 1 60 300 Tm (T) Tj ET\n")
        result, occurrences = run_extract(data, "object_render_mode")
        self.assertEqual(result["status"], "completed")
        clip_object = occurrences[0]
        self.assertIn(":tr7:clip", clip_object["raw_source_locator"])
        facts = clip_object["geometry"]["basis"]
        self.assertIn("font=Helvetica", facts)
        self.assertNotIn("\x00", facts)
        self.assertIn("not a hidden or visible verdict", " ".join(clip_object["limitations"]))


class PaintOverlapTests(unittest.TestCase):
    """Criterion: paint order/overlap are recorded facts, never a verdict."""

    def test_f02_covered_amount_records_later_opaque_overlap(self):
        result, occurrences = run_extract(
            fixture_bytes("public/covered-amount.pdf"), "paint_overlap"
        )
        self.assertEqual(result["status"], "completed")
        overlaps = {
            o["raw_source_locator"]: o
            for o in occurrences
            if "overlap" in o["raw_source_locator"]
        }
        covered = next(o for loc, o in overlaps.items() if ":later[" in loc)
        # The white cover rect paints after the $1,000 text (generator intent).
        self.assertIn("later[3]", covered["raw_source_locator"])
        self.assertIn("not a hidden or visible verdict", " ".join(covered["limitations"]))

    def test_white_on_dark_and_white_on_light_controls_get_no_verdict(self):
        """F04-style synthesized controls: identical white text over a dark
        rect vs over a light rect. The module records the same structural
        facts for both and emits no hidden/visible distinction — a universal
        verdict is impossible by construction."""
        fill = "1 1 1 rg BT /F0 26 Tf 0 Tr 1 0 0 1 50 220 Tm ($100) Tj ET\n"
        dark_rect = build_pdf("0.1 0.1 0.4 rg 40 200 240 80 re f\n" + fill)
        light_rect = build_pdf("1 1 1 rg 40 200 240 80 re f\n" + fill)
        dark_result, dark_occurrences = run_extract(dark_rect, "object_render_mode")
        light_result, light_occurrences = run_extract(light_rect, "object_render_mode")
        self.assertEqual(dark_result["status"], "completed")
        self.assertEqual(light_result["status"], "completed")
        for occ in dark_occurrences + light_occurrences:
            schema_validator("Occurrence").validate(occ)
        # The overlap experiment on the same controls also stays verdict-free.
        for capability in ("paint_overlap", "crop_metadata"):
            for data in (dark_rect, light_rect):
                result, occurrences = run_extract(data, capability)
                self.assertEqual(result["status"], "completed")
                blob = json.dumps(occurrences).lower()
                for verdict in NO_VERDICT_STRINGS:
                    self.assertNotIn(verdict, blob)
        dark_blob = json.dumps(dark_occurrences).lower()
        light_blob = json.dumps(light_occurrences).lower()
        for blob in (dark_blob, light_blob):
            for verdict in NO_VERDICT_STRINGS:
                self.assertNotIn(verdict, blob)
        # Identical mode records: nothing in the output distinguishes the two
        # controls as hidden vs visible.
        dark_text = next(o for o in dark_occurrences if o["raw_text"] == "$100")
        light_text = next(o for o in light_occurrences if o["raw_text"] == "$100")
        self.assertEqual(dark_text["raw_source_locator"], light_text["raw_source_locator"])
        self.assertEqual(dark_text["geometry"]["basis"], light_text["geometry"]["basis"])

    def test_f03_invisible_text_produces_no_overlap_alarm(self):
        # Invisible layer text is not reported as overlapped or hidden: the
        # raster image paints first, so no later opaque object covers it.
        result, occurrences = run_extract(
            fixture_bytes("development/scan-correct.pdf"), "paint_overlap"
        )
        self.assertEqual(result["status"], "completed")
        for occurrence in occurrences:
            self.assertNotIn(":later[", occurrence["raw_source_locator"])


class CropMetadataTests(unittest.TestCase):
    """Criterion: off-crop observation keeps raw geometry; display stays crop."""

    def test_off_crop_object_keeps_unclipped_native_geometry(self):
        # Crop the page to a small window: text objects outside it keep
        # their unclipped canonical coordinates (raw geometry preserved).
        content = (
            "BT /F0 14 Tf 1 0 0 1 60 340 Tm (INSIDE) Tj ET\n"
            "BT /F0 14 Tf 1 0 0 1 420 40 Tm (OUTSIDE1) Tj ET\n"
            "BT /F0 14 Tf 1 0 0 1 30 30 Tm (OUTSIDE2) Tj ET\n"
        )
        data = build_pdf(content, media_box="[0 0 520 400]", crop_box="[20 300 160 380]")
        result, occurrences = run_extract(data, "crop_metadata")
        self.assertEqual(result["status"], "completed")
        off_crop = [o for o in occurrences if "off-crop" in o["raw_source_locator"]]
        self.assertEqual(len(off_crop), 2)
        for occurrence in off_crop:
            polygon = occurrence["geometry"]["polygon"]
            self.assertIsNotNone(polygon)
            outside = any(x < 20 or x > 160 or y < 0 or y > 80 for x, y in polygon)
            self.assertTrue(outside, polygon)
            self.assertIn(
                "page display remains the crop", " ".join(occurrence["limitations"])
            )

    def test_page_properties_are_recorded(self):
        data = build_pdf(
            "BT /F0 12 Tf 1 0 0 1 60 340 Tm (IN) Tj ET\n",
            media_box="[0 0 520 400]",
            crop_box="[10 10 500 380]",
        )
        result, occurrences = run_extract(data, "crop_metadata")
        self.assertEqual(result["status"], "completed")
        props = next(
            o for o in occurrences if o["raw_source_locator"] == "pdfium:page[props]"
        )
        self.assertIn("effective_view=10.0,10.0,500.0,380.0", props["raw_text"])
        self.assertIn("user_unit=1.0", props["raw_text"])
        schema_validator("Occurrence").validate(props)

    def test_userunit_page_properties_carry_it_once(self):
        result, occurrences = run_extract(
            fixture_bytes("development/userunit-2.pdf"), "crop_metadata"
        )
        self.assertEqual(result["status"], "completed")
        props = next(
            o for o in occurrences if o["raw_source_locator"] == "pdfium:page[props]"
        )
        self.assertIn("user_unit=2.0", props["raw_text"])
        self.assertIn("physical=1040.0x800.0pt", props["raw_text"])


class UnsupportedCompositingTests(unittest.TestCase):
    """Criterion: unsupported compositing is explicitly recorded."""

    def test_alpha_fill_is_recorded_as_unsupported_compositing(self):
        # ExtGState alpha (ca/CA 0.5) applied to a text object: the fill
        # alpha drops below 255 and the occurrence records the limit.
        content = (
            "/G0 gs\nBT /F0 12 Tf 0 Tr 1 0 0 1 60 300 Tm (T) Tj ET\n"
            "0.2 0.2 0.2 rg 30 280 100 30 re f\n"
            "BT /F0 12 Tf 0 Tr 1 0 0 1 60 260 Tm (U) Tj ET\n"
        )
        data = build_pdf(
            content,
            extra_resources=" /ExtGState << /G0 6 0 R >>",
            extra_objects={6: "<< /Type /ExtGState /ca 0.5 /CA 0.5 >>"},
        )
        result, occurrences = run_extract(data, "object_render_mode")
        self.assertEqual(result["status"], "completed")
        alpha_limited = [
            o
            for o in occurrences
            if any("alpha compositing" in lim for lim in o["limitations"])
        ]
        self.assertTrue(alpha_limited, "alpha compositing limit must be recorded")

    def test_nested_form_xobject_is_not_traversed_and_recorded(self):
        # A Form XObject draws the text; the page content only invokes it.
        # The traversal stays top-level and records the unsupported compositing.
        content = "/X0 Do\n"
        form_stream = "BT /F0 12 Tf 1 0 0 1 40 300 Tm (NESTED) Tj ET\n"
        data = build_pdf(
            content,
            extra_resources=" /XObject << /X0 6 0 R >>",
            extra_objects={
                6: (
                    "<< /Type /XObject /Subtype /Form /BBox [0 0 520 400] "
                    "/Resources << /Font << /F0 5 0 R >> >> /Length %d >>\nstream\n%s\nendstream"
                    % (len(form_stream), form_stream)
                )
            },
        )
        result, occurrences = run_extract(data, "object_render_mode")
        self.assertEqual(result["status"], "completed")
        forms = [
            o
            for o in occurrences
            if "form:nested-not-traversed" in o["raw_source_locator"]
        ]
        self.assertEqual(len(forms), 1)
        self.assertIn("compositing unsupported", " ".join(forms[0]["limitations"]))
        # The nested text is NOT emitted: no false text link, no claimed check.
        self.assertFalse(any(o["raw_text"] == "NESTED" for o in occurrences))


class BudgetAndTerminalTests(unittest.TestCase):
    """I05/I17: typed terminals; partial evidence survives budget overrun."""

    def test_unsupported_capability_and_region_and_page(self):
        data = fixture_bytes("public/geometry-0.pdf")
        result, _ = run_extract(data, "native_text")
        self.assertEqual(result["status"], "unsupported")
        handle = pdfium.open_document(data, None, 1)
        chunks: list[list[dict]] = []
        bad_region = {
            "id": "r",
            "page_index": 0,
            "reader_ids": [structure.READER_ID],
            "capability": "object_render_mode",
            "region_id": "some-region",
        }
        result = structure.extract(handle, bad_region, chunks.append)
        self.assertEqual(result["status"], "unsupported")
        result = structure.extract(handle, plan("object_render_mode", page_index=9), chunks.append)
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("page_out_of_range", result["reason"])
        handle.close()
        closed = pdfium.open_document(data, None, 1)
        closed.close()
        chunks = []
        result = structure.extract(closed, plan("object_render_mode"), chunks.append)
        self.assertEqual(result["status"], "failed")

    def test_object_budget_returns_resource_limit_with_prior_evidence(self):
        data = fixture_bytes("development/scan-correct.pdf")  # 14 objects
        handle = pdfium.open_document(data, None, 1)
        chunks: list[list[dict]] = []
        with unittest.mock.patch.object(structure, "MAX_PAGE_OBJECTS", 5):
            result = structure.extract(handle, plan("object_render_mode"), chunks.append)
        handle.close()
        occurrences = [o for chunk in chunks for o in chunk]
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reason"].startswith("resource_limit"))
        # Scanned the first 5 objects: obj[0] is the raster image (not a mode
        # observation), obj[1..4] are text -> 4 emitted with prior evidence.
        self.assertEqual(result["produced_occurrence_count"], 4)
        self.assertEqual(len(occurrences), 4)
        self.assertEqual(len(result["retained_occurrence_ids"]), 4)

    def test_cancellation_is_a_terminal(self):
        data = fixture_bytes("development/scan-correct.pdf")
        result, occurrences = run_extract(data, "object_render_mode", cancel=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(occurrences, [])

    def test_results_and_occurrences_validate(self):
        for relative, capability in (
            ("development/scan-correct.pdf", "object_render_mode"),
            ("public/covered-amount.pdf", "paint_overlap"),
            ("public/geometry-0.pdf", "crop_metadata"),
        ):
            with self.subTest(fixture=relative):
                result, occurrences = run_extract(fixture_bytes(relative), capability)
                self.assertEqual(result["status"], "completed")
                for occurrence in occurrences:
                    schema_validator("Occurrence").validate(occurrence)


if __name__ == "__main__":
    unittest.main()
