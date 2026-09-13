"""F16 adjacent-crop: prove three distinct clipping relationships.

All three fixtures paint the same two amounts; only the page CropBox differs.
This suite derives each text run's horizontal extent from the rendered glyph
boxes (pypdfium2, a pinned product dependency) and compares it with the page's
own CropBox, so the three declared relationships - both fully inside, the
neighbour crossing the right edge, and a partial glyph crossing the left edge -
are measured rather than asserted from prose. A disposable copy proves the
detector keys on the CropBox.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pypdfium2 as pdfium

from family_pdf import box, patched_copy, page_object
from test_fixtures import FIXTURES

DEV = FIXTURES / "development"
CONTROL_BOX = b"[30 100 240 140]"
ADJACENT_BOX = b"[30 100 150 140]"
CLIPPED_BOX = b"[50 100 100 140]"
TOLERANCE = 0.5


def read(name: str) -> bytes:
    return (DEV / name).read_bytes()


def crop_box(data: bytes) -> list[float]:
    found = box(page_object(data), b"/CropBox")
    assert found is not None, "fixture must declare a CropBox"
    return found


def run_spans(path: Path) -> list[dict]:
    """One entry per whitespace-separated run: its text and horizontal extent."""
    document = pdfium.PdfDocument(str(path))
    page = document[0]
    textpage = page.get_textpage()
    total = textpage.count_chars()
    runs: list[dict] = []
    current: dict | None = None
    for index in range(total):
        char = textpage.get_text_range(index, 1)
        left, _bottom, right, _top = textpage.get_charbox(index)
        if char.strip() == "":
            current = None
            continue
        if current is None:
            current = {"text": char, "left": left, "right": right}
            runs.append(current)
        else:
            current["text"] += char
            current["left"] = min(current["left"], left)
            current["right"] = max(current["right"], right)
    return runs


def classify(span: dict, crop: list[float]) -> str:
    """fully_inside, crosses_left, crosses_right or outside."""
    left_edge, _bottom, right_edge, _top = crop
    if span["right"] <= right_edge + TOLERANCE and span["left"] >= left_edge - TOLERANCE:
        return "fully_inside"
    if span["right"] < left_edge - TOLERANCE or span["left"] > right_edge + TOLERANCE:
        return "outside"
    if span["left"] < left_edge:
        return "crosses_left"
    return "crosses_right"


class TestAdjacentCropRelationships(unittest.TestCase):
    def test_boxes_are_distinct_and_nested_on_the_horizontal_axis(self):
        control = crop_box(read("adjacent-crop-control.pdf"))
        adjacent = crop_box(read("adjacent-crop-adjacent.pdf"))
        clipped = crop_box(read("adjacent-crop-clipped.pdf"))
        self.assertEqual(control, [30.0, 100.0, 240.0, 140.0])
        self.assertEqual(adjacent, [30.0, 100.0, 150.0, 140.0])
        self.assertEqual(clipped, [50.0, 100.0, 100.0, 140.0])
        self.assertEqual(len({tuple(control), tuple(adjacent), tuple(clipped)}), 3)
        self.assertGreater(control[2], adjacent[2])
        self.assertGreater(adjacent[2], clipped[2])
        self.assertGreater(clipped[0], adjacent[0], "the clipped crop starts further right")

    def test_all_three_paint_identical_content(self):
        from family_pdf import content_bytes

        contents = {
            content_bytes(read(name))
            for name in (
                "adjacent-crop-control.pdf",
                "adjacent-crop-adjacent.pdf",
                "adjacent-crop-clipped.pdf",
            )
        }
        self.assertEqual(len(contents), 1, "only the CropBox may differ between the siblings")

    def test_control_reads_both_amounts_fully_inside(self):
        spans = run_spans(DEV / "adjacent-crop-control.pdf")
        self.assertEqual([s["text"] for s in spans], ["$100", "$200"])
        self.assertEqual([classify(s, crop_box(read("adjacent-crop-control.pdf"))) for s in spans], ["fully_inside", "fully_inside"])

    def test_adjacent_crop_cuts_the_neighbour_at_the_right_edge(self):
        spans = run_spans(DEV / "adjacent-crop-adjacent.pdf")
        crop = crop_box(read("adjacent-crop-adjacent.pdf"))
        kinds = [classify(span, crop) for span in spans]
        self.assertEqual(kinds, ["fully_inside", "crosses_right"])
        neighbour = spans[1]
        self.assertLess(neighbour["left"], crop[2], "the neighbour starts inside the crop")
        self.assertGreater(neighbour["right"], crop[2], "and continues past it")

    def test_clipped_crop_cuts_the_glyph_at_the_left_edge(self):
        spans = run_spans(DEV / "adjacent-crop-clipped.pdf")
        crop = crop_box(read("adjacent-crop-clipped.pdf"))
        kinds = [classify(span, crop) for span in spans]
        self.assertEqual(kinds, ["crosses_left", "outside"])
        partial = spans[0]
        self.assertLess(partial["left"], crop[0], "the glyph begins left of the crop edge")
        self.assertLess(partial["right"], crop[2], "and ends inside the right edge")

    def test_the_three_relationships_are_pairwise_different(self):
        relationships = {}
        for name in ("adjacent-crop-control.pdf", "adjacent-crop-adjacent.pdf", "adjacent-crop-clipped.pdf"):
            data = read(name)
            crop = crop_box(data)
            relationships[name] = tuple(classify(span, crop) for span in run_spans(DEV / name))
        self.assertEqual(len(set(relationships.values())), 3, "each sibling must clip differently")


class TestAdjacentCropCounterfactual(unittest.TestCase):
    def test_restoring_the_control_cropbox_removes_the_clipping(self):
        """Mutation: give the adjacent copy the control's CropBox.

        The 'crosses the right edge' classification must become 'fully_inside',
        proving the assertion measures the page box rather than the file name.
        """
        with tempfile.TemporaryDirectory() as tmp:
            mutated = patched_copy(
                DEV / "adjacent-crop-adjacent.pdf",
                Path(tmp) / "adjacent-as-control.pdf",
                [(ADJACENT_BOX, CONTROL_BOX)],
            )
            data = mutated.read_bytes()
            self.assertEqual(crop_box(data), [30.0, 100.0, 240.0, 140.0])
            spans = run_spans(mutated)
            self.assertEqual(
                [classify(span, crop_box(data)) for span in spans],
                ["fully_inside", "fully_inside"],
            )
            # The unmutated fixture must still show the clipping.
            original = read("adjacent-crop-adjacent.pdf")
            self.assertEqual(
                [classify(span, crop_box(original)) for span in run_spans(DEV / "adjacent-crop-adjacent.pdf")],
                ["fully_inside", "crosses_right"],
            )

    def test_widening_the_clipped_crop_removes_the_partial_glyph(self):
        with tempfile.TemporaryDirectory() as tmp:
            mutated = patched_copy(
                DEV / "adjacent-crop-clipped.pdf",
                Path(tmp) / "clipped-as-control.pdf",
                [(CLIPPED_BOX, CONTROL_BOX)],
            )
            data = mutated.read_bytes()
            self.assertEqual(
                [classify(span, crop_box(data)) for span in run_spans(mutated)],
                ["fully_inside", "fully_inside"],
            )


if __name__ == "__main__":
    unittest.main()
