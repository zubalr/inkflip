"""F09 text-transform: prove the treatment files carry a real matrix effect.

The declared mechanism is "polygon transform not axis-only box": the same
painted text and the same crosshair path are placed under an identity matrix,
a shear, and a quarter-turn. This suite reads the committed bytes and proves
that the difference is a transform effect on identical content, rather than a
difference in what is painted. It also proves the detector is sensitive to the
intended defect by mutating a disposable copy back to the identity matrix.
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from family_pdf import content_bytes, painted_texts, patched_copy, same_length, tm_matrices
from test_fixtures import FIXTURES

DEV = FIXTURES / "development"
IDENTITY = [1.0, 0.0, 0.0, 1.0, 60.0, 120.0]
SKEW = [0.9, 0.25, 0.0, 1.0, 60.0, 120.0]
ROTATE = [0.0, 1.0, -1.0, 0.0, 220.0, 80.0]

_PATHS = re.compile(rb"^\s*0\.5 w .*$", re.M)


def read(name: str) -> bytes:
    return (DEV / name).read_bytes()


def is_axis_only(matrix: list[float]) -> bool:
    """A text matrix maps to an axis-aligned box only when b and c are zero."""
    _a, b, c, _d, _e, _f = matrix
    return b == 0.0 and c == 0.0


class TestTextTransformMatrices(unittest.TestCase):
    def setUp(self):
        self.control = content_bytes(read("text-transform-control.pdf"))
        self.skew = content_bytes(read("text-transform-skew.pdf"))
        self.rotated = content_bytes(read("text-transform-rotated.pdf"))

    def test_each_variant_declares_exactly_one_matrix(self):
        for name, content in (("control", self.control), ("skew", self.skew), ("rotated", self.rotated)):
            with self.subTest(variant=name):
                self.assertEqual(len(tm_matrices(content)), 1)

    def test_control_is_the_axis_only_identity(self):
        matrix = tm_matrices(self.control)[0]
        self.assertEqual(matrix, IDENTITY)
        self.assertTrue(is_axis_only(matrix))

    def test_skew_is_a_non_axis_only_shear(self):
        matrix = tm_matrices(self.skew)[0]
        self.assertEqual(matrix, SKEW)
        self.assertNotEqual(matrix[1], 0.0, "shear must carry a non-zero off-diagonal term")
        self.assertFalse(is_axis_only(matrix), "a sheared run is not an axis-aligned box")

    def test_rotated_has_no_axis_aligned_basis(self):
        matrix = tm_matrices(self.rotated)[0]
        self.assertEqual(matrix, ROTATE)
        self.assertEqual((matrix[0], matrix[3]), (0.0, 0.0), "a quarter-turn has no positive x/y basis")
        self.assertEqual((abs(matrix[1]), abs(matrix[2])), (1.0, 1.0))
        self.assertFalse(is_axis_only(matrix))

    def test_only_the_matrix_differs_between_variants(self):
        """The mechanism is a transform effect, so painted content must be identical."""
        texts = {tuple(painted_texts(c)) for c in (self.control, self.skew, self.rotated)}
        self.assertEqual(len(texts), 1, "all three variants must paint the same strings")
        self.assertEqual(texts.pop(), ("$100",))
        paths = {tuple(_PATHS.findall(c)) for c in (self.control, self.skew, self.rotated)}
        self.assertEqual(len(paths), 1, "the crosshair path must be byte-identical across variants")

    def test_robust_text_extraction_is_not_available_for_sheared_runs(self):
        """Observable consequence: the sheared/rotated runs still emit the same
        characters, so a naive text reader cannot tell them apart on text alone.
        Only geometry distinguishes them - which is why the mechanism assertion
        above is about the matrix, not about the extracted string."""
        self.assertEqual(painted_texts(self.skew), painted_texts(self.control))
        self.assertNotEqual(tm_matrices(self.skew), tm_matrices(self.control))


class TestTextTransformCounterfactual(unittest.TestCase):
    def test_identity_matrix_removes_the_detected_effect(self):
        """Mutation: force the skew copy back to the identity matrix.

        The non-axis-only predicate must go false, proving the assertion keys on
        the actual matrix and not on the file name, the hash, or the expectation
        file's prose.
        """
        with tempfile.TemporaryDirectory() as tmp:
            source = DEV / "text-transform-skew.pdf"
            mutated = Path(tmp) / "skew-as-identity.pdf"
            patched_copy(
                source,
                mutated,
                [(b"0.9 0.25 0 1 60 120", same_length(b"0.9 0.25 0 1 60 120", "1 0 0 1 60 120"))],
            )
            matrix = tm_matrices(content_bytes(mutated.read_bytes()))[0]
            self.assertEqual(matrix, IDENTITY, "patched copy must carry the identity matrix")
            self.assertTrue(is_axis_only(matrix))
            self.assertFalse(
                is_axis_only(tm_matrices(content_bytes(source.read_bytes()))[0]),
                "the real fixture must still be non-axis-only",
            )

    def test_rotating_copy_back_to_identity_removes_the_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = DEV / "text-transform-rotated.pdf"
            mutated = Path(tmp) / "rotated-as-identity.pdf"
            patched_copy(source, mutated, [(b"0 1 -1 0 220 80", same_length(b"0 1 -1 0 220 80", "1 0 0 1 220 80"))])
            matrix = tm_matrices(content_bytes(mutated.read_bytes()))[0]
            self.assertTrue(is_axis_only(matrix))
            self.assertEqual(matrix[4:6], [220.0, 80.0], "only the basis changed, not the origin")


if __name__ == "__main__":
    unittest.main()
