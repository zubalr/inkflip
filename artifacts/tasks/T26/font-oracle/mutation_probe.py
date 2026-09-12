"""Run from the checkout root with its frozen native Python; no files are changed."""
import importlib.util
import io
import json
import platform
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

root = Path.cwd()
spec = importlib.util.spec_from_file_location(
    "reader_geometry_tests", root / "native/tests/readers/test_readers.py"
)
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
reader = tests.pdfium_reader
original_transform = reader._canonical_transform
original_polygon = reader._canonical_polygon


def twice(meta):
    return [value * meta["user_unit"] for value in original_transform(meta)]


def wrong_axis(meta):
    transform = original_transform(meta)
    transform[3] = -transform[3]
    return transform


def missing_crop_translation(meta):
    transform = original_transform(meta)
    transform[4] = 0
    return transform


def wrong_last_corner(transform, box):
    polygon = original_polygon(transform, box)
    polygon[3][0] += 1
    return polygon


def run_case(name, target=None, replacement=None):
    suite = unittest.TestSuite(
        tests.TestPdfiumGeometry(method) for method in (
            "test_rotations_store_identical_canonical_anchors",
            "test_userunit_scales_exactly_once",
        )
    )
    output = io.StringIO()
    runner = unittest.TextTestRunner(stream=output)
    if target is None:
        result = runner.run(suite)
    else:
        with patch.object(reader, target, replacement):
            result = runner.run(suite)
    failures = len(result.failures)
    errors = len(result.errors)
    print(json.dumps({"case": name, "tests": result.testsRun,
                      "assertion_failures": failures, "errors": errors}))
    if errors or result.testsRun != 2:
        raise AssertionError(output.getvalue())
    if target is None:
        assert result.wasSuccessful(), output.getvalue()
    else:
        assert failures > 0, f"Mutation survived: {name}"


print(json.dumps({"python": sys.version, "platform": platform.platform(),
                  "binding": str(reader.pypdfium2.PYPDFIUM_INFO),
                  "pdfium": str(reader.pypdfium2.PDFIUM_INFO),
                  "engine_sha256": reader.describe()["asset_hashes"],
                  "raw_dollar_box": tests.raw_dollar_box(
                      tests.fixture_bytes("public/geometry-0.pdf"))}))
run_case("unmodified")
run_case("UserUnit applied twice", "_canonical_transform", twice)
run_case("y axis reversed", "_canonical_transform", wrong_axis)
run_case("crop x translation omitted", "_canonical_transform", missing_crop_translation)
run_case("last corner alone shifted", "_canonical_polygon", wrong_last_corner)
