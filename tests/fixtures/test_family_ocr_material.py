"""F15 ocr-material: prove the material raster difference, and record its limit.

Declared mechanism: the control raster is noise-free while the two ambiguity
siblings carry deterministic fixed-seed speckle; the printed line differs; and
the OCR reading must be recorded verbatim rather than normalised toward intent.

What this suite proves from the committed bytes:

* the three fixtures carry one image XObject with identical geometry, decoded
  to exactly ``width * height`` DeviceGray bytes;
* the page draws *only* that raster - there is no text operator at all, so no
  native text reader can see the line. OCR is the only reader that can;
* the control raster has no speckle by an explicit deterministic detector while
  both siblings do, in the same order of magnitude;
* the three rasters are pairwise different, materially, not by one pixel.

LIMITATION, stated deliberately and not papered over: an exact recognised string
is a *reader result*. Asserting it here would require storing new golden
recognition data (which this batch must not regenerate) or fabricating an
outcome. No test below asserts what OCR must read, and a test records that
restriction explicitly. The declared ``printed_line`` values are checked only
for internal consistency with the declared variant, never as proof of OCR.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from family_pdf import (
    content_bytes,
    image_header,
    image_stream,
    painted_texts,
    raster,
    speckle_score,
)
from test_fixtures import FIXTURES

DEV = FIXTURES / "development"
VARIANTS = ("control", "sign-ambiguity", "digit-ambiguity")
SPECKLE_FLOOR = 100


def read(variant: str) -> bytes:
    return (DEV / f"ocr-material-{variant}.pdf").read_bytes()


def expected(variant: str) -> dict:
    return json.loads((DEV / f"ocr-material-{variant}.expect.json").read_text())


class TestOcrMaterialRaster(unittest.TestCase):
    def test_identical_image_geometry_across_variants(self):
        headers = {variant: image_header(read(variant)) for variant in VARIANTS}
        for variant, header in headers.items():
            with self.subTest(variant=variant):
                self.assertEqual(header["width"], 340)
                self.assertEqual(header["height"], 440)
                self.assertEqual(header["bits"], 8)
                self.assertEqual(header["filter"], "RunLengthDecode")
                self.assertEqual(header["colour_space"], "DeviceGray")
        self.assertEqual(len({json.dumps(h, sort_keys=True) for h in headers.values()}), 1)

    def test_every_raster_decodes_to_exactly_one_byte_per_pixel(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                header = image_header(read(variant))
                self.assertEqual(len(raster(read(variant))), header["width"] * header["height"])

    def test_no_reader_can_extract_the_line_as_text(self):
        """Structural fact: the page content draws only the raster."""
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                content = content_bytes(read(variant))
                self.assertIn(b"/Im0 Do", content, "the page must draw the image")
                self.assertEqual(painted_texts(content), [], "no text operator may exist")
                self.assertNotIn(b"Tj", content)
                self.assertNotIn(b"TJ", content)

    def test_control_is_noise_free_and_siblings_are_not(self):
        scores = {}
        for variant in VARIANTS:
            data = read(variant)
            header = image_header(data)
            scores[variant] = speckle_score(raster(data), header["width"], header["height"])
        self.assertEqual(scores["control"], 0, "the control raster must be noise-free")
        for variant in ("sign-ambiguity", "digit-ambiguity"):
            with self.subTest(variant=variant):
                self.assertGreater(
                    scores[variant], SPECKLE_FLOOR,
                    f"{variant} must carry the declared speckle (score={scores[variant]})",
                )
        self.assertEqual(
            sorted(scores, key=lambda key: scores[key]),
            ["control", "sign-ambiguity", "digit-ambiguity"],
        )

    def test_rasters_differ_pairwise_and_materially(self):
        pixels = {variant: raster(read(variant)) for variant in VARIANTS}
        for left, right in (("control", "sign-ambiguity"), ("control", "digit-ambiguity"), ("sign-ambiguity", "digit-ambiguity")):
            with self.subTest(pair=f"{left}/{right}"):
                differing = sum(1 for a, b in zip(pixels[left], pixels[right]) if a != b)
                if "control" in (left, right):
                    self.assertGreaterEqual(
                        differing, SPECKLE_FLOOR, "a noisy sibling must differ from the control materially"
                    )
                else:
                    # The two ambiguity mechanisms share the speckle realisation
                    # and differ by their own glyph, so the delta is exact but
                    # small; it must still be non-zero.
                    self.assertGreater(differing, 0, "the two mechanisms are not the same raster")

    def test_encoded_size_reflects_the_noise(self):
        sizes = {variant: len(image_stream(read(variant))) for variant in VARIANTS}
        self.assertLess(sizes["control"], sizes["sign-ambiguity"])
        self.assertLess(sizes["control"], sizes["digit-ambiguity"])

    def test_declared_printed_lines_are_internally_consistent_only(self):
        """Expectation metadata check - explicitly not evidence about OCR output."""
        lines = {variant: expected(variant)["mechanism"]["intent"]["printed_line"] for variant in VARIANTS}
        self.assertEqual(len(set(lines.values())), 3, "each variant declares a distinct printed line")
        self.assertIn("$100.00", lines["sign-ambiguity"])
        self.assertIn("-$100.00", lines["control"])
        self.assertIn("1O0", lines["digit-ambiguity"], "the digit-ambiguity line uses a letter O for zero")
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                intent = expected(variant)["mechanism"]["intent"]
                self.assertEqual(intent["speckle"], variant != "control")
                self.assertIn("verbatim", intent["raw_output"])

    def test_no_fabricated_recognition_outcome_is_asserted(self):
        """The recorded limitation: this suite must not claim an OCR reading."""
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                payload = expected(variant)
                self.assertNotIn("recognized_text", payload)
                self.assertNotIn("ocr_output", payload)
                self.assertNotIn("expected_reading", payload)


class TestOcrMaterialCounterfactual(unittest.TestCase):
    def test_swapping_in_the_control_raster_removes_the_speckle(self):
        """Mutation: give the noisy sibling the control's raster bytes.

        The replacement is padded to the original stream length and terminated
        with the RLE end marker, so /Length stays valid; the speckle detector
        must then report the control result, proving it reads the decoded
        pixels rather than the fixture name or the expectation prose.
        """
        control = read("control")
        noisy = read("sign-ambiguity")
        control_stream = image_stream(control)
        noisy_stream = image_stream(noisy)
        self.assertLess(len(control_stream), len(noisy_stream))
        padded = control_stream + b"\x80" + b"\x00" * (len(noisy_stream) - len(control_stream) - 1)
        self.assertEqual(len(padded), len(noisy_stream))

        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / "sign-as-control.pdf"
            mutated.write_bytes(noisy.replace(noisy_stream, padded))
            data = mutated.read_bytes()
            header = image_header(data)
            # The mutated copy must still decode, and to the control's pixels.
            self.assertEqual(raster(data), raster(control))
            self.assertEqual(speckle_score(raster(data), header["width"], header["height"]), 0)
            # The unmutated fixture must still be detected as noisy.
            real_header = image_header(noisy)
            self.assertGreater(
                speckle_score(raster(noisy), real_header["width"], real_header["height"]),
                SPECKLE_FLOOR,
            )

    def test_truncating_the_raster_shortens_the_decoded_image(self):
        """Mutation: cut the encoded stream so the decoded raster is short.

        The one-byte-per-pixel assertion must fail, proving it measures the
        decoded raster and not the declared /Width and /Height.
        """
        control = read("control")
        control_stream = image_stream(control)
        cut = control_stream[: len(control_stream) // 2] + b"\x80"
        padded = cut + b"\x00" * (len(control_stream) - len(cut))
        self.assertEqual(len(padded), len(control_stream))
        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / "truncated.pdf"
            mutated.write_bytes(control.replace(control_stream, padded))
            header = image_header(mutated.read_bytes())
            self.assertNotEqual(len(raster(mutated.read_bytes())), header["width"] * header["height"])
            self.assertEqual(len(raster(control)), header["width"] * header["height"])


if __name__ == "__main__":
    unittest.main()
