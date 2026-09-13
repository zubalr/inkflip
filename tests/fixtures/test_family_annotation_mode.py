"""F25 annotation-mode: inspect the actual annotation objects, not the prose.

The declared mechanism is that the annotated sibling records real annotations
(a static Square appearance) and an inert form field whose actions are never
executed, while the control page records none. This suite reads the /Annots
array and each annotation object from the committed bytes and mutates a
disposable copy to prove the assertion depends on those objects.
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from family_pdf import (
    annotations,
    content_bytes,
    object_stream,
    painted_texts,
    page_object,
    patched_copy,
)
from test_fixtures import FIXTURES

DEV = FIXTURES / "development"
ANNOTS_SLOT = b"/Annots [6 0 R 7 0 R] "


def read(name: str) -> bytes:
    return (DEV / name).read_bytes()


class TestAnnotationObjects(unittest.TestCase):
    def setUp(self):
        self.control = read("annotation-mode-control.pdf")
        self.annotated = read("annotation-mode-annotated.pdf")

    def test_control_page_records_no_annotation(self):
        self.assertEqual(annotations(self.control), [])
        self.assertNotIn(b"/Annots", page_object(self.control))

    def test_annotated_page_records_exactly_two_objects(self):
        found = annotations(self.annotated)
        self.assertEqual(len(found), 2)
        self.assertEqual(sorted(item["number"] for item in found), [6, 7])

    def test_square_annotation_has_a_rect_and_a_static_appearance(self):
        square = next(a for a in annotations(self.annotated) if b"/Subtype /Square" in a["body"])
        self.assertIn(b"/Type /Annot", square["body"])
        rect = re.search(rb"/Rect \[([^\]]+)\]", square["body"])
        self.assertIsNotNone(rect, "a Square annotation must declare /Rect")
        values = [float(v) for v in rect.group(1).split()]
        self.assertEqual(len(values), 4)
        self.assertLess(values[0], values[2])
        self.assertLess(values[1], values[3])
        self.assertIn(b"/AP", square["body"], "static appearance stream must be recorded")
        appearance_ref = re.search(rb"/N (\d+) 0 R", square["body"])
        self.assertIsNotNone(appearance_ref, "the appearance must name an appearance object")
        appearance = object_stream(self.annotated, int(appearance_ref.group(1)))
        self.assertIsNotNone(appearance, "the declared appearance object must carry a stream")
        self.assertIn(b"re f", appearance, "the static appearance paints a rectangle")

    def test_widget_field_is_a_text_field_and_not_executed(self):
        widget = next(a for a in annotations(self.annotated) if b"/Subtype /Widget" in a["body"])
        self.assertIn(b"/FT /Tx", widget["body"])
        self.assertIn(b"/T /InkflipField", widget["body"])
        self.assertIsNone(widget["stream"], "a form field carries no executable stream in this fixture")

    def test_no_executable_action_is_present_anywhere(self):
        for name, data in (("control", self.control), ("annotated", self.annotated)):
            with self.subTest(variant=name):
                self.assertNotIn(b"/JavaScript", data)
                self.assertNotIn(b"/JS", data)
                self.assertNotIn(b"/OpenAction", data)
                self.assertNotIn(b"/AA", data, "no additional-actions dictionary may be present")
                self.assertNotIn(b"/Launch", data)
                self.assertNotIn(b"/URI", data)

    def test_page_text_differs_but_structure_is_the_same(self):
        self.assertEqual(painted_texts(content_bytes(self.control)), ["PLAIN"])
        self.assertEqual(painted_texts(content_bytes(self.annotated)), ["ANNOTATED"])
        for data in (self.control, self.annotated):
            page = page_object(data)
            self.assertIn(b"/MediaBox [0 0 320 240]", page)


class TestAnnotationCounterfactual(unittest.TestCase):
    def test_removing_the_annots_array_removes_the_detected_objects(self):
        """Mutation: blank the page's /Annots reference in a disposable copy.

        The same-length replacement keeps every declared /Length valid; the
        annotation assertion must then report the control result, proving it
        reads the /Annots array rather than the expectation prose.
        """
        with tempfile.TemporaryDirectory() as tmp:
            mutated = patched_copy(
                DEV / "annotation-mode-annotated.pdf",
                Path(tmp) / "annotated-without-annots.pdf",
                [(ANNOTS_SLOT, b" " * len(ANNOTS_SLOT))],
            )
            data = mutated.read_bytes()
            self.assertNotIn(b"/Annots", page_object(data))
            self.assertEqual(annotations(data), [])
            self.assertEqual(
                len(annotations(read("annotation-mode-annotated.pdf"))),
                2,
                "the unmutated fixture must still carry both annotations",
            )


if __name__ == "__main__":
    unittest.main()
