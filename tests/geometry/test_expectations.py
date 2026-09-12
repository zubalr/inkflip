"""Python leg of TEST-04: the committed golden must equal the independent
exact-arithmetic derivation, and the derivation's own closed-form
cross-checks must hold. Runs under `uv run --project native python -m
pytest tests/geometry` (pytest in the native dev group) and under plain
`python3 -m pytest` (stdlib only, no third-party imports)."""
from __future__ import annotations

import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import derive_expectations as de  # noqa: E402


def test_committed_golden_matches_independent_derivation():
    expected = de.derive()
    text = json.dumps(expected, indent=2, sort_keys=True) + "\n"
    on_disk = (HERE / "expected.json").read_text()
    assert on_disk == text, (
        "expected.json is stale; regenerate via "
        "python3 tests/geometry/derive_expectations.py"
    )


def test_check_mode_reports_fresh():
    out = subprocess.run(
        [sys.executable, str(HERE / "derive_expectations.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr


def test_closed_form_agrees_with_matrix_path_on_all_fixture_points():
    # The derive() path already asserts this; re-verify on a wider grid so
    # the golden is anchored by two genuinely independent derivations.
    view = [Fraction(20), Fraction(40), Fraction(500), Fraction(390)]
    u = Fraction(2)
    w, h = de.canonical_size(view, u)
    c = de.canonical_m(view, u)
    for deg in (0, 90, 180, 270):
        r = de.rotation_m(deg, w, h)
        d = de.compose_m(r, c)
        for px in range(20, 501, 37):
            for py in range(40, 391, 41):
                p = (Fraction(px), Fraction(py))
                assert de.apply_m(d, p) == de.display_closed_form(
                    deg, view, u, p
                )


def test_worked_example_matches_published_numeric_example():
    # planning/architecture/COORDINATES.md: (48,220) -> canonical (56,340)
    # -> display@90 (360,56) -> raster@1.5 (540,84) -> ocr (80,48).
    expected = de.derive()
    anchor = expected["pages"]["geometry-90"]["maps"]["text_anchor"]
    assert anchor["canonical"] == [56, 340]
    assert anchor["display"] == [360, 56]
    assert anchor["raster_1_5"] == [540, 84]
    assert anchor["ocr_crop_500_60_k2"] == [80, 48]
    assert anchor["recovered_canonical"] == anchor["canonical"]


def test_userunit_sizes_are_single_application():
    expected = de.derive()["userunit"]
    for us, size in (
        ("0.5", [260, 200]),
        ("1", [520, 400]),
        ("2", [1040, 800]),
        ("10", [5200, 4000]),
    ):
        assert expected[us]["canonical_size_pt"] == size
        # Fiducial: 100 user units * u physical points, applied once.
        assert expected[us]["fiducial_physical_size_pt"] == [
            float(us) * 100,
            float(us) * 100,
        ]


def test_singular_matrix_rejected_in_reference_path():
    import pytest

    with pytest.raises(AssertionError):
        de.inverse_m([Fraction(1), Fraction(2), Fraction(2), Fraction(4),
                      Fraction(0), Fraction(0)])
