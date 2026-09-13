"""F12 reading-order: prove order changes while the content multiset is stable.

The declared mechanism is explicit: the same readings arrive in a different
stream order and no accessibility verdict follows from it. This suite proves
both halves - identical painted content and identical geometry, different
emission order - and mutates a disposable copy to prove the order assertion is
sensitive to stream order rather than to any incidental difference.
"""
from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

from family_pdf import content_bytes, patched_copy, text_order, text_runs
from test_fixtures import FIXTURES

PUBLIC = FIXTURES / "public"
CONTROL_ORDER = ["LEFT-1", "LEFT-2", "RIGHT-1", "RIGHT-2"]
REORDERED_ORDER = ["RIGHT-1", "RIGHT-2", "LEFT-1", "LEFT-2"]


def read(name: str) -> bytes:
    return (PUBLIC / name).read_bytes()


class TestReadingOrderMechanism(unittest.TestCase):
    def setUp(self):
        self.control = content_bytes(read("reading-order-control.pdf"))
        self.reordered = content_bytes(read("reading-order-reordered.pdf"))

    def test_stream_orders_match_the_declared_intent(self):
        self.assertEqual(text_order(self.control), CONTROL_ORDER)
        self.assertEqual(text_order(self.reordered), REORDERED_ORDER)

    def test_content_multiset_is_identical(self):
        self.assertEqual(Counter(text_order(self.control)), Counter(text_order(self.reordered)))

    def test_geometry_is_identical_for_every_run(self):
        self.assertEqual(
            sorted(text_runs(self.control)),
            sorted(text_runs(self.reordered)),
            "each reading keeps its coordinates; only the emission order changed",
        )

    def test_visual_columns_are_preserved(self):
        for content, label in ((self.control, "control"), (self.reordered, "reordered")):
            with self.subTest(variant=label):
                runs = text_runs(content)
                left = {text for x, _y, text in runs if x < 100}
                right = {text for x, _y, text in runs if x >= 100}
                self.assertEqual(left, {"LEFT-1", "LEFT-2"})
                self.assertEqual(right, {"RIGHT-1", "RIGHT-2"})

    def test_the_order_really_differs(self):
        self.assertNotEqual(text_order(self.control), text_order(self.reordered))


def sorted_content_copy(source: Path, destination: Path) -> Path:
    """Copy a fixture with its content lines emitted in column-major order.

    Sorting whole lines by (x, then descending y) is a pure permutation, so the
    total stream length - and every declared /Length - is preserved exactly,
    while the emission order becomes the control's reading order.
    """
    data = source.read_bytes()
    content = content_bytes(data)
    lines = [line for line in content.split(b"\n") if line.strip()]
    def key(line: bytes):
        runs = text_runs(line + b"\n")
        x, y, _text = runs[0]
        return (x, -y)
    ordered = b"\n".join(sorted(lines, key=key)) + b"\n"
    if len(ordered) != len(content):
        raise AssertionError("line permutation must preserve stream length")
    destination.write_bytes(data.replace(content, ordered))
    return destination


class TestReadingOrderCounterfactual(unittest.TestCase):
    def test_reordering_the_copy_into_reading_order_removes_the_difference(self):
        """Mutation: emit the reordered copy's lines in column-major order.

        Line permutation preserves the stream length exactly, so the copy stays
        a well-formed fixture; the difference assertion must then report no
        difference, proving it keys on emission order and not on the filename,
        the digest, or the expectation prose.
        """
        with tempfile.TemporaryDirectory() as tmp:
            mutated = sorted_content_copy(
                PUBLIC / "reading-order-reordered.pdf", Path(tmp) / "reordered-sorted.pdf"
            )
            order = text_order(content_bytes(mutated.read_bytes()))
            self.assertEqual(order, CONTROL_ORDER, "column-major emission restores the control order")
            self.assertEqual(
                text_runs(content_bytes(mutated.read_bytes())),
                sorted(text_runs(content_bytes(mutated.read_bytes())), key=lambda r: (r[0], -r[1])),
                "the mutated copy must be emitted in geometric order",
            )
            self.assertEqual(Counter(order), Counter(CONTROL_ORDER))
            # The unmutated fixture must still differ from the control.
            self.assertNotEqual(
                text_order(content_bytes(read("reading-order-reordered.pdf"))), CONTROL_ORDER
            )

    def test_reordering_the_control_breaks_the_control_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            mutated = sorted_content_copy(
                PUBLIC / "reading-order-reordered.pdf", Path(tmp) / "same-content-different-order.pdf"
            )
            self.assertNotEqual(
                text_order(content_bytes(mutated.read_bytes())),
                text_order(content_bytes(read("reading-order-reordered.pdf"))),
            )


if __name__ == "__main__":
    unittest.main()
